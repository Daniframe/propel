"""A provider that answers from a script.

It ships in the package rather than in the tests so that the annotation layer can be exercised
end to end, by us and by anyone extending the pipeline, without spending anything.
"""

import json
import random
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from . import register_provider
from .base import BatchRequest, Completion

DEFAULT_RESPONSE = "Working outward from 0.\n<FINAL_RANGE>[-1, +2]</FINAL_RANGE>"


class MockProvider:
    """Answers every call from `response`, and records what it was asked.

    response: a string, a Completion, a mapping from key to either, or a callable
        `(system, user)` returning either. A mapping with no entry for a prompt answers with an
        error completion rather than raising, as a real provider would.
    key: turns `(system, user)` into the mapping key; the user prompt by default, which is the
        one thing both the sequential and the batch path have in common.
    transient_failures: how many times each key fails with a retryable error before the
        scripted answer arrives, for exercising bounded retry. Sequential path only.
    """

    name = "mock"

    def __init__(self, model: str = "mock-1", *, response=DEFAULT_RESPONSE, key=None,
                 transient_failures: int = 0):
        self.model = model
        self.response = response
        self.key = key or (lambda system, user: user)
        self.transient_failures = transient_failures
        self.calls: list[tuple[str, str]] = []  # every (system, user) received, in order
        self.attempts: dict[str, int] = {}      # key -> how many times it has been asked

    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int | None = None) -> Completion:
        self.calls.append((system, user))
        key = self.key(system, user)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        if self.attempts[key] <= self.transient_failures:
            return Completion(text="", error="mock transient failure")
        return self._scripted(system, user)

    def _scripted(self, system: str, user: str) -> Completion:
        answer = self.response
        if callable(answer):
            answer = answer(system, user)
        elif isinstance(answer, Mapping):
            key = self.key(system, user)
            if key not in answer:
                return Completion(text="", error=f"mock has no scripted response for {key[:80]!r}")
            answer = answer[key]
        if isinstance(answer, Completion):
            return answer
        return Completion(text=answer, raw={"provider": self.name, "model": self.model})


class MockBatchProvider(MockProvider):
    """Adds a batch API that bends the way real ones bend: results come back in a different
    order, ids go missing, unknown ids turn up, and a batch can fail outright.

    scramble: return results in a shuffled order, as a real batch does.
    drop: custom_ids to leave out of the results.
    unknown: custom_ids to add that were never sent.
    states: the sequence `poll_batch` walks through, the last repeating; "completed" by default.
    state_path: where to keep the submitted batches, so that a later process can poll and fetch
        them. A real batch lives on the provider's side, which is what lets submit, status and
        fetch be separate commands; without this the mock could not stand in for that.
    """

    def __init__(self, model: str = "mock-1", *, scramble: bool = True, drop=(), unknown=(),
                 states=None, seed: int = 0, state_path=None, **kwargs):
        super().__init__(model, **kwargs)
        self.state_path = Path(state_path) if state_path else None
        self.scramble = scramble
        self.drop = _as_set(drop)
        self.unknown = tuple(_as_set(unknown))
        self.states = [states] if isinstance(states, str) else list(states) if states else None
        self.random = random.Random(seed)
        self.batches: dict[str, list] = {}   # batch_id -> the requests it was given
        self.polls: dict[str, int] = {}      # batch_id -> how many times it has been polled

    def submit_batch(self, requests, *, temperature: float = 0.0,
                     max_tokens: int | None = None) -> str:
        self._load()
        requests = list(requests)
        batch_id = f"mock-batch-{len(self.batches) + 1}"
        self.batches[batch_id] = requests
        self.calls.extend((request.system, request.user) for request in requests)
        self._save()
        return batch_id

    def poll_batch(self, batch_id: str) -> str:
        self._load()
        if batch_id not in self.batches:
            raise KeyError(f"no such batch {batch_id!r}")
        self.polls[batch_id] = self.polls.get(batch_id, 0) + 1
        self._save()
        if self.states is None:
            return "completed"
        return self.states[min(self.polls[batch_id] - 1, len(self.states) - 1)]

    def fetch_batch(self, batch_id: str) -> dict[str, Completion]:
        self._load()
        requests = list(self.batches[batch_id])
        if self.scramble:
            self.random.shuffle(requests)
        results = {request.custom_id: self._scripted(request.system, request.user)
                   for request in requests if request.custom_id not in self.drop}
        for custom_id in self.unknown:
            results[custom_id] = Completion(text=DEFAULT_RESPONSE)
        return results


    def _load(self):
        if self.state_path and self.state_path.exists():
            stored = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.batches = {batch_id: [BatchRequest(**request) for request in requests]
                            for batch_id, requests in stored["batches"].items()}
            self.polls = dict(stored["polls"])

    def _save(self):
        if self.state_path:
            self.state_path.write_text(json.dumps({
                "batches": {batch_id: [asdict(request) for request in requests]
                            for batch_id, requests in self.batches.items()},
                "polls": self.polls,
            }), encoding="utf-8")


def _as_set(value):
    """One id given as a string is one id, not a set of characters."""
    return {value} if isinstance(value, str) else set(value)


def _build(model: str = "mock-1", *, batch: bool = False, **kwargs):
    """`get_provider("mock", batch=True)` hands back the batch-capable one."""
    return (MockBatchProvider if batch else MockProvider)(model, **kwargs)


register_provider("mock", _build)
