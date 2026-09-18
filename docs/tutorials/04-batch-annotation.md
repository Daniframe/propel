# Tutorial 4: batch annotation

A batch sends every instance in one request to the provider's batch API.

- **Cost:** about half of `run`.
- **Speed:** minutes to hours; OpenAI and Azure promise completion within 24 hours, and
  Anthropic finishes most batches within one.
- **Providers:** `openai` (official endpoint), `azure` (Global Batch deployments), `anthropic`,
  and `mock` for rehearsals.

The workflow is three commands, so that nothing depends on one process staying alive:

```
submit  →  job file  →  status (as often as you like)  →  fetch
```

**You need:** PROPEL, run from the project root. Everything below rehearses with the `mock`
provider; [step 6](#6-with-a-real-provider) shows the real commands.

## 1. A rehearsal configuration

The mock can behave like a slow batch: it walks through the states you give it, one per poll.
A list of states can only be given in a YAML file, so write one:

```python
from pathlib import Path

Path("out").mkdir(exist_ok=True)
Path("out/batch_rehearsal.yaml").write_text("""\
provider: mock
model: mock-1
provider_options:
  batch: true
  state_path: out/mock_state.json
  states: [pending, running, completed]
""", encoding="utf-8")
```

`state_path` stores the submitted batch on disk, as a provider's servers would. Without it,
`status` and `fetch` would find no batch.

## 2. Submit

```bash
propel-annotate submit --instances examples/items_RA.jsonl --dimension RA --out out/RA_batch.jsonl \
    --config out/batch_rehearsal.yaml
```

```text
submitted batch mock-batch-1 with 120 requests
wrote out/RA_batch.jsonl.job.json
next: propel-annotate status --job out/RA_batch.jsonl.job.json
```

The job file is written before anything else happens, and holds everything `status` and `fetch`
need:

```python
import json

job = json.loads(Path("out/RA_batch.jsonl.job.json").read_text(encoding="utf-8"))
print({key: job[key] for key in ("batch_id", "provider", "model", "dimension", "n_requests", "out")})
```

```text
{'batch_id': 'mock-batch-1', 'provider': 'mock', 'model': 'mock-1', 'dimension': 'RA', 'n_requests': 120, 'out': 'out/RA_batch.jsonl'}
```

It never holds credentials: `status` and `fetch` read those from the environment, as `submit`
did.

## 3. Poll, and fetch when done

```bash
propel-annotate status --job out/RA_batch.jsonl.job.json
propel-annotate fetch --job out/RA_batch.jsonl.job.json   # exits 1
propel-annotate status --job out/RA_batch.jsonl.job.json
propel-annotate fetch --job out/RA_batch.jsonl.job.json
```

```text
batch mock-batch-1: pending
  120 requests for RA via mock:mock-1, submitted 2026-09-18T09:12:03+00:00
batch mock-batch-1 is running; nothing to fetch yet
batch mock-batch-1: completed
  120 requests for RA via mock:mock-1, submitted 2026-09-18T09:12:03+00:00
  next: propel-annotate fetch --job out/RA_batch.jsonl.job.json
120 ok, 0 parse-failed, 0 provider-error out of 120 total
wrote out/RA_batch.jsonl
```

`fetch` on an unfinished batch changes nothing and exits 1, so it is safe to run from a
scheduled job until it succeeds.

The rows come back shuffled, as real batch results do, and are rejoined by `question_id`. The
output is in input order:

```python
from propensity import read_table

rows = read_table("out/RA_batch.jsonl")
assert rows["question_id"].tolist() == [f"RA_{i:03d}" for i in range(120)]
```

## 4. Wait in one command

`submit --wait` polls every `poll_interval_s` seconds (default 60) until the batch ends, then
fetches it:

```python
Path("out/batch_wait.yaml").write_text("""\
provider: mock
model: mock-1
provider_options: {batch: true, state_path: out/mock_wait.json}
poll_interval_s: 1
""", encoding="utf-8")
```

```bash
propel-annotate submit --instances examples/items_RA.jsonl --dimension RA --out out/RA_wait.jsonl \
    --config out/batch_wait.yaml --wait
```

```text
submitted batch mock-batch-1 with 120 requests
wrote out/RA_wait.jsonl.job.json
next: propel-annotate status --job out/RA_wait.jsonl.job.json
batch mock-batch-1 ended as completed
120 ok, 0 parse-failed, 0 provider-error out of 120 total
wrote out/RA_wait.jsonl
```

The job file is still written first. If the wait is interrupted, carry on with `status` and
`fetch`.

## 5. When things go wrong

### The inputs changed after submitting

`fetch` rebuilds every prompt from the job's instances, rubric and trait name, and compares
them with what was submitted. If anything changed, the rows would describe prompts that were
never sent, so it refuses:

```python
from propensity import load_instances, write_table

Path("out/drift.yaml").write_text(
    "provider: mock\nmodel: mock-1\nprovider_options: {batch: true, state_path: out/mock_drift.json}\n",
    encoding="utf-8")
write_table(load_instances("examples/items_RA.jsonl"), "out/items_copy.jsonl")
```

```bash
propel-annotate submit --instances out/items_copy.jsonl --dimension RA --out out/RA_drift.jsonl --config out/drift.yaml
```

```python
edited = load_instances("out/items_copy.jsonl")
edited[0]["question_text"] += " Explain your choice."
write_table(edited, "out/items_copy.jsonl")
```

```bash
propel-annotate fetch --job out/RA_drift.jsonl.job.json   # exits 2
```

```text
error: the prompts no longer match the ones submitted as mock-batch-1, so the instances or the rubric changed since. Submit again, or pass --force to fetch anyway and accept rows attributed to prompts that have moved.
```

- **The same check** catches a rubric that changed between `submit` and `fetch`, for example
  after upgrading PROPEL to a release with new rubric versions.
- **The right fix** is to resubmit.
- **`--force`** fetches anyway, when you know the change is harmless: a new field that is not
  `question_text`, for instance.

```bash
propel-annotate fetch --job out/RA_drift.jsonl.job.json --force
```

### Missing and unknown ids

A real batch can lose results. The mock reproduces this with `drop`, and ids that were never
sent with `unknown`:

```python
Path("out/lossy.yaml").write_text(
    "provider: mock\nmodel: mock-1\n"
    "provider_options: {batch: true, state_path: out/mock_lossy.json, drop: [RA_005, RA_006], unknown: [ghost]}\n",
    encoding="utf-8")
```

```bash
propel-annotate submit --instances examples/items_RA.jsonl --dimension RA --out out/RA_lossy.jsonl --config out/lossy.yaml
propel-annotate fetch --job out/RA_lossy.jsonl.job.json
```

```text
warning: batch mock-batch-1 returned 1 id(s) that were never sent: ['ghost']
118 ok, 0 parse-failed, 2 provider-error out of 120 total
```

- **Every instance still gets a row.** The lost ones carry `error = "missing from the batch
  output"`: rerun them with `run` ([Tutorial 3](03-annotating-with-a-provider.md#6-rerun-the-failures)).
- **Unknown ids** are reported and dropped.

### A failed or cancelled batch

`status` shows `failed` or `cancelled`, and `fetch` has nothing to collect. Fix the cause the
provider's console reports (usually quota or an invalid request), then submit again.

```python
Path("out/failing.yaml").write_text(
    "provider: mock\nmodel: mock-1\n"
    "provider_options: {batch: true, state_path: out/mock_failing.json, states: failed}\n",
    encoding="utf-8")
```

```bash
propel-annotate submit --instances examples/items_RA.jsonl --dimension RA --out out/RA_failed.jsonl --config out/failing.yaml
propel-annotate status --job out/RA_failed.jsonl.job.json
propel-annotate fetch --job out/RA_failed.jsonl.job.json   # exits 1
```

```text
batch mock-batch-1: failed
  120 requests for RA via mock:mock-1, submitted 2026-09-18T09:14:40+00:00
batch mock-batch-1 ended as failed; nothing to fetch. Submit it again.
```

## 6. With a real provider

<!-- no-run -->
```bash
# Anthropic: Message Batches
export ANTHROPIC_API_KEY="sk-ant-..."
propel-annotate submit --instances data/items_RA.jsonl --dimension RA --out out/RA.jsonl \
    --provider anthropic --model claude-haiku-4-5

# OpenAI: Files + Batches
export OPENAI_API_KEY="sk-..."
propel-annotate submit --instances data/items_RA.jsonl --dimension RA --out out/RA.jsonl \
    --provider openai --model gpt-4.1

# Azure OpenAI: a Global Batch deployment
propel-annotate submit --instances data/items_RA.jsonl --dimension RA --out out/RA.jsonl \
    --provider azure --model my-global-batch-deployment

# later, from any shell with the same credentials
propel-annotate status --job out/RA.jsonl.job.json
propel-annotate fetch --job out/RA.jsonl.job.json
```

- **Rehearse first.** A mock rehearsal costs nothing, and a pilot `run` on 20 instances
  ([Tutorial 3](03-annotating-with-a-provider.md#2-run-a-pilot-of-20-instances)) costs little.
- **Anthropic accepts ids of 1 to 64 letters, digits, `-` and `_`.** `submit` refuses before
  sending anything if an id does not fit. Check first:

```python
from propensity.providers.anthropic import CUSTOM_ID

instances = load_instances("examples/items_RA.jsonl")
unfit = [i["question_id"] for i in instances if not CUSTOM_ID.match(i["question_id"])]
print(unfit or "every id fits")
```

```text
every id fits
```

- **OpenAI-compatible servers** other than OpenAI's are batch-capable only if they implement
  the Batches API. PROPEL checks once; without it, `submit` fails with
  `provider 'openai' has no batch API`, and `run` is the way.

## 7. From Python

The same steps, for pipelines of your own. Submit in one process:

```python
from propensity import get_provider, load_presentation, load_rubric
from propensity.annotation import build_requests, submit

provider = get_provider("mock", batch=True, state_path="out/api_state.json")
requests = build_requests(instances, propensity_name="risk aversion",
                          rubric=load_rubric("RA"), presentation=load_presentation())
batch_id = submit(provider, requests)
```

and collect in another, once `poll_batch` says `completed`:

```python
from propensity.annotation import collect, rows_from_completions, summarise

provider = get_provider("mock", batch=True, state_path="out/api_state.json")
if provider.poll_batch(batch_id) == "completed":
    rows = rows_from_completions(instances, collect(provider, batch_id, requests),
                                 dimension="RA", annotator=f"{provider.name}:{provider.model}")
    print(summarise(rows))
```

```text
120 ok, 0 parse-failed, 0 provider-error out of 120 total
```

`annotate(..., mode="batch")` does all of it in one blocking call, polling every
`poll_interval` seconds.
