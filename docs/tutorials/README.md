# Tutorials

Hands-on walkthroughs, in a sensible reading order. Tutorials 1 and 2 cover the whole library
in miniature; the rest go deep on one stage each.

| # | Tutorial | Needs credentials | Covers |
|---|---|---|---|
| 1 | [Offline walkthrough](01-offline-walkthrough.md) | no | annotate with a scripted mock, simulate subjects, fit, plot; all in Python |
| 2 | [The command line](02-command-line.md) | no | `propel-annotate` (`run`, `submit`, `status`, `fetch`) and `propel-fit`, flags, config files, errors |
| 3 | [Annotating with a real provider](03-annotating-with-a-provider.md) | yes | every provider, pilots, reading explanations, cost, rerunning failures, several dimensions |
| 4 | [Batch annotation](04-batch-annotation.md) | no (mock rehearsal) | job files, polling, `--wait`, drift, lost ids, failed batches, the Python batch API |
| 5 | [Preparing outcomes](05-preparing-outcomes.md) | no | long and wide forms, validation, missing values, matching ids, legacy annotation files |
| 6 | [Fitting and diagnostics](06-fitting-and-diagnostics.md) | no | the profile table, fitting one cell, every diagnostic on a broken bank, fit settings |
| 7 | [Validating with incited models](07-validating-with-incitement.md) | no | the recovery check that must precede any interpretation |
| 8 | [Plots](08-plots.md) | no | every figure, combined figures, files, notebooks |
| 9 | [Writing a rubric](09-writing-a-rubric.md) | no | a rubric of your own, its structure check, a new version, checks before spending |
| 10 | [Adding a provider](10-adding-a-provider.md) | no | a custom provider, its batch version, the path-equivalence check |
| 11 | [Troubleshooting](11-troubleshooting.md) | | every error message, its cause and its fix |

## Conventions

- **Where to run.** Run everything from one working directory. Put the example data there
  first with `python -m propensity.examples`, which writes `examples/`. Tutorials write only
  under `out/`.
- **Code blocks follow on.** Within a tutorial, each Python block continues from the ones
  before: paste them into one session, script or notebook.
- **Shells.** Commands are written for bash. In PowerShell, replace a trailing `\` with a
  backtick, or join the lines.
- **Expected output.** Blocks marked as output show what the step prints. Timestamps and batch
  ids will differ.
- **Kept in sync.** Every tutorial that needs no credentials is run by the test suite exactly
  as written (`tests/test_docs.py`).
