# PROPEL

**PROPensity Estimation Library.** Measures the behavioural propensities of AI models, following
*Capabilities Ain't All You Need: Measuring Propensities in AI* (arXiv [2602.18182](https://arxiv.org/abs/2602.18182)).

Capability benchmarks say what a model *can* do. They do not say what it *will* do when a task
leaves room for a choice: take the safe payoff or gamble, answer outside its competence or hedge.
PROPEL puts those tendencies on a psychometric footing. Each task instance gets a **demand
interval** `[lower, upper]`, the range of propensity levels on a `-3 … +3` scale at which an agent
would still get it right. A model's successes and failures across many instances then fit its
**propensity level** `theta` on the same scale.

| | Capability | Propensity |
|---|---|---|
| Instance annotation | a demand level | a demand **interval** `[b_l, b_u]` |
| Response function | monotone logistic | **bell-shaped**: both tails fail |
| More is better? | yes | no, there is an optimum |

PROPEL has two independent entry points:

- **`propel-annotate`** labels task instances with demand intervals, through any LLM provider
  with an API. Intervals belong to the task, not to a model, so this is paid once and reused for
  every model you ever evaluate.
- **`propel-fit`** takes those intervals and your models' instance-level results, and fits
  `theta` per model and trait, with a confidence interval, diagnostics, and optional plots.

PROPEL does **not** run the models being evaluated, generate items, or judge answers. You bring
the results as a file of 0/1 outcomes.

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Annotating instances](#annotating-instances)
- [Fitting propensity levels](#fitting-propensity-levels)
- [Before you trust a number](#before-you-trust-a-number)
- [Python API](#python-api)
- [Adding a provider](#adding-a-provider)
- [Rubrics](#rubrics)
- [Development](#development)

## Installation

Python 3.10 or later. From a clone of the repository:

```bash
pip install -e ".[openai,plot]"
```

The core needs numpy, scipy, pandas, statsmodels and PyYAML. Everything else is an extra, and
installing one provider's SDK is never needed to use another's:

| Extra | Installs | For |
|---|---|---|
| `openai` | `openai` | OpenAI, and any OpenAI-compatible server (vLLM, Ollama, LM Studio, OpenRouter, Together…) |
| `azure` | `openai` | Azure OpenAI |
| `anthropic` | `anthropic` | Anthropic |
| `google` | `google-genai` | Google Gemini |
| `http` | `httpx` | any other HTTP endpoint |
| `plot` | `matplotlib`, `seaborn` | `propel-fit --plots` and the plotting functions |
| `dotenv` | `python-dotenv` | reading credentials from a `.env` file |
| `dev` | `pytest` | the test suite |

Using a provider or plotting without its extra raises an `ImportError` naming the command that
installs it.

## Quick start

Run from the repository root, where `config/` and `rubrics/` live.

```bash
# 1. Annotate instances on risk aversion (RA). Credentials come from the environment.
export OPENAI_API_KEY=...
propel-annotate run --instances items.jsonl --dimension RA --out RA_annotations.jsonl \
    --provider openai --model gpt-4.1

# 2. Fit every model in your outcomes file.
propel-fit --annotations RA_annotations.jsonl --outcomes outcomes.csv \
    --out profiles.csv --plots plots/
```

To try the whole chain offline first, use `--provider mock --model mock-1`. It answers every
instance with a scripted interval, and spends nothing.

## Annotating instances

### Instances

A `.jsonl` or `.csv` file with one instance per row. Only `question_id` and `question_text` are
read; every other field passes through to the output unchanged.

```jsonl
{"question_id": "RA_0", "question_text": "Choose between: Option A (certain $100) or Option B (50% chance of $220, 50% chance of $0)"}
```

`question_id` must be unique and stable: it is the join key for everything that follows. A file
without one gets `{file stem}_{row index}`, numbered over the whole file. If you sample, sample
**after** loading, never before, or different subsets get different ids and cannot be joined.

### One call at a time, or a batch

```bash
propel-annotate run    --instances items.jsonl --dimension RA --out RA.jsonl --provider openai --model gpt-4.1
propel-annotate submit --instances items.jsonl --dimension RA --out RA.jsonl --provider openai --model gpt-4.1
propel-annotate status --job RA.jsonl.job.json
propel-annotate fetch  --job RA.jsonl.job.json
```

- **`run`** calls the provider once per instance, in parallel threads (`--max-workers`, default
  8), retrying provider errors with backoff (`--max-retries`, default 3). This is the reference
  path.
- **`submit`** uses the provider's native batch API, about half the price where one exists. It
  writes a job file **before** polling starts, so a batch that takes hours survives a closed
  laptop. `status` reports progress, and `fetch` collects the results into the same rows `run`
  would have written. `submit --wait` polls and fetches in one go, and can still be resumed from
  the job file.
- `fetch` rebuilds the prompts and refuses if they no longer match the ones submitted, because
  the instances or rubric changed in between. `--force` overrides that.

Both paths build byte-identical prompts and produce identical rows; the test suite checks this for
every batch-capable provider.

### Providers

| `--provider` | Credentials (environment) | Batch | Notes |
|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | yes | `base_url` points it at any OpenAI-compatible server, whose batch support is probed rather than assumed |
| `azure` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` | yes | `--model` is the **deployment name**. Batches need a Global Batch deployment; `batch=false` for a standard one. `api_version` for a resource on dated API versions |
| `anthropic` | `ANTHROPIC_API_KEY` | yes | `max_tokens` defaults to 16000. A `question_id` must match `[a-zA-Z0-9_-]{1,64}` to be batched |
| `google` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | no | |
| `http` | `api_key_env` of your choice, sent as a bearer token | no | Needs `url`, `build_payload` and `extract_text`; see below |
| `mock` | none | with `batch=true` | Offline and scripted, for trying the pipeline. Across `submit`, `status` and `fetch` it also needs `state_path=mock_state.json` |

Provider arguments go through `--provider-option KEY=VALUE` (repeatable) or `provider_options`
in `config/annotation.yaml`. `true`, `false`, `null` and numbers are converted. For example, a
local Ollama server:

```bash
propel-annotate run --instances items.jsonl --dimension RA --out RA.jsonl \
    --provider openai --model llama3 \
    --provider-option base_url=http://localhost:11434/v1 --provider-option api_key=ollama
```

**Credentials** are read from the environment, and never from config or job files. Each adapter
has its own default variable, and `--provider-option api_key_env=MY_VAR` reads another. With the
`dotenv` extra, `propel-annotate` also loads a `.env` file. Keep real keys out of
`--provider-option api_key=...`: that value is left out of job files on purpose, so `status` and
`fetch` need the key in the environment anyway.

**Temperature** is 0, so that intervals are stable across reruns. Several current models reject
the parameter, among them Claude Opus 4.7 and later, Claude Sonnet 5, and OpenAI's reasoning
models. Those calls fail and are recorded as provider errors, not dropped silently. To use such a
model, pass `--provider-option send_temperature=false`: the request then carries no temperature,
and a warning says that reruns may give different intervals.

**Any other endpoint** works through `http`, with two functions you write:

```python
# myformat.py
def build_payload(system, user, *, model, temperature, max_tokens):
    return {"model": model, "prompt": system + user, "temperature": temperature}

def extract_text(response_json):
    return response_json["output"]["text"]
```

```yaml
# config/annotation.yaml
provider: http
model: in-house-model
provider_options:
  url: https://llm.example.internal/v1/generate
  build_payload: myformat.py:build_payload   # a file path, or module:function if importable
  extract_text: myformat.py:extract_text
  api_key_env: INHOUSE_LLM_KEY
  headers: {X-Team: propensities}
```

### Output

One row per instance, in input order, always, including the failures:

```jsonl
{"question_id": "RA_0", "dimension": "RA", "lower": -1, "upper": 3, "annotator": "openai:gpt-4.1", "explanation": "...", "parse_ok": true, "error": null, "parse_error": null, "parse_method": "final_range", "question_text": "..."}
```

- **`explanation`** is the model's full response, and the only audit trail. It is kept even when
  parsing fails.
- **`parse_ok`** is false when no valid interval could be read. **`parse_error`** says why, and
  such rows are excluded from fitting.
- **`error`** is set when the provider call itself failed.
- **`parse_method`** says how the interval was found. The model is asked to end with
  `<FINAL_RANGE>[lower, upper]</FINAL_RANGE>`, and the last such tag wins; two legacy patterns are
  tried before giving up.

The run ends with a summary such as `480 ok, 12 parse-failed, 8 provider-error out of 500 total`.
A 480/500 run is never mistaken for a 500/500 one.

**Cost** scales with instances × dimensions, and the rubric dominates the input tokens: each
prompt carries the full rubric, roughly 2,500 tokens for RA. It is paid once per instance set,
not per model evaluated.

## Fitting propensity levels

### Outcomes

Your models' results, one 0/1 outcome per (instance, model). Long form is preferred:

```csv
question_id,subject_id,outcome
RA_0,gpt-4o,1
RA_0,llama-3.3-70b,0
```

Wide form works too; the subject is the column name without `_outcome`:

```csv
question_id,gpt-4o_outcome,llama-3.3-70b_outcome
RA_0,1,0
```

A subject is whatever you measured: a model, or a model under a particular system prompt. The
file is read permissively and validated strictly:
- Outcomes must be 0 or 1; `true`/`false` and `"1"`/`"0"` are accepted. A probability such as
  0.7 is rejected, never rounded.
- A missing outcome stays missing and is **never** counted as a failure: an instance that
  produced no response is not one the model got wrong.
- Each `(question_id, subject_id)` pair must be unique.

Violations raise an error that names the offending rows.

Annotation files from earlier tooling are also read: `propensity_lower`/`propensity_upper`,
`lower_bound`/`upper_bound`, wide `{DIM}_l`/`{DIM}_u` columns, and `custom_id` or `instance_id`
for the id. A file without a `dimension` column needs its code on the command line, as
`--annotations RA=file.jsonl`.

### Running the fit

```bash
propel-fit --annotations RA=RA.jsonl Ex=Ex.jsonl --outcomes outcomes.csv --out profiles.csv \
    [--subjects gpt-4o llama-3.3-70b] [--dimensions RA] [--min-items 30] [--plots plots/]
```

Settings come from `config/modelling.yaml`, and flags override them. The fit is maximum
likelihood over a bell-shaped response model, with guarded restarts when the first attempt does
not converge.

The command prints the **join yield** first: how many annotated instances found outcomes. A
silently partial join, from mismatched ids, is the most common way this pipeline goes wrong. Then
it prints how many cells were fitted, and which cells carry warnings.

### The profile table

One row per (subject, dimension); one subject's profile is a filter on it.

| Column | Meaning |
|---|---|
| `theta`, `se`, `ci95_lower`, `ci95_upper` | the fitted level, its standard error and 95% confidence interval |
| `n_items` | instances joined for this cell |
| `converged` | whether the optimiser converged. **Read it together with the interval**: a tight interval around a fit that did not converge means nothing |
| `reference_ll`, `gof`, `pseudo_r2` | log-likelihood at `theta = 0` (an unbiased agent), at the fitted `theta`, and the improvement over it |
| `skip_reason` | why a cell was not fitted; its row is kept, with `theta` empty, rather than silently dropped |
| `frac_orthogonal`, `n_distinct_intervals`, `outcome_rate` | the diagnostics below |
| `n_attempts`, `n_converged`, `restart_theta_std` | restart statistics, when restarts were needed |
| `warnings` | every diagnostic this cell triggered |

### Diagnostics

These are how an unusable item bank is caught. Every fitted cell is checked:

| Diagnostic | Warns when | Why |
|---|---|---|
| `n_items` | below 50 (cells below `--min-items`, default 30, are not fitted) | the fit is unstable |
| `frac_orthogonal` | above 0.5; the cell is **refused** above 0.9 | an instance annotated `[-3, +3]` is solved at every level and carries no information |
| `n_distinct_intervals` | below 5 | too little variety to locate `theta` |
| `outcome_rate` | outside 5–95% | all-success or all-failure data has no interior maximum |
| `converged` | false | the interval is not trustworthy |
| `pseudo_r2` | negative | the fit explains the data worse than `theta = 0` |

### Plots

`--plots DIR` draws two figures per (subject, dimension) cell and two per dimension. The grids
share one convention: a cell that holds data is coloured and labelled, a valid but empty cell is
pale grey, and an impossible cell is blank.

Per cell (`save_profile_plots`), `{subject}_{dimension}_curve.png` and `..._surface.png`. Cells
that could not be fitted are drawn too, without an estimate.

- **Propensity curve.** The fraction of successes against the interval centre `(b_l + b_u)/2`,
  binned, with a LOWESS smooth. A solid line marks `theta` and dashed lines its confidence bounds.
  Points are jittered by ±0.25 for display only, never for fitting.
- **Propensity surface.** Success over the grid of interval bounds, `b_l` across and `b_u` up:
  - observed cells are coloured red to green by mean success and show their count;
  - valid but unobserved cells are pale grey;
  - impossible cells (`b_l > b_u`) are blank.

  The diagonal marks the intervals centred on `theta`. A bank whose observations sit in a few
  cells, or far from the diagonal, is visible at a glance.

Per dimension (`save_annotation_plots`), how the annotated intervals spread, before any model is
involved. Instances that failed to parse are left out, as they are from the fit.

- **Interval distribution**, `{dimension}_intervals.png`: each cell of the bounds grid shows its
  share of the bank.
- **Interval tree**, `{dimension}_tree.png`: the same intervals by centre across and length up.
  Zero-length intervals form the base and `[-3, +3]` is the tip, so a bank crowded with
  orthogonal instances shows up at once. An even length needs a whole centre and an odd one a
  half, so half the cells inside the outline are blank: no interval with whole-numbered bounds
  can land there. In Python, `show_invalid=True` fills those cells in light grey instead, so the
  whole grid stays visible.
- **All trees side by side**, `interval_trees.png`, when there are several dimensions, on one
  colour scale.

In Python, `plot_model_surface(build_model_surface(theta))` also draws the surface the response
model predicts for a given `theta`, in the empirical surface's colours and orientation. By
default it uses the empirical surface's integer grid, so the two can be compared cell for cell.
With `build_model_surface(theta, smooth=True)` it is a continuous surface instead, drawn as
filled contours with labelled lines at 0.25, 0.5 and 0.75.

## Before you trust a number

A fitted `theta` means something only once the chain has been shown to recover a level you already
know. This check exercises rubric quality, annotation fidelity and the fit together, per
dimension, and **producing its data is your job**, since PROPEL does not run models:

1. Take a model and **incite** it to a known level with an explicit system prompt, for example
   one describing a moderate preference for the safe option, for level `+2` on risk aversion.
   Do this for several levels, and for no incitement at all.
2. Run it over the annotated instances and record the 0/1 outcomes, one subject per level
   (`gpt-4o_RA_+2`, `gpt-4o_RA_-1`, …).
3. `propel-fit` them. Incited `+2` should come back as `theta ≈ +2`, `-1` as `≈ -1`, and so on.

Run this for each dimension before reading anything into an uninstructed model's profile. If the
incited levels do not come back, suspect the rubric or the annotations before the model.

## Python API

Everything the CLIs do is available as functions:

```python
from propensity import (annotate, get_provider, load_instances, load_rubric, load_presentation,
                        load_annotations, load_outcomes, fit_profiles, save_profile_plots)

rows = annotate(
    load_instances("items.jsonl"),
    provider=get_provider("anthropic", model="claude-haiku-4-5"),
    dimension="RA", propensity_name="risk aversion",
    rubric=load_rubric("RA"), presentation=load_presentation(),
    mode="auto",  # the batch API where the provider has one, one call at a time otherwise
)

annotations = load_annotations("RA_annotations.jsonl")
outcomes = load_outcomes("outcomes.csv")
profiles = fit_profiles(annotations, outcomes)          # a DataFrame, as in the table above
save_profile_plots(profiles, annotations, outcomes, "plots/")
```

For a single cell, `fit_theta(demands, success)` fits one `(N, 2)` array of intervals against one
array of outcomes. The `build_*` functions return plain data, and each `plot_*` function draws
its counterpart onto any matplotlib `Axes`:

| Data | Drawn by |
|---|---|
| `build_empirical_curve(demands, success)` | `plot_propensity_curve` |
| `build_empirical_surface(demands, success)` | `plot_propensity_surface` |
| `build_model_surface(theta, smooth=False)` | `plot_model_surface`: cells if not smooth, contours if smooth |
| `build_interval_distribution(demands)` | `plot_interval_distribution` |
| `build_interval_tree(demands)` | `plot_interval_tree`, or `plot_interval_trees({name: tree, …})` for several on one scale |

## Adding a provider

A provider is any object with `name`, `model`, and a `complete` method. The pipeline depends on
nothing else:

```python
from propensity.providers import Completion, get_provider, register_provider

class MyProvider:
    name = "mine"

    def __init__(self, model, *, api_key=None):
        self.model = model
        self.client = ...  # import the vendor SDK here, not at module level

    def complete(self, system, user, *, temperature=0.0, max_tokens=None):
        try:
            text = ...  # call the API; deliver `system` however the API expects it
        except Exception as exc:
            return Completion(text="", error=f"{type(exc).__name__}: {exc}")  # never raise
        return Completion(text=text)

register_provider("mine", MyProvider)
provider = get_provider("mine", model="m-1")
```

- **`complete` must not raise.** A failure comes back as a `Completion` with `error` set, so one
  bad call is recorded rather than ending a run.
- **For a native batch API**, also implement `submit_batch(requests, *, temperature, max_tokens)
  -> batch_id`, `poll_batch(batch_id) -> "pending" | "running" | "completed" | "failed" |
  "cancelled"`, and `fetch_batch(batch_id) -> {custom_id: Completion}`. Ship the batch-capable
  version as a separate class, so `isinstance(p, BatchCapable)` is always truthful.
- **To make it available to the CLI**, add the module to `propensity/providers/` and to the import
  line at the bottom of `propensity/providers/__init__.py`.

The adapters shipped are each under 120 lines of code, and a test holds them to it.

## Rubrics

`rubrics/{CODE}/{CODE}_v1.md` holds one rubric per dimension, and `rubrics/presentation.md` the
shared reasoning procedure and output contract. The rubric's wording determines every interval
ever fitted against it, which makes it the highest-leverage file in the project.

| Code | Trait | Rubric |
|---|---|---|
| `RA` | risk aversion | v1 |
| `Ex` | extraversion | v1 |
| `Ul` | ultracrepidarianism: asserting beyond one's competence | v1 |
| `BR` | blue vs red colour preference (literally coloured options) | v1 |
| `TD` | delay of gratification | **not yet written** |

The v1 files are copied from the prior implementation with only line endings changed, because
their wording produced the existing annotation data. Measured against the intended rubric
structure, they have known gaps, left for a v2:

- None of the four contains the propensity-range definition sentence word for word.
- Ex and Ul have no `[-3, +3]` (orthogonal) or `[0, 0]` (degenerate) full example.
- Ex's Level -3 and +3 headings are not written as saturating ("or below" / "or above").
- Ul's title is misspelled ("ULTRACREPIDARIANSIM").

Editing a rubric changes every prompt built from it, and annotations made with different wording
are not comparable. `tests/test_rubric_files.py` pins each file's hash, so a change cannot happen
by accident. Add a new version as `{CODE}_v2.md` and select it with `--rubric-version v2`.

## Development

```bash
python -m venv ~/.venvs/propel      # keep the environment outside synced folders such as OneDrive
~/.venvs/propel/Scripts/python -m pip install -e ".[dev,plot,openai,anthropic,google,http]"   # bin/ on Linux/macOS
~/.venvs/propel/Scripts/python -m pytest -q -W error
```

The tests make no network calls (a fixture refuses socket connections), need no credentials, and
run with any subset of the extras installed. Tests that drive a real vendor SDK or matplotlib
skip when it is absent. Each adapter is tested against a fake client, and also against its real
SDK over an in-memory HTTP transport.

The design specification is [CLAUDE.md](CLAUDE.md), and [PLAN.md](PLAN.md) records how the build
went, phase by phase, with every deviation from the specification.
