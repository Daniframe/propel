# PROPEL

**PROPensity Estimation Library.** Measures the behavioural propensities of AI models, following
*Capabilities Ain't All You Need: Measuring Propensities in AI* (arXiv [2602.18182](https://arxiv.org/abs/2602.18182)).

Capability benchmarks say what a model *can* do. They do not say what it *will* do when a task
leaves room for a choice: take the safe payoff or gamble, answer beyond its competence or hedge.
PROPEL measures those tendencies:
- each task instance gets a **demand interval** `[lower, upper]`: the propensity levels, on a
  `-3 … +3` scale, at which an agent would still get it right;
- a model's successes and failures across many instances then fit its **propensity level**
  `theta` on the same scale.

| | Capability | Propensity |
|---|---|---|
| Instance annotation | a demand level | a demand **interval** `[b_l, b_u]` |
| Response function | monotone logistic | **bell-shaped**: both tails fail |
| More is better? | yes | no, there is an optimum |

Two independent tools:

- **`propel-annotate`** labels task instances with demand intervals, using any LLM provider
  (OpenAI, Azure OpenAI, Anthropic, Google, OpenAI-compatible servers, or any HTTP endpoint).
  Intervals belong to the task, not to a model: annotate once, reuse for every model you
  evaluate.
- **`propel-fit`** fits `theta` per model and trait from those intervals and your models' 0/1
  results. It reports a confidence interval, diagnostics that flag unusable item banks, and,
  optionally, figures.

PROPEL does not run the models being evaluated, generate items, or score answers: you bring
the results as a file.

## Install

```bash
pip install ".[openai,plot]"        # pick the extras you need: openai, azure, anthropic, google, http, plot, dotenv
```

Python 3.10 or later. [Installation](docs/installation.md) lists every extra.

## Quick start

From the project root, with the bundled example data and no credentials:

```bash
propel-fit --annotations examples/annotations_RA.jsonl --outcomes examples/outcomes_long.csv \
    --out out/profiles.csv --plots out/plots
```

With your own instances and a real model:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
propel-annotate run --instances items.jsonl --dimension RA --out RA.jsonl \
    --provider anthropic --model claude-haiku-4-5
propel-fit --annotations RA.jsonl --outcomes my_results.csv --out profiles.csv
```

Or in Python:

```python
from propensity import annotate, fit_profiles, get_provider, load_annotations, load_instances
from propensity import load_outcomes, load_presentation, load_rubric, write_table

rows = annotate(load_instances("items.jsonl"), provider=get_provider("openai", model="gpt-4.1"),
                dimension="RA", propensity_name="risk aversion",
                rubric=load_rubric("RA"), presentation=load_presentation())
write_table(rows, "RA.jsonl")
profiles = fit_profiles(load_annotations("RA.jsonl"), load_outcomes("my_results.csv"))
```

## Documentation

| | |
|---|---|
| [Documentation home](docs/README.md) | start here |
| [Concepts](docs/concepts.md) | levels, demand intervals, `theta`, diagnostics |
| [Tutorials](docs/tutorials/README.md) | eleven walkthroughs, from a five-minute offline run to writing rubrics and providers |
| [Command line](docs/cli.md) · [Configuration](docs/configuration.md) · [Providers](docs/providers.md) | every flag, setting and option |
| [Data formats](docs/data-formats.md) · [Rubrics and prompts](docs/rubrics.md) · [Plots](docs/plots.md) | the files, the prompts, the figures |
| [Dimensions](docs/dimensions.md) · [Managing rubrics](docs/managing-rubrics.md) | every dimension shipped; updating rubrics and adding dimensions |
| [API reference](docs/api/README.md) | every public function |

## Dimensions

Each dimension has its own rubric, and the rubrics ship inside the package, with a catalogue of
trait names, poles and versions. [Dimensions](docs/dimensions.md) lists them all.

- **Updating a rubric or adding a dimension:** [Managing rubrics](docs/managing-rubrics.md).
- **Trying a rubric of your own** without changing the package:
  [Tutorial 9](docs/tutorials/09-writing-a-rubric.md).

## Before trusting a number

Check that the chain recovers levels you set yourself: incite a model to known levels, fit it,
and compare ([Tutorial 7](docs/tutorials/07-validating-with-incitement.md)). Do it for each
dimension before interpreting any uninstructed model.

## Development

```bash
pip install -e ".[dev,plot,openai,anthropic,google,http]"
pytest -q -W error
```

The tests need no network and no credentials, and run with any subset of the extras installed.
Tests that need an SDK or matplotlib skip when it is absent. Every tutorial that needs no
credentials is executed as written.
