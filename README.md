# PROPEL

**PROPensity Estimation Library.** Measures behavioural propensities of AI models, following
*Capabilities Ain't All You Need: Measuring Propensities in AI* (arXiv 2602.18182).

Two independent entry points:

- `annotate`: label each task instance with a propensity demand interval `[lower, upper]`,
  using any LLM provider reachable through an API.
- `fit`: from those intervals and your own instance-level results, fit a propensity level
  `theta` per subject and trait, and build propensity curves, surfaces and profiles.

PROPEL does not run the models being evaluated. You supply their results as a file.

> Work in progress. The design spec is in [CLAUDE.md](CLAUDE.md).
