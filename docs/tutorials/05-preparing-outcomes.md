# Tutorial 5: preparing outcomes

PROPEL fits from your models' results: one 0/1 outcome per (instance, subject). Running the
models and scoring their answers happen outside PROPEL. This tutorial covers shaping those
results so they load, validate and join cleanly.

**You need:** PROPEL, run where `python -m propensity.examples` has put the example data in `examples/`.

## 1. From your evaluation log to long form

Suppose your harness logged one row per model answer:

```python
import pandas as pd

log = (pd.read_csv("examples/outcomes_long.csv")
       .rename(columns={"question_id": "item", "subject_id": "model", "outcome": "correct"}))
log["correct"] = log["correct"].map({1.0: True, 0.0: False})    # booleans, with NaN for no answer
print(log.head(3).to_string(index=False))
```

```text
  item      model correct
RA_000 demo-model    True
RA_001 demo-model    True
RA_002 demo-model   False
```

Rename to PROPEL's columns and write it out:

```python
from propensity import write_table

outcomes_file = log.rename(columns={"item": "question_id", "model": "subject_id", "correct": "outcome"})
write_table(outcomes_file, "out/outcomes.csv")
```

What each column must hold:
- **`question_id`:** exactly the instance ids you annotated.
- **`subject_id`:** any name for what produced the answers.
- **`outcome`:** `1`/`0`, `true`/`false`, or empty for no answer.

## 2. Load and validate

```python
from propensity import load_outcomes

outcomes = load_outcomes("out/outcomes.csv")
print(len(outcomes), "outcomes;", outcomes["outcome"].unique().tolist())
```

```text
477 outcomes; [1, 0]
```

The file has 480 rows, but the 3 without an answer were dropped. A missing answer is not a wrong
answer, so **never fill missing outcomes with 0**.

## 3. Wide form

One column per subject, named `{subject}_outcome`. Other columns are ignored.

```python
wide = outcomes.pivot(index="question_id", columns="subject_id", values="outcome")
wide.columns = [f"{subject}_outcome" for subject in wide.columns]
write_table(wide.reset_index(), "out/outcomes_wide.csv")

same = load_outcomes("out/outcomes_wide.csv")
assert len(same) == len(outcomes)
```

## 4. What is refused

Validation is strict, and every error names the offending rows.

**A probability is not an outcome.** Threshold it yourself, deliberately, before handing it
over:

```python
from propensity import ContractError

bad = outcomes.astype({"outcome": float})
bad.loc[0, "outcome"] = 0.7
try:
    load_outcomes(bad)
except ContractError as error:
    print(error)
```

```text
<DataFrame>: outcomes must be 0 or 1; got ('RA_000', 'demo-model', 0.7)
```

**Each (question_id, subject_id) pair once.** A model answered twice (resampling, retries) must
be reduced to one outcome first:

```python
try:
    load_outcomes(pd.concat([outcomes, outcomes.head(2)]))
except ContractError as error:
    print(error)
```

```text
<DataFrame>: duplicate (question_id, subject_id) ('RA_000', 'demo-model'), ('RA_001', 'demo-model')
```

**Missing columns:**

```python
try:
    load_outcomes(outcomes.drop(columns="outcome"))
except ContractError as error:
    print(error)
```

```text
<DataFrame>: missing column(s) ['outcome']
```

`load_outcomes` and `load_annotations` accept a DataFrame as well as a path, as above.

## 5. Make the ids match

The fit joins annotations and outcomes on `question_id`, and nothing else. Ids that differ in
the slightest way do not join:

| Annotations | Outcomes | Joins? |
|---|---|---|
| `RA_007` | `RA_007` | yes |
| `7` | `7.0` | yes: numeric ids are normalised |
| `RA_007` | `RA_7` | **no** |
| `RA_007` | `ra_007` | **no** |
| `007` | `7` | **no**: `"007"` is kept as text |

Check the join before fitting:

```python
import warnings
from propensity import join_annotations_outcomes, load_annotations

annotations = load_annotations("examples/annotations_RA.jsonl")
joined, report = join_annotations_outcomes(annotations, outcomes)
print(report["per_dimension"])
```

```text
{'RA': {'n_annotated': 117, 'n_joined': 117, 'yield': 1.0}}
```

Now break half of the ids, as a formatting mismatch would:

```python
broken = outcomes.copy()
odd = broken["question_id"].str[-1].isin(list("13579"))
broken.loc[odd, "question_id"] = broken.loc[odd, "question_id"].str.replace("RA_", "RA-")

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    _, report = join_annotations_outcomes(annotations, broken)
print(report["per_dimension"]["RA"])
print(caught[0].message)
```

```text
{'n_annotated': 117, 'n_joined': 59, 'yield': 0.5042735042735043}
low join yield, check that question_ids match. RA: 50% (59 of 117 annotated instances have outcomes)
```

`propel-fit` prints the yield first thing. A yield well below 100% is almost always an id
mismatch, not missing data.

## 6. Name subjects usefully

A subject is any opaque string. Encoding the condition in it keeps results readable:

| Subject id | Meaning |
|---|---|
| `gpt-4o` | the model, uninstructed |
| `gpt-4o_RA_+2` | the model under a system prompt inciting risk-aversion level `+2` |
| `gpt-4o@t0.7` | the model at temperature 0.7 |

Subject ids appear in plot filenames too. Characters that are not safe in a filename are
replaced, and `+` and `-` are kept.

## 7. Several dimensions, one file

One outcomes file can serve every dimension. Each outcome joins every annotation with its
`question_id`:
- **Different instances per dimension** (e.g. ids `RA_*` and `Ex_*`): each outcome counts
  towards its own dimension.
- **The same instance annotated on two dimensions:** its outcome counts towards both. That is
  intended, since one task can reveal several traits.

## 8. Annotation files from older tooling

`load_annotations` (and `propel-fit`) read older shapes directly:

```python
legacy = pd.DataFrame({"custom_id": ["RA_000", "RA_001"],
                       "propensity_lower": [-3, -2], "propensity_upper": [1, 3]})
print(load_annotations(legacy, dimension="RA").to_string(index=False))

wide_legacy = pd.DataFrame({"question_id": ["q1", "q2"], "RA_l": [-1, 0], "RA_u": [2, 3],
                            "Ex_l": [-3, -3], "Ex_u": [3, 0]})
print(load_annotations(wide_legacy).to_string(index=False))
```

```text
question_id dimension  lower  upper  parse_ok
     RA_000        RA   -3.0    1.0      True
     RA_001        RA   -2.0    3.0      True
question_id dimension  lower  upper  parse_ok
         q1        RA   -1.0    2.0      True
         q2        RA    0.0    3.0      True
         q1        Ex   -3.0    3.0      True
         q2        Ex   -3.0    0.0      True
```

A file without a `dimension` column needs the dimension given: `dimension="RA"` in Python, or
`--annotations RA=legacy.jsonl` for `propel-fit`. [Data formats](../data-formats.md#annotations)
lists every accepted shape.
