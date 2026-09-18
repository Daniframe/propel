"""The annotation runner, including path equivalence: the sequential and batch paths build
identical prompts and write identical rows."""

import pytest

from propensity.annotation.prompts import build_annotation_prompt
from propensity.annotation.runner import (
    annotate,
    build_requests,
    collect,
    rows_from_completions,
    run_sequential,
    summarise,
)
from propensity.errors import ContractError, DataWarning, ProviderError
from propensity.providers.base import Completion
from propensity.providers.mock import MockBatchProvider, MockProvider

RUBRIC, PRESENTATION = "RUBRIC", "</rubric>\nAnnotate the following task:"
NAME = "risk aversion"


def instances(n=4):
    return [{"question_id": f"RA_{i}", "question_text": f"Q{i}?", "source": "bench"}
            for i in range(n)]


def script(n=4, template="<FINAL_RANGE>[{lower}, +2]</FINAL_RANGE>"):
    """A response per prompt, keyed the way the mock keys them: by the user prompt."""
    answers = {}
    for i, instance in enumerate(instances(n)):
        _, user = build_annotation_prompt(NAME, RUBRIC, PRESENTATION, instance["question_text"])
        answers[user] = template.format(lower=-i)  # 0, -1, -2, -3: all valid with +2
    return answers


def run(provider, mode, n=4, **kwargs):
    return annotate(instances(n), provider=provider, dimension="RA", propensity_name=NAME,
                    rubric=RUBRIC, presentation=PRESENTATION, mode=mode, retry_backoff=0,
                    poll_interval=0, **kwargs)


# --- T7: the two paths cannot disagree ---------------------------------------------------

def test_t7_sequential_and_batch_produce_identical_prompts_and_rows():
    answers = script()
    sequential_provider = MockProvider(response=answers)
    batch_provider = MockBatchProvider(response=answers, scramble=True, seed=3)

    # One worker, so the sequential calls are made, and recorded, in input order.
    sequential_rows = run(sequential_provider, "sequential", max_workers=1)
    batch_rows = run(batch_provider, "batch")

    assert sequential_rows == batch_rows
    assert sequential_provider.calls == batch_provider.calls  # byte-identical prompts, same order
    assert [row["question_id"] for row in batch_rows] == ["RA_0", "RA_1", "RA_2", "RA_3"]
    assert all(row["parse_ok"] for row in batch_rows)


def test_t7_holds_with_parallel_workers_whatever_order_the_calls_finish_in():
    answers = script(n=16)
    sequential_provider = MockProvider(response=answers)
    batch_provider = MockBatchProvider(response=answers, scramble=True, seed=3)

    sequential_rows = run(sequential_provider, "sequential", n=16, max_workers=8)
    batch_rows = run(batch_provider, "batch", n=16)

    assert sequential_rows == batch_rows  # rows always come back in input order
    assert sorted(sequential_provider.calls) == sorted(batch_provider.calls)


def test_a_scrambled_batch_is_rejoined_by_id_never_by_position():
    answers = script()
    provider = MockBatchProvider(response=answers, scramble=True, seed=1)
    rows = run(provider, "batch")
    for row in rows:
        _, user = build_annotation_prompt(NAME, RUBRIC, PRESENTATION, row["question_text"])
        assert row["explanation"] == answers[user], row["question_id"]


def test_an_id_that_was_never_sent_is_reported_and_dropped():
    provider = MockBatchProvider(unknown=["ghost"])
    requests = build_requests(instances(2), propensity_name=NAME, rubric=RUBRIC,
                              presentation=PRESENTATION)
    batch_id = provider.submit_batch(requests)
    with pytest.warns(DataWarning, match="never sent.*ghost"):
        completions = collect(provider, batch_id, requests)
    assert set(completions) == {"RA_0", "RA_1"}


def test_an_id_missing_from_the_batch_output_becomes_a_provider_error_row():
    rows = run(MockBatchProvider(drop=["RA_2"]), "batch")
    missing = [row for row in rows if row["question_id"] == "RA_2"][0]
    assert missing["error"] == "missing from the batch output"
    assert missing["parse_ok"] is False and missing["lower"] is None
    assert sum(row["parse_ok"] for row in rows) == 3


def test_a_failed_batch_is_recorded_on_every_row():
    rows = run(MockBatchProvider(states=["failed"]), "batch")
    assert all("ended as failed" in row["error"] for row in rows)
    assert not any(row["parse_ok"] for row in rows)


# --- dispatch ----------------------------------------------------------------------------

def test_batch_mode_needs_a_batch_capable_provider():
    with pytest.raises(ProviderError, match="no batch API"):
        run(MockProvider(), "batch")


def test_auto_takes_the_batch_api_when_there_is_one():
    provider = MockBatchProvider()
    run(provider, "auto")
    assert len(provider.batches) == 1


def test_auto_falls_back_to_sequential_and_says_so(caplog):
    provider = MockProvider()
    with caplog.at_level("INFO"):
        run(provider, "auto")
    assert "no batch API" in caplog.text
    assert len(provider.calls) == 4


def test_an_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="mode must be one of"):
        run(MockProvider(), "quickly")


def test_a_non_zero_temperature_is_flagged(caplog):
    with caplog.at_level("WARNING"):
        run(MockProvider(), "sequential", temperature=0.7)
    assert "intervals will not be stable" in caplog.text


# --- rows ---------------------------------------------------------------------------------

def test_every_instance_gets_one_row_in_input_order_with_its_other_fields():
    rows = run(MockProvider(), "sequential")
    assert [row["question_id"] for row in rows] == [f"RA_{i}" for i in range(4)]
    first = rows[0]
    assert list(first)[:10] == ["question_id", "dimension", "lower", "upper", "annotator",
                                "explanation", "parse_ok", "error", "parse_error", "parse_method"]
    assert (first["dimension"], first["annotator"]) == ("RA", "mock:mock-1")
    assert first["source"] == "bench" and first["question_text"] == "Q0?"  # passed through


def test_an_instance_field_never_overwrites_a_canonical_one():
    rows = rows_from_completions(
        [{"question_id": "q0", "question_text": "Q", "lower": 99, "parse_ok": "nonsense"}],
        {"q0": Completion(text="<FINAL_RANGE>[0, 1]</FINAL_RANGE>")},
        dimension="RA", annotator="mock:mock-1")
    assert (rows[0]["lower"], rows[0]["upper"]) == (0, 1)
    assert rows[0]["parse_ok"] is True


def test_a_provider_error_is_recorded_and_told_apart_from_a_parse_failure(capsys):
    answers = script()
    for user in list(answers)[:1]:
        answers[user] = Completion(text="", error="502 from upstream")
    for user in list(answers)[1:2]:
        answers[user] = "I could not decide."

    rows = run(MockProvider(response=answers), "sequential")
    by_id = {row["question_id"]: row for row in rows}

    assert by_id["RA_0"]["error"] == "502 from upstream" and by_id["RA_0"]["parse_error"] is None
    assert by_id["RA_1"]["error"] is None
    assert by_id["RA_1"]["parse_error"] == "no propensity range found in the response"
    assert by_id["RA_1"]["explanation"] == "I could not decide."  # the text is never discarded
    assert capsys.readouterr().out.strip() == "2 ok, 1 parse-failed, 1 provider-error out of 4 total"


def test_the_summary_counts_each_kind_of_failure_once():
    rows = [{"parse_ok": True, "error": None}, {"parse_ok": False, "error": None},
            {"parse_ok": False, "error": "boom"}]
    assert summarise(rows) == "1 ok, 1 parse-failed, 1 provider-error out of 3 total"


# --- the sequential path -----------------------------------------------------------------

def test_a_transient_failure_is_retried_until_it_works():
    provider = MockProvider(transient_failures=2)
    rows = run(provider, "sequential", max_retries=3)
    assert all(row["parse_ok"] for row in rows)
    assert len(provider.attempts) == 4 and set(provider.attempts.values()) == {3}


def test_retries_are_bounded_and_the_failure_is_recorded():
    provider = MockProvider(transient_failures=5)
    rows = run(provider, "sequential", max_retries=1)
    assert all(row["error"] == "mock transient failure" for row in rows)
    assert len(provider.calls) == 8  # four instances, two attempts each


def test_a_parse_failure_is_not_retried():
    provider = MockProvider(response="no interval here")
    run(provider, "sequential", max_retries=3)
    assert len(provider.calls) == 4


def test_progress_is_reported_for_every_instance():
    seen = []
    run(MockProvider(), "sequential", on_progress=lambda done, total: seen.append((done, total)))
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_the_transport_settings_reach_the_provider():
    class Recorder:
        name, model = "recorder", "m"

        def __init__(self):
            self.kwargs = []

        def complete(self, system, user, *, temperature=0.0, max_tokens=None):
            self.kwargs.append({"temperature": temperature, "max_tokens": max_tokens})
            return Completion(text="<FINAL_RANGE>[0, 0]</FINAL_RANGE>")

    provider = Recorder()
    requests = build_requests(instances(2), propensity_name=NAME, rubric=RUBRIC,
                              presentation=PRESENTATION)
    run_sequential(provider, requests, temperature=0.0, max_tokens=256, max_workers=2)
    assert provider.kwargs == [{"temperature": 0.0, "max_tokens": 256}] * 2


# --- building the requests ---------------------------------------------------------------

def test_duplicate_question_ids_are_refused_before_anything_is_sent():
    rows = instances(2) + [{"question_id": "RA_0", "question_text": "again?"}]
    with pytest.raises(ContractError, match="duplicate question_id"):
        build_requests(rows, propensity_name=NAME, rubric=RUBRIC, presentation=PRESENTATION)


@pytest.mark.parametrize("bad,match", [
    ([{"question_text": "Q"}], "no question_id"),
    ([{"question_id": "q0"}], "no question_text"),
    ([{"question_id": "q0", "question_text": "  "}], "no question_text"),
])
def test_instances_that_cannot_be_annotated_are_refused(bad, match):
    with pytest.raises(ContractError, match=match):
        build_requests(bad, propensity_name=NAME, rubric=RUBRIC, presentation=PRESENTATION)


def test_the_request_carries_the_id_and_the_assembled_prompt():
    requests = build_requests(instances(1), propensity_name=NAME, rubric=RUBRIC,
                              presentation=PRESENTATION)
    system, user = build_annotation_prompt(NAME, RUBRIC, PRESENTATION, "Q0?")
    assert requests[0].custom_id == "RA_0"
    assert (requests[0].system, requests[0].user) == (system, user)
