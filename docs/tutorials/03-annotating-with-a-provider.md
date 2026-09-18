# Tutorial 3: annotating with a real provider

Set up a provider, run a pilot, read what the annotator wrote, then annotate the whole bank and
repair any failures. The blocks below spend real money on real APIs; the same steps work on
the `mock` provider for a dry run.

**You need:** PROPEL with the extra for your provider ([Installation](../installation.md)),
credentials in the environment, and your instances in the [instance format](../data-formats.md#instances).

## 1. Choose a provider and a model

| Provider | Try first | Batch API | Notes |
|---|---|---|---|
| `openai` | `gpt-4.1` | yes | also any OpenAI-compatible server via `base_url` |
| `azure` | your deployment | yes, on Global Batch deployments | `--model` is the deployment name |
| `anthropic` | `claude-haiku-4-5` | yes | newer models need `send_temperature=false` |
| `google` | `gemini-2.5-flash` | no | |
| local (vLLM, Ollama) | a large instruct model | no | the `openai` provider with `base_url` |

The annotator must follow the rubric's reasoning. For risk aversion, that means computing and
comparing expected values. Small models often cannot, and produce confident but meaningless
intervals: step 3 is how you find out.

## 2. Run a pilot of 20 instances

Sample **after** loading, so each instance keeps its own id:

<!-- no-run -->
```python
import random
from propensity import load_instances, write_table

instances = load_instances("data/items_RA.jsonl")
write_table(random.Random(0).sample(instances, 20), "data/pilot_RA.jsonl")
```

Then annotate the pilot, choosing one of these:

<!-- no-run -->
```bash
# OpenAI
export OPENAI_API_KEY="sk-..."
propel-annotate run --instances data/pilot_RA.jsonl --dimension RA --out out/pilot_RA.jsonl \
    --provider openai --model gpt-4.1

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
propel-annotate run --instances data/pilot_RA.jsonl --dimension RA --out out/pilot_RA.jsonl \
    --provider anthropic --model claude-haiku-4-5

# Anthropic, a model that rejects temperature
propel-annotate run --instances data/pilot_RA.jsonl --dimension RA --out out/pilot_RA.jsonl \
    --provider anthropic --model claude-sonnet-5 --provider-option send_temperature=false

# Google
export GEMINI_API_KEY="..."
propel-annotate run --instances data/pilot_RA.jsonl --dimension RA --out out/pilot_RA.jsonl \
    --provider google --model gemini-2.5-flash

# Azure OpenAI: --model is your deployment's name
export AZURE_OPENAI_API_KEY="..." AZURE_OPENAI_ENDPOINT="https://my-resource.openai.azure.com"
propel-annotate run --instances data/pilot_RA.jsonl --dimension RA --out out/pilot_RA.jsonl \
    --provider azure --model my-gpt41-deployment --provider-option batch=false

# A local model served by Ollama, vLLM or LM Studio
propel-annotate run --instances data/pilot_RA.jsonl --dimension RA --out out/pilot_RA.jsonl \
    --provider openai --model llama3.3:70b \
    --provider-option base_url=http://localhost:11434/v1 --provider-option api_key=local
```

For local models, make sure the context window holds the whole prompt: about 10,500 characters
(roughly 2,500 tokens) for `RA`. A truncated prompt loses the rubric's start, and the answers
degrade without any error.

## 3. Read every explanation

The only way to judge rubric quality and annotator competence is to read what the annotator
wrote. Do this on every pilot.

<!-- no-run -->
```python
from propensity import read_table

rows = read_table("out/pilot_RA.jsonl")
for row in rows.itertuples():
    outcome = f"[{row.lower}, {row.upper}]" if row.parse_ok else (row.error or row.parse_error)
    print(f"=== {row.question_id}: {outcome}\n{row.question_text}\n")
    print(row.explanation[-2000:], "\n")
```

For each instance, check that the annotator:
- **picked the right unbiased option** (for `RA`, the one with the higher expected value);
- **did the rubric's comparison,** with the numbers, at each level;
- **worked outwards from 0 in both directions,** stopping at the first No;
- **drew bounds that follow from its own Yes/No answers;**
- **ended with `<FINAL_RANGE>[a, b]</FINAL_RANGE>`.**

Where to look when a check fails:
- **The model reasons well but disagrees with you:** look at the rubric.
- **The model does not reason at all:** use a stronger one.

## 4. Estimate the cost

Every prompt carries the full rubric. Input tokens are roughly characters ÷ 4:

<!-- no-run -->
```python
from propensity import build_annotation_prompt, load_instances, load_presentation, load_rubric

instances = load_instances("data/items_RA.jsonl")
rubric, presentation = load_rubric("RA"), load_presentation()
characters = sum(len(system) + len(user) for system, user in (
    build_annotation_prompt("risk aversion", rubric, presentation, i["question_text"])
    for i in instances))
print(f"{len(instances)} prompts, about {characters / 4 / 1e6:.2f} M input tokens")
```

Add the output: the level-by-level reasoning is typically 500 to 3,000 tokens per instance.
Multiply by the number of dimensions. A batch ([Tutorial 4](04-batch-annotation.md)) costs
about half as much.

## 5. Annotate the whole bank

<!-- no-run -->
```bash
propel-annotate run --instances data/items_RA.jsonl --dimension RA --out out/RA.jsonl \
    --provider openai --model gpt-4.1 --max-workers 8
```

- **`--max-workers`** sets parallel calls. Lower it if you hit rate limits.
- **Provider errors** are retried up to `--max-retries` times, with backoff.
- **The summary line** tells you whether anything is left to repair:

```text
347 ok, 1 parse-failed, 2 provider-error out of 350 total
```

## 6. Rerun the failures

**Provider errors** (rate limits, timeouts, overloads) deserve a second try. Rerun just those
instances, then merge the new rows into the file:

<!-- no-run -->
```python
import pandas as pd
from propensity import annotate, get_provider, load_instances, load_presentation, load_rubric
from propensity import read_table, write_table

instances = load_instances("data/items_RA.jsonl")
rows = read_table("out/RA.jsonl")
failed = set(rows.loc[rows["error"].notna(), "question_id"])        # provider errors only

retried = annotate([i for i in instances if i["question_id"] in failed],
                   provider=get_provider("openai", model="gpt-4.1"),
                   dimension="RA", propensity_name="risk aversion",
                   rubric=load_rubric("RA"), presentation=load_presentation(),
                   mode="sequential", max_workers=2)

position = {i["question_id"]: n for n, i in enumerate(instances)}
merged = pd.concat([rows[~rows["question_id"].isin(failed)], pd.DataFrame(retried)])
write_table(merged.sort_values("question_id", key=lambda ids: ids.map(position)), "out/RA.jsonl")
```

Rerun with the **same provider and model**: the `annotator` field records it, and a bank
annotated by two models is not one bank.

**Parse failures** are different. At temperature 0 the same prompt returns the same answer, so
rerunning does not help. Read their explanations first:

| Explanation | Cause | Fix |
|---|---|---|
| cut off mid-sentence; error `stopped at max_tokens…` | the response hit the length cap | raise `max_tokens` in `config/annotation.yaml`, then rerun those instances |
| complete reasoning, but no range, or a range outside −3…+3 | the model ignored the output contract | use a stronger model |
| a refusal, or `finish reason SAFETY` | the provider declined | reword the instance, or use another model |

To rerun parse failures anyway, e.g. after raising `max_tokens`, select them with
`rows["error"].isna() & ~rows["parse_ok"].astype(bool)` and use the recipe above. The
`astype(bool)` is needed because `read_table` keeps JSON values as Python objects.

## 7. Several dimensions

One command per dimension; the instances can be the same file or different ones:

<!-- no-run -->
```bash
for DIM in RA Ex Ul BR; do
  propel-annotate run --instances data/items_$DIM.jsonl --dimension $DIM --out out/$DIM.jsonl \
      --provider anthropic --model claude-haiku-4-5
done
```

`propel-fit --annotations out/RA.jsonl out/Ex.jsonl out/Ul.jsonl out/BR.jsonl ...` then fits
them all at once.

## 8. The same from Python

<!-- no-run -->
```python
from propensity import annotate, get_provider, load_instances, load_presentation, load_rubric
from propensity import write_table

provider = get_provider("anthropic", model="claude-haiku-4-5", max_retries=5)
rows = annotate(load_instances("data/items_RA.jsonl"), provider=provider, dimension="RA",
                propensity_name="risk aversion", rubric=load_rubric("RA"),
                presentation=load_presentation(), mode="sequential", max_workers=4,
                on_progress=lambda done, total: print(f"{done}/{total}", end="\r"))
write_table(rows, "out/RA.jsonl")
```

- **`mode`.** `"sequential"` matches `propel-annotate run`. `"auto"` would use the provider's
  batch API and block until it finishes.
- **`max_retries=5`** here goes to the Anthropic SDK client, which retries HTTP errors itself.
  `annotate` also takes its own `max_retries`, for retries at the instance level.

Every provider option: [Providers](../providers.md).
