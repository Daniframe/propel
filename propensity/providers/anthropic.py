"""Anthropic's Messages API.

The system part travels as the top-level `system` parameter. `max_tokens` is required by the API,
and defaults generously here because current models think before answering and the thinking
counts against it. The SDK is imported lazily.
"""

import logging
import os
import re

from ..errors import ProviderError
from . import register_provider
from .base import Completion

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16000
CUSTOM_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")  # what Message Batches accepts
BATCH_STATES = {"in_progress": "running", "canceling": "running", "ended": "completed"}


class AnthropicProvider:
    """One Messages API call per request. The api_key comes from here or from `api_key_env`;
    left unset, the SDK resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or an `ant auth login`
    profile. Current models (Opus 4.7 and later, Sonnet 5, Fable) reject temperature 0 with a 400,
    and need `send_temperature=False`; Opus 4.6, Sonnet 4.6 and Haiku 4.5 still accept it.
    `request_options` is merged into every request; any other keyword goes to the SDK client."""

    name = "anthropic"
    api_key_env = "ANTHROPIC_API_KEY"

    def __init__(self, model: str, *, api_key=None, api_key_env=None, client=None,
                 send_temperature=True, request_options=None, **client_options):
        self.model = model
        self.send_temperature = send_temperature
        self.request_options = dict(request_options or {})
        if not send_temperature:
            logger.warning("temperature is not sent to %s:%s, so its intervals may differ between "
                           "reruns", self.name, model)
        self.client = client if client is not None else self._client(
            api_key, api_key_env or self.api_key_env, client_options)

    def _client(self, api_key, api_key_env, client_options):
        try:
            import anthropic
        except ImportError:
            raise ImportError("the 'anthropic' provider needs the anthropic package: "
                              'pip install "propel[anthropic]"') from None
        return anthropic.Anthropic(api_key=api_key or os.environ.get(api_key_env), **client_options)

    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int | None = None) -> Completion:
        params = self.params(system, user, temperature, max_tokens)
        if "temperature" in params:  # gone from the 1.x SDK's signature, not from the API
            params["extra_body"] = {"temperature": params.pop("temperature")}
        try:
            message = self.client.messages.create(**params)
        except Exception as exc:  # never raise: the run records failures and carries on
            return Completion(text="", error=f"{type(exc).__name__}: {exc}")
        return _completion_from(message)

    def params(self, system: str, user: str, temperature: float, max_tokens) -> dict:
        """The request body: the system part is a top-level parameter here."""
        params = {"model": self.model, "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
                  "system": system, "messages": [{"role": "user", "content": user}]}
        if self.send_temperature:
            params["temperature"] = temperature
        return {**params, **self.request_options}


class AnthropicBatchProvider(AnthropicProvider):
    """Adds Message Batches: half the price, most batches finished within the hour."""

    def submit_batch(self, requests, *, temperature: float = 0.0, max_tokens=None) -> str:
        requests = list(requests)
        unfit = [request.custom_id for request in requests if not CUSTOM_ID.match(request.custom_id)]
        if unfit:  # refuse before anything is sent, rather than fail the whole batch server-side
            raise ProviderError("Message Batches takes custom_ids of 1 to 64 letters, digits, '-' "
                                f"or '_', and these question_ids do not fit: {unfit[:5]}. Rename "
                                "them, or use mode='sequential'.")
        return self.client.messages.batches.create(requests=[
            {"custom_id": request.custom_id,
             "params": self.params(request.system, request.user, temperature, max_tokens)}
            for request in requests]).id

    def poll_batch(self, batch_id: str) -> str:
        status = self.client.messages.batches.retrieve(batch_id).processing_status
        return BATCH_STATES.get(status, "running")

    def fetch_batch(self, batch_id: str) -> dict[str, Completion]:
        """Keyed by custom_id: results arrive in any order. A request that errored, was
        cancelled or expired becomes an error completion rather than a missing row."""
        completions = {}
        for entry in self.client.messages.batches.results(batch_id):
            result = entry.result
            if result.type == "succeeded":
                completions[entry.custom_id] = _completion_from(result.message)
            else:
                detail = getattr(result, "error", None)
                completions[entry.custom_id] = Completion(
                    text="", error=f"batch request {result.type}" + (f": {detail}" if detail else ""))
        return completions


def _completion_from(message) -> Completion:
    raw = message.model_dump() if hasattr(message, "model_dump") else None
    usage = (raw or {}).get("usage")
    text = "".join(block.text for block in message.content if block.type == "text")
    if message.stop_reason == "refusal":
        return Completion(text="", raw=raw, usage=usage, error="the model declined the request")
    if message.stop_reason == "max_tokens":
        return Completion(text="", raw=raw, usage=usage,
                          error="stopped at max_tokens before finishing; raise max_tokens")
    if not text:
        return Completion(text="", raw=raw, usage=usage, error="the provider returned an empty response")
    return Completion(text=text, raw=raw, usage=usage)


def _build(model: str, *, batch: bool = True, **kwargs):
    """Message Batches is open to every API key, so the batch-capable class is the default."""
    return (AnthropicBatchProvider if batch else AnthropicProvider)(model, **kwargs)


register_provider("anthropic", _build)
