"""Azure OpenAI: CLAUDE.md §4.4, a thin subclass of the OpenAI adapter.

`model` is the **deployment name**, not the public model name. Azure now serves the OpenAI v1
API at `{endpoint}/openai/v1/`, which the plain OpenAI client speaks; pass `api_version` only for
a resource still on dated API versions. The SDK is imported lazily.
"""

import os

from ..errors import ProviderError
from . import register_provider
from .openai_compat import OpenAIBatchProvider, OpenAICompatProvider


class AzureOpenAIProvider(OpenAICompatProvider):
    """The endpoint comes from here or from `endpoint_env` (AZURE_OPENAI_ENDPOINT), and the key
    from here or `api_key_env` (AZURE_OPENAI_API_KEY)."""

    name = "azure"
    api_key_env = "AZURE_OPENAI_API_KEY"
    endpoint_env = "AZURE_OPENAI_ENDPOINT"
    batch_endpoint = "/chat/completions"  # Azure's batches.create takes it without the /v1

    def __init__(self, model: str, *, endpoint=None, endpoint_env=None, api_version=None,
                 **kwargs):
        self.endpoint = endpoint or os.environ.get(endpoint_env or self.endpoint_env)
        self.api_version = api_version
        super().__init__(model, **kwargs)

    def _client(self, api_key, api_key_env, base_url, client_options):
        if not (self.endpoint or base_url):
            raise ProviderError("the 'azure' provider needs the resource endpoint: pass endpoint=... "
                                f"or set {self.endpoint_env}")
        openai = self._sdk()
        api_key = api_key or os.environ.get(api_key_env)
        if self.api_version:
            return openai.AzureOpenAI(api_key=api_key, azure_endpoint=self.endpoint,
                                      api_version=self.api_version, **client_options)
        return openai.OpenAI(api_key=api_key, **client_options,
                             base_url=base_url or f"{self.endpoint.rstrip('/')}/openai/v1/")


class AzureOpenAIBatchProvider(AzureOpenAIProvider, OpenAIBatchProvider):
    """Needs a Global Batch deployment: `model` names it, and every line of the batch uses it."""


def _build(model: str, *, batch: bool = True, **kwargs):
    """Batch-capable by default, as Azure OpenAI is; pass batch=False for a standard deployment,
    which cannot take batch jobs. A probe cannot tell the two apart, so none is made."""
    return (AzureOpenAIBatchProvider if batch else AzureOpenAIProvider)(model, **kwargs)


register_provider("azure", _build)
