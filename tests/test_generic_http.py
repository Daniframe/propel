"""The http adapter, against a fake client: no network, no credentials, nothing spent."""

import json

import pytest
from fakes import FakeHTTPClient

from propensity.errors import ProviderError
from propensity.providers import BatchCapable, LLMProvider, get_provider
from propensity.providers.generic_http import GenericHTTPProvider

URL = "https://llm.internal.example/v2/generate"


def build_payload(system, user, *, model, temperature, max_tokens):
    """An in-house format: one prompt field, the system part prepended."""
    return {"engine": model, "prompt": system + user, "temp": temperature, "limit": max_tokens}


def extract_text(response):
    return response["output"]["text"]


def provider(client, **kwargs):
    return GenericHTTPProvider("house-model", url=URL, build_payload=build_payload,
                               extract_text=extract_text, client=client, **kwargs)


def test_the_payload_is_built_by_the_caller_and_posted_as_json():
    client = FakeHTTPClient({"output": {"text": "<FINAL_RANGE>[0, 1]</FINAL_RANGE>"}})
    completion = provider(client).complete("SYSTEM", "USER", temperature=0.0, max_tokens=64)
    assert client.posts == [{"url": URL, "headers": {}, "json": {
        "engine": "house-model", "prompt": "SYSTEMUSER", "temp": 0.0, "limit": 64}}]
    assert completion.text == "<FINAL_RANGE>[0, 1]</FINAL_RANGE>" and completion.error is None
    assert completion.raw == {"output": {"text": "<FINAL_RANGE>[0, 1]</FINAL_RANGE>"}}


def test_a_key_becomes_a_bearer_header_and_extra_headers_ride_along(monkeypatch):
    monkeypatch.setenv("HOUSE_LLM_KEY", "from-env")
    client = FakeHTTPClient({"output": {"text": "ok"}})
    provider(client, api_key_env="HOUSE_LLM_KEY", headers={"X-Team": "vrain"}).complete("S", "U")
    provider(client, api_key="explicit").complete("S", "U")
    assert client.posts[0]["headers"] == {"Authorization": "Bearer from-env", "X-Team": "vrain"}
    assert client.posts[1]["headers"] == {"Authorization": "Bearer explicit"}


def test_the_callables_can_be_named_as_module_paths():
    client = FakeHTTPClient({"output": {"text": "ok"}})
    by_name = GenericHTTPProvider("m", url=URL, client=client,
                                  build_payload="test_generic_http:build_payload",
                                  extract_text="test_generic_http:extract_text")
    assert by_name.complete("S", "U").text == "ok"
    assert client.posts[0]["json"]["prompt"] == "SU"


def test_the_callables_can_be_named_by_file_path_even_with_a_drive_letter(tmp_path):
    formats = tmp_path / "house_format.py"  # absolute, so "C:\..." on Windows: two colons
    formats.write_text("def build(system, user, **settings):\n    return {'q': user}\n\n"
                       "def read(response):\n    return response['a']\n", encoding="utf-8")
    client = FakeHTTPClient({"a": "from a file"})
    by_path = GenericHTTPProvider("m", url=URL, client=client, build_payload=f"{formats}:build",
                                  extract_text=f"{formats}:read")
    assert by_path.complete("S", "U").text == "from a file"
    assert client.posts[0]["json"] == {"q": "U"}


@pytest.mark.parametrize("name", ["no_such_module_anywhere:build", "test_generic_http:missing",
                                  "missing_file.py:build", "no colon at all"])
def test_a_callable_that_cannot_be_loaded_is_named_in_a_clear_error(name):
    with pytest.raises(ProviderError, match="cannot load .*file.py:function or module:function"):
        GenericHTTPProvider("m", url=URL, client=FakeHTTPClient(), build_payload=name,
                            extract_text=extract_text)


@pytest.mark.parametrize("client,expected", [
    (FakeHTTPClient(raises=RuntimeError("connection refused")), "RuntimeError: connection refused"),
    (FakeHTTPClient({"detail": "overloaded"}, status=503), "RuntimeError: HTTP 503"),
    (FakeHTTPClient(ValueError("not JSON")), "ValueError: not JSON"),
    (FakeHTTPClient({"unexpected": "shape"}), "KeyError: 'output'"),
    (FakeHTTPClient({"output": {"text": ""}}), "the provider returned an empty response"),
])
def test_every_failure_is_returned_and_never_raised(client, expected):
    completion = provider(client).complete("S", "U")
    assert (completion.text, completion.error) == ("", expected)


def test_a_response_that_cannot_be_read_is_kept_for_the_audit_trail():
    completion = provider(FakeHTTPClient({"unexpected": "shape"})).complete("S", "U")
    assert completion.raw == {"unexpected": "shape"}


def test_http_registers_itself_and_runs_one_call_at_a_time():
    built = get_provider("http", model="m", url=URL, build_payload=build_payload,
                         extract_text=extract_text, client=FakeHTTPClient())
    assert isinstance(built, LLMProvider) and not isinstance(built, BatchCapable)
    assert (built.name, built.model) == ("http", "m")


def test_a_real_httpx_client_sends_the_same_request():
    httpx = pytest.importorskip("httpx")
    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers.get("authorization"),
                     json.loads(request.content)))
        return httpx.Response(200, json={"output": {"text": "done"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    completion = provider(client, api_key="k").complete("S", "U", max_tokens=8)
    assert completion.text == "done"
    assert seen == [(URL, "Bearer k", {"engine": "house-model", "prompt": "SU", "temp": 0.0,
                                       "limit": 8})]
