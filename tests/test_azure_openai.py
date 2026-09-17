"""The azure adapter, against a fake client: no network, no credentials, nothing spent."""

import json

import pytest
from fakes import FakeOpenAIClient

from propensity.errors import ProviderError
from propensity.providers import BatchCapable, LLMProvider, get_provider
from propensity.providers.azure_openai import AzureOpenAIBatchProvider, AzureOpenAIProvider
from propensity.providers.base import BatchRequest

ENDPOINT = "https://my-resource.openai.azure.com"


def requests(n=2):
    return [BatchRequest(custom_id=f"q{i}", system="S", user=f"U{i}") for i in range(n)]


@pytest.fixture
def sdk(monkeypatch):
    """The real openai module, with its client classes replaced by recorders."""
    openai = pytest.importorskip("openai")
    built = []
    for cls in ("OpenAI", "AzureOpenAI"):
        monkeypatch.setattr(openai, cls, lambda _cls=cls, **kwargs: built.append((_cls, kwargs)) or _cls)
    return built


# --- building the client -----------------------------------------------------------------

def test_the_v1_api_is_reached_through_the_plain_openai_client(sdk, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", ENDPOINT + "/")  # a trailing slash is tolerated
    AzureOpenAIProvider("my-gpt41-deployment")
    assert sdk == [("OpenAI", {"api_key": "azure-key",
                               "base_url": f"{ENDPOINT}/openai/v1/"})]


def test_an_api_version_selects_the_dated_azure_client(sdk):
    AzureOpenAIProvider("dep", endpoint=ENDPOINT, api_key="k", api_version="2024-10-21", timeout=30)
    assert sdk == [("AzureOpenAI", {"api_key": "k", "azure_endpoint": ENDPOINT,
                                    "api_version": "2024-10-21", "timeout": 30})]


def test_the_environment_variable_names_are_the_caller_s_choice(sdk, monkeypatch):
    monkeypatch.setenv("TEAM_AZURE_KEY", "team-key")
    monkeypatch.setenv("TEAM_AZURE_ENDPOINT", ENDPOINT)
    AzureOpenAIProvider("dep", api_key_env="TEAM_AZURE_KEY", endpoint_env="TEAM_AZURE_ENDPOINT")
    assert sdk[0][1] == {"api_key": "team-key", "base_url": f"{ENDPOINT}/openai/v1/"}


def test_a_missing_endpoint_is_named_before_anything_is_sent(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    with pytest.raises(ProviderError, match="endpoint=.*AZURE_OPENAI_ENDPOINT"):
        AzureOpenAIProvider("dep", api_key="k")


# --- requests ----------------------------------------------------------------------------

def test_model_is_the_deployment_name_and_travels_as_is():
    client = FakeOpenAIClient()
    provider = AzureOpenAIProvider("my-gpt41-deployment", client=client)
    provider.complete("SYSTEM", "USER")
    assert client.bodies[0]["model"] == "my-gpt41-deployment"
    assert client.bodies[0]["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert (provider.name, provider.model) == ("azure", "my-gpt41-deployment")


def test_a_batch_names_the_endpoint_without_the_v1_prefix():
    client = FakeOpenAIClient()
    AzureOpenAIBatchProvider("global-batch-dep", client=client).submit_batch(requests())
    lines = client.uploaded_lines()
    assert [line["url"] for line in lines] == ["/v1/chat/completions"] * 2
    assert {line["body"]["model"] for line in lines} == {"global-batch-dep"}
    assert client.submitted[0]["endpoint"] == "/chat/completions"
    assert client.submitted[0]["completion_window"] == "24h"


def test_a_batch_round_trip_rejoins_by_custom_id():
    client = FakeOpenAIClient(respond=lambda body: body["messages"][1]["content"].lower(), seed=2)
    provider = AzureOpenAIBatchProvider("dep", client=client)
    batch_id = provider.submit_batch(requests(4))
    assert provider.poll_batch(batch_id) == "completed"
    assert {k: v.text for k, v in provider.fetch_batch(batch_id).items()} == {
        f"q{i}": f"u{i}" for i in range(4)}


# --- choosing the class ------------------------------------------------------------------

def test_azure_is_batch_capable_by_default_and_never_probed():
    client = FakeOpenAIClient(batches=False)
    provider = get_provider("azure", model="dep", client=client)
    assert isinstance(provider, BatchCapable) and isinstance(provider, LLMProvider)
    assert client.probes == 0


def test_a_standard_deployment_can_opt_out_of_batches():
    provider = get_provider("azure", model="dep", client=FakeOpenAIClient(), batch=False)
    assert isinstance(provider, AzureOpenAIProvider) and not isinstance(provider, BatchCapable)


# --- the real SDK, over an in-memory transport -------------------------------------------

def test_the_real_sdk_puts_every_call_under_the_resource_v1_path():
    pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")
    seen = []
    chat = {"id": "c", "object": "chat.completion", "created": 0, "model": "dep",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "done"}}]}
    batch = {"id": "batch_1", "object": "batch", "endpoint": "/chat/completions",
             "input_file_id": "file-1", "completion_window": "24h", "status": "in_progress",
             "created_at": 0}

    def handler(request):
        seen.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json={"id": "file-1", "object": "file", "bytes": 1,
                                             "created_at": 0, "filename": "batch_input.jsonl",
                                             "purpose": "batch", "status": "processed"})
        if request.url.path.endswith("/batches"):
            assert json.loads(request.content)["endpoint"] == "/chat/completions"
            return httpx.Response(200, json=batch)
        if "/batches/" in request.url.path:
            return httpx.Response(200, json=batch)
        return httpx.Response(200, json=chat)

    provider = get_provider("azure", model="dep", endpoint=ENDPOINT, api_key="azure-key",
                            max_retries=0,
                            http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.complete("S", "U").text == "done"
    assert provider.poll_batch(provider.submit_batch(requests())) == "running"
    assert [path for _, path, _ in seen] == [
        "/openai/v1/chat/completions", "/openai/v1/files", "/openai/v1/batches",
        "/openai/v1/batches/batch_1"]
    assert {auth for _, _, auth in seen} == {"Bearer azure-key"}
