"""OpenAI, and anything that speaks its API: CLAUDE.md §4.4.

`base_url` points this same adapter at a self-hosted vLLM or Ollama server, LM Studio,
OpenRouter, Together or an in-house gateway. The SDK is imported lazily.
"""

import json
import os

from . import register_provider
from .base import Completion

CHAT_URL = "/v1/chat/completions"
# OpenAI's own batch statuses, mapped onto BatchState.
BATCH_STATES = {"validating": "pending", "in_progress": "running", "finalizing": "running",
                "cancelling": "running", "completed": "completed", "failed": "failed",
                "expired": "failed", "cancelled": "cancelled"}


class OpenAICompatProvider:
    """One chat completion per call. The api_key comes from here or from `api_key_env`;
    `client` takes an already-built SDK client, which is how the tests stay off the network;
    `request_options` is merged into every request, for a model that wants something else such
    as `max_completion_tokens`; any other keyword goes to the SDK client."""

    name = "openai"
    api_key_env = "OPENAI_API_KEY"
    batch_url = CHAT_URL

    def __init__(self, model: str, *, api_key=None, api_key_env=None, base_url=None, client=None,
                 request_options=None, **client_options):
        self.model = model
        self.base_url = base_url
        self.request_options = dict(request_options or {})
        self.client = client if client is not None else self._client(
            api_key, api_key_env or self.api_key_env, base_url, client_options)

    def _client(self, api_key, api_key_env, base_url, client_options):
        try:
            import openai
        except ImportError:
            raise ImportError(f"the {self.name!r} provider needs the openai package: "
                              'pip install "propel[openai]"') from None
        return openai.OpenAI(api_key=api_key or os.environ.get(api_key_env),
                             base_url=base_url, **client_options)

    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int | None = None) -> Completion:
        try:
            response = self.client.chat.completions.create(
                **self.request_body(system, user, temperature, max_tokens))
        except Exception as exc:  # never raise: the run records failures and carries on (§4.2)
            return Completion(text="", error=f"{type(exc).__name__}: {exc}")
        raw = response.model_dump() if hasattr(response, "model_dump") else None
        text = response.choices[0].message.content if response.choices else None
        if not text:
            return Completion(text="", raw=raw, error="the provider returned an empty response")
        return Completion(text=text, raw=raw, usage=(raw or {}).get("usage"))

    def request_body(self, system: str, user: str, temperature: float, max_tokens) -> dict:
        """The system part travels as a `system` role message here (§4.1 rule 6)."""
        body = {"model": self.model, "temperature": temperature,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        return {**body, **self.request_options}


class OpenAIBatchProvider(OpenAICompatProvider):
    """Adds the Files plus Batches API: about half the price, within a 24-hour window."""

    def submit_batch(self, requests, *, temperature: float = 0.0, max_tokens=None) -> str:
        lines = [json.dumps({"custom_id": request.custom_id, "method": "POST",
                             "url": self.batch_url,
                             "body": self.request_body(request.system, request.user,
                                                       temperature, max_tokens)})
                 for request in requests]
        upload = self.client.files.create(file=("batch_input.jsonl", "\n".join(lines).encode()),
                                          purpose="batch")
        return self.client.batches.create(input_file_id=upload.id, endpoint=self.batch_url,
                                          completion_window="24h").id

    def poll_batch(self, batch_id: str) -> str:
        return BATCH_STATES.get(self.client.batches.retrieve(batch_id).status, "running")

    def fetch_batch(self, batch_id: str) -> dict[str, Completion]:
        """Keyed by custom_id, since batch output does not keep input order. The error file is
        folded in, so a failed request becomes a row rather than a silence."""
        batch = self.client.batches.retrieve(batch_id)
        completions = {}
        for file_id in (batch.output_file_id, getattr(batch, "error_file_id", None)):
            for line in (self.client.files.content(file_id).text.splitlines() if file_id else []):
                if line.strip():
                    result = json.loads(line)
                    completions[result.get("custom_id")] = _completion_from(result)
        return completions


def _completion_from(result: dict) -> Completion:
    response = result.get("response") or {}
    body = response.get("body") or {}
    if result.get("error"):
        return Completion(text="", raw=result, error=str(result["error"]))
    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        text = None
    if not text:
        return Completion(text="", raw=result, error="no completion in the batch output "
                                                     f"(status {response.get('status_code')})")
    return Completion(text=text, raw=result, usage=body.get("usage"))


def _probe(client) -> bool:
    try:
        client.batches.list(limit=1)
        return True
    except Exception:
        return False


def _build(model: str, *, batch=None, **kwargs):
    """batch=None probes a custom endpoint rather than assuming: plenty of OpenAI-compatible
    servers have no batch API, and finding that out at submit time wastes a run. The official
    endpoint has one, so it is not probed."""
    provider = OpenAICompatProvider(model, **kwargs)
    if batch is None:
        batch = provider.base_url is None or _probe(provider.client)
    if not batch:
        return provider
    return OpenAIBatchProvider(model, client=provider.client, base_url=provider.base_url,
                               request_options=provider.request_options)


register_provider("openai", _build)
