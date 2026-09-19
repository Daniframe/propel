# Changelog

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
