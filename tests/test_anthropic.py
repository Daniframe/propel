"""The anthropic adapter, against a fake client: no network, no credentials, nothing spent."""

import json
import logging
from types import SimpleNamespace

import pytest
from fakes import FakeAnthropicClient, anthropic_message

from propensity.errors import ProviderError
from propensity.providers import BatchCapable, LLMProvider, get_provider
from propensity.providers.anthropic import (
    BATCH_STATES,
    DEFAULT_MAX_TOKENS,
    AnthropicBatchProvider,
    AnthropicProvider,
)
from propensity.providers.base import BatchRequest

MODEL = "claude-haiku-4-5"


def requests(n=2):
    return [BatchRequest(custom_id=f"RA_{i}", system="S", user=f"U{i}") for i in range(n)]


# --- one call at a time ------------------------------------------------------------------

def test_the_system_part_is_a_top_level_parameter():
    client = FakeAnthropicClient()
    AnthropicProvider(MODEL, client=client).complete("SYSTEM", "USER")
    params = client.params[0]
    assert params["system"] == "SYSTEM"
    assert params["messages"] == [{"role": "user", "content": "USER"}]
    assert params["model"] == MODEL


def test_max_tokens_is_always_sent_and_defaults_generously():
    client = FakeAnthropicClient()
    provider = AnthropicProvider(MODEL, client=client)
    provider.complete("S", "U")
    provider.complete("S", "U", max_tokens=2048)
    assert [params["max_tokens"] for params in client.params] == [DEFAULT_MAX_TOKENS, 2048]


def test_temperature_travels_in_extra_body_which_the_1x_sdk_still_forwards():
    client = FakeAnthropicClient()
    AnthropicProvider(MODEL, client=client).complete("S", "U", temperature=0.0)
    assert "temperature" not in client.params[0]  # a TypeError in messages.create() since 1.x
    assert client.params[0]["extra_body"] == {"temperature": 0.0}


def test_temperature_can_be_left_out_for_a_model_that_rejects_it(caplog):
    client = FakeAnthropicClient()
    with caplog.at_level(logging.WARNING):
        provider = AnthropicBatchProvider("claude-opus-5", client=client, send_temperature=False)
    provider.complete("S", "U")
    provider.submit_batch(requests(1))
    assert "extra_body" not in client.params[0] and "temperature" not in client.params[0]
    assert "temperature" not in client.submitted[0][0]["params"]
    assert "temperature is not sent to anthropic:claude-opus-5" in caplog.text


def test_request_options_reach_both_paths():
    client = FakeAnthropicClient()
    provider = AnthropicBatchProvider(MODEL, client=client, request_options={"metadata": {"user_id": "u"}})
    provider.complete("S", "U")
    provider.submit_batch(requests(1))
    assert client.params[0]["metadata"] == {"user_id": "u"}
    assert client.submitted[0][0]["params"]["metadata"] == {"user_id": "u"}


def test_only_text_blocks_make_the_answer():
    client = FakeAnthropicClient(["<FINAL_RANGE>", "[0, 1]</FINAL_RANGE>"], usage={"output_tokens": 9})
    completion = AnthropicProvider(MODEL, client=client).complete("S", "U")
    assert completion.text == "<FINAL_RANGE>[0, 1]</FINAL_RANGE>"  # the thinking block is left out
    assert completion.usage == {"output_tokens": 9} and completion.error is None
    assert completion.raw["content"][0]["type"] == "thinking"  # but kept in the audit trail


def test_a_provider_failure_is_returned_and_never_raised():
    client = FakeAnthropicClient(raises=RuntimeError("529 overloaded"))
    completion = AnthropicProvider(MODEL, client=client).complete("S", "U")
    assert (completion.text, completion.error) == ("", "RuntimeError: 529 overloaded")


@pytest.mark.parametrize("stop_reason,text,expected", [
    ("refusal", "partial", "the model declined the request"),
    ("max_tokens", "Level 0: the agent", "stopped at max_tokens before finishing; raise max_tokens"),
    ("end_turn", "", "the provider returned an empty response"),
])
def test_an_unfinished_answer_is_an_error_with_its_text_kept_in_raw(stop_reason, text, expected):
    client = FakeAnthropicClient(text, stop_reason=stop_reason)
    completion = AnthropicProvider(MODEL, client=client).complete("S", "U")
    assert (completion.text, completion.error) == ("", expected)
    assert completion.raw["stop_reason"] == stop_reason


# --- Message Batches ---------------------------------------------------------------------

def test_a_batch_sends_one_request_per_prompt_with_the_same_params():
    client = FakeAnthropicClient()
    provider = AnthropicBatchProvider(MODEL, client=client)
    assert provider.submit_batch(requests(), temperature=0.0, max_tokens=512) == "msgbatch_1"
    sent = client.submitted[0]
    assert [request["custom_id"] for request in sent] == ["RA_0", "RA_1"]
    assert sent[1]["params"] == {"model": MODEL, "max_tokens": 512, "system": "S",
                                 "messages": [{"role": "user", "content": "U1"}],
                                 "temperature": 0.0}  # batch params are forwarded as they are


@pytest.mark.parametrize("bad_id", ["RA 0", "RA.0", "x" * 65, ""])
def test_an_id_message_batches_would_reject_is_refused_before_anything_is_sent(bad_id):
    client = FakeAnthropicClient()
    unfit = [BatchRequest(custom_id=bad_id, system="S", user="U")] + requests(1)
    with pytest.raises(ProviderError, match="mode='sequential'"):
        AnthropicBatchProvider(MODEL, client=client).submit_batch(unfit)
    assert client.submitted == []


@pytest.mark.parametrize("status,expected", sorted(BATCH_STATES.items()))
def test_every_processing_status_maps_onto_a_batch_state(status, expected):
    provider = AnthropicBatchProvider(MODEL, client=FakeAnthropicClient(status=status))
    assert provider.poll_batch("msgbatch_1") == expected


def test_an_unfamiliar_status_is_treated_as_still_running():
    provider = AnthropicBatchProvider(MODEL, client=FakeAnthropicClient(status="something_new"))
    assert provider.poll_batch("msgbatch_1") == "running"


def test_fetching_keys_by_custom_id_and_turns_every_failure_into_an_error():
    def entry(custom_id, **result):
        return SimpleNamespace(custom_id=custom_id, result=SimpleNamespace(**result))

    client = FakeAnthropicClient(results=[
        entry("RA_3", type="expired"),
        entry("RA_1", type="errored", error="invalid_request_error: prompt is too long"),
        entry("RA_0", type="succeeded", message=anthropic_message("first")),
        entry("RA_2", type="canceled"),
        entry("RA_4", type="succeeded", message=anthropic_message("cut", stop_reason="max_tokens")),
    ])
    completions = AnthropicBatchProvider(MODEL, client=client).fetch_batch("msgbatch_1")
    assert completions["RA_0"].text == "first" and completions["RA_0"].error is None
    assert completions["RA_1"].error == "batch request errored: invalid_request_error: prompt is too long"
    assert completions["RA_2"].error == "batch request canceled"
    assert completions["RA_3"].error == "batch request expired"
    assert "max_tokens" in completions["RA_4"].error
    assert all(completions[k].text == "" for k in ("RA_1", "RA_2", "RA_3", "RA_4"))


# --- choosing the class and building the client ------------------------------------------

def test_anthropic_is_batch_capable_by_default():
    provider = get_provider("anthropic", model=MODEL, client=FakeAnthropicClient())
    assert isinstance(provider, BatchCapable) and isinstance(provider, LLMProvider)
    assert (provider.name, provider.model) == ("anthropic", MODEL)
    unbatched = get_provider("anthropic", model=MODEL, client=FakeAnthropicClient(), batch=False)
    assert not isinstance(unbatched, BatchCapable)


def test_the_key_comes_from_the_environment_and_an_explicit_one_wins(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    built = []
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: built.append(kwargs) or "sdk")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    monkeypatch.setenv("TEAM_CLAUDE_KEY", "team-key")

    assert AnthropicProvider(MODEL).client == "sdk"
    AnthropicProvider(MODEL, api_key="explicit")
    AnthropicProvider(MODEL, api_key_env="TEAM_CLAUDE_KEY", max_retries=5)
    assert built == [{"api_key": "from-env"}, {"api_key": "explicit"},
                     {"api_key": "team-key", "max_retries": 5}]


# --- the real SDK, over an in-memory transport -------------------------------------------

def test_the_real_sdk_sends_what_the_api_expects_and_reads_back_a_batch():
    anthropic = pytest.importorskip("anthropic")
    # The HTTP library the SDK is built on: httpx2 from 1.0, httpx before.
    http = pytest.importorskip("httpx2" if int(anthropic.__version__.split(".")[0]) >= 1 else "httpx")
    message = {"id": "msg_1", "type": "message", "role": "assistant", "model": MODEL,
               "content": [{"type": "text", "text": "<FINAL_RANGE>[0, 1]</FINAL_RANGE>"}],
               "stop_reason": "end_turn", "stop_sequence": None,
               "usage": {"input_tokens": 5, "output_tokens": 7}}
    batch = {"id": "msgbatch_1", "type": "message_batch", "processing_status": "ended",
             "created_at": "2026-09-17T00:00:00Z", "expires_at": "2026-09-18T00:00:00Z",
             "archived_at": None, "cancel_initiated_at": None, "ended_at": "2026-09-17T00:10:00Z",
             "results_url": "https://api.anthropic.com/v1/messages/batches/msgbatch_1/results",
             "request_counts": {"processing": 0, "succeeded": 1, "errored": 1, "canceled": 0,
                                "expired": 0}}
    results = [{"custom_id": "RA_1", "result": {"type": "errored", "error": {
                    "type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}}},
               {"custom_id": "RA_0", "result": {"type": "succeeded", "message": message}}]
    bodies = {}

    def handler(request):
        path = request.url.path
        assert request.headers["x-api-key"] == "sk-test"
        if request.method == "POST":
            bodies[path] = json.loads(request.content)
            return http.Response(200, json=message if path == "/v1/messages" else batch)
        if path.endswith("/results"):
            return http.Response(200, content="\n".join(map(json.dumps, results)).encode())
        return http.Response(200, json=batch)

    client = anthropic.Anthropic(api_key="sk-test", max_retries=0,
                                 http_client=http.Client(transport=http.MockTransport(handler)))
    provider = get_provider("anthropic", model=MODEL, client=client)

    assert provider.complete("S", "U", temperature=0.0).text == "<FINAL_RANGE>[0, 1]</FINAL_RANGE>"
    batch_id = provider.submit_batch(requests(), temperature=0.0)
    assert provider.poll_batch(batch_id) == "completed"
    completions = provider.fetch_batch(batch_id)

    single = bodies["/v1/messages"]
    assert single == {"model": MODEL, "max_tokens": DEFAULT_MAX_TOKENS, "system": "S",
                      "messages": [{"role": "user", "content": "U"}], "temperature": 0.0}
    assert bodies["/v1/messages/batches"]["requests"][0]["params"] == {**single, "messages": [
        {"role": "user", "content": "U0"}]}  # the same request, whichever path carried it
    assert completions["RA_0"].text.startswith("<FINAL_RANGE>")
    assert completions["RA_1"].text == "" and "invalid_request_error" in completions["RA_1"].error
