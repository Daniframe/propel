"""Google's Gemini API, through the google-genai SDK.

The system part travels as `system_instruction`. Not batch-capable here, so the core runs it one
call at a time. The SDK is imported lazily.
"""

import logging
import os

from . import register_provider
from .base import Completion

logger = logging.getLogger(__name__)


class GoogleProvider:
    """One generate_content call per request. The api_key comes from here or from `api_key_env`;
    left unset, the SDK reads GEMINI_API_KEY or GOOGLE_API_KEY itself. `send_temperature=False` is
    for a model that rejects it; `config_options` is merged into every request's config; any other
    keyword goes to the SDK client."""

    name = "google"
    api_key_env = "GEMINI_API_KEY"

    def __init__(self, model: str, *, api_key=None, api_key_env=None, client=None,
                 send_temperature=True, config_options=None, **client_options):
        self.model = model
        self.send_temperature = send_temperature
        self.config_options = dict(config_options or {})
        if not send_temperature:
            logger.warning("temperature is not sent to %s:%s, so its intervals may differ between "
                           "reruns", self.name, model)
        self.client = client if client is not None else self._client(
            api_key, api_key_env or self.api_key_env, client_options)

    def _client(self, api_key, api_key_env, client_options):
        try:
            from google import genai
        except ImportError:
            raise ImportError("the 'google' provider needs the google-genai package: "
                              'pip install "propel[google]"') from None
        return genai.Client(api_key=api_key or os.environ.get(api_key_env), **client_options)

    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int | None = None) -> Completion:
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=user, config=self.config(system, temperature, max_tokens))
            text = response.text
        except Exception as exc:  # never raise: the run records failures and carries on
            return Completion(text="", error=f"{type(exc).__name__}: {exc}")
        raw = response.model_dump() if hasattr(response, "model_dump") else None
        if not text:  # a safety block or a spent token budget, most likely: say which
            candidate = (getattr(response, "candidates", None) or [None])[0]
            reason = getattr(getattr(candidate, "finish_reason", None), "value", None)
            return Completion(text="", raw=raw, error="the provider returned an empty response"
                              + (f" (finish reason {reason})" if reason else ""))
        return Completion(text=text, raw=raw, usage=(raw or {}).get("usage_metadata"))

    def config(self, system: str, temperature: float, max_tokens) -> dict:
        """The request config: the system part travels as `system_instruction` here. The
        SDK takes a plain dict for the config, so no SDK type is needed to build it. No tools
        are passed, so the SDK's automatic function calling loop is switched off: one prompt,
        one request."""
        config = {"system_instruction": system, "automatic_function_calling": {"disable": True}}
        if self.send_temperature:
            config["temperature"] = temperature
        if max_tokens is not None:
            config["max_output_tokens"] = max_tokens
        return {**config, **self.config_options}


register_provider("google", GoogleProvider)
