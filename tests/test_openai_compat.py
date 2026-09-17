"""The openai adapter, against a fake client: no network, no credentials, nothing spent."""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from propensity.providers import BatchCapable, LLMProvider, available_providers, get_provider
from propensity.providers.base import BatchRequest
from propensity.providers.openai_compat import (
    BATCH_STATES,
    OpenAIBatchProvider,
    OpenAICompatProvider,
)


class Response:
    def __init__(self, text, usage=None):
        self.choices = ([SimpleNamespace(message=SimpleNamespace(content=text))]
                        if text is not None else [])
        self.usage = usage

    def model_dump(self):
        return {"choices": [{"message": {"content": choice.message.content}}
                            for choice in self.choices], "usage": self.usage}


class FakeClient:
    """The slice of the OpenAI SDK this adapter touches."""

    def __init__(self, text="answer", usage=None, raises=None, status="completed",
                 output=(), errors=(), batches=True):
        self.bodies, self.uploads, self.submitted, self.fetched = [], [], [], []
        self.text, self.usage, self.raises, self.status = text, usage, raises, status
        self.files_content = {"out-1": output, "err-1": errors}
        self.has_error_file = bool(errors)
        self.batches_supported = batches
        self.probes = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.files = SimpleNamespace(create=self._upload, content=self._content)
        self.batches = SimpleNamespace(create=self._submit, retrieve=self._retrieve,
                                       list=self._list)

    def _create(self, **body):
        self.bodies.append(body)
        if self.raises:
            raise self.raises
        return Response(self.text, self.usage)

    def _upload(self, *, file, purpose):
        self.uploads.append({"file": file, "purpose": purpose})
        return SimpleNamespace(id="file-1")

    def _submit(self, **kwargs):
        self.submitted.append(kwargs)
        return SimpleNamespace(id="batch-1")

    def _retrieve(self, batch_id):
        self.fetched.append(batch_id)
        return SimpleNamespace(id=batch_id, status=self.status, output_file_id="out-1",
                               error_file_id="err-1" if self.has_error_file else None)

    def _content(self, file_id):
        lines = self.files_content.get(file_id, ())
        return SimpleNamespace(text="\n".join(json.dumps(line) for line in lines))

    def _list(self, limit=None):
        self.probes += 1
        if not self.batches_supported:
            raise RuntimeError("404 page not found")
        return SimpleNamespace(data=[])


def chat_result(custom_id, text, status=200, usage=None):
    return {"custom_id": custom_id, "response": {"status_code": status,
            "body": {"choices": [{"message": {"content": text}}], "usage": usage}}}


def requests(n=2):
    return [BatchRequest(custom_id=f"q{i}", system="S", user=f"U{i}") for i in range(n)]


# --- one call at a time ------------------------------------------------------------------

def test_the_request_carries_the_system_part_as_a_system_message():
    client = FakeClient()
    OpenAICompatProvider("gpt-4.1", client=client).complete("SYSTEM", "USER", temperature=0.0)
    body = client.bodies[0]
    assert body["model"] == "gpt-4.1" and body["temperature"] == 0.0
    assert body["messages"] == [{"role": "system", "content": "SYSTEM"},
                                {"role": "user", "content": "USER"}]
    assert "max_tokens" not in body  # left out unless asked for


def test_max_tokens_and_request_options_reach_the_request():
    client = FakeClient()
    provider = OpenAICompatProvider("o1", client=client,
                                    request_options={"max_completion_tokens": 900})
    provider.complete("S", "U", max_tokens=256)
    assert client.bodies[0]["max_tokens"] == 256
    assert client.bodies[0]["max_completion_tokens"] == 900


def test_a_completion_carries_the_text_the_usage_and_the_raw_response():
    client = FakeClient(text="<FINAL_RANGE>[0, 1]</FINAL_RANGE>", usage={"total_tokens": 12})
    completion = OpenAICompatProvider("gpt-4.1", client=client).complete("S", "U")
    assert completion.text == "<FINAL_RANGE>[0, 1]</FINAL_RANGE>"
    assert completion.usage == {"total_tokens": 12} and completion.error is None
    assert completion.raw["choices"][0]["message"]["content"] == completion.text


def test_a_provider_failure_is_returned_and_never_raised():
    client = FakeClient(raises=RuntimeError("429 rate limited"))
    completion = OpenAICompatProvider("gpt-4.1", client=client).complete("S", "U")
    assert completion.text == ""
    assert completion.error == "RuntimeError: 429 rate limited"


@pytest.mark.parametrize("text", [None, ""])
def test_an_empty_response_is_an_error_not_an_empty_annotation(text):
    completion = OpenAICompatProvider("gpt-4.1", client=FakeClient(text=text)).complete("S", "U")
    assert completion.text == "" and "empty response" in completion.error


# --- building the client -----------------------------------------------------------------

def test_the_key_comes_from_the_environment_and_an_explicit_one_wins(monkeypatch):
    openai = pytest.importorskip("openai")  # only this pair needs the SDK itself
    captured = {}
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: captured.update(kwargs) or "sdk")
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")

    assert OpenAICompatProvider("gpt-4.1").client == "sdk"
    assert captured["api_key"] == "from-env" and captured["base_url"] is None

    OpenAICompatProvider("gpt-4.1", api_key="explicit")
    assert captured["api_key"] == "explicit"


def test_the_environment_variable_name_and_the_endpoint_are_the_caller_s_choice(monkeypatch):
    openai = pytest.importorskip("openai")
    captured = {}
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: captured.update(kwargs) or "sdk")
    monkeypatch.setenv("MY_GATEWAY_KEY", "gateway-key")

    OpenAICompatProvider("llama-3.3-70b", api_key_env="MY_GATEWAY_KEY",
                         base_url="http://localhost:8000/v1", timeout=30)
    assert captured == {"api_key": "gateway-key", "base_url": "http://localhost:8000/v1",
                        "timeout": 30}


def test_without_the_sdk_the_error_says_which_extra_installs_it():
    script = (
        "import sys\n"
        "class Blocker:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] == 'openai':\n"
        "            raise ImportError('blocked')\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "from propensity.providers import get_provider\n"
        "try:\n"
        "    get_provider('openai', model='gpt-4.1')\n"
        "except ImportError as exc:\n"
        "    print(exc)\n"
        "else:\n"
        "    raise AssertionError('constructing a provider should have raised ImportError')\n"
    )
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert 'pip install "propel[openai]"' in done.stdout


# --- the batch API -----------------------------------------------------------------------

def test_a_batch_is_uploaded_as_one_json_line_per_request():
    client = FakeClient()
    provider = OpenAIBatchProvider("gpt-4.1", client=client)

    assert provider.submit_batch(requests(2), temperature=0.0, max_tokens=64) == "batch-1"

    name, payload = client.uploads[0]["file"]
    assert (name, client.uploads[0]["purpose"]) == ("batch_input.jsonl", "batch")
    lines = [json.loads(line) for line in payload.decode().splitlines()]
    assert [line["custom_id"] for line in lines] == ["q0", "q1"]
    assert lines[0]["url"] == "/v1/chat/completions" and lines[0]["method"] == "POST"
    assert lines[0]["body"]["messages"][1]["content"] == "U0"
    assert lines[0]["body"]["max_tokens"] == 64
    assert client.submitted[0] == {"input_file_id": "file-1",
                                   "endpoint": "/v1/chat/completions",
                                   "completion_window": "24h"}


@pytest.mark.parametrize("status,expected", sorted(BATCH_STATES.items()))
def test_every_provider_status_maps_onto_a_batch_state(status, expected):
    client = FakeClient(status=status)
    assert OpenAIBatchProvider("gpt-4.1", client=client).poll_batch("batch-1") == expected


def test_an_unfamiliar_status_is_treated_as_still_running():
    client = FakeClient(status="something_new")
    assert OpenAIBatchProvider("gpt-4.1", client=client).poll_batch("batch-1") == "running"


def test_fetching_keys_by_custom_id_and_folds_in_the_error_file():
    client = FakeClient(
        output=[chat_result("q1", "second", usage={"total_tokens": 3}),
                chat_result("q0", "first")],  # out of order, as a real batch comes back
        errors=[{"custom_id": "q2", "error": {"code": "rate_limit_exceeded", "message": "slow down"}}])
    completions = OpenAIBatchProvider("gpt-4.1", client=client).fetch_batch("batch-1")

    assert set(completions) == {"q0", "q1", "q2"}
    assert completions["q0"].text == "first"
    assert completions["q1"].usage == {"total_tokens": 3}
    assert completions["q2"].text == "" and "rate_limit_exceeded" in completions["q2"].error


def test_a_result_with_no_completion_becomes_an_error_row():
    client = FakeClient(output=[{"custom_id": "q0", "response": {"status_code": 500, "body": {}}}])
    completions = OpenAIBatchProvider("gpt-4.1", client=client).fetch_batch("batch-1")
    assert completions["q0"].text == ""
    assert "no completion in the batch output (status 500)" in completions["q0"].error


# --- choosing the class ------------------------------------------------------------------

def test_the_official_endpoint_is_batch_capable_without_being_probed():
    client = FakeClient(batches=False)  # the probe would fail, and must not be called
    provider = get_provider("openai", model="gpt-4.1", client=client)
    assert isinstance(provider, OpenAIBatchProvider) and isinstance(provider, BatchCapable)
    assert client.probes == 0


def test_a_custom_endpoint_is_probed_once():
    with_batches = FakeClient(batches=True)
    assert isinstance(get_provider("openai", model="m", client=with_batches,
                                   base_url="http://vllm:8000/v1"), OpenAIBatchProvider)
    assert with_batches.probes == 1

    without = FakeClient(batches=False)
    provider = get_provider("openai", model="m", client=without, base_url="http://vllm:8000/v1")
    assert isinstance(provider, OpenAICompatProvider)
    assert not isinstance(provider, BatchCapable)  # asking for a batch would fail at submit time
    assert without.probes == 1


@pytest.mark.parametrize("batch,expected", [(True, True), (False, False)])
def test_the_batch_choice_can_be_forced(batch, expected):
    provider = get_provider("openai", model="m", client=FakeClient(), batch=batch)
    assert isinstance(provider, BatchCapable) is expected


def test_the_adapter_registers_itself_and_satisfies_the_protocol():
    assert "openai" in available_providers()
    provider = get_provider("openai", model="gpt-4.1", client=FakeClient())
    assert isinstance(provider, LLMProvider)
    assert (provider.name, provider.model) == ("openai", "gpt-4.1")


def test_settings_survive_the_switch_to_the_batch_class():
    client = FakeClient()
    provider = get_provider("openai", model="m", client=client, base_url="http://x/v1",
                            request_options={"seed": 7}, batch=True)
    provider.complete("S", "U")
    assert provider.base_url == "http://x/v1" and client.bodies[0]["seed"] == 7
