"""The one narrow protocol the core depends on: CLAUDE.md §4.2.

Everything upstream of a provider talks to `LLMProvider` and nothing else. Anything a provider
cannot do is emulated by the core, so a provider without a batch API still works.
"""

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class Completion:
    """One provider response. `error` is set instead of raising, with `text` left empty."""

    text: str
    raw: dict | None = None
    usage: dict | None = None
    error: str | None = None


@dataclass(frozen=True)
class BatchRequest:
    """One prompt in a batch. `(system, user)` is the transport unit, never one joined string:
    adapters decide how to deliver the system part (§4.1 rule 6)."""

    custom_id: str
    system: str
    user: str


BatchState = Literal["pending", "running", "completed", "failed", "cancelled"]


@runtime_checkable
class LLMProvider(Protocol):
    """What every adapter provides.

    `complete` must not raise on a provider error: it catches and returns a Completion with
    `error` set, so that the annotation layer can count failures instead of dying mid-run.

    Data members mean `isinstance` works but `issubclass` raises TypeError; use isinstance.
    """

    name: str
    model: str

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion: ...


@runtime_checkable
class BatchCapable(Protocol):
    """Optional. Implement only where the provider has a native batch API.

    Batch output order does not match input order, so `fetch_batch` is keyed by custom_id and
    the caller rejoins on it.
    """

    def submit_batch(self, requests: list[BatchRequest], *,
                     temperature: float = 0.0,
                     max_tokens: int | None = None) -> str: ...

    def poll_batch(self, batch_id: str) -> BatchState: ...

    def fetch_batch(self, batch_id: str) -> dict[str, Completion]: ...
