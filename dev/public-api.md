# Draft: what PROPEL promises to keep stable

A design sketch for review, written while preparing 0.2.0. `dev/` ships with neither the sdist
nor the wheel. The version of this that users read is [docs/stability.md](../docs/stability.md);
this file records the reasoning and the open questions.

## Why now

Until 0.2.0 everything was public by accident: 45 names came out of `import propensity`, none
marked, and nothing said which of them could change. Colleagues are starting to build on the
package, so the surface needs a boundary. The point is not to freeze PROPEL, which is still
`0.x`, but to make every break deliberate, announced and visible in the version number.

## Three tiers

| Tier | What it means | Where it lives |
|---|---|---|
| **Stable** | Changes follow the versioning policy: a break bumps the minor number (while `0.x`) and is announced in the changelog after a deprecation period where one is possible | the names in `propensity.__all__`, the commands and their flags, the file formats, the config keys, the rubric layout |
| **Provisional** | Useful, documented, but still moving: may change in any minor release, with a changelog line | the batch job file's contents, the figures' appearance, `check_rubric`'s exact wording |
| **Internal** | No promises at all | anything named with a leading underscore, `propensity.cli.*` beyond its commands, `docs/` scripts, `dev/`, the test helpers |

The tiers are what makes "PROPEL 0.2.0" mean something: without them, every patch release is a
gamble for anyone importing more than `annotate`.

## The stable surface

**Python.** The 46 names in `propensity.__all__`: the two entry points (`annotate`,
`fit_profiles`), the loaders and writers, the model and fitting functions, the rubric and
catalogue readers, the prompt builder and parser, the runner's building blocks, the provider
protocol and registry, the plotting functions, and the error and warning classes. Submodules
(`propensity.annotation`, `.modelling`, `.providers`) re-export their own parts; importing from
them is equally supported.

**Commands.** `propel-annotate run|submit|status|fetch` and `propel-fit`, with the flags the
[command line](../docs/cli.md) page documents, their defaults, and their exit codes (0 success,
1 "not ready yet", 2 refused).

**Files.** What the tools read and write, column by column: instances, annotation rows,
outcomes in both shapes, the profile table. New columns may be appended; existing ones keep
their names, positions and meanings.

**Configuration.** The keys in `config/annotation.yaml` and `config/modelling.yaml`.

**Rubrics.** The directory layout, the catalogue's fields, and the rule that a rubric file,
once it has annotated anything, never changes: a new version is a new file.

## What counts as a break

A break is anything that can make working code fail, or make old results incomparable with new
ones. Removing or renaming an exported name, a flag, a column or a config key. Changing what a
column means. **And, specifically for this project: changing any prompt.** A rubric's text, the
presentation block, the trait names, the prompt layout, or which rubric version is the default
all change the intervals an annotator produces. That is a break even though no code fails,
which is why 0.1.1 (the line break before the question) and 0.1.2 (risk aversion v2 as the
default) were minor releases rather than patches.

Compatible, by contrast: appending a column or a row field, adding an optional keyword
argument, adding a flag with a default that preserves behaviour, adding a dimension, adding a
rubric version without making it current, adding a provider.

## Deprecation

Removal is a two-step process, because a library that removes things without warning is one
people pin and stop upgrading:

1. The old name keeps working and emits `PropensityDeprecationWarning`, which subclasses
   `FutureWarning` so that it is shown to users by default. (`DeprecationWarning` is hidden
   outside `__main__`, which would defeat the point.) The changelog says what to use instead.
2. It is removed no earlier than the next minor release, and the changelog says so again.

`propensity._deprecation.warn_deprecated` is the one helper; it is internal on purpose.

## Open questions for review

- **Plotting.** The functions are stable, but the figures are not: any change to colours,
  labels or layout would otherwise be a breaking change. Provisional feels right, but if you
  publish figures from PROPEL directly, say so and I will pin them with image tests instead.
- **The batch job file.** Written by `submit`, read by `fetch`. People will inspect it; some
  will script against it. Provisional for now.
- **`propensity.cli`.** The commands are stable, the Python functions behind them are not.
  Anyone calling `propensity.cli.annotate.main(...)` from Python is relying on an internal.
- **The 1.0 line.** My proposal: 1.0 waits until every provider has been exercised against its
  real API, the rubric set is settled, and the file formats have survived a real study. Until
  then `0.x`, where a minor bump is allowed to break things.
