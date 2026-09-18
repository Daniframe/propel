# Tutorial 6: fitting and diagnostics

Fit propensity levels, read the profile table, recognise an item bank that cannot measure, and
tune the fit.

**You need:** PROPEL, run where `python -m propensity.examples` has put the example data in `examples/`.

## 1. Fit every subject

```python
import warnings
from propensity import fit_profiles, load_annotations, load_outcomes, profile_vector

annotations = load_annotations("examples/annotations_RA.jsonl")
outcomes = load_outcomes("examples/outcomes_long.csv")
profiles = fit_profiles(annotations, outcomes)
print(profiles[["subject_id", "dimension", "n_items", "theta", "se", "ci95_lower", "ci95_upper",
                "converged", "pseudo_r2"]].round(3).to_string(index=False))
```

```text
      subject_id dimension  n_items  theta    se  ci95_lower  ci95_upper  converged  pseudo_r2
      demo-model        RA      114  0.422 0.147       0.134       0.710          1      0.135
demo-model_RA_+2        RA      117  1.886 0.144       1.604       2.168          1      0.770
demo-model_RA_-2        RA      117 -2.056 0.136      -2.322      -1.790          1      0.821
 demo-model_RA_0        RA      117  0.086 0.149      -0.205       0.378          1      0.006
```

| Column | Read it as |
|---|---|
| `theta` | the level, on `-3 … +3`. For `RA`, positive means risk-averse |
| `ci95_lower`, `ci95_upper` | a 95% interval. Two subjects differ when their intervals do not overlap |
| `converged` | 1 when the optimiser converged. An interval around a fit that did not converge means nothing |
| `pseudo_r2` | improvement over an unbiased agent. Near 0 means `theta = 0` explains the data about as well |
| `n_items` | joined instances. `demo-model` has 114, because 3 of its outcomes are missing |

One subject's profile, as a dictionary:

```python
print({dimension: round(theta, 2) for dimension, theta in profile_vector(profiles, "demo-model_RA_+2").items()})
```

```text
{'RA': 1.89}
```

## 2. One cell by hand

`fit_profiles` is a loop over cells around `fit_theta`. To fit one cell yourself:

```python
from propensity import fit_diagnostics, fit_theta, join_annotations_outcomes

joined, report = join_annotations_outcomes(annotations, outcomes)
cell = joined[(joined["subject_id"] == "demo-model_RA_+2") & (joined["dimension"] == "RA")]
demands, success = cell[["lower", "upper"]].to_numpy(), cell["outcome"].to_numpy()

fit = fit_theta(demands, success)
print({key: round(value, 3) for key, value in fit.items()})
print(fit_diagnostics(demands, success, fit=fit))
```

```text
{'theta_hat': 1.886, 'se': 0.144, 'ci95_lower': 1.604, 'ci95_upper': 2.168, 'convergence': 1.0, 'reference_ll': -193.948, 'gof': -44.568, 'pseudo_r2': 0.77, 'n_attempts': 1, 'n_converged': 1, 'restart_theta_std': 0.0}
{'n_items': 117, 'frac_orthogonal': 0.3333333333333333, 'n_distinct_intervals': 7, 'outcome_rate': 0.6923076923076923, 'refuse': False, 'warnings': []}
```

`n_attempts` is 1: the first attempt converged, so no restarts were needed.

## 3. Banks that cannot measure

A fit always returns a number. The diagnostics say whether to believe it. Each case below builds
a deliberately bad bank.

```python
import numpy as np
import pandas as pd
from propensity import two_sided_sigma

rng = np.random.default_rng(1)

def simulate(intervals, theta, subject="model"):
    """Annotations and outcomes for a bank of (lower, upper) intervals, at a known theta."""
    ids = [f"q{i}" for i in range(len(intervals))]
    bank = pd.DataFrame({"question_id": ids, "dimension": "RA",
                         "lower": [lo for lo, _ in intervals], "upper": [hi for _, hi in intervals]})
    results = pd.DataFrame({"question_id": ids, "subject_id": subject, "outcome": [
        int(rng.random() < two_sided_sigma(theta, lo, hi)) for lo, hi in intervals]})
    return bank, results

def fit_quietly(bank, results, **settings):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        row = fit_profiles(bank, results, **settings).iloc[0]
    summary = row[["n_items", "theta", "converged", "skip_reason", "warnings"]].to_dict()
    return {**summary, "theta": round(summary["theta"], 2)}
```

**Mostly orthogonal.** `[-3, +3]` instances are solved at every level, so they say nothing
about `theta`:

```python
print(fit_quietly(*simulate([(-3, 3)] * 95 + [(0, 1)] * 5, theta=1.0)))
```

```text
{'n_items': 100, 'theta': nan, 'converged': None, 'skip_reason': '95% of instances are [-3, +3]; theta is not identified', 'warnings': '95% of items are [-3, +3]; theta is not identified; only 2 distinct intervals; success rate 96.0% is near-degenerate'}
```

- **Above 90% orthogonal**, the cell is refused: it keeps its row, but gets no estimate.
- **Between 50% and 90%**, it is fitted, with a warning.

**Too little variety.** A bank where every interval is the same cannot locate `theta`. This is
what a broken annotator produces: the `mock` provider gives every instance `[-1, 2]`.

```python
print(fit_quietly(*simulate([(-1, 2)] * 100, theta=1.5)))
```

```text
{'n_items': 100, 'theta': 0.5, 'converged': 1, 'skip_reason': None, 'warnings': 'only 1 distinct intervals; fit explains the data worse than theta = 0 (pseudo_r2 = -6.01)'}
```

The fit converged to the midpoint of the only interval, whatever the subject's level: the true
`theta` here is 1.5. `converged` is 1, and only the warnings say the number is meaningless.

**Degenerate outcomes.** A subject that succeeds everywhere has no interior maximum:

```python
bank, results = simulate([(lo, 3) for lo in rng.integers(-3, 1, 100)], theta=0.0)
results["outcome"] = 1
print(fit_quietly(bank, results))
```

```text
{'n_items': 100, 'theta': 1.07, 'converged': 1, 'skip_reason': None, 'warnings': 'only 4 distinct intervals; success rate 100.0% is near-degenerate'}
```

The estimate drifts somewhere the likelihood is flat. Restarts are not spent on degenerate
data.

**Too few instances.**

```python
bank, results = simulate([(lo, hi) for lo, hi in rng.integers(-3, 4, (40, 2)) if lo <= hi], theta=0.5)
print(fit_quietly(bank, results))
print(fit_quietly(bank, results, min_items=10))
```

```text
{'n_items': 23, 'theta': nan, 'converged': None, 'skip_reason': 'only 23 joined instances, below min_items=30', 'warnings': 'only 23 items; the fit is unstable below 50'}
{'n_items': 23, 'theta': 0.52, 'converged': 1, 'skip_reason': None, 'warnings': 'only 23 items; the fit is unstable below 50'}
```

Of the 40 random pairs, only the 23 with `lower <= upper` are intervals.
- **Below `min_items`** (default 30), a cell is recorded with a `skip_reason` and no estimate.
- **Above it but below 50 instances**, it is fitted, with a warning.

The full list of checks and thresholds: [Diagnostics](../concepts.md#diagnostics).

## 4. Tune the fit

Every setting is a keyword argument of `fit_profiles`, passed on to `fit_theta`. All but
`max_retries` and `patience` are also keys in `config/modelling.yaml` for `propel-fit`
([Configuration](../configuration.md#configmodellingyaml)).

```python
settings = {
    "min_items": 30,                # fewer joined instances: record, do not fit
    "robust": True,                 # restart when the first attempt does not converge
    "restart_range": (-5.0, 5.0),   # restarts stay inside this range
    "max_retries": 20,              # most restarts
    "patience": 2,                  # stop after this many unproductive restarts in a row
    "maxiter": 500,                 # iterations per attempt
    "likelihood": "sum",            # "product" only to reproduce published numbers
}
tuned = fit_profiles(annotations, outcomes, **settings)
```

`k`, `min_width` and `rho` change the response model itself. Leave them at their defaults
unless you are studying the model: estimates fitted under different values are not comparable.

**Reproducing published numbers.** The original pipeline used the product likelihood without
restarts:

```python
published = fit_profiles(annotations, outcomes, likelihood="product", robust=False)
print(f"largest difference: {(published['theta'] - profiles['theta']).abs().max():.1e}")
```

```text
largest difference: 2.5e-08
```

On a bank of this size the two agree to many decimals. The product form underflows on banks of
several hundred instances, which is why `sum` is the default.

## 5. Profiles across dimensions

Each dimension has its own annotations; the outcomes file can be shared. Here a second,
synthetic dimension reuses the same intervals, to show the shape of the result:

```python
ex = annotations.assign(dimension="Ex")
both = pd.concat([annotations, ex], ignore_index=True)
profile_table = fit_profiles(both, outcomes)
wide = profile_table.pivot(index="subject_id", columns="dimension", values="theta").round(2)
print(wide)
```

```text
dimension           Ex    RA
subject_id
demo-model        0.42  0.42
demo-model_RA_+2  1.89  1.89
demo-model_RA_-2 -2.06 -2.06
demo-model_RA_0   0.09  0.09
```

With real data each dimension has different instances, and so different levels.
`profile_vector(profile_table, "demo-model")` gives `{"Ex": …, "RA": …}` for radar or
parallel-coordinate plots.

## 6. Saving

```python
from propensity import write_table

write_table(profiles, "out/profiles.csv")        # or .jsonl
print(profiles.attrs["join_report"]["per_dimension"])
```

```text
{'RA': {'n_annotated': 117, 'n_joined': 117, 'yield': 1.0}}
```

The CSV has the columns listed in [Data formats](../data-formats.md#profiles).
`profiles.attrs["join_report"]` holds the join report in memory; it is not written to the file.
