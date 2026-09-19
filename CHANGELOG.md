# Changelog

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
