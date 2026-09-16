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

## Development

```bash
python -m venv ~/.venvs/propel          # keep the environment outside synced folders
~/.venvs/propel/Scripts/python -m pip install -e ".[dev,plot]"   # bin/ instead of Scripts/ on Linux/macOS
~/.venvs/propel/Scripts/python -m pytest -q
```

Tests make no network calls and need no credentials.

## Rubrics

`rubrics/` holds one rubric per dimension plus the shared presentation block. They are copied
from the prior implementation with only line endings changed, because their wording produced
the existing annotation data. Measured against the rubric structure in CLAUDE.md §7.1, they
have these known gaps, left for a future v2:

- None of the four contains the propensity-range definition sentence word for word.
- Ex and Ul have no `[-3, +3]` (orthogonal) or `[0, 0]` (degenerate) full example.
- Ex's Level -3 and +3 headings are not written as saturating ("or below" / "or above").
- Ul's title is misspelled ("ULTRACREPIDARIANSIM").
- There is no TD (delay of gratification) rubric yet.

Editing a rubric changes every prompt built from it. `tests/test_rubric_files.py` pins each
file's hash, so a change can't happen by accident.
