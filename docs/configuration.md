# Configuration

Each command reads one YAML file. Settings resolve in this order, last wins:

1. built-in defaults;
2. the YAML file (`--config`, default `config/annotation.yaml` or `config/modelling.yaml`,
   relative to the working directory);
3. command-line flags.

A missing YAML file is not an error: the defaults apply. Unknown keys are ignored.
Credentials never go in these files ([Credentials](installation.md#credentials)).

## `config/annotation.yaml`

Read by `propel-annotate run` and `submit`.

```yaml
provider: openai
model: gpt-4.1
provider_options: {}

temperature: 0.0
max_tokens: null
max_workers: 8
max_retries: 3
poll_interval_s: 60

# optional overrides; by default the packaged rubrics and their catalogue decide
# rubrics_dir: my_rubrics
# rubric_version: v2
# dimensions:
#   TD: delay of gratification
```

| Key | Default | Flag | Meaning |
|---|---|---|---|
| `provider` | none | `--provider` | provider name: `openai`, `azure`, `anthropic`, `google`, `http`, `mock` |
| `model` | none | `--model` | model name; for `azure`, the deployment name |
| `provider_options` | `{}` | `--provider-option KEY=VALUE` (repeatable, merged on top) | keyword arguments for the provider ([Providers](providers.md)) |
| `temperature` | `0.0` | none | sampling temperature. Keep 0: intervals must be stable across reruns |
| `max_tokens` | `null` | none | response length cap; `null` leaves it to the provider (Anthropic then uses 16000) |
| `max_workers` | `8` | `--max-workers` | parallel calls for `run` |
| `max_retries` | `3` | `--max-retries` | retries per instance after a provider error, for `run` |
| `poll_interval_s` | `60` | none | seconds between polls for `submit --wait` |
| `rubrics_dir` | the packaged rubrics | `--rubrics-dir` | a directory of your own holding `presentation.md`, `{CODE}/{CODE}_{version}.md` and, optionally, `dimensions.yaml` |
| `rubric_version` | the catalogue's current version | `--rubric-version` | which rubric file to read |
| `dimensions` | the catalogue's names | `--propensity-name` | dimension code → the trait's name as the prompt words it |

**Trait names and versions come from the catalogue.** The rubrics' catalogue
(`propensity/rubrics/dimensions.yaml`, [Managing rubrics](managing-rubrics.md#the-catalogue))
gives every shipped dimension its trait name and current rubric version. Override them only
deliberately:
- **The trait name is prompt text.** It is inserted into the prompt ("…showing bias towards
  risk aversion"), so a different name means different prompts, and annotations that are not
  comparable. `dimensions:` and `--propensity-name` exist for dimensions the catalogue does not
  list.
- **A dimension with no name** from the flag, the file or the catalogue is an error.

**`provider_options` versus `--provider-option`.** Flags are merged over the file.
`--provider-option` converts `true`/`false` to booleans, `none`/`null` to `None`, and numbers
to numbers; everything else stays a string. Options that take a dictionary, such as
`request_options`, `config_options` or `headers`, can only be given in the YAML file.

```bash
propel-annotate run ... --provider-option base_url=http://localhost:8000/v1 --provider-option send_temperature=false
```

`status` and `fetch` do not read the provider settings from this file: they rebuild the
provider from the job file ([Job files](data-formats.md#job-files)).

## `config/modelling.yaml`

Read by `propel-fit`.

```yaml
propensity:
  min_width: 0.1
  rho: 2.0
  k_default: 1.0
  n_bins: 20
  lowess_frac: 0.4
  maxiter: 500
  robust: true
  restart_range: [-5.0, 5.0]
  likelihood: sum

profiles:
  min_items: 30
```

| Key | Default | Flag | Meaning |
|---|---|---|---|
| `propensity.min_width` | `0.1` | none | intervals narrower than this are widened outwards before computing steepness |
| `propensity.rho` | `2.0` | none | how fast steepness grows as an interval narrows |
| `propensity.k_default` | `1.0` | none | base slope of the response model |
| `propensity.n_bins` | `20` | none | bins for the starting-point curve, and for `--plots` curves |
| `propensity.lowess_frac` | `0.4` | none | LOWESS bandwidth for the same |
| `propensity.maxiter` | `500` | none | optimiser iterations per attempt |
| `propensity.robust` | `true` | `--no-robust` | guarded restarts when the first attempt does not converge |
| `propensity.restart_range` | `[-5, 5]` | none | bounds for the restarts |
| `propensity.likelihood` | `sum` | `--likelihood` | `sum` (stable) or `product` (only to reproduce published numbers exactly) |
| `profiles.min_items` | `30` | `--min-items` | cells with fewer joined instances are recorded but not fitted |

The same settings are keyword arguments of `fit_theta` and `fit_profiles` in Python
([API](api/modelling.md#fit_theta)), where `k_default` is `k`.

## Environment variables

| Variable | Used by |
|---|---|
| `OPENAI_API_KEY` | `openai` |
| `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` | `azure` |
| `ANTHROPIC_API_KEY` | `anthropic` |
| `GEMINI_API_KEY`, `GOOGLE_API_KEY` | `google` |
| any name | `http`, via `api_key_env` |
| `MPLBACKEND` | matplotlib; set to `Agg` for headless drawing in your own scripts (the `save_*` functions and `--plots` never need a display) |

Every provider takes `api_key_env` to read a different variable, and `api_key` to pass the key
directly (Python only; keep keys out of command lines). With the `dotenv` extra installed,
`propel-annotate` loads `.env` from the working directory first.

## Using files from elsewhere

```bash
propel-annotate run --config ~/propel/annotation.yaml --rubrics-dir ~/propel/rubrics ...
propel-fit --config ~/propel/modelling.yaml ...
```
