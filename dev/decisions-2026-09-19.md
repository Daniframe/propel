# Decisions taken overnight, 19–20 September 2026

Work done unattended, with the instruction to decide and justify rather than ask. Everything is
committed locally; **nothing was pushed, tagged or uploaded**, because the rubrics' copyright
is not cleared. Each section says what was decided and why, so any of it can be reversed.

## Which version gets what

The instruction mapped features to versions: dimensions and the two bug fixes to 0.1.2,
provenance to 0.1.3, the public API to 0.2.0, Python 3.14 to 0.3.0. That left the work already
prepared as "0.1.1" — the line break before the question, advisory rubric checks, and the
incitement rewording — without a home, since the dimensions were part of that same batch.

**Decision:** keep 0.1.1 for those three changes alone and move the dimensions into 0.1.2 with
the fixes. The alternative, folding everything into 0.1.2 and skipping 0.1.1, would have lost
the distinction between a prompt-layout change and a content change, which is the distinction
the stability policy now turns on. The wheel built earlier and labelled 0.1.1 therefore
contains what is now 0.1.2's dimensions: **do not distribute that file**; it was moved to
`scratchpad/dist-0.1.1-superseded`.

## Rewriting three commits

The advisory-checks commit regenerated `docs/dimensions.md` while the not-yet-committed
`RA_v2.md` was present on disk, so the page linked to a file those commits did not contain, and
two tests failed at that point in the history.

**Decision:** rebuild the affected commits in a clean worktree, replay the two later commits,
and move `main` only after checking that the final file tree was byte-identical (it was:
`f6bf8b6…`). Rewriting unpushed history is cheaper than leaving three commits that fail their
own tests. All seven rebuilt commits were then tested in clean checkouts: 509 to 563 tests each.

## The two fixes (0.1.2)

- **`.env`.** `load_dotenv()` searches from the calling module's folder, so an installed package
  looked inside the environment and never found the user's file. Now `find_dotenv(usecwd=True)`:
  the working directory, then upwards. Variables already set in the environment still win, which
  is python-dotenv's default and the least surprising rule. Two tests fail on the old code.
- **Token usage.** Adapters already returned `Completion.usage` and the runner dropped it.
  Three columns are recorded instead of the raw dict: a dict does not survive CSV, and each
  provider names its fields differently. `normalise_usage` maps OpenAI (both shapes), Anthropic
  and Gemini onto `input_tokens` (whole prompt, cached part included), `cached_input_tokens`
  and `output_tokens` (everything billed as output). Anthropic reports cache reads and writes
  outside `input_tokens`, so they are added back; Gemini reports "thoughts" outside
  `candidates_token_count`, so those are added to output. Unknown shapes give None, never a
  guess.

## Provenance (0.1.3)

Asked for: the rubric version and the package version on every annotation. Recorded:
`rubric_version`, `rubric_sha256` and `propensity_version`.

- **The hash was added** because `rubric_version` is meaningless for a rubric of your own, and
  because two rubrics can share a version string across directories. The hash identifies the
  exact text that produced the interval.
- **Auto-detection:** when the Python API is not told a version, a rubric whose text matches a
  packaged version is recognised. The command line always knows the version and passes it.
- **A warning on mixing.** `load_annotations` warns when one dimension's rows come from
  different rubrics. It is per file: annotations split across files are still only comparable if
  you check. Making the tidy frame carry provenance would have changed a documented format for
  a check most users do not need.
- **Columns are appended, never inserted.** That is now part of the stability policy, so old
  files and readers keep working.

## The public API (0.2.0)

Three tiers (stable, provisional, internal), `__all__` in the package and each submodule,
`docs/stability.md` as the promise, and tests that fail if the page and the code disagree. The
design sketch, with the open questions, is in `dev/public-api.md`.

Two choices worth flagging:
- **`PropensityDeprecationWarning` subclasses `FutureWarning`**, not `DeprecationWarning`,
  because Python hides the latter outside `__main__`; a deprecation nobody sees is not a
  deprecation.
- **Changing a prompt counts as a breaking change**, even though no code fails: it makes
  existing annotations incomparable. That is why 0.1.1 and 0.1.2 are minor releases.

## CI and releases

- **Action versions were looked up, not remembered:** `checkout@v7`, `setup-python@v7`,
  `upload-artifact@v7`, `download-artifact@v8`, `pypa/gh-action-pypi-publish@release/v1`.
- **A pushed tag publishes to TestPyPI; PyPI needs a manual run of the workflow, on a tag.**
  A permanent release should take a deliberate second action, and the `pypi` environment can
  carry a required reviewer.
- **Trusted publishing**, so no token is stored anywhere. Setup steps are in `dev/releasing.md`.
- **One script, `.github/scripts/check-dist.sh`,** for the fresh-install check, so CI and a
  laptop run the same thing. It works around Git Bash's path conversion and macOS's bash 3.2.
- The workflows pass `actionlint`. They cannot be run until the repository is pushed.

## Python 3.14 (0.3.0)

Verified in `python:3.14-slim` before claiming it: 583 tests with every extra, 527 passed and
56 skipped core-only. **3.10 stays supported**, though it reaches end of life in October 2026;
dropping it changes what users can install and is your call, not a side effect of tonight.

## Left undone, deliberately

- **Nothing was pushed, tagged or uploaded.** Pushing would publish the new rubrics.
- **No provider was called.** No credentials, no spending; `dev/provider-free-tiers.md` says
  what could be tested for free and what needs about $5–10.
- **`Co`, `IM` and `Op` still have no `[0, 0]` full example**, so they do not pass all
  recommended checks. Adding one is writing rubric content, which is yours.
- **The catalogue summaries** for the 11 new dimensions are my drafts and want your review.
