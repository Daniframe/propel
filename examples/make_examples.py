"""Build the synthetic example files used by the tutorials.

Deterministic: running it again reproduces the files exactly.

    python examples/make_examples.py

Files written next to this script:

    items_RA.jsonl          120 risk-aversion instances (lotteries), ready to annotate
    annotations_RA.jsonl    demand intervals for those instances, in the canonical format
    outcomes_long.csv       0/1 outcomes for four subjects, long form
    outcomes_wide.csv       the same outcomes, wide form

The intervals come from a fixed rule on each lottery's expected-value ratio, not from an LLM,
and the outcomes are simulated from the response model at known propensity levels:

    demo-model          theta = +0.7   (an uninstructed subject)
    demo-model_RA_-2    theta = -2.0   (incited to level -2)
    demo-model_RA_0     theta =  0.0   (incited to level 0)
    demo-model_RA_+2    theta = +2.0   (incited to level +2)
"""

import csv
import json
import random
from pathlib import Path

import numpy as np

from propensity import two_sided_sigma

HERE = Path(__file__).resolve().parent
N_ITEMS = 120
SUBJECTS = {"demo-model": 0.7, "demo-model_RA_-2": -2.0, "demo-model_RA_0": 0.0,
            "demo-model_RA_+2": 2.0}
UNPARSED = {"RA_017", "RA_058", "RA_101"}   # annotations that "failed to parse"
NO_RESPONSE = {"RA_004", "RA_033", "RA_090"}  # demo-model produced no answer for these


def make_items(rng):
    items = []
    for i in range(N_ITEMS):
        certain = rng.randrange(50, 500, 10)
        chance = rng.choice([10, 20, 25, 40, 50, 60, 75, 80, 90])
        ratio = rng.choice([0.3, 0.5, 0.7, 0.85, 1.0, 1.15, 1.4, 2.0, 3.0])
        prize = max(10, round(certain * ratio * 100 / chance / 10) * 10)
        items.append({
            "question_id": f"RA_{i:03d}",
            "question_text": (f"Choose between: Option A (certain ${certain}) or Option B "
                              f"({chance}% chance of ${prize}, {100 - chance}% chance of $0)"),
            "source": "synthetic",
            "ev_ratio": round(chance / 100 * prize / certain, 3),
        })
    return items


def interval(ratio):
    """The rule standing in for an annotator. RA's positive pole is risk aversion."""
    if 0.95 <= ratio <= 1.05:
        return -3, 3                      # equal expected values: any preference is fine
    if ratio > 1:                         # the gamble is better: risk-averse levels fail first
        upper = 0 if ratio < 1.25 else 1 if ratio < 1.6 else 2 if ratio < 2.5 else 3
        return -3, upper
    lower = 0 if ratio > 0.8 else -1 if ratio > 0.6 else -2 if ratio > 0.4 else -3
    return lower, 3                       # the sure thing is better: risk seekers fail first


def main():
    rng = random.Random(7)
    items = make_items(rng)
    with open(HERE / "items_RA.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for item in items:
            f.write(json.dumps({k: item[k] for k in ("question_id", "question_text", "source")}) + "\n")

    bounds = {}
    with open(HERE / "annotations_RA.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for item in items:
            lower, upper = interval(item["ev_ratio"])
            bounds[item["question_id"]] = (lower, upper)
            row = {"question_id": item["question_id"], "dimension": "RA", "lower": lower,
                   "upper": upper, "annotator": "synthetic:ev-rule",
                   "explanation": (f"Synthetic interval from the expected-value ratio "
                                   f"{item['ev_ratio']}.\n<FINAL_RANGE>[{lower}, {upper}]</FINAL_RANGE>"),
                   "parse_ok": True, "error": None}
            if item["question_id"] in UNPARSED:
                row.update(lower=None, upper=None, parse_ok=False,
                           explanation="The response ended before giving a range.")
            f.write(json.dumps(row) + "\n")

    draws = np.random.default_rng(11)
    table = {}
    for subject, theta in SUBJECTS.items():
        for item in items:
            qid = item["question_id"]
            p = float(np.clip(two_sided_sigma(theta, *bounds[qid]), 0, 1))
            outcome = int(draws.random() < p)
            table[qid, subject] = "" if subject == "demo-model" and qid in NO_RESPONSE else outcome

    with open(HERE / "outcomes_long.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["question_id", "subject_id", "outcome"])
        for subject in SUBJECTS:
            for item in items:
                writer.writerow([item["question_id"], subject, table[item["question_id"], subject]])

    with open(HERE / "outcomes_wide.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["question_id", *(f"{subject}_outcome" for subject in SUBJECTS)])
        for item in items:
            writer.writerow([item["question_id"], *(table[item["question_id"], s] for s in SUBJECTS)])
    print(f"wrote {N_ITEMS} items, their annotations and outcomes for {len(SUBJECTS)} subjects "
          f"to {HERE}")


if __name__ == "__main__":
    main()
