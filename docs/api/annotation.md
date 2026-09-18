# `propensity.annotation`

Turning instances into demand intervals: rubric files, prompt assembly, response parsing, and
the runner that drives a provider.

- [Rubrics](#rubrics): `load_rubric`, `load_presentation`, `rubric_path_for`, `available_dimensions`, `available_versions`, `check_rubric`
- [The catalogue](#the-catalogue): `load_dimensions`, `get_dimension`, `Dimension`
- [Prompts](#prompts): `build_annotation_prompt`, `as_single_string`
- [Parsing](#parsing): `parse_final_range`, `ParsedRange`
- [Runner](#runner): `annotate` and its building blocks

## Rubrics

`propensity.annotation.rubrics`. Every function takes an optional `rubrics_dir`: the rubrics
that ship with the package by default, or a directory of your own with the same layout
([Managing rubrics](../managing-rubrics.md)).

| Constant | Value |
|---|---|
| `RUBRICS_DIR` | the installed `propensity/rubrics/` directory |
| `PRESENTATION_FILE` | `"presentation.md"` |
| `CATALOGUE_FILE` | `"dimensions.yaml"` |
| `DEFAULT_VERSION` | `"v1"`: the version for a dimension the catalogue does not list |

```python
load_rubric(code, rubrics_dir=None, version=None) -> str
load_presentation(rubrics_dir=None) -> str
rubric_path_for(code, rubrics_dir=None, version=None) -> Path
available_dimensions(rubrics_dir=None, version=None) -> list[str]
available_versions(code, rubrics_dir=None) -> list[str]
check_rubric(text) -> list[str]
```

| Function | Returns |
|---|---|
| `load_rubric` | the text of `{rubrics_dir}/{code}/{code}_{version}.md`, as stored. Without `version`, the catalogue's current one |
| `load_presentation` | the text of `{rubrics_dir}/presentation.md` |
| `rubric_path_for` | the path `load_rubric` reads |
| `available_dimensions` | sorted codes with at least one rubric file, or with a rubric of `version` when given |
| `available_versions` | one dimension's versions on disk, oldest first (`v2` before `v10`) |
| `check_rubric` | the ways a rubric's text departs from the [required structure](../rubrics.md#rubric-structure); `[]` when there are none |

**Raises** `ContractError` when:
- the dimension has no rubric (the message lists the dimensions that exist);
- it has no rubric of that version (the message lists its versions);
- the file is not valid UTF-8.

```python
from propensity.annotation import available_dimensions, available_versions, check_rubric, load_rubric

available_dimensions()                  # ['BR', 'Ex', 'RA', 'Ul']
available_versions("RA")                # ['v1']
rubric = load_rubric("RA")              # the current version
check_rubric(rubric)                    # []
```

## The catalogue

Each rubrics directory may hold a `dimensions.yaml`: one entry per dimension, giving its trait
name, poles and current version ([format](../managing-rubrics.md#the-catalogue)).

```python
load_dimensions(rubrics_dir=None) -> dict[str, Dimension]
get_dimension(code, rubrics_dir=None) -> Dimension
```

| Function | Returns |
|---|---|
| `load_dimensions` | every entry, keyed by code; `{}` for a directory without a catalogue |
| `get_dimension` | one entry. Raises `ContractError` for an unknown code, naming the known ones |

A catalogue that is not valid YAML, has an entry that is not a mapping, or has a missing or
unknown field raises `ContractError` naming the entry.

### `Dimension`

Frozen dataclass.

| Field | Meaning |
|---|---|
| `code` | the dimension's code and folder name, e.g. `RA` |
| `name` | the trait as the prompt words it, e.g. `risk aversion` |
| `negative`, `positive` | what `-3` and `+3` mean |
| `version` | the rubric version used unless another is asked for |
| `summary` | one line describing the trait |

```python
from propensity import get_dimension, load_rubric, load_presentation, build_annotation_prompt

dimension = get_dimension("RA")
system, user = build_annotation_prompt(dimension.name, load_rubric(dimension.code),
                                       load_presentation(), "Choose: $100 now or a 50% chance of $220.")
```

## Prompts

`propensity.annotation.prompts`.

### `build_annotation_prompt`

```python
build_annotation_prompt(propensity_name, rubric, presentation, question_text) -> tuple[str, str]
```

Returns `(system, user)` for one instance:
- `system` is `ANNOTATION_SYSTEM`;
- `user` is the rubric preamble, the rubric, the presentation block and the question, joined
  byte for byte ([Prompt assembly](../rubrics.md#prompt-assembly)).

| Parameter | Meaning |
|---|---|
| `propensity_name` | the trait in words, e.g. `"risk aversion"` |
| `rubric` | the rubric text, from `load_rubric` |
| `presentation` | the presentation block, from `load_presentation` |
| `question_text` | the instance's text |

`ANNOTATION_SYSTEM = "You are an expert at analyzing questions for cognitive biases."`

### `as_single_string`

```python
as_single_string(system, user) -> str
```

`system + user`, for an API with a single input field. Use it inside a custom provider's
`build_payload` or `complete`.

## Parsing

`propensity.annotation.parsing`.

### `parse_final_range`

```python
parse_final_range(text) -> ParsedRange
```

Reads the demand interval from a response ([Parsing rules](../rubrics.md#parsing)):
- it tries `<FINAL_RANGE>[a, b]</FINAL_RANGE>`, then `The propensity range is [a, b]`, then any
  `[a, b]`;
- it takes the last match of the first pattern found;
- it requires `-3 ≤ a ≤ b ≤ 3`;
- it never raises.

```python
from propensity import parse_final_range

parse_final_range("... <FINAL_RANGE>[-1, +2]</FINAL_RANGE>")
# ParsedRange(lower=-1, upper=2, parse_ok=True, method='final_range', error=None)
parse_final_range("<FINAL_RANGE>[4, 1]</FINAL_RANGE>")
# ParsedRange(lower=None, upper=None, parse_ok=False, method='final_range',
#             error='[4, 1] violates -3 <= lower <= upper <= 3')
parse_final_range("no answer")
# ParsedRange(lower=None, upper=None, parse_ok=False, method=None,
#             error='no propensity range found in the response')
```

### `ParsedRange`

Frozen dataclass.

| Field | Type | Meaning |
|---|---|---|
| `lower`, `upper` | int or None | the bounds; None unless `parse_ok` |
| `parse_ok` | bool | a valid interval was found |
| `method` | str or None | `final_range`, `legacy_phrase`, `legacy_bracket`, or None |
| `error` | str or None | why parsing failed |

Constants: `PATTERNS` (the three `(method, compiled regex)` pairs, in order), `SCALE = (-3, 3)`.

## Runner

`propensity.annotation.runner`. Constants:
- `ROW_FIELDS`: the ten canonical row fields, in order;
- `MODES = ("auto", "batch", "sequential")`;
- `DONE_STATES = ("completed", "failed", "cancelled")`.

### `annotate`

```python
annotate(instances, *, provider, dimension, propensity_name, rubric, presentation,
         mode="auto", temperature=0.0, max_tokens=None, max_workers=8, max_retries=3,
         on_progress=None, retry_backoff=1.0, poll_interval=60.0) -> list[dict]
```

Annotates every instance on one dimension with one provider.

| Parameter | Default | Meaning |
|---|---|---|
| `instances` | required | list of dicts with `question_id` and `question_text`, e.g. from `load_instances` |
| `provider` | required | any [`LLMProvider`](providers.md#protocol), e.g. from `get_provider` |
| `dimension` | required | dimension code written on every row |
| `propensity_name` | required | the trait in words, inserted into the prompt; for a catalogued dimension, `get_dimension(code).name` |
| `rubric`, `presentation` | required | texts from `load_rubric(code)`, `load_presentation()` |
| `mode` | `"auto"` | `"sequential"`: one call per instance; `"batch"`: the provider's batch API (raises if it has none); `"auto"`: batch when available, else sequential |
| `temperature` | `0.0` | anything else logs a warning: intervals will not be stable across reruns |
| `max_tokens` | `None` | response cap passed to the provider; None leaves it to the provider |
| `max_workers` | `8` | threads for the sequential path |
| `max_retries` | `3` | retries per instance after a provider error (sequential path) |
| `on_progress` | `None` | `callable(done, total)`, called after each instance (sequential path) |
| `retry_backoff` | `1.0` | first retry delay in seconds, doubling each attempt; 0 disables waiting |
| `poll_interval` | `60.0` | seconds between polls (batch path) |

**Returns** one row per instance, in input order, including failures
([row format](../data-formats.md#annotations)). It also prints the summary line
`N ok, N parse-failed, N provider-error out of N total`.

**Raises**:
- `ContractError` for a missing, empty or duplicate `question_id`, or a missing or empty
  `question_text`;
- `ProviderError` for `mode="batch"` on a provider without a batch API;
- `ValueError` for an unknown `mode`.

**Batch path.** The batch path submits, waits (`poll_interval`), and collects:
- a batch that ends `failed` or `cancelled` gives a provider-error row for every instance;
- an instance missing from the output becomes a provider-error row;
- ids that were never sent are warned about and dropped.

Unlike the CLI's `submit`, it blocks until the batch finishes.

### Building blocks

The pieces `annotate` composes, for custom workflows such as submitting in one process and
fetching in another.

```python
build_requests(instances, *, propensity_name, rubric, presentation) -> list[BatchRequest]
```
One `BatchRequest(custom_id=question_id, system, user)` per instance. Validates ids and texts
exactly as `annotate` does.

```python
run_sequential(provider, requests, *, temperature=0.0, max_tokens=None, max_workers=8,
               max_retries=3, retry_backoff=1.0, on_progress=None) -> dict[str, Completion]
```
One `complete` call per request, in a thread pool. Provider errors are retried with backoff;
parse failures are not (nothing is parsed here). The result is keyed by `custom_id`.

```python
submit(provider, requests, *, temperature=0.0, max_tokens=None) -> str
wait_for_batch(provider, batch_id, *, poll_interval=60.0) -> str
collect(provider, batch_id, requests=None) -> dict[str, Completion]
require_batch(provider) -> None
```

| Function | Does |
|---|---|
| `submit` | sends the requests as one batch; returns the batch id |
| `wait_for_batch` | polls until the state is in `DONE_STATES`, and returns it |
| `collect` | fetches a finished batch, keyed by `custom_id`. Given `requests`, ids never sent are warned about (`DataWarning`) and dropped |
| `require_batch` | raises `ProviderError` unless the provider is `BatchCapable`; all three above call it |

```python
rows_from_completions(instances, completions, *, dimension, annotator) -> list[dict]
```

Parses each completion and returns the rows:
- one row per instance, in input order;
- an instance without a completion gets `error = "missing from the batch output"`;
- `annotator` is written on every row, conventionally `f"{provider.name}:{provider.model}"`.

```python
summarise(rows) -> str
```
The summary line: `"N ok, N parse-failed, N provider-error out of N total"`.

```python
from propensity.annotation import build_requests, collect, rows_from_completions, submit

requests = build_requests(instances, propensity_name="risk aversion", rubric=rubric,
                          presentation=presentation)
batch_id = submit(provider, requests)
# ... later, possibly in another process ...
if provider.poll_batch(batch_id) == "completed":
    rows = rows_from_completions(instances, collect(provider, batch_id, requests),
                                 dimension="RA", annotator=f"{provider.name}:{provider.model}")
```
