"""Token usage on every annotation row: each provider's shape, both paths, and the totals line."""

import pytest
from fakes import FakeOpenAIClient

from propensity import get_provider
from propensity.annotation.runner import (
    ROW_FIELDS,
    USAGE_FIELDS,
    annotate,
    normalise_usage,
    rows_from_completions,
    summarise_usage,
)
from propensity.providers.base import Completion

RUBRIC, PRESENTATION = "RUBRIC", "</rubric>\nAnnotate the following task:"
INSTANCES = [{"question_id": f"RA_{i}", "question_text": f"Q{i}?"} for i in range(3)]


@pytest.mark.parametrize("usage,expected", [
    ({"prompt_tokens": 2400, "completion_tokens": 850,               # OpenAI chat completions
      "prompt_tokens_details": {"cached_tokens": 2304}}, (2400, 850, 2304)),
    ({"prompt_tokens": 2400, "completion_tokens": 850}, (2400, 850, None)),
    ({"input_tokens": 2400, "output_tokens": 850,                     # OpenAI responses
      "input_tokens_details": {"cached_tokens": 1024}}, (2400, 850, 1024)),
    ({"input_tokens": 96, "output_tokens": 850,                       # Anthropic: input_tokens
      "cache_read_input_tokens": 2304, "cache_creation_input_tokens": 0}, (2400, 850, 2304)),
    ({"input_tokens": 100, "output_tokens": 850, "cache_read_input_tokens": None,
      "cache_creation_input_tokens": 2300}, (2400, 850, None)),       # excludes cache writes too
    ({"prompt_token_count": 2400, "candidates_token_count": 800,      # Gemini: thoughts are
      "thoughts_token_count": 50, "cached_content_token_count": 2048}, (2400, 850, 2048)),  # output
    ({"prompt_token_count": 2400, "candidates_token_count": 850}, (2400, 850, None)),
    (None, (None, None, None)),
    ({"something": "else"}, (None, None, None)),
])
def test_each_providers_usage_becomes_the_same_three_counts(usage, expected):
    assert tuple(normalise_usage(usage)[field] for field in USAGE_FIELDS) == expected


def test_the_usage_fields_follow_parse_method_in_the_canonical_row():
    start = ROW_FIELDS.index("parse_method") + 1
    assert ROW_FIELDS[start:start + 3] == ("input_tokens", "output_tokens", "cached_input_tokens")


def test_rows_carry_the_counts_even_for_failures():
    completions = {"RA_0": Completion(text="<FINAL_RANGE>[0, 1]</FINAL_RANGE>",
                                      usage={"prompt_tokens": 10, "completion_tokens": 5}),
                   "RA_1": Completion(text="", error="refused",
                                      usage={"prompt_tokens": 10, "completion_tokens": 0})}
    rows = rows_from_completions(INSTANCES, completions, dimension="RA", annotator="x:y")
    assert [(row["input_tokens"], row["output_tokens"]) for row in rows] == [(10, 5), (10, 0), (None, None)]


USAGE = {"prompt_tokens": 2400, "completion_tokens": 850, "prompt_tokens_details": {"cached_tokens": 2304}}


def run(mode, client):
    provider = get_provider("openai", model="gpt-x", client=client)
    return annotate(INSTANCES, provider=provider, dimension="RA", propensity_name="risk aversion",
                    rubric=RUBRIC, presentation=PRESENTATION, mode=mode, max_workers=1,
                    retry_backoff=0, poll_interval=0)


def test_both_paths_record_the_same_counts_and_print_the_totals(capsys):
    answer = "<FINAL_RANGE>[0, 1]</FINAL_RANGE>"
    sequential = run("sequential", FakeOpenAIClient(answer, usage=USAGE))
    batch = run("batch", FakeOpenAIClient(answer, usage=USAGE, seed=3))

    assert sequential == batch
    assert {(row["input_tokens"], row["output_tokens"], row["cached_input_tokens"]) for row in batch} == {
        (2400, 850, 2304)}
    printed = capsys.readouterr().out
    assert printed.count("tokens: 7,200 input (6,912 cached), 2,550 output, over 3 of 3 rows") == 2


def test_no_totals_line_when_the_provider_reports_no_usage(capsys):
    run("sequential", FakeOpenAIClient("<FINAL_RANGE>[0, 1]</FINAL_RANGE>"))
    assert "tokens:" not in capsys.readouterr().out
    assert summarise_usage([{"input_tokens": None, "output_tokens": None}]) is None
