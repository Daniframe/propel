import subprocess
import sys
from dataclasses import FrozenInstanceError

import pytest

from propensity import providers
from propensity.errors import ProviderError
from propensity.providers import (
    BatchCapable,
    BatchRequest,
    Completion,
    LLMProvider,
    available_providers,
    get_provider,
    register_provider,
)
from propensity.providers.mock import DEFAULT_RESPONSE, MockBatchProvider, MockProvider


@pytest.fixture
def clean_registry():
    """The registry is module state; put it back after a test adds to it."""
    saved = dict(providers._REGISTRY)
    yield
    providers._REGISTRY.clear()
    providers._REGISTRY.update(saved)


def requests(n=3):
    return [BatchRequest(custom_id=f"q{i}", system="S", user=f"U{i}") for i in range(n)]


# --- the protocol -----------------------------------------------------------------------

def test_the_two_protocols_separate_batch_capable_providers():
    assert isinstance(MockProvider(), LLMProvider)
    assert not isinstance(MockProvider(), BatchCapable)
    assert isinstance(MockBatchProvider(), LLMProvider)
    assert isinstance(MockBatchProvider(), BatchCapable)
    assert not isinstance(object(), LLMProvider)


def test_completions_and_requests_are_frozen_with_the_documented_defaults():
    completion = Completion(text="hello")
    assert (completion.raw, completion.usage, completion.error) == (None, None, None)
    with pytest.raises(FrozenInstanceError):
        completion.text = "no"
    with pytest.raises(FrozenInstanceError):
        BatchRequest(custom_id="q0", system="S", user="U").user = "no"


# --- the registry: a new provider needs no core change ---------------------------------

def test_the_mock_registers_itself():
    assert "mock" in available_providers()
    assert isinstance(get_provider("mock"), MockProvider)
    assert not isinstance(get_provider("mock"), MockBatchProvider)
    assert isinstance(get_provider("mock", batch=True), MockBatchProvider)


def test_the_registry_passes_keyword_arguments_through():
    provider = get_provider("mock", model="mock-9", response="scripted")
    assert (provider.name, provider.model) == ("mock", "mock-9")
    assert provider.complete("S", "U").text == "scripted"


def test_an_unknown_provider_says_what_is_available():
    with pytest.raises(ProviderError, match="unknown provider 'nope'.*mock"):
        get_provider("nope")


def test_a_new_provider_needs_no_core_change(clean_registry):
    class Elsewhere:
        name, model = "elsewhere", "m"

        def __init__(self, token=None):
            self.token = token

        def complete(self, system, user, *, temperature=0.0, max_tokens=None):
            return Completion(text=f"{self.token}:{user}")

    register_provider("elsewhere", Elsewhere)
    provider = get_provider("elsewhere", token="abc")
    assert "elsewhere" in available_providers()
    assert isinstance(provider, LLMProvider)
    assert provider.complete("S", "U").text == "abc:U"


def test_two_providers_coexist_without_sharing_state():
    first, second = get_provider("mock", model="a"), get_provider("mock", model="b")
    first.complete("S", "U")
    assert second.calls == [] and first.calls == [("S", "U")]


# --- the mock ---------------------------------------------------------------------------

def test_the_default_response_carries_a_parsable_range():
    completion = MockProvider().complete("S", "U")
    assert "<FINAL_RANGE>[-1, +2]</FINAL_RANGE>" in completion.text
    assert completion.error is None
    assert completion.raw == {"provider": "mock", "model": "mock-1"}


@pytest.mark.parametrize("response,expected", [
    ("fixed", "fixed"),
    (lambda system, user: f"{system}|{user}", "S|U"),
    ({"U": "mapped"}, "mapped"),
    (Completion(text="prebuilt", usage={"tokens": 3}), "prebuilt"),
])
def test_responses_can_be_fixed_callable_mapped_or_prebuilt(response, expected):
    assert MockProvider(response=response).complete("S", "U").text == expected


def test_an_unscripted_prompt_returns_an_error_rather_than_raising():
    completion = MockProvider(response={"other": "x"}).complete("S", "U")
    assert completion.text == "" and "no scripted response" in completion.error


def test_calls_are_recorded_in_order_and_counted_per_key():
    provider = MockProvider()
    provider.complete("S", "U1")
    provider.complete("S", "U2")
    provider.complete("S", "U1")
    assert provider.calls == [("S", "U1"), ("S", "U2"), ("S", "U1")]
    assert provider.attempts == {"U1": 2, "U2": 1}


def test_transient_failures_give_way_to_the_scripted_answer():
    provider = MockProvider(response="eventually", transient_failures=2)
    assert [provider.complete("S", "U").error for _ in range(2)] == ["mock transient failure"] * 2
    assert provider.complete("S", "U").text == "eventually"


def test_a_custom_key_groups_prompts():
    provider = MockProvider(response={"S": "by system"}, key=lambda system, user: system)
    assert provider.complete("S", "U1").text == "by system"
    assert provider.complete("S", "U2").text == "by system"
    assert provider.attempts == {"S": 2}


# --- the mock's batch API ----------------------------------------------------------------

def test_a_batch_records_its_prompts_and_answers_every_id():
    provider = MockBatchProvider(response=lambda system, user: f"answer to {user}")
    batch_id = provider.submit_batch(requests())

    assert batch_id == "mock-batch-1"
    assert provider.calls == [("S", "U0"), ("S", "U1"), ("S", "U2")]
    assert provider.poll_batch(batch_id) == "completed"
    results = provider.fetch_batch(batch_id)
    assert {k: v.text for k, v in results.items()} == {
        "q0": "answer to U0", "q1": "answer to U1", "q2": "answer to U2"}


def test_batch_results_come_back_in_a_different_order():
    provider = MockBatchProvider(scramble=True, seed=1)
    batch_id = provider.submit_batch(requests(8))
    fetched = list(provider.fetch_batch(batch_id))
    assert fetched != [request.custom_id for request in requests(8)]  # rejoin by custom_id
    assert sorted(fetched) == [f"q{i}" for i in range(8)]


def test_a_batch_can_lose_ids_and_invent_them():
    provider = MockBatchProvider(drop=["q1"], unknown=["ghost"], scramble=False)
    results = provider.fetch_batch(provider.submit_batch(requests()))
    assert set(results) == {"q0", "q2", "ghost"}


def test_polling_walks_a_scripted_sequence_then_holds():
    provider = MockBatchProvider(states=["pending", "running", "completed"])
    batch_id = provider.submit_batch(requests(1))
    assert [provider.poll_batch(batch_id) for _ in range(4)] == [
        "pending", "running", "completed", "completed"]
    assert provider.polls[batch_id] == 4


def test_a_batch_can_fail_outright():
    provider = MockBatchProvider(states=["failed"])
    batch_id = provider.submit_batch(requests(1))
    assert provider.poll_batch(batch_id) == "failed"


def test_an_unknown_batch_id_is_an_error():
    with pytest.raises(KeyError):
        MockBatchProvider().poll_batch("mock-batch-404")


def test_both_paths_answer_the_same_prompt_identically():
    """The groundwork for T7: the answer depends on the prompt, not on the path it arrived by."""
    script = {f"U{i}": f"answer {i}" for i in range(3)}
    sequential, batch = MockProvider(response=script), MockBatchProvider(response=script)

    one_at_a_time = {r.custom_id: sequential.complete(r.system, r.user) for r in requests()}
    in_a_batch = batch.fetch_batch(batch.submit_batch(requests()))
    assert one_at_a_time == in_a_batch
    assert sorted(sequential.calls) == sorted(batch.calls)


# --- T9: provider isolation --------------------------------------------------------------

ISOLATION_SCRIPT = """
import sys

BLOCKED = ("openai", "anthropic", "google", "httpx", "matplotlib", "seaborn")


class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError(f"{name} is blocked for this test")
        return None


sys.meta_path.insert(0, Blocker())

# Prove the blocker bites, so this test cannot pass merely because an SDK is absent.
for blocked in BLOCKED:
    try:
        __import__(blocked)
    except ImportError:
        pass
    else:
        raise AssertionError(f"{blocked} imported despite the blocker")
sys.modules.pop("google", None)  # a namespace package can survive a failed submodule import

import propensity
import propensity.modelling
import propensity.providers
import propensity.providers.mock

provider = propensity.providers.get_provider("mock")
assert provider.complete("S", "U").text, "the mock must work with no SDK installed"
leaked = [name for name in BLOCKED if name in sys.modules]
assert not leaked, f"importing propensity pulled in {leaked}"
print("ok")
"""


def test_t9_the_core_imports_with_no_vendor_sdk_installed():
    done = subprocess.run([sys.executable, "-c", ISOLATION_SCRIPT],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().endswith("ok")


def test_importing_the_package_does_not_pull_in_a_vendor_sdk():
    # The adapter modules import their SDK lazily, so none of this is loaded by `import`.
    script = ("import propensity.providers, sys; "
              "print([m for m in ('openai', 'anthropic', 'google', 'httpx') if m in sys.modules])")
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"
