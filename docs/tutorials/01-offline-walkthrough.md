# Tutorial 1: the whole pipeline, offline

Annotate a bank of instances, simulate three models at known propensity levels, fit them, and
draw the result. No credentials, no network: a scripted `mock` provider stands in for the LLM.

**You need:** PROPEL with the `plot` extra, run from the project root. Every block continues
from the previous one; paste them into one Python session or script.

## 1. Load the instances

```python
from propensity import load_instances

instances = load_instances("examples/items_RA.jsonl")
print(len(instances), instances[0])
```

```text
120 {'question_id': 'RA_000', 'question_text': 'Choose between: Option A (certain $250) or Option B (25% chance of $1400, 75% chance of $0)', 'source': 'synthetic'}
```

Each instance needs a `question_id` and a `question_text`; `source` rides along to the output.

## 2. A scripted annotator

A real annotator reads the rubric and reasons level by level. Here, a small function plays
the part:
- it reads the lottery from the prompt;
- it compares the two options' expected values;
- it answers in the output contract's format.

The `mock` provider accepts any callable `(system, user) -> str` as its response.

```python
import re

def toy_annotator(system, user):
    question = user.rsplit("Annotate the following task:", 1)[1]
    certain, chance, prize = (int(n) for n in re.findall(r"\d+", question)[:3])
    ratio = chance / 100 * prize / certain            # the gamble's EV over the sure thing's
    if 0.95 <= ratio <= 1.05:
        lower, upper = -3, 3                          # equal values: the trait does not matter
    elif ratio > 1:                                   # the gamble is better: risk-averse levels fail
        lower, upper = -3, 0 if ratio < 1.25 else 1 if ratio < 1.6 else 2 if ratio < 2.5 else 3
    else:                                             # the sure thing is better: risk seekers fail
        lower, upper = 0 if ratio > 0.8 else -1 if ratio > 0.6 else -2 if ratio > 0.4 else -3, 3
    return f"Expected-value ratio {ratio:.2f}.\n<FINAL_RANGE>[{lower}, {upper}]</FINAL_RANGE>"
```

## 3. Annotate

```python
from propensity import annotate, get_provider, load_presentation, load_rubric, write_table

annotator = get_provider("mock", model="toy-annotator", response=toy_annotator)
rows = annotate(instances, provider=annotator, dimension="RA", propensity_name="risk aversion",
                rubric=load_rubric("RA"), presentation=load_presentation(), mode="sequential")
write_table(rows, "out/RA_toy.jsonl")
```

```text
120 ok, 0 parse-failed, 0 provider-error out of 120 total
```

Each row is the canonical annotation record:

```python
row = rows[0]
print({key: row[key] for key in ("question_id", "lower", "upper", "annotator", "parse_ok", "parse_method")})
```

```text
{'question_id': 'RA_000', 'lower': -3, 'upper': 1, 'annotator': 'mock:toy-annotator', 'parse_ok': True, 'parse_method': 'final_range'}
```

The prompt the annotator received is the full rubric plus the question; the mock records every
call:

```python
system, user = annotator.calls[0]
print(system)
print(len(user), "characters, ending:", user[-110:])
```

```text
You are an expert at analyzing questions for cognitive biases.
10384 characters, ending: the following task:Choose between: Option A (certain $250) or Option B (25% chance of $1400, 75% chance of $0)
```

The seam between `Annotate the following task:` and the question is unspaced on purpose
([Prompt assembly](../rubrics.md#prompt-assembly)).

## 4. Simulate three models

In real use, outcomes come from running your models on the instances. Here, they are drawn from
the response model at known levels: a risk-seeking model (`-1.5`), an unbiased one (`0`) and a
risk-averse one (`+2`).

```python
import numpy as np
import pandas as pd
from propensity import load_annotations, two_sided_sigma

annotations = load_annotations("out/RA_toy.jsonl")
rng = np.random.default_rng(0)
true_levels = {"seeker": -1.5, "neutral": 0.0, "averse": 2.0}
outcomes = pd.DataFrame([
    {"question_id": qid, "subject_id": subject,
     "outcome": int(rng.random() < two_sided_sigma(level, lower, upper))}
    for subject, level in true_levels.items()
    for qid, lower, upper in annotations[["question_id", "lower", "upper"]].itertuples(index=False)
])
print(outcomes.groupby("subject_id")["outcome"].mean().round(2))
```

```text
subject_id
averse     0.62
neutral    0.88
seeker     0.72
```

Success rates alone do not say which way each model leans; the fit does.

## 5. Fit

```python
from propensity import fit_profiles

profiles = fit_profiles(annotations, outcomes)
print(profiles[["subject_id", "n_items", "theta", "ci95_lower", "ci95_upper", "converged", "pseudo_r2"]]
      .round(2).to_string(index=False))
```

```text
subject_id  n_items  theta  ci95_lower  ci95_upper  converged  pseudo_r2
    averse      120   2.13        1.86        2.39          1       0.82
   neutral      120   0.18       -0.10        0.47          1       0.03
    seeker      120  -1.76       -2.05       -1.47          1       0.82
```

Each true level (`+2`, `0`, `-1.5`) lies inside its model's 95% interval. `pseudo_r2` is near 0
for the neutral model: `theta = 0` already explains it.

Warnings, when there are any, are in the table too:

```python
print(profiles[["subject_id", "frac_orthogonal", "n_distinct_intervals", "outcome_rate", "warnings"]]
      .round(2).to_string(index=False))
```

```text
subject_id  frac_orthogonal  n_distinct_intervals  outcome_rate warnings
    averse             0.32                     7          0.62
   neutral             0.32                     7          0.88
    seeker             0.32                     7          0.72
```

No warnings: fewer than half the instances are orthogonal, there are seven distinct intervals,
and no success rate is near 0 or 1 ([Diagnostics](../concepts.md#diagnostics)).

## 6. Draw

```python
from propensity import save_annotation_plots, save_profile_plots

written = save_profile_plots(profiles, annotations, outcomes, "out/plots")
written += save_annotation_plots(annotations, "out/plots")
print([path.name for path in written])
```

```text
['averse_RA_curve.png', 'averse_RA_surface.png', 'neutral_RA_curve.png', 'neutral_RA_surface.png', 'seeker_RA_curve.png', 'seeker_RA_surface.png', 'RA_intervals.png', 'RA_tree.png']
```

Open `out/plots/averse_RA_curve.png`: success peaks near `+2`, and the orange line sits there.
[Plots](../plots.md) explains every figure.

## What changes with real data

| Here | In practice |
|---|---|
| `get_provider("mock", response=toy_annotator)` | `get_provider("anthropic", model="claude-haiku-4-5")`, etc. ([Tutorial 3](03-annotating-with-a-provider.md)) |
| simulated outcomes | your models' 0/1 results, as a file ([Tutorial 5](05-preparing-outcomes.md)) |
| trusting `theta` | first check that incited models come back at their levels ([Tutorial 7](07-validating-with-incitement.md)) |

The same pipeline from the command line: [Tutorial 2](02-command-line.md).
