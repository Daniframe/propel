"""The google adapter, against a fake client: no network, no credentials, nothing spent."""

import json
import logging

import pytest
from fakes import FakeGenAIClient

from propensity.providers import BatchCapable, LLMProvider, get_provider
from propensity.providers.google import GoogleProvider

MODEL = "gemini-2.5-flash"


def test_the_system_part_travels_as_system_instruction():
    client = FakeGenAIClient()
    GoogleProvider(MODEL, client=client).complete("SYSTEM", "USER", temperature=0.0)
    call = client.calls[0]
    assert (call["model"], call["contents"]) == (MODEL, "USER")
    assert call["config"] == {"system_instruction": "SYSTEM", "temperature": 0.0,
                              "automatic_function_calling": {"disable": True}}


def test_max_tokens_and_config_options_reach_the_config():
    client = FakeGenAIClient()
    provider = GoogleProvider(MODEL, client=client,
                              config_options={"thinking_config": {"thinking_budget": 0}})
    provider.complete("S", "U", max_tokens=256)
    assert client.calls[0]["config"]["max_output_tokens"] == 256
    assert client.calls[0]["config"]["thinking_config"] == {"thinking_budget": 0}


def test_temperature_can_be_left_out_for_a_model_that_rejects_it(caplog):
    client = FakeGenAIClient()
    with caplog.at_level(logging.WARNING):
        GoogleProvider(MODEL, client=client, send_temperature=False).complete("S", "U")
    assert "temperature" not in client.calls[0]["config"]
    assert "temperature is not sent to google:gemini-2.5-flash" in caplog.text


def test_a_completion_carries_the_text_the_usage_and_the_raw_response():
    client = FakeGenAIClient("<FINAL_RANGE>[0, 1]</FINAL_RANGE>", usage={"total_token_count": 12})
    completion = GoogleProvider(MODEL, client=client).complete("S", "U")
    assert completion.text == "<FINAL_RANGE>[0, 1]</FINAL_RANGE>" and completion.error is None
    assert completion.usage == {"total_token_count": 12}
    assert completion.raw["candidates"][0]["text"] == completion.text


def test_a_provider_failure_is_returned_and_never_raised():
    client = FakeGenAIClient(raises=RuntimeError("429 RESOURCE_EXHAUSTED"))
    completion = GoogleProvider(MODEL, client=client).complete("S", "U")
    assert (completion.text, completion.error) == ("", "RuntimeError: 429 RESOURCE_EXHAUSTED")


@pytest.mark.parametrize("text", [None, ""])
def test_an_empty_response_is_an_error_that_names_the_finish_reason(text):
    client = FakeGenAIClient(text, finish_reason="SAFETY")
    completion = GoogleProvider(MODEL, client=client).complete("S", "U")
    assert completion.text == ""
    assert completion.error == "the provider returned an empty response (finish reason SAFETY)"


def test_google_registers_itself_and_runs_one_call_at_a_time():
    provider = get_provider("google", model=MODEL, client=FakeGenAIClient())
    assert isinstance(provider, LLMProvider) and not isinstance(provider, BatchCapable)
    assert (provider.name, provider.model) == ("google", MODEL)


def test_the_key_comes_from_the_environment_and_an_explicit_one_wins(monkeypatch):
    genai = pytest.importorskip("google.genai")
    built = []
    monkeypatch.setattr(genai, "Client", lambda **kwargs: built.append(kwargs) or "sdk")
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")

    assert GoogleProvider(MODEL).client == "sdk"
    GoogleProvider(MODEL, api_key="explicit", http_options={"timeout": 30_000})
    assert built == [{"api_key": "from-env"},
                     {"api_key": "explicit", "http_options": {"timeout": 30_000}}]


def test_the_real_sdk_sends_what_the_api_expects():
    genai = pytest.importorskip("google.genai")
    httpx = pytest.importorskip("httpx")
    seen = []

    def handler(request):
        seen.append((request.url.path, request.headers.get("x-goog-api-key"),
                     json.loads(request.content)))
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": "done"}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 5, "totalTokenCount": 12}})

    client = genai.Client(api_key="g-key", http_options={
        "httpx_client": httpx.Client(transport=httpx.MockTransport(handler))})
    completion = get_provider("google", model=MODEL, client=client).complete(
        "S", "U", temperature=0.0, max_tokens=100)

    assert completion.text == "done" and completion.usage["total_token_count"] == 12
    path, key, body = seen[0]  # one request: automatic function calling is off
    assert (len(seen), path, key) == (1, f"/v1beta/models/{MODEL}:generateContent", "g-key")
    assert body["systemInstruction"]["parts"] == [{"text": "S"}]
    assert body["contents"] == [{"role": "user", "parts": [{"text": "U"}]}]
    assert body["generationConfig"] == {"temperature": 0.0, "maxOutputTokens": 100}
