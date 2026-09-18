# Providers

A provider is the LLM that annotates instances. PROPEL ships six:

| Name | Extra | Credentials | Batch API | System prompt sent as |
|---|---|---|---|---|
| [`openai`](#openai) | `openai` | `OPENAI_API_KEY` | official endpoint: yes; other servers: detected | a `system` message |
| [`azure`](#azure) | `azure` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` | yes (Global Batch deployments) | a `system` message |
| [`anthropic`](#anthropic) | `anthropic` | `ANTHROPIC_API_KEY` | yes (Message Batches) | the top-level `system` parameter |
| [`google`](#google) | `google` | `GEMINI_API_KEY` | no | `system_instruction` |
| [`http`](#http) | `http` | your choice | no | however your `build_payload` sends it |
| [`mock`](#mock) | none | none | with `batch=true` | (scripted; nothing is sent) |

From the command line, name the provider with `--provider` and pass its options with
`--provider-option KEY=VALUE`, or under `provider_options:` in `config/annotation.yaml`.
From Python:

```python
from propensity import get_provider

provider = get_provider("openai", model="gpt-4.1")
provider = get_provider("anthropic", model="claude-haiku-4-5", batch=False)
```

## Options every provider takes

| Option | Meaning |
|---|---|
| `model` | the model name (`--model`); for `azure`, the deployment name |
| `api_key` | the key itself. Python only: keep keys off command lines and out of files |
| `api_key_env` | read the key from this environment variable instead of the default |
| `client` | Python only: an already-built SDK client, used as is |

Beyond these:
- `openai`, `azure`, `anthropic` and `google` pass every other keyword to their SDK's client
  constructor, e.g. `timeout`, `max_retries`, `default_headers`.
- `http` and `mock` take only the options listed in their sections.

**An unknown option fails at start-up.** The CLI reports
`could not start the '…' provider: TypeError: … unexpected keyword argument '…'`.

## Temperature

Annotation runs at temperature 0, so that an instance gets the same interval every time.
Some models reject the parameter:
- recent Claude Opus and Sonnet models reject it outright, or reject any value but the default;
- OpenAI's reasoning models accept only the default.

Such a model fails every call, and every row becomes a provider error; nothing is dropped
silently. To use one, turn temperature off:

```bash
propel-annotate run ... --provider anthropic --model claude-opus-5 --provider-option send_temperature=false
```

With `send_temperature=false` the request carries no temperature, and PROPEL logs a warning:
reruns may give slightly different intervals. `openai`, `azure`, `anthropic` and `google` take
this option.

## `openai`

OpenAI's Chat Completions API, and anything that speaks it.

| Option | Default | Meaning |
|---|---|---|
| `base_url` | OpenAI | another OpenAI-compatible server |
| `api_key_env` | `OPENAI_API_KEY` | |
| `send_temperature` | `true` | see [Temperature](#temperature) |
| `request_options` | `{}` | merged into every request body, e.g. `{"seed": 7}` or `{"max_completion_tokens": 8000}` |
| `batch` | detected | `true` or `false` forces the choice ([below](#batching)) |
| any other | | passed to `openai.OpenAI(...)`: `timeout`, `max_retries`, `organization`, `project`, `default_headers`, `http_client` |

The request is `{"model", "messages": [system, user], "temperature": 0}`. It carries
`max_tokens` only when you set `max_tokens` in the configuration. Reasoning models want
`max_completion_tokens` instead: pass it in `request_options`, and leave `max_tokens` unset.

### Other servers

| Server | `base_url` | Notes |
|---|---|---|
| vLLM | `http://HOST:8000/v1` | `--model` is the served model name |
| Ollama | `http://localhost:11434/v1` | any non-empty `api_key`, e.g. `ollama`; raise the context window (`num_ctx`) above the prompt length, about 2,500 tokens for RA |
| LM Studio | `http://localhost:1234/v1` | any non-empty `api_key` |
| OpenRouter | `https://openrouter.ai/api/v1` | `api_key_env=OPENROUTER_API_KEY` |
| Together | `https://api.together.xyz/v1` | `api_key_env=TOGETHER_API_KEY` |

The OpenAI client refuses to start without some key. For a local server that needs none, pass
a placeholder:

```bash
propel-annotate run ... --provider openai --model llama3 \
    --provider-option base_url=http://localhost:11434/v1 --provider-option api_key=ollama
```

### Batching

- **The official endpoint** has the Files and Batches APIs, so `get_provider("openai", ...)`
  is batch-capable.
- **A custom `base_url`** is probed once with a `batches.list` call, and is batch-capable only
  if that succeeds. Most local servers have no batch API.
- **`batch=true` or `batch=false`** skips the probe.

## `azure`

Azure OpenAI, through the v1 API at `{endpoint}/openai/v1/`.

| Option | Default | Meaning |
|---|---|---|
| `endpoint` | `$AZURE_OPENAI_ENDPOINT` | the resource endpoint, e.g. `https://my-resource.openai.azure.com` |
| `endpoint_env` | `AZURE_OPENAI_ENDPOINT` | read the endpoint from another variable |
| `api_key_env` | `AZURE_OPENAI_API_KEY` | |
| `api_version` | none | for a resource still on dated API versions, e.g. `2024-10-21`; switches to `openai.AzureOpenAI` |
| `base_url` | derived from the endpoint | the full v1 URL, overriding the endpoint |
| `send_temperature`, `request_options` | | as for `openai` |
| `batch` | `true` | `false` for a standard (non-batch) deployment |
| any other | | passed to the OpenAI client |

- **`--model` is the deployment name,** not the model name. Every request and every batch line
  uses it.
- **Batches need a Global Batch deployment.** A probe cannot tell the two deployment types
  apart, so the choice is yours: `batch=false` for a standard deployment, which then works
  with `run`.
- **A missing endpoint** is reported before anything is sent.

## `anthropic`

Anthropic's Messages API.

| Option | Default | Meaning |
|---|---|---|
| `api_key_env` | `ANTHROPIC_API_KEY` | |
| `send_temperature` | `true` | `false` for models that reject temperature ([above](#temperature)) |
| `request_options` | `{}` | merged into every request, e.g. `{"metadata": {"user_id": "lab"}}` |
| `batch` | `true` | Message Batches; `false` for the plain provider |
| any other | | passed to `anthropic.Anthropic(...)`: `timeout`, `max_retries`, `base_url` |

- **`max_tokens` is always sent,** 16000 unless configured. Current models reason before
  answering, and the reasoning counts against it. A response cut off by the limit becomes a
  provider error: `stopped at max_tokens before finishing; raise max_tokens`.
- **A refusal** becomes a provider error: `the model declined the request`.
- **Only text blocks form the answer.** Other content blocks, such as reasoning, are kept in
  the raw response but not parsed.
- **Batch ids.** Message Batches accepts ids of 1 to 64 letters, digits, `-` and `_`. `submit`
  refuses, before sending anything, when a `question_id` does not fit. Rename the instances,
  or use `run`.
- **In a batch,** results that errored, were cancelled or expired become provider-error rows.
- **Server-side model fallbacks are never enabled.** A fallback would change which model
  annotated, and make the `annotator` field false.

| Model | Temperature |
|---|---|
| `claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-6` | accepted |
| `claude-opus-5`, `claude-sonnet-5`, and Opus 4.7 or later | pass `send_temperature=false` |

## `google`

Google Gemini through the `google-genai` SDK.

| Option | Default | Meaning |
|---|---|---|
| `api_key_env` | `GEMINI_API_KEY` | unset: the SDK also reads `GOOGLE_API_KEY` |
| `send_temperature` | `true` | |
| `config_options` | `{}` | merged into every request's config, e.g. `{"thinking_config": {"thinking_budget": 0}}` or `safety_settings` |
| any other | | passed to `genai.Client(...)`, e.g. `http_options` |

- **The request.** The system part goes as `system_instruction`, the configured `max_tokens`
  as `max_output_tokens`, and the SDK's automatic function calling is switched off.
- **An empty response** becomes a provider error naming its finish reason, e.g.
  `the provider returned an empty response (finish reason SAFETY)`.
- **Not batch-capable:** use `run`.

## `http`

Any endpoint the others do not cover. You provide two functions:

```python
# myformat.py
def build_payload(system, user, *, model, temperature, max_tokens):
    """The JSON body for one prompt. Deliver the system part however the endpoint expects it."""
    return {"model": model, "system": system, "prompt": user,
            "temperature": temperature, "max_tokens": max_tokens or 4096}


def extract_text(response_json):
    """The answer text from the endpoint's JSON response."""
    return response_json["output"]["text"]
```

| Option | Default | Meaning |
|---|---|---|
| `url` | required | the endpoint; each prompt is POSTed to it as JSON |
| `build_payload` | required | a callable, or `"path/to/file.py:function"`, or `"module:function"` |
| `extract_text` | required | same forms |
| `headers` | `{}` | extra request headers (YAML or Python: a mapping) |
| `api_key` / `api_key_env` | none | when set, sent as `Authorization: Bearer <key>` |
| `timeout` | `120` | seconds per request |
| `client` | a new `httpx.Client` | Python only |

```yaml
# config/annotation.yaml
provider: http
model: in-house-model
provider_options:
  url: https://llm.example.internal/v1/generate
  build_payload: myformat.py:build_payload
  extract_text: myformat.py:extract_text
  api_key_env: INHOUSE_LLM_KEY
  headers: {X-Team: propensities}
```

- **Naming the functions.** `path/to/file.py:function` loads the file directly. A path with a
  drive letter, `C:\...\fmt.py:build`, works too: the last colon separates the function.
  `module:function` needs the module to be importable. A console script does not put the
  working directory on the import path, so prefer the file form for your own files.
- **Errors.** A failed request, an HTTP error status, a non-JSON body, or an `extract_text`
  that raises all become provider errors, with the response kept in `raw` when there was one.
- **Not batch-capable:** use `run`.

## `mock`

Answers from a script, offline and free. It is meant for trying the pipeline, rehearsing batch
workflows and testing.

| Option | Default | Meaning |
|---|---|---|
| `model` | `mock-1` | appears in `annotator` as `mock:<model>` |
| `response` | `"Working outward from 0.\n<FINAL_RANGE>[-1, +2]</FINAL_RANGE>"` | a string; or, in Python, a `Completion`, a mapping from key to either, or a callable `(system, user)` returning either |
| `key` | the user prompt | Python only: `(system, user) -> key` for a mapping `response` |
| `transient_failures` | `0` | each key fails this many times before answering; exercises retries (`run` only) |
| `batch` | `false` | `true` gives the batch-capable mock |
| `scramble` | `true` | batch results come back shuffled, as real ones do |
| `drop` | none | ids to leave out of the batch results |
| `unknown` | none | ids to add to the batch results that were never sent |
| `states` | always `completed` | the states `status` walks through, the last repeating, e.g. `["pending", "running", "completed"]` or `failed` |
| `seed` | `0` | shuffling seed |
| `state_path` | none | a file keeping submitted batches, so `status` and `fetch` work across separate commands |

- **A mapping `response`** with no entry for a prompt gives a provider-error completion, as a
  real API failure would.
- **For batch rehearsals on the command line,** always pass `state_path`: without it, each
  command starts with no memory of the batch.

```bash
propel-annotate submit --instances examples/items_RA.jsonl --dimension RA --out out/RA.jsonl \
    --provider mock --model mock-1 --provider-option batch=true --provider-option state_path=out/mock.json
```

A mock that returns ranges depending on the question is Python-only; see
[Tutorial 1](tutorials/01-offline-walkthrough.md).

## Failures

Provider failures never stop a run. Each one becomes a row with `error` set and `parse_ok`
false, and the summary line counts them. Rerun just those instances with the recipe in
[Tutorial 3](tutorials/03-annotating-with-a-provider.md#6-rerun-the-failures).

Retries happen at two levels:
- **PROPEL**, for `run`: `max_retries` (default 3) with a backoff of 1, 2, 4… seconds.
- **The vendor SDKs** (`openai`, `anthropic`) retry transient HTTP errors on their own; tune
  them with `--provider-option max_retries=N`.

Rate limits: lower `--max-workers`.

## Your own provider

Any object with `name`, `model` and a `complete` method is a provider. Register it and it
works everywhere a built-in one does ([Tutorial 10](tutorials/10-adding-a-provider.md)).
