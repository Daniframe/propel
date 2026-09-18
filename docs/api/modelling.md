# `propensity.modelling`

From files to fitted propensity levels.

- [Files and validation](#files-and-validation) (`modelling.io`)
- [The response model](#two_sided_sigma) (`modelling.model`)
- [The fit](#fit_theta) (`modelling.mle`)
- [Profiles](#fit_profiles) (`modelling.profiles`)
- [Curves](#build_empirical_curve) (`modelling.curves`)
- [Surfaces](#surfaces) (`modelling.surfaces`)
- Figures: [plotting](plotting.md)

## Files and validation

`propensity.modelling.io`. Formats and rules in detail: [Data formats](../data-formats.md).

### `read_table`, `write_table`

```python
read_table(path) -> pd.DataFrame
write_table(data, path) -> Path
```

| Function | Does |
|---|---|
| `read_table` | reads `.jsonl` (values keep their JSON types) or `.csv` (every cell as a string) |
| `write_table` | writes a DataFrame or a list of dicts as `.jsonl` (NaN becomes `null`, UTF-8, non-ASCII kept) or `.csv`; creates parent directories; returns the path |

Any other extension raises `ContractError`.

### `load_instances`

```python
load_instances(path) -> list[dict]
```

The instances to annotate, as dicts:
- `question_id` is a string, generated as `{stem}_{row}` when the file has none;
- `question_text` is required;
- every other field is kept.

**Raises** `ContractError` for:
- mixed presence of ids, or an empty id;
- a missing or empty text;
- a duplicate id;
- an empty file;
- an unsupported extension.

### `load_annotations`

```python
load_annotations(source, *, dimension=None) -> pd.DataFrame
```

Annotations in any accepted shape ([list](../data-formats.md#what-load_annotations-and-propel-fit-read)),
normalised to `question_id · dimension · lower · upper · parse_ok`.

| Parameter | Meaning |
|---|---|
| `source` | a path, or a DataFrame |
| `dimension` | for a file without a `dimension` column, the dimension of every row (then required); otherwise, keep only this dimension |

**Raises** `ContractError` for:
- no recognisable bound columns;
- a missing dimension;
- a missing id;
- a non-numeric bound or an unreadable `parse_ok`;
- a usable interval outside `-3 ≤ lower ≤ upper ≤ 3`;
- a duplicate (`question_id`, `dimension`);
- a `dimension=` filter that matches nothing.

Rows that failed to parse are kept, with `parse_ok` false.

### `load_outcomes`

```python
load_outcomes(source) -> pd.DataFrame
```

Outcomes in long or wide form, normalised to `question_id · subject_id · outcome` (int 0/1).
Missing outcomes are dropped and logged, never counted as failures.

**Raises** `ContractError` for:
- a value other than 0/1 (probabilities included);
- a duplicate (`question_id`, `subject_id`);
- a missing id;
- neither form's columns present.

### `join_annotations_outcomes`

```python
join_annotations_outcomes(annotations, outcomes, *, min_items=50, min_yield=0.9) -> tuple[pd.DataFrame, dict]
```

Drops unusable annotations (`parse_ok` false or a null bound), then inner-joins on
`question_id`.

**Returns** `(joined, report)`:
- `joined` has columns `question_id · dimension · lower · upper · subject_id · outcome`;
- `report` holds `n_annotation_rows`, `n_unusable`, `per_dimension`
  (`n_annotated`, `n_joined`, `yield`), `n_outcome_ids`, `n_unmatched_outcome_ids` and
  `cell_sizes`.

**Warns** `DataWarning`:
- when any dimension's yield is below `min_yield`;
- when any (subject, dimension) cell has fewer than `min_items` instances;
- when there is nothing usable to join.

**Raises** `ContractError` for missing columns or duplicate keys.

## `two_sided_sigma`

`propensity.modelling.model`.

```python
two_sided_sigma(x, b_l, b_u, k1=1.0, k2=1.0, min_width=0.1, rho=2.0)
```

The response model: the probability that an agent at level `x` succeeds on an instance with
interval `[b_l, b_u]`. It is bell-shaped, in `[0, 1]`, and exactly 1 at the midpoint.

| Parameter | Meaning |
|---|---|
| `x` | level(s); scalar or array |
| `b_l`, `b_u` | one interval (scalars), `b_l ≤ b_u` |
| `k1`, `k2` | base slopes of the lower and upper sides; the fit uses `k1 == k2` |
| `min_width` | narrower intervals are widened symmetrically outwards to this width |
| `rho` | steepness added as the interval narrows: slope `= k + e^(rho/w) − 1` |

```python
import numpy as np
from propensity import two_sided_sigma

two_sided_sigma(0.5, -1, 2)                        # 1.0 at the midpoint
two_sided_sigma(np.linspace(-3, 3, 7), 0, 0)       # a zero-width interval: sharp, finite
```

## `neg_log_likelihood`

`propensity.modelling.mle`.

```python
neg_log_likelihood(theta, demands, success, k=1.0, *, likelihood="sum", min_width=0.1, rho=2.0)
```

The negative log-likelihood of `theta` given intervals and outcomes, with probabilities
clipped to `[1e-10, 1 − 1e-10]`:
- **`likelihood="sum"`** is the stable form: a sum of logs;
- **`"product"`** multiplies the probabilities first, and underflows to `inf` for a few hundred
  items. It exists only to reproduce published numbers exactly.

## `fit_theta`

```python
fit_theta(demands, success, *, k=1.0, x_init=None, n_bins=20, lowess_frac=0.4, maxiter=500,
          robust=True, max_retries=20, patience=2, restart_range=(-5.0, 5.0),
          likelihood="sum", min_width=0.1, rho=2.0) -> dict
```

Fits one subject's `theta` on one dimension by maximum likelihood.

| Parameter | Default | Meaning |
|---|---|---|
| `demands` | required | `(N, 2)` intervals |
| `success` | required | `(N,)` outcomes, 0/1 only |
| `k` | `1.0` | base slope (`k_default` in the config file) |
| `x_init` | the curve's peak | starting point; default is the argmax of the LOWESS-smoothed success-by-centre curve (the median centre when there are fewer than two populated bins) |
| `n_bins`, `lowess_frac` | `20`, `0.4` | for that curve |
| `maxiter` | `500` | iterations per attempt |
| `robust` | `True` | restart when the first attempt does not converge |
| `max_retries` | `20` | most restarts |
| `patience` | `2` | stop after this many restarts in a row that do not improve |
| `restart_range` | `(-5, 5)` | bounds for restarts |
| `likelihood` | `"sum"` | `"sum"` or `"product"` |
| `min_width`, `rho` | `0.1`, `2.0` | the response model's |

**Algorithm:**
1. **First attempt.** Unbounded BFGS from `x_init`.
2. **Restarts,** only if the first attempt did not converge, `robust` is set, and the outcomes
   are not all identical:
   - bounded L-BFGS-B attempts, starting at points spread outwards from `x_init`, alternating
     sides;
   - an attempt *qualifies* if it converged strictly inside `restart_range`;
   - the search stops at the first qualifying attempt, or after `patience` unproductive ones;
   - a restart replaces the first attempt only if it qualifies **and** fits better. Estimates
     are never averaged across attempts.
3. **Uncertainty.** `se = sqrt(inverse Hessian)`, and `ci95 = theta ± 1.96·se`. `se` is NaN if
   the curvature is not positive.

**Returns:**

| Key | Meaning |
|---|---|
| `theta_hat` | the estimate |
| `se`, `ci95_lower`, `ci95_upper` | uncertainty |
| `convergence` | `1.0` or `0.0` |
| `reference_ll` | log-likelihood at `theta = 0` |
| `gof` | log-likelihood at `theta_hat` |
| `pseudo_r2` | `1 − gof / reference_ll` |
| `n_attempts`, `n_converged`, `restart_theta_std` | with `robust=True`: attempts made, how many converged, the spread of their estimates |

**Raises** `ValueError` for:
- wrong shapes, or no items;
- NaN bounds;
- outcomes other than 0/1;
- an unknown `likelihood`.

```python
from propensity import fit_theta

fit = fit_theta(demands, success)
print(f"{fit['theta_hat']:.2f} [{fit['ci95_lower']:.2f}, {fit['ci95_upper']:.2f}]",
      "converged" if fit["convergence"] else "NOT converged")
```

## `fit_diagnostics`

```python
fit_diagnostics(demands, success, fit=None) -> dict
```

The checks that catch unusable item banks.

| Key | Meaning |
|---|---|
| `n_items` | instances |
| `frac_orthogonal` | share with `lower ≤ −3` and `upper ≥ 3` |
| `n_distinct_intervals` | distinct `(lower, upper)` pairs |
| `outcome_rate` | share of successes |
| `refuse` | `True` when `frac_orthogonal > 0.9`: `theta` is not identified |
| `warnings` | list of messages |

A message is added to `warnings` for each of:
- fewer than 50 items;
- more than 50% orthogonal;
- fewer than 5 distinct intervals;
- a success rate outside 5–95%;
- with `fit` given: a fit that did not converge;
- with `fit` given: a negative `pseudo_r2`.

Constants in `modelling.mle`: `MIN_ITEMS_WARN = 50`, `ORTHOGONAL_WARN = 0.5`,
`ORTHOGONAL_REFUSE = 0.9`, `MIN_DISTINCT_INTERVALS = 5`, `OUTCOME_RATE_RANGE = (0.05, 0.95)`,
`LIKELIHOODS = ("sum", "product")`, `P_CLIP = 1e-10`.

## `fit_profiles`

`propensity.modelling.profiles`.

```python
fit_profiles(annotations, outcomes, *, subjects=None, dimensions=None, min_items=30, **fit_kwargs) -> pd.DataFrame
```

Fits every (subject, dimension) cell.

| Parameter | Default | Meaning |
|---|---|---|
| `annotations` | required | tidy annotations (`question_id`, `dimension`, `lower`, `upper`, optional `parse_ok`), e.g. from `load_annotations` |
| `outcomes` | required | tidy outcomes, e.g. from `load_outcomes` |
| `subjects` | every subject in `outcomes`, sorted | cells to fit |
| `dimensions` | every dimension in `annotations`, sorted | cells to fit |
| `min_items` | `30` | cells with fewer joined instances are recorded, not fitted |
| `**fit_kwargs` | | passed to `fit_theta`: `k`, `robust`, `likelihood`, `restart_range`, … |

**Returns** one row per (subject, dimension), subject by subject, with columns
`PROFILE_COLUMNS + DIAGNOSTIC_COLUMNS` ([table](../data-formats.md#profiles)).
- **No cell is ever dropped.** Cells that cannot be fitted keep their row, with `theta` NaN
  and a `skip_reason`. A cell whose fit raises is recorded as `fit failed: …`, and the sweep
  continues.
- **The join report** is in `profiles.attrs["join_report"]`.

**Warns** as `join_annotations_outcomes` does. **Raises** only for invalid inputs
(`ContractError`).

```python
from propensity import fit_profiles, load_annotations, load_outcomes

profiles = fit_profiles(load_annotations("examples/annotations_RA.jsonl"),
                        load_outcomes("examples/outcomes_long.csv"),
                        min_items=30, likelihood="sum", robust=True)
```

### `profile_vector`

```python
profile_vector(profiles, subject_id) -> dict[str, float]
```

`{dimension: theta}` for one subject; `theta` is NaN for unfitted cells. Raises `KeyError`
for an unknown subject.

## `build_empirical_curve`

`propensity.modelling.curves`.

```python
build_empirical_curve(demands, success, *, n_bins=20, lowess_frac=0.4, jitter=0.0, seed=None) -> dict
```

Success binned by interval centre `(b_l + b_u)/2`, with a LOWESS smooth of the bin means.

| Parameter | Meaning |
|---|---|
| `n_bins` | equal-width bins over the observed centres |
| `lowess_frac` | LOWESS bandwidth |
| `jitter` | half-width of uniform noise added to both bounds, **for display only**; `0.25` is usual for plots |
| `seed` | makes the jitter repeatable |

**Returns** `bin_centers`, `bin_means` (NaN for empty bins), `lowess_x` and `lowess_y`. With
fewer than two populated bins, the LOWESS arrays are just those bins. The caller's arrays are
never modified.

## Surfaces

`propensity.modelling.surfaces`. Every grid is a DataFrame indexed by `b_u` (rows) and `b_l`
(columns), or by `length` and `centre` for trees. `demands_int` must be whole numbers within
`[r1, r2]`; otherwise `ValueError`.

### `build_empirical_surface`

```python
build_empirical_surface(demands_int, success, *, r1=-3, r2=3) -> dict
```

One subject's success per interval. Returns:
- `prob`: mean success per cell, NaN where nothing was observed;
- `counts`: observations per cell;
- `grid`: `r1 … r2`.

Cells are *observed* (`counts > 0`), *valid but unobserved* (`b_l ≤ b_u`, `counts == 0`), or
*impossible* (`b_l > b_u`).

### `build_model_surface`

```python
build_model_surface(theta, *, smooth=False, resolution=0.05, k=1.0, min_width=0.1, rho=2.0, r1=-3, r2=3) -> dict
```

The success `two_sided_sigma` predicts at `theta` for every interval. Returns:
- `prob`: NaN where `b_l > b_u`;
- `grid`;
- `theta`;
- `smooth`.

| Parameter | Meaning |
|---|---|
| `smooth` | `False`: the integer grid, cell for cell with the empirical surface; `True`: a continuous grid |
| `resolution` | grid step when `smooth=True` |
| `k`, `min_width`, `rho` | the response model's parameters |

### `build_interval_distribution`

```python
build_interval_distribution(demands_int, *, r1=-3, r2=3) -> dict
```

How a bank's intervals spread over the bounds grid. Returns `counts`, `proportions` (of all
intervals), `grid` and `n_items`.

### `build_interval_tree`

```python
build_interval_tree(demands_int, *, r1=-3, r2=3) -> dict
```

The same by length (rows, `0 … r2 − r1`) and centre (columns, `r1 … r2` in steps of 0.5).

**Returns:**
- `counts`, `proportions`;
- `reachable`: whether an interval with whole-numbered bounds inside `[r1, r2]` can have that
  centre and length (28 cells on the default grid);
- `centres`, `lengths`, `n_items`.
