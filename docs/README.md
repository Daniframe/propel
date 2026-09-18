# PROPEL documentation

PROPEL measures the behavioural propensities of AI models: what a model tends to do when a task
leaves room for a choice, as opposed to what it can do. It follows *Capabilities Ain't All You
Need: Measuring Propensities in AI* ([arXiv 2602.18182](https://arxiv.org/abs/2602.18182)).

The library has two independent halves:

| Stage | Command | Python | Input | Output |
|---|---|---|---|---|
| **Annotate** | `propel-annotate` | `propensity.annotate` | task instances + a rubric | one demand interval `[lower, upper]` per instance |
| **Fit** | `propel-fit` | `propensity.fit_profiles` | intervals + your models' 0/1 results | a propensity level `theta` per model and trait |

PROPEL never runs the models being evaluated. You bring their results as a file.

## Start here

1. [Installation](installation.md)
2. [Concepts](concepts.md): levels, demand intervals, `theta`, profiles and diagnostics.
3. [Tutorial 1](tutorials/01-offline-walkthrough.md): the whole pipeline in Python, offline, in
   five minutes.

## Tutorials

| # | Tutorial | You will |
|---|---|---|
| 1 | [Offline walkthrough](tutorials/01-offline-walkthrough.md) | annotate, simulate, fit and plot, with no credentials |
| 2 | [The command line](tutorials/02-command-line.md) | run both commands on the bundled example data |
| 3 | [Annotating with a real provider](tutorials/03-annotating-with-a-provider.md) | set up each provider, run, inspect and rerun failures |
| 4 | [Batch annotation](tutorials/04-batch-annotation.md) | submit, poll, fetch and recover long batches |
| 5 | [Preparing outcomes](tutorials/05-preparing-outcomes.md) | shape your results so they join cleanly |
| 6 | [Fitting and diagnostics](tutorials/06-fitting-and-diagnostics.md) | fit, read the profile table, tune the fit |
| 7 | [Validating with incited models](tutorials/07-validating-with-incitement.md) | check the chain recovers known levels |
| 8 | [Plots](tutorials/08-plots.md) | draw every figure, in files or notebooks |
| 9 | [Writing a rubric](tutorials/09-writing-a-rubric.md) | write, check, try and version a rubric of your own |
| 10 | [Adding a provider](tutorials/10-adding-a-provider.md) | connect an API PROPEL does not ship |
| 11 | [Troubleshooting](tutorials/11-troubleshooting.md) | map an error message to its fix |

## Guides

| Guide | Covers |
|---|---|
| [Data formats](data-formats.md) | instances, annotations, outcomes, profiles, job files; accepted legacy shapes |
| [Configuration](configuration.md) | both YAML files, environment variables, precedence |
| [Command line](cli.md) | every subcommand, flag, output and exit code |
| [Providers](providers.md) | every provider's options, credentials, batching and temperature |
| [Dimensions](dimensions.md) | every dimension shipped: code, trait, poles, rubric versions |
| [Rubrics and prompts](rubrics.md) | rubric files and structure, prompt assembly, the output contract, parsing |
| [Managing rubrics](managing-rubrics.md) | the catalogue; updating a rubric; adding a dimension |
| [Plots](plots.md) | every figure and how to read it |

## API reference

[Public API](api/README.md), module by module: [annotation](api/annotation.md),
[modelling](api/modelling.md), [plotting](api/plotting.md), [providers](api/providers.md),
[errors](api/errors.md).

## Examples

[The example data](../propensity/examples/README.md) is a small synthetic dataset (120
risk-aversion instances, their intervals, and outcomes for four simulated subjects) that the
tutorials use. It ships with the package: `python -m propensity.examples` copies it into
`./examples`.
