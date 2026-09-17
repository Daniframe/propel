"""Provider adapters, and the registry that resolves them by name: CLAUDE.md §4.

The core depends on the `LLMProvider` protocol in `base.py` and nothing else. Only modules in
this package may import a vendor SDK, and each imports lazily, inside the constructor or the
method that needs it, so installing one provider's SDK is never required to use another's.

Adding a provider means adding a module here that calls `register_provider`; no core module
changes. Nothing is cached and nothing is shared: two providers can be used in the same process.
"""

from ..errors import ProviderError
from .base import BatchCapable, BatchRequest, BatchState, Completion, LLMProvider

_REGISTRY: dict[str, callable] = {}


def register_provider(name: str, factory) -> None:
    """Registers a factory under `name`. Adapter modules call this as they are imported."""
    _REGISTRY[str(name)] = factory


def available_providers() -> list[str]:
    """The names `get_provider` accepts."""
    return sorted(_REGISTRY)


def get_provider(name: str, **kwargs):
    """Builds the named provider.

    Credentials can be passed here, or left to the adapter's own environment variables, whose
    names the adapter declares and the caller may override. An adapter whose SDK is not
    installed raises ImportError here, naming the extra that installs it.
    """
    factory = _REGISTRY.get(name)
    if factory is None:
        raise ProviderError(
            f"unknown provider {name!r}; available: {', '.join(available_providers()) or 'none'}")
    return factory(**kwargs)


from . import mock, openai_compat  # noqa: E402  imported for their self-registration
