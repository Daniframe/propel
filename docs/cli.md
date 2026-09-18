# Command line

Two commands, installed with the package:

| Command | Does |
|---|---|
| [`propel-annotate`](#propel-annotate) | instances + rubric → one demand interval per instance |
| [`propel-fit`](#propel-fit) | intervals + outcomes → a profile table (and, optionally, plots) |

Both are also runnable as modules: `python -m propensity.cli.annotate`, `python -m propensity.cli.fit`.

Results go to stdout, and progress, warnings and errors to stderr.

## `propel-annotate`

```
propel-annotate {run,submit,status,fetch} ...
```

| Subcommand | Does |
|---|---|
| [`run`](#run) | one call per instance, in parallel; writes the rows when done |
| [`submit`](#submit) | sends every instance as one batch through the provider's batch API; writes a job file |
| [`status`](#status) | reports a submitted batch's state |
| [`fetch`](#fetch) | collects a finished batch into rows |

`run` works with every provider. `submit`, `status` and `fetch` need a batch-capable one
(`openai`, `azure`, `anthropic`, or `mock` with `batch=true`). Batches cost about half as
much, and take minutes to hours.

With the `dotenv` extra installed, every subcommand first loads `.env` from the working
directory.

### Options shared by `run` and `submit`

| Flag | Required | Default | Meaning |
|---|---|---|---|
| `--instances PATH` | yes | | instances file, `.jsonl` or `.csv` ([format](data-formats.md#instances)) |
| `--dimension CODE` | yes | | dimension code, e.g. `RA` ([all codes](dimensions.md)); selects the rubric `{CODE}/{CODE}_{version}.md` |
| `--out PATH` | yes | | where to write the rows, `.jsonl` or `.csv` ([format](data-formats.md#annotations)) |
| `--provider NAME` | yes, here or in the config | config `provider` | `openai`, `azure`, `anthropic`, `google`, `http`, `mock` |
| `--model NAME` | yes, here or in the config | config `model` | model name; for `azure`, the deployment name |
| `--provider-option KEY=VALUE` | no | config `provider_options` | provider argument; repeatable ([Providers](providers.md)) |
| `--propensity-name TEXT` | no | the catalogue's name | the trait's name as the prompt words it; needed only for a dimension the catalogue does not list |
| `--rubrics-dir DIR` | no | the packaged rubrics | a rubrics directory of your own ([layout](managing-rubrics.md#rubrics-outside-the-package)) |
| `--rubric-version V` | no | the catalogue's current version | e.g. `v1` to reproduce annotations made with an older version |
| `--max-workers N` | no | `8` | parallel calls (`run` only) |
| `--max-retries N` | no | `3` | retries per instance after a provider error (`run` only) |
| `--config PATH` | no | `config/annotation.yaml` | settings file ([Configuration](configuration.md)) |

`--provider-option` values: `true`/`false` become booleans, `none`/`null` become `None`, and
numbers become numbers. Everything else stays a string.

### `run`

```bash
propel-annotate run --instances examples/items_RA.jsonl --dimension RA --out out/RA.jsonl \
    --provider openai --model gpt-4.1
```

```
annotated 25/120
annotated 50/120
...
annotated 120/120
120 ok, 0 parse-failed, 0 provider-error out of 120 total
wrote out/RA.jsonl
```

- **Progress** goes to stderr every 25 instances.
- **Retries.** A provider error is retried up to `--max-retries` times, waiting 1, 2, 4… seconds.
  A response that fails to parse is not retried: at temperature 0 it would come back the same.
- **Every instance gets a row**, in input order, including failures. Read the summary line: a
  480/500 run is not a 500/500 run. [Tutorial 3](tutorials/03-annotating-with-a-provider.md)
  shows how to rerun only the failures.
- The rows are written once, at the end.

### `submit`

```bash
propel-annotate submit --instances examples/items_RA.jsonl --dimension RA --out out/RA.jsonl \
    --provider anthropic --model claude-haiku-4-5
```

```
submitted batch msgbatch_01H... with 120 requests
wrote out/RA.jsonl.job.json
next: propel-annotate status --job out/RA.jsonl.job.json
```

| Extra flag | Meaning |
|---|---|
| `--wait` | poll every `poll_interval_s` seconds (config, default 60) until the batch ends, then fetch it |

- **The job file** `<out>.job.json` is written **before** any polling
  ([format](data-formats.md#job-files)). A `--wait` that is interrupted loses nothing: carry on
  with `status` and `fetch`.
- **An unsupported provider** fails with `provider '…' has no batch API; use mode='sequential'`:
  use `run` instead.

### `status`

```bash
propel-annotate status --job out/RA.jsonl.job.json
```

```
batch msgbatch_01H...: completed
  120 requests for RA via anthropic:claude-haiku-4-5, submitted 2026-09-18T10:02:11+00:00
  next: propel-annotate fetch --job out/RA.jsonl.job.json
```

| Flag | Meaning |
|---|---|
| `--job PATH` | the job file `submit` wrote (required) |
| `--config PATH` | accepted for symmetry; the job file holds every setting |

The state is one of `pending`, `running`, `completed`, `failed` or `cancelled`.

### `fetch`

```bash
propel-annotate fetch --job out/RA.jsonl.job.json
```

```
120 ok, 0 parse-failed, 0 provider-error out of 120 total
wrote out/RA.jsonl
```

| Flag | Meaning |
|---|---|
| `--job PATH` | the job file (required) |
| `--out PATH` | write somewhere other than the job's `out` |
| `--force` | fetch even though the prompts no longer match the ones submitted |
| `--config PATH` | accepted for symmetry; the job file holds every setting |

Before fetching, `fetch` rebuilds every prompt from the job's instances file, rubric and trait
name. If they changed since `submit`, it refuses: the rows would be attributed to prompts that
were never sent. `--force` overrides this.

Other behaviour:
- **A batch still running:** prints `batch … is running; nothing to fetch yet` and exits 1.
- **A batch that failed or was cancelled:** prints `batch … ended as failed; nothing to fetch.
  Submit it again.` and exits 1.
- **An instance missing from the batch output:** it becomes a provider-error row
  (`missing from the batch output`).
- **An id in the output that was never sent:** reported as a warning and dropped.

### Exit codes

| Code | When |
|---|---|
| 0 | rows or a job file were written (check the summary line for failures) |
| 1 | `fetch`: the batch has not finished, or ended as `failed` or `cancelled` |
| 2 | bad input or setup, reported on one line starting with `error:` |

Exit code 2 covers:
- a missing file, rubric, trait name, provider or model;
- invalid instances;
- an unknown provider or an option it does not take;
- a missing SDK, which the error names with its extra;
- credentials the SDK rejects at start-up;
- a provider without batching for `submit`;
- prompts that drifted since `submit`, for `fetch`;
- an invalid command line.

## `propel-fit`

```
propel-fit --annotations [CODE=]PATH [[CODE=]PATH ...] --outcomes PATH --out PATH [options]
```

```bash
propel-fit --annotations examples/annotations_RA.jsonl --outcomes examples/outcomes_long.csv \
    --out out/profiles.csv
```

```
join yield RA: 117/117 annotated instances have outcomes (100%)
3 annotation rows were unusable (failed to parse, or a null bound)
3 outcome question_ids have no annotation
fitted 4 of 4 (subject, dimension) cells
wrote out/profiles.csv
```

| Flag | Default | Meaning |
|---|---|---|
| `--annotations [CODE=]PATH ...` | required | one or more annotation files. Prefix `CODE=` for a file with no `dimension` column; a file with one needs no prefix |
| `--outcomes PATH` | required | outcomes file, long or wide ([format](data-formats.md#outcomes)) |
| `--out PATH` | required | the profile table, `.csv` or `.jsonl` ([format](data-formats.md#profiles)) |
| `--subjects ID ...` | every subject in the outcomes | fit only these |
| `--dimensions CODE ...` | every annotated dimension | fit only these |
| `--min-items N` | config `profiles.min_items`, 30 | cells with fewer joined instances are recorded, not fitted |
| `--likelihood {sum,product}` | config, `sum` | `product` only to reproduce published numbers exactly |
| `--no-robust` | robust on | one fit attempt, no restarts |
| `--plots DIR` | off | also write the figures below (needs the `plot` extra) |
| `--config PATH` | `config/modelling.yaml` | settings file ([Configuration](configuration.md#configmodellingyaml)) |

Every annotation file is loaded, normalised and concatenated, so dimensions and legacy shapes
can be mixed:

```bash
propel-fit --annotations RA=legacy_ra.jsonl Ex=legacy_ex.csv all_dims.jsonl --outcomes results.csv --out profiles.csv
```

**On stderr**, `propel-fit` also reports:
- dropped missing outcomes, as an `INFO` line;
- a low join yield (below 90% for a dimension), as a `warning:` line;
- cells under 50 instances, as a `warning:` line.

**On stdout**, the report lists:
- up to 10 skipped cells, with their reasons;
- up to 3 cells that carry diagnostic warnings;
- how many fitted cells did not converge.

The profile table holds every diagnostic for every cell.

### `--plots DIR`

Checked before fitting, so a missing `plot` extra fails fast. For each (subject, dimension)
cell with joined data, and for each dimension:

| File | Figure |
|---|---|
| `{subject}_{dimension}_curve.png` | propensity curve |
| `{subject}_{dimension}_surface.png` | propensity surface |
| `{dimension}_intervals.png` | how the dimension's intervals spread over the bounds grid |
| `{dimension}_tree.png` | the same by centre and length (the "Christmas tree") |
| `interval_trees.png` | every dimension's tree on one colour scale (two or more dimensions) |

- **Cells not fitted** are drawn too, without an estimate and with the reason in the title.
- **Filenames** are made safe, keeping signed levels such as `_+2` readable. Names that would
  collide get a numeric suffix.
- **A figure that fails** is logged and skipped.

[Plots](plots.md) explains how to read each figure.

### Exit codes

| Code | When |
|---|---|
| 0 | the profile table was written |
| 2 | bad input, reported on one line starting with `error:`, or `--plots` without the `plot` extra |
