# Changelog

## 0.5.1

- **Fixed: a rubric check reported a sentence that was there.** The propensity-range check
  matched the threshold literally as `50%`, so the four rubrics that write "at least 50 percent
  probability" - `Ac`, `Np`, `Pw` and `Ul` v2 - were warned about on every annotation run. The
  check now accepts `%`, `percent` and `per cent`, in any case and with or without a space. No
  rubric text changed, so annotations are unaffected; only the warning was wrong.
  `BR`, `Sc` and `Tr` really do lack the sentence and are still reported.


## 0.5.0

**Every fitted number changes.** Estimates from earlier versions are not comparable with these,
and the reason is that the old ones were often wrong.

- **The fit searches the whole range instead of descending from a starting point.** The
  likelihood is evaluated on a 3,201-point grid over `theta` in [-8, +8] and the best point is
  then refined locally. Every annotated interval contains 0, so near `theta = 0` the model
  predicts `p = 1` on every item and each failure is pinned at the clip floor: the gradient
  vanishes, and BFGS stopped there and reported convergence. The integer bounds and the
  `e^(rho/w)` slope term also leave several local maxima - a median of seven on real banks - so
  which one a local method found depended on where it started.
- **Confidence intervals are profile-likelihood intervals,** where the log-likelihood falls by
  half the chi-square 95% quantile. The previous intervals came from BFGS's inverse-Hessian
  approximation, which on a plateau is the identity matrix and prints as `se = 1.000` whatever
  the data say. An end the search never reaches is now reported as `-inf` or `+inf` rather than
  as a number: the data do not bound `theta` on that side.
- **`se` is the interval's half-width** expressed as a standard error, and empty when an end is
  open. It is not a curvature estimate.
- **Degenerate outcome columns are refused, not fitted.** A cell where every outcome is a
  success or every outcome is a failure carries nothing to locate `theta` with; it is almost
  always an API or judging failure, and a number for it reads as behaviour. It is now recorded
  with a `skip_reason`, like an over-orthogonal bank.
- **New columns:** `identified` (0 when the data cannot locate `theta` at all) and
  `n_local_maxima` (how many maxima the search found; above 1, a local optimiser's answer would
  have depended on its starting point). They replace `n_attempts`, `n_converged` and
  `restart_theta_std`, which described restarts that no longer happen.
- **Retired:** `--no-robust`, and the `robust`, `restart_range`, `max_retries`, `patience`,
  `maxiter` and `x_init` arguments. They are still accepted, ignored, and announced with
  `PropensityDeprecationWarning`. `config/modelling.yaml` gains `grid_range`, `grid_step` and
  `refine`.
- **The search range is derived, not chosen.** `grid_range` defaults to `[-8, +8]` because that
  is where the model gives the widest interval the scale allows, `[-3, +3]`, a success
  probability below 1e-3: past it the model predicts failure on every item of every bank, so a
  fit that still improves out there is unidentified rather than extreme, and says so. Over the
  485 cells of the paper and the safety battery, no identified maximum passes `|theta|` = 4.7.
- **`grid_step`, not `grid_points`.** Resolution is now independent of the range; fixing a point
  count meant narrowing the search silently sharpened the grid. Pass `grid_points` to set a
  count directly.


## 0.4.0

- **Thirteen new dimensions, from the propensity hierarchy.** The Schwartz basic values
  — achievement (`Ac`), benevolence (`Bn`), conformity (`Cf`), hedonism (`He`), power
  (`Pw`), security (`Sc`), self-direction (`SD`), stimulation (`St`), tradition (`Tr`) and
  universalism (`Un`) — plus conscientiousness (`Cs`), need for power (`Np`) and temporal
  discounting (`TD`). The package now ships 28 dimensions.
- **Extraversion and ultracrepidarianism have a `v2`,** the hierarchy's rubric for each, and it
  is now the catalogue's default. `Ex_v1` and `Ul_v1`, the rubrics behind the paper's
  annotations, stay in the package: request them with `--rubric-version v1`. Annotations made
  with `v1` and `v2` are not comparable. This follows what risk aversion did in 0.1.2.
- **The eleven rubrics already shipped are unchanged,** byte for byte. Comparing them against
  the hierarchy's showed the same text in different notation, which 0.1.2 had already
  normalised, so there was nothing to take.
- **Achievement ships once.** The hierarchy holds it twice, as `achievement_value` and
  `need_for_achievement`, but both folders carry the same rubric (98.5% identical, both titled
  "Achievement Propensity").
- Known gaps in the imported rubrics, all advisory: hedonism has no level -3; conformity,
  security and tradition have no full-examples section; several lack a degenerate `[0, 0]`
  example. [Dimensions](docs/dimensions.md#recommended-checks) lists each one.


## 0.3.0

- **Python 3.14 is supported and tested.** The suite runs on 3.10 to 3.14 in CI, on Linux,
  Windows and macOS. 3.10 remains supported.

## 0.2.0

- **The public API is defined.** `propensity.__all__` (and each submodule's) names what is
  stable; [Stability and versioning](docs/stability.md) says what that promises, what is
  provisional, what is internal, and which changes count as breaking. Changing a prompt counts,
  because it makes existing annotations incomparable, which is why 0.1.1 and 0.1.2 were minor
  releases.
- **Deprecations will be announced.** `PropensityDeprecationWarning` subclasses `FutureWarning`,
  so it is shown by default; a stable name keeps working for at least one minor release after
  it is deprecated. Nothing is deprecated yet.
- **`ANNOTATION_SYSTEM`** is now exported from the top-level package.
- **Continuous integration.** The suite runs on Linux, Windows and macOS for Python 3.10 to
  3.13, at the dependency floors, and against the built wheel. A pushed tag builds, checks and
  publishes to TestPyPI; publishing to PyPI stays manual (`dev/releasing.md`).

## 0.1.3

- **Every annotation records what produced it.** Rows end with `rubric_version`,
  `rubric_sha256` and `propensity_version`. The command line always knows the version; in
  Python, pass `rubric_version=` to `annotate`, or let it recognise a packaged rubric from its
  text. The SHA-256 identifies any rubric, packaged or your own.
- **Mixed rubrics are flagged.** `load_annotations` warns when one dimension's rows come from
  different rubrics: their intervals are not comparable.

## 0.1.2

- **Eleven new dimensions,** each with a `v1` rubric: agreeableness (`Ag`), altruism (`Al`),
  competitiveness (`Cm`), cooperativeness (`Co`), intrinsic motivation (`IM`), machiavellianism
  (`Mc`), narcissism (`Nr`), need for affiliation (`Af`), neuroticism (`Ne`), openness (`Op`)
  and psychopathy (`Ps`). The package now ships 15 dimensions.
- **Risk aversion `v2`, now `RA`'s default.** It belongs to the same set as the new dimensions.
  `RA_v1`, the rubric behind the paper's annotations, stays in the package: request it with
  `--rubric-version v1` (or `version="v1"`) to annotate with it. Annotations made with `v1` and
  `v2` are not comparable.
- **Notation.** The new rubrics' wording is unchanged. Their notation was brought into line
  with the output contract and the recommended checks: ASCII minus signs, ranges bounded at ±3
  instead of ±∞, "50%", saturating ±3 level headings, and titles without codes. Where a rubric's
  Level 0 section had a `[0, 0]` example, it was also added to the full examples. `Co`, `IM` and
  `Op` have none yet, so they do not pass all recommended checks.
- **Fixed: `.env` is found.** `propel-annotate` looks for `.env` in the working directory, then
  in each folder above it. An installed package used to look only next to its own files, and
  never found yours. Variables already set in the environment still win.
- **Fixed: token usage is recorded.** Every annotation row now has `input_tokens`,
  `output_tokens` and `cached_input_tokens`, from whatever the provider reports, and a run ends
  with their totals. They join the canonical row fields, after `parse_method`.

## 0.1.1

- **The task starts on its own line.** The prompt now puts exactly one line break between
  "Annotate the following task:" and the instance, however `presentation.md` ends. This changes
  every prompt of every dimension: annotations made with 0.1.0 are not comparable with new
  ones, and reproducing them needs 0.1.0.
- **Rubric checks are recommendations.** A rubric that does not pass all of `check_rubric`'s
  checks is still used. Annotating with it logs a warning naming what it misses, and
  [Dimensions](docs/dimensions.md#recommended-checks) lists each current rubric's result. The
  test suite no longer fails on a rubric's gaps.
- **The incitement check is optional.** Recovering incited levels ([Tutorial 7](docs/tutorials/07-validating-with-incitement.md))
  is presented as an end-to-end check worth trying, not a step PROPEL requires.

## 0.1.0

First release.

- **Annotation.** `propel-annotate run`, `submit`, `status` and `fetch`, and `propensity.annotate`:
  a demand interval per instance from any LLM provider, one call at a time or as a batch.
- **Providers.** `openai` (and OpenAI-compatible servers), `azure`, `anthropic`, `google`,
  `http` and `mock`, each an optional extra. Custom providers register with
  `register_provider`.
- **Rubrics.** Four dimensions ship with the package: `RA`, `Ex`, `Ul` and `BR`, with a
  catalogue of trait names, poles and versions.
- **Fitting.** `propel-fit` and `propensity.fit_profiles`: `theta` with a 95% confidence
  interval per subject and dimension, fit diagnostics, and a join-yield report.
- **Plots.** Propensity curves, surfaces, profiles and annotation trees, with the `plot` extra.
- **Example data.** A synthetic risk-aversion dataset, copied out with
  `python -m propensity.examples`.
