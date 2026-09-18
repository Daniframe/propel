"""The whole pipeline offline: annotate with the mock, then fit simulated outcomes.

This is the validation with incited models, with the inciting replaced by simulation: outcomes
are drawn for a subject sitting at a known propensity level, and the fit has to find it again.
It exercises annotation, the annotation rows, the loaders, the join and the fit in one pass,
with no network and nothing spent.
"""

import re
import warnings

import numpy as np
import pytest

from propensity import (
    fit_profiles,
    load_annotations,
    load_outcomes,
    two_sided_sigma,
    write_table,
)
from propensity.annotation import annotate, load_presentation, load_rubric
from propensity.providers import get_provider

INTERVAL_IN_TEXT = re.compile(r"\[(-?\d+), (-?\d+)\]")
TRUE_THETA = {"steady": -1.5, "reckless": 1.0}


def instances(n=200, seed=0):
    """Instances whose text carries the interval an ideal annotator would return."""
    rng = np.random.default_rng(seed)
    lower = rng.integers(-3, 4, n)
    upper = np.array([rng.integers(low, 4) for low in lower])
    return [{"question_id": f"RA_{i}", "question_text": f"Item {i}: choose an option [{low}, {high}]"}
            for i, (low, high) in enumerate(zip(lower, upper))]


def annotator_reading_the_text(system, user):
    """A mock annotator that reads the interval out of the question and answers the contract."""
    low, high = INTERVAL_IN_TEXT.findall(user)[-1]
    return f"Working outward from 0...\n<FINAL_RANGE>[{low}, {high}]</FINAL_RANGE>"


def test_annotate_then_fit_recovers_the_level_each_subject_was_simulated_at(tmp_path, capsys):
    provider = get_provider("mock", model="scripted", response=annotator_reading_the_text)
    rubrics = tmp_path / "rubrics"
    (rubrics / "RA").mkdir(parents=True)
    (rubrics / "RA" / "RA_v1.md").write_text("# RISK AVERSION PROPENSITY\n", encoding="utf-8")
    (rubrics / "presentation.md").write_text("</rubric>\nAnnotate the following task:",
                                             encoding="utf-8", newline="")

    rows = annotate(instances(), provider=provider, dimension="RA", propensity_name="risk aversion",
                    rubric=load_rubric("RA", rubrics), presentation=load_presentation(rubrics),
                    mode="auto", max_workers=4)
    assert capsys.readouterr().out.strip() == "200 ok, 0 parse-failed, 0 provider-error out of 200 total"

    annotations_path = write_table(rows, tmp_path / "RA_annotations.jsonl")
    annotations = load_annotations(annotations_path)
    assert len(annotations) == 200 and annotations["parse_ok"].all()

    # Outcomes for two subjects at known levels, drawn from the model the fit will invert.
    rng = np.random.default_rng(7)
    outcome_rows = []
    for subject, theta in TRUE_THETA.items():
        for _, row in annotations.iterrows():
            p = np.clip(two_sided_sigma(theta, row["lower"], row["upper"]), 0.0, 1.0)
            outcome_rows.append({"question_id": row["question_id"], "subject_id": subject,
                                 "outcome": int(rng.binomial(1, p))})
    outcomes = load_outcomes(write_table(outcome_rows, tmp_path / "outcomes.csv"))

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a clean run warns about nothing
        profiles = fit_profiles(annotations, outcomes)

    assert profiles.attrs["join_report"]["per_dimension"]["RA"]["yield"] == 1.0
    assert len(profiles) == 2
    for subject, theta in TRUE_THETA.items():
        row = profiles[profiles.subject_id == subject].iloc[0]
        assert row.n_items == 200
        assert abs(row.theta - theta) < 0.25, f"{subject}: {row.theta:+.3f} against {theta:+.3f}"
        assert row.ci95_lower < row.theta < row.ci95_upper
        assert row.skip_reason is None
