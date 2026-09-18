# Tutorial 2: the command line

Both commands, end to end, on the bundled example data. No credentials: annotation uses the
`mock` provider.

**You need:** PROPEL with the `plot` extra, and the example data:

```bash
python -m propensity.examples      # copies it into ./examples
```

## The example data

| File | Holds |
|---|---|
| `examples/items_RA.jsonl` | 120 risk-aversion instances (lotteries) |
| `examples/annotations_RA.jsonl` | their demand intervals, in the canonical format; 3 failed to parse |
| `examples/outcomes_long.csv` | 0/1 outcomes for four subjects, long form; 3 missing |
| `examples/outcomes_wide.csv` | the same outcomes, wide form |

The four subjects were simulated at known levels: `demo-model` at `+0.7`, and three incited
copies, `demo-model_RA_-2`, `demo-model_RA_0` and `demo-model_RA_+2`.

`python -m propensity.examples.generate examples` rebuilds all four files, identically.

## 1. Annotate, one call at a time

```bash
propel-annotate run --instances examples/items_RA.jsonl --dimension RA --out out/RA_mock.jsonl \
    --provider mock --model mock-1
```

```text
annotated 25/120
annotated 50/120
annotated 75/120
annotated 100/120
annotated 120/120
120 ok, 0 parse-failed, 0 provider-error out of 120 total
wrote out/RA_mock.jsonl
```

What happened:
- **The trait's name** in the prompt, "risk aversion", and the rubric version, `v1`, came from
  the dimension catalogue ([Dimensions](../dimensions.md)).
- **The rubric** was the packaged `RA_v1.md`.
- **The answers.** The mock answered every instance with its default response,
  `<FINAL_RANGE>[-1, +2]</FINAL_RANGE>`, so every interval is `[-1, 2]`.

```python
from propensity import read_table

rows = read_table("out/RA_mock.jsonl")
print(rows.columns.tolist())
print(rows[["question_id", "lower", "upper", "annotator", "parse_ok"]].head(3).to_string(index=False))
```

```text
['question_id', 'dimension', 'lower', 'upper', 'annotator', 'explanation', 'parse_ok', 'error', 'parse_error', 'parse_method', 'question_text', 'source']
question_id lower upper   annotator parse_ok
     RA_000    -1     2 mock:mock-1     True
     RA_001    -1     2 mock:mock-1     True
     RA_002    -1     2 mock:mock-1     True
```

`--out` also takes `.csv`.

## 2. Annotate as a batch

A batch-capable provider can take all instances at once, at about half the price. The mock
rehearses it:
- `batch=true` gives the batch-capable mock;
- `state_path` keeps the submitted batch between commands, as a real provider's servers do.

```bash
propel-annotate submit --instances examples/items_RA.jsonl --dimension RA --out out/RA_batch.jsonl \
    --provider mock --model mock-1 --provider-option batch=true --provider-option state_path=out/mock_state.json
propel-annotate status --job out/RA_batch.jsonl.job.json
propel-annotate fetch --job out/RA_batch.jsonl.job.json
```

```text
submitted batch mock-batch-1 with 120 requests
wrote out/RA_batch.jsonl.job.json
next: propel-annotate status --job out/RA_batch.jsonl.job.json
batch mock-batch-1: completed
  120 requests for RA via mock:mock-1, submitted 2026-09-18T07:57:45+00:00
  next: propel-annotate fetch --job out/RA_batch.jsonl.job.json
120 ok, 0 parse-failed, 0 provider-error out of 120 total
wrote out/RA_batch.jsonl
```

The rows are the same as step 1's; which path ran never changes the result.
[Tutorial 4](04-batch-annotation.md) covers batches in depth.

## 3. Fit

The mock's intervals are all identical, which is useless for fitting. Fit the example intervals
instead:

```bash
propel-fit --annotations examples/annotations_RA.jsonl --outcomes examples/outcomes_long.csv \
    --out out/profiles.csv
```

```text
INFO examples/outcomes_long.csv: dropped 3 missing outcomes (not counted as failures)
join yield RA: 117/117 annotated instances have outcomes (100%)
3 annotation rows were unusable (failed to parse, or a null bound)
3 outcome question_ids have no annotation
fitted 4 of 4 (subject, dimension) cells
wrote out/profiles.csv
```

Read the report top down:

| Line | Meaning |
|---|---|
| `dropped 3 missing outcomes` | three instances with no response from `demo-model`: dropped, not counted as failures |
| `join yield RA: 117/117` | every usable annotation found outcomes. Anything below 90% triggers a warning |
| `3 annotation rows were unusable` | the three instances that failed to parse, left out of the fit |
| `3 outcome question_ids have no annotation` | those same three, seen from the outcomes side |
| `fitted 4 of 4` | no cell was skipped |

```python
import pandas as pd

profiles = pd.read_csv("out/profiles.csv")
print(profiles[["subject_id", "theta", "ci95_lower", "ci95_upper", "converged", "warnings"]]
      .round(2).to_string(index=False))
```

```text
      subject_id  theta  ci95_lower  ci95_upper  converged  warnings
      demo-model   0.42        0.13        0.71          1       NaN
demo-model_RA_+2   1.89        1.60        2.17          1       NaN
demo-model_RA_-2  -2.06       -2.32       -1.79          1       NaN
 demo-model_RA_0   0.09       -0.21        0.38          1       NaN
```

The incited copies come back near `+2`, `-2` and `0`. `demo-model`, simulated at `+0.7`, comes
back at `0.42`, with `0.7` just inside its interval.

## 4. The same fit from wide outcomes

```bash
propel-fit --annotations examples/annotations_RA.jsonl --outcomes examples/outcomes_wide.csv \
    --out out/profiles_wide.csv
```

```python
wide = pd.read_csv("out/profiles_wide.csv")
assert wide["theta"].round(6).tolist() == profiles["theta"].round(6).tolist()
```

## 5. Choose what to fit

```bash
propel-fit --annotations examples/annotations_RA.jsonl --outcomes examples/outcomes_long.csv \
    --out out/incited.csv --subjects demo-model_RA_-2 demo-model_RA_+2 --min-items 100
propel-fit --annotations examples/annotations_RA.jsonl --outcomes examples/outcomes_long.csv \
    --out out/published.csv --likelihood product --no-robust
```

| Flag | Effect |
|---|---|
| `--subjects`, `--dimensions` | fit only these cells |
| `--min-items N` | record, but skip, cells with fewer joined instances |
| `--likelihood product --no-robust` | the original published procedure; only to reproduce published numbers |

## 6. Plots

```bash
propel-fit --annotations examples/annotations_RA.jsonl --outcomes examples/outcomes_long.csv \
    --out out/profiles.csv --plots out/plots
```

This adds, after the report, `wrote 10 plots to out/plots`:
- a curve and a surface for each of the four subjects;
- `RA_intervals.png` and `RA_tree.png` for the dimension.

## 7. Your own settings file

Every setting has a default. A YAML file overrides them, and flags override the file.

```python
from pathlib import Path

Path("out/strict.yaml").write_text(
    "propensity:\n"
    "  robust: true\n"
    "  restart_range: [-4.0, 4.0]\n"
    "profiles:\n"
    "  min_items: 60\n", encoding="utf-8")
```

```bash
propel-fit --annotations examples/annotations_RA.jsonl --outcomes examples/outcomes_long.csv \
    --out out/strict.csv --config out/strict.yaml
```

[Configuration](../configuration.md) lists every key.

## 8. Errors

Bad input is reported on one line, and the command exits with code 2:

```bash
propel-fit --annotations examples/items_RA.jsonl --outcomes examples/outcomes_long.csv --out out/x.csv  # exits 2
```

```text
error: examples/items_RA.jsonl: no demand-interval columns; expected lower/upper, propensity_lower/propensity_upper, lower_bound/upper_bound or {DIM}_l/{DIM}_u
```

[Troubleshooting](11-troubleshooting.md) maps every message to its fix.
