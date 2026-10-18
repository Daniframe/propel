# Stability and versioning

What PROPEL promises to keep stable, what may still change, and what a version number means.

- [Three tiers](#three-tiers)
- [The stable Python API](#the-stable-python-api)
- [The stable command line](#the-stable-command-line)
- [The stable file formats](#the-stable-file-formats)
- [What counts as a breaking change](#what-counts-as-a-breaking-change)
- [Deprecation](#deprecation)
- [Version numbers](#version-numbers)

## Three tiers

| Tier | Promise | What is in it |
|---|---|---|
| **Stable** | changes follow the [version policy](#version-numbers), are announced in [the changelog](../CHANGELOG.md), and are deprecated first where that is possible | the names in `propensity.__all__`, the commands and their flags, the file formats, the configuration keys, the rubric layout |
| **Provisional** | may change in any minor release, with a changelog line | the batch job file's contents, how the figures look, the exact wording of `check_rubric`'s messages and of log messages |
| **Internal** | no promises | anything whose name starts with `_`, the functions inside `propensity.cli`, the scripts in `docs/`, and everything in `dev/` |

## The stable Python API

Everything `from propensity import *` gives you, also importable from its submodule
(`propensity.annotation`, `propensity.modelling`, `propensity.providers`):

```text
annotate ANNOTATION_SYSTEM available_providers BatchCapable BatchRequest build_annotation_prompt
build_empirical_curve build_empirical_surface build_interval_distribution build_interval_tree
build_model_surface Completion ContractError DataWarning Dimension fit_diagnostics fit_profiles
fit_theta get_dimension get_provider join_annotations_outcomes LLMProvider load_annotations
load_dimensions load_instances load_outcomes load_presentation load_rubric neg_log_likelihood
parse_final_range ParseError plot_interval_distribution plot_interval_tree plot_interval_trees
plot_model_surface plot_propensity_curve plot_propensity_surface profile_vector
PropensityDeprecationWarning PropensityError ProviderError read_table register_provider
save_annotation_plots save_profile_plots two_sided_sigma write_table
```

`propensity.__version__` is stable too. The runner's building blocks
(`build_requests`, `run_sequential`, `submit`, `wait_for_batch`, `collect`,
`rows_from_completions`, `summarise`, `summarise_usage`, `normalise_usage`, `provenance`,
`require_batch`) and the rubric helpers (`available_dimensions`, `available_versions`,
`rubric_path_for`, `check_rubric`, `RUBRICS_DIR`) are stable in their submodules.

## The stable command line

`propel-annotate run`, `submit`, `status` and `fetch`, and `propel-fit`: their flags, their
defaults ([Command line](cli.md)), and their exit codes.

| Code | Means |
|---|---|
| 0 | done |
| 1 | nothing to do yet, e.g. a batch still running |
| 2 | refused: bad input, missing credentials, unknown provider |

## The stable file formats

Column names, positions and meanings ([Data formats](data-formats.md)). New columns are
appended; existing ones never move or change meaning.

Annotation rows, in order, then the instance's own fields:

```text
question_id dimension lower upper annotator explanation parse_ok error parse_error parse_method
input_tokens output_tokens cached_input_tokens rubric_version rubric_sha256 propensity_version
```

The profile table, in order:

```text
subject_id dimension n_items theta se ci95_lower ci95_upper converged reference_ll gof pseudo_r2
skip_reason frac_orthogonal n_distinct_intervals outcome_rate identified
n_local_maxima warnings
```

Instances need `question_id` and `question_text`; outcomes need `question_id`, `subject_id`
and `outcome`, or the wide form. The keys in `config/annotation.yaml` and
`config/modelling.yaml` are stable ([Configuration](configuration.md)), as is the rubric
directory layout ([Managing rubrics](managing-rubrics.md)).

## What counts as a breaking change

Anything that can make working code fail, **or make existing annotations incomparable with new
ones**:

- removing or renaming an exported name, a flag, a column or a configuration key;
- changing what a column means;
- **changing any prompt**: a rubric's text, the presentation block, a trait name, the prompt
  layout, or which rubric version a dimension uses by default.

That last group breaks no code at all, which is exactly why it is called out: intervals
annotated before and after are not comparable. Every annotation row records
`rubric_version`, `rubric_sha256` and `propensity_version` so that you can tell.

These are compatible, and need no deprecation: appending a column or row field, adding an
optional keyword argument, adding a flag whose default keeps the old behaviour, adding a
dimension, adding a rubric version without making it current, adding a provider.

## Deprecation

Before a stable name disappears:

1. it keeps working and warns with `PropensityDeprecationWarning`, a `FutureWarning`, so you
   see it without turning warnings on. The changelog says what replaces it;
2. it is removed no earlier than the next minor release, and the changelog says so again.

To fail on them in your own test suite: `python -W error::FutureWarning -m pytest`.

## Version numbers

PROPEL is `0.x`: the minor number carries breaking changes, and the patch number carries fixes.

| Change | Example | Bump |
|---|---|---|
| a fix, or anything invisible to callers | `.env` was not being read | patch: 0.1.2 → 0.1.3 |
| a compatible addition | new dimensions, new columns, a new provider | patch or minor |
| a breaking change, prompts included | a new default rubric version; a changed prompt layout | minor: 0.1.3 → 0.2.0 |

**1.0 waits** until every provider has been exercised against its real API, the dimension set
is settled, and the file formats have survived a real study. After 1.0, breaking changes bump
the major number instead.
