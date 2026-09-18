# Changelog

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
