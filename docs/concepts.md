# Concepts

The measurement model in brief. Enough to use the library correctly and to read its output.

## Propensities

A **capability** is what a model *can* do. A **propensity** is what it *tends* to do when a task
leaves room for a choice: take the sure payoff or gamble, answer beyond its competence or hedge.
Two models with the same capabilities can differ sharply in propensity, and capability profiles
do not see it.

## Dimensions

Each propensity is a **dimension** (or trait), with a short code, two poles, and its own rubric.
For example:

| Code | Trait | Negative pole | Positive pole |
|---|---|---|---|
| `RA` | risk aversion | risk-seeking | risk-averse |
| `Ul` | ultracrepidarianism | diffidence | overextension beyond one's competence |

[Dimensions](dimensions.md) lists every dimension PROPEL ships. Never infer a dimension's meaning
from its code: `BR` is literally coloured options, a red bucket versus a blue one.

## Levels

A propensity level is a number on a signed scale from `-3` to `+3`:

- **`0`** is the unbiased, instrumentally rational agent.
- **The sign** is the direction of the tendency.
- **The magnitude** is how much task-relevant evidence it takes to override it: at `±1` a
  moderate difference suffices, at `±2` only a severe one, and at `±3` nothing does.
- **The endpoints saturate**: `-3` means "`-3` or lower", and `+3` means "`+3` or higher".

## Demand intervals

A **demand interval** `[b_l, b_u]` is a property of one task instance: the range of levels at
which an agent would still answer it correctly with probability at least 0.5, assuming no other
bias and no capability shortfall.

| Interval | Meaning |
|---|---|
| `[-1, +3]` | fails only for agents at `-2` or below |
| `[0, 0]` | only the unbiased agent succeeds |
| `[-3, +3]` | **orthogonal**: every level succeeds, so it carries no information about the trait |

The interval belongs to the task, not to any model, so a bank is annotated once and reused for
every model ever evaluated. PROPEL obtains intervals by asking an LLM to apply the dimension's
rubric ([Rubrics and prompts](rubrics.md)).

## The response model

The probability that an agent at level `x` succeeds on an instance with interval `[b_l, b_u]` is
bell-shaped. It peaks at exactly 1 at the interval's midpoint and falls on both sides:

```
P(x) = A · σ(k'(x − b_l)) · σ(−k'(x − b_u)),   k' = k + e^(ρ/w) − 1,   w = max(b_u − b_l, min_width)
```

- `σ` is the logistic function, and `A` normalises the peak to 1.
- **Narrow intervals get steeper sides.** They discriminate sharply between levels, and they
  carry most of the information.
- **Wide intervals** are forgiving across many levels.
- **An interval narrower than `min_width`** (default 0.1) is widened symmetrically outwards.
  This keeps `[0, 0]` finite.
- **`rho`** (default 2) sets how fast steepness grows as the interval narrows.
- **`k`** (default 1) is the base slope.

`two_sided_sigma` implements it.

## Fitting theta

A subject's **propensity level** `theta` on one dimension is fitted by maximum likelihood from
its successes and failures on the annotated instances:

- **The optimisation.** It starts from the peak of a smoothed success-by-interval-centre curve.
  When the first attempt does not converge, it retries from a spread of starting points kept
  inside `[-5, 5]`, and never averages across them.
- **`se`, `ci95_lower`, `ci95_upper`.** The standard error comes from the inverse Hessian, and
  the 95% interval is `theta ± 1.96·se`.
- **`reference_ll`.** The log-likelihood at `theta = 0`, the unbiased agent.
- **`gof`.** The log-likelihood at the fitted `theta`.
- **`pseudo_r2 = 1 − gof / reference_ll`.** How much better than an unbiased agent the fit
  explains the data. It is negative when the fit is worse than `theta = 0`, which signals a fit
  to distrust.

A **subject** is whatever produced the outcomes: a model, or a model under a particular system
prompt. PROPEL treats it as an opaque identifier.

## Profiles

A subject's **profile** is its vector of `theta` across dimensions. `fit_profiles` produces one
row per (subject, dimension); a profile is a filter on that table.

## Diagnostics

Some item banks cannot locate `theta` whatever the subject does. Every fit is checked:

| Check | Warns when | Why it matters |
|---|---|---|
| `n_items` | below 50 | the fit is unstable |
| `frac_orthogonal` | above 0.5; **refused** above 0.9 | `[-3, +3]` instances carry no information |
| `n_distinct_intervals` | below 5 | too little variety to locate `theta` |
| `outcome_rate` | outside 5–95% | all-success or all-failure data has no interior maximum |
| `converged` | false | the confidence interval is not trustworthy |
| `pseudo_r2` | negative | the fit explains the data worse than `theta = 0` |

**Join yield** is checked before any fit: the share of annotated instances that found outcomes.
A low yield almost always means mismatched `question_id`s.

## Curves and surfaces

Two empirical views of one subject's data, independent of the fitted model:

- **Propensity curve.** Success rate binned by interval centre, with a LOWESS smooth. It peaks
  near `theta`.
- **Propensity surface.** Success rate over the grid of `(b_l, b_u)`. The line
  `b_l + b_u = 2·theta` marks the intervals centred on the estimate. A bank whose observations
  sit in a few cells, or far from that line, shows up at a glance.

## Validation

A fitted `theta` means something only once the chain has recovered a level known in advance.
The check is to incite a model to a level with an explicit system prompt, run it, fit it, and
compare. Incited `+2` should come back near `+2`. It exercises rubric quality, annotation
fidelity and the fit together, and should be run per dimension before trusting numbers about
uninstructed models ([Tutorial 7](tutorials/07-validating-with-incitement.md)).
