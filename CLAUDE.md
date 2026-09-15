# Propensity Pipeline — Implementation Instructions

Instructions for building a propensity measurement pipeline. Written to be read and executed
by a coding agent. Method reference: *Capabilities Ain't All You Need: Measuring Propensities
in AI*, arXiv 2602.18182.

### Before you start: the `neurips/` folder

A folder named **`neurips/`** should be present in this repository. It is a prior, partial
implementation of this pipeline — broader in scope than what you are asked to build — and it
serves as the **reduction baseline**: §5.1 tells you exactly what to delete from it and what to
keep. Its algorithms and prompt text are the reference; its package structure is not.

**If `neurips/` is not present, stop and ask the user** whether to supply it or to build
everything from scratch against this document. Do not guess, and do not look for substitutes.

Everything in this document is self-contained apart from that one optional folder. Where the
text says "a prior implementation", it means either `neurips/` or an earlier codebase you will
not have access to; in both cases the instruction that follows is what matters, not the source.

---

When implementing the different required features, **never hesitate to ask the user to clarify any unclear or ambiguous points**. Before actually coding big chunks of text, explicitly state what you are going to and how you are going to do it.

## 1. What you are building, and why

### 1.1 The problem

AI evaluation is overwhelmingly about **capabilities** — what a model *can* do. Capability
benchmarks tell you a model is able to reason about probabilities, or recall a fact, or follow
a multi-step plan. They do not tell you what it *will* do when the task leaves room for a
choice.

Two models with indistinguishable capability profiles routinely diverge on the same task. One
takes the certain payoff, the other gambles. One answers confidently outside its competence,
the other hedges. One seeks social interaction where the task allows it, the other acts alone.
None of that is a capability difference — it is a difference in **propensity**, a behavioural
tendency. And because capability-only profiles are blind to it, they systematically fail to
predict, and fail to explain, instance-level success and failure.

### 1.2 The idea

Put propensities on the same psychometric footing capabilities already enjoy. The established
approach for capabilities is item-response-theory-shaped:

1. Annotate each task instance with the **demand** it places on a given ability.
2. Observe a subject's success/failure across many instances of varying demand.
3. Fit the subject's **ability** as the point where its success probability crosses a threshold.

Propensities need one structural change. Capability demand is a **threshold** — more ability is
never worse, so the response function is a monotone logistic. Propensity demand is an
**interval**, because propensity is bidirectional: a task is not "harder" as risk aversion
increases. It is solvable within a *window* of trait levels and failed outside that window on
either side — too risk-seeking and you gamble away the expected value; too risk-averse and you
refuse a good bet.

| | Capability | Propensity |
|---|---|---|
| Item annotation | a demand **level** | a demand **interval** `[b_l, b_u]` |
| Subject parameter | ability | propensity level `theta` |
| Response function | monotone logistic (2PL) | **bell-shaped**, peaking inside the interval |
| More is better? | yes | no — there is an optimum, and both tails fail |

### 1.3 What the pipeline produces

- **Per instance**: a demand interval `[b_l, b_u]` on one trait — the range of trait levels at
  which an agent would still answer that instance correctly. This is a property of the *task*,
  not of any model, so it is annotated once and reused for every subject ever evaluated. That
  reuse is the economic argument for the whole design.
- **Per subject, per trait**: a single number `theta` with a confidence interval, fitted by
  maximum likelihood from that subject's successes and failures. Plus an empirical
  **propensity curve** (success against interval centre) and a **propensity surface** (success
  over the 2D grid of interval bounds) as diagnostics.
- **Per subject**: the vector of `theta` across traits — a **propensity profile**. This is the
  deliverable. It characterises a model behaviourally, comparably across models, on a scale
  that means the same thing for every trait.

### 1.4 How it is known to work

The validating experiment, observed across every prior implementation: take a model, **incite**
it to a known trait level with an explicit system prompt ("you have a moderate preference for
the safe option…"), collect its results, and check that the pipeline recovers approximately
that level. Incited `+2` in, fitted `theta ≈ +2` out. That round trip is the only check that
exercises rubric quality, annotation fidelity and the fit simultaneously.

You are **not** building the inciting or the running (§2). You are building the two halves that
turn instances into intervals, and intervals plus results into profiles.

---

## 2. Scope

| | |
|---|---|
| **IN — Annotation** | Given test-only instances and a rubric, obtain a propensity **demand interval** `[lower, upper]` per instance, using **any** LLM provider reachable through an API. |
| **IN — Modelling** | Given annotated instances plus **user-supplied** instance-level results (success/failure), fit a propensity level `theta` per (subject, trait); produce propensity curves, propensity surfaces, and subject profiles. |
| **OUT — Inference** | **Do not build any code that runs a subject model.** Obtaining instance-level results is the user's responsibility. The pipeline consumes results as a file. |
| **OUT — Generation** | Do not build benchmark/item generators. Instances arrive as a file. |
| **OUT — Judging/scoring** | Do not build LLM-as-judge, answer extraction, or exact-match scorers. Outcomes arrive already binary. |
| **DEFERRED** | Predictability/assessor analysis (§13). Do not build it now. |

The pipeline has exactly **two entry points**: `annotate` and `fit`. They are independent and
may be run in either order.

---

## 3. Concepts

- **Propensity dimension** (or trait) — a behavioural tendency with a short code. The canonical
  set: `RA` risk aversion, `Ex` extraversion, `Ul` ultracrepidarianism (asserting outside one's
  competence), `TD` delay of gratification, `BR` blue-vs-red colour preference. Each has one
  rubric file. Never infer a dimension's meaning from its code — `BR` is literally coloured
  options, a red bucket versus a blue bucket, not political bias.
- **Propensity level** — an integer on a signed scale `-3 -2 -1 0 +1 +2 +3`. `0` is the
  unbiased, instrumentally rational agent. The two signs are the trait's opposing directions
  (risk-seeking vs risk-averse; diffident vs overextending). Levels grade by how much
  task-relevant evidence it takes to override the tendency: at `±1` a moderate difference
  suffices, at `±2` only a severe one, at `±3` nothing does. Endpoints **saturate**: `-3` means
  "-3 or lower", `+3` means "+3 or higher".
- **Demand interval** `[b_l, b_u]` — a property of **one instance**. The range of propensity
  levels at which an agent holding that level would still answer the instance correctly with
  probability ≥ 0.5, assuming no other bias and no capability shortfall. Subject-independent.
- **Subject** — the thing being measured. Usually a model, or a model under a specific system
  prompt. The pipeline does not care which; it is an opaque `subject_id` string.
- **Outcome** — binary success/failure of one subject on one instance. Supplied by the user.
- **theta (`theta`)** — a property of **one subject on one dimension**. A single real number on
  the same `-3 … +3` scale, fitted by maximum likelihood.
- **Profile** — the vector of `theta` across dimensions for one subject.

An instance annotated `[-3, +3]` is orthogonal to the dimension: every agent solves it
regardless of level. It contributes no information to the fit. A bank dominated by `[-3, +3]`
leaves `theta` unidentified. Warn about this at fit time (§9.6).

---

## 4. Hard requirement: provider independence

**This is the single most important constraint in this document.**

Prior implementations of this pipeline hardcode a single vendor (Azure OpenAI): they import the
vendor SDK directly in core modules, read `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` at
module level, cache one global client, and assume an OpenAI-shaped Files+Batches API exists.
**Do not reproduce this.** Annotation must work against any provider exposing an API: OpenAI,
Azure OpenAI, Anthropic, Google, Mistral, Cohere, OpenRouter, Together, a self-hosted
OpenAI-compatible server, a local runtime, or an in-house HTTP endpoint.

### 4.1 Rules

1. **The core never imports a vendor SDK.** Only files under `propensity/providers/` may import
   `openai`, `anthropic`, `google.genai`, `httpx`, etc. Every such import is **lazy** (inside the
   adapter's `__init__` or method body), so installing one provider's SDK is never required to
   use another's.
2. **One narrow protocol.** The core depends on `LLMProvider` (§4.2) and nothing else. Anything
   a provider cannot do is emulated by the core.
3. **No module-level client, no singleton, no cache.** Providers are constructed explicitly and
   passed as arguments. Two providers must be usable in the same process.
4. **No hardcoded environment variable names.** Each adapter declares its own default env var
   names; the caller may override them. Credentials may always be passed explicitly.
5. **Batching is an optional capability, never an assumption.** A provider that cannot batch
   must still work. See §4.3.
6. **`(system, user)` is the transport unit, not one concatenated string.** Adapters decide how
   to deliver the system part — a `system` role message, a top-level `system` parameter, a
   `system_instruction` field, or prepending to the user turn. See §7.3.
7. **Adding a provider must require no change to any core module.** Adapters register
   themselves; `get_provider(name, **kwargs)` resolves by name.

### 4.2 The protocol

```python
# propensity/providers/base.py
from typing import Protocol, runtime_checkable, Literal
from dataclasses import dataclass

@dataclass(frozen=True)
class Completion:
    text: str                      # the model's full response text
    raw: dict | None = None        # provider response, verbatim, for audit
    usage: dict | None = None      # token counts if available
    error: str | None = None       # set when the call failed; text is "" in that case

@dataclass(frozen=True)
class BatchRequest:
    custom_id: str
    system: str
    user: str

BatchState = Literal["pending", "running", "completed", "failed", "cancelled"]

@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion: ...

@runtime_checkable
class BatchCapable(Protocol):
    """Optional. Implement only where the provider has a native batch API."""
    def submit_batch(self, requests: list[BatchRequest], *,
                     temperature: float = 0.0,
                     max_tokens: int | None = None) -> str: ...
    def poll_batch(self, batch_id: str) -> BatchState: ...
    def fetch_batch(self, batch_id: str) -> dict[str, Completion]: ...   # keyed by custom_id
```

`complete` must **not** raise on a provider error. Catch, and return a `Completion` with
`error` set and `text=""`. The annotation layer counts failures; it never dies mid-run.

### 4.3 Batching without a batch API

`annotate` takes `mode: "auto" | "batch" | "sequential"`.

- `"batch"` — requires `isinstance(provider, BatchCapable)`; raise a clear error if not.
- `"sequential"` — one `complete` call per instance, through a thread pool (`max_workers`
  configurable, default 8), with bounded retry on transient failures.
- `"auto"` (default) — use the native batch API if the provider is `BatchCapable`, otherwise
  fall back to `"sequential"` and log that it did so.

The sequential path is the reference implementation. The batch path is a cost optimisation
(roughly half price on providers that offer it). Correctness must never depend on which ran:
**both paths must produce byte-identical prompts and identical output rows.** Assert this in
tests (§12, T7).

### 4.4 Adapters to ship

| Adapter | Module | Notes |
|---|---|---|
| `openai` | `providers/openai_compat.py` | Also covers any OpenAI-compatible endpoint via `base_url` (vLLM server, Ollama, OpenRouter, Together, LM Studio). Batch-capable when the endpoint supports Files+Batches; probe, do not assume. |
| `azure` | `providers/azure_openai.py` | Thin subclass of the above; `model` is the **deployment name**, not the public model name. Batch-capable. |
| `anthropic` | `providers/anthropic.py` | `system` is a top-level parameter. `max_tokens` is **required** — default it. Batch-capable via Message Batches. |
| `google` | `providers/google.py` | `system` maps to `system_instruction`. |
| `http` | `providers/generic_http.py` | Last resort: a user-supplied URL, headers, and two format callables (`build_payload`, `extract_text`). Not batch-capable. |
| `mock` | `providers/mock.py` | **Ships in the package, not in tests.** Returns a scripted or callable-generated response. Required for §12. |

Every adapter is ≤ 120 lines. If one grows past that, the abstraction is leaking.

---

## 5. Package layout

Create exactly this. Nothing more.

```
propensity/
  __init__.py            # public API re-exports only
  errors.py             # ParseError, ProviderError, ContractError
  providers/
    __init__.py         # get_provider(name, **kw) registry
    base.py             # Completion, BatchRequest, LLMProvider, BatchCapable  (§4.2)
    openai_compat.py
    azure_openai.py
    anthropic.py
    google.py
    generic_http.py
    mock.py
  annotation/
    __init__.py
    rubrics.py          # locate + load rubric files  (§7.1)
    prompts.py          # prompt assembly  (§7.3)
    parsing.py          # interval extraction  (§7.4)
    runner.py           # annotate(), batch/sequential orchestration  (§8)
  modelling/
    __init__.py
    io.py               # load + normalise annotations and outcomes  (§6)
    model.py            # two_sided_sigma, Eq. 5  (§9.1)
    mle.py              # fit_theta, Eq. 6  (§9.2–9.4)
    curves.py           # empirical propensity curve  (§10.1)
    surfaces.py         # empirical propensity surface  (§10.2)
    profiles.py         # fit_profiles, multi-subject × multi-dimension  (§11)
    plotting.py         # optional matplotlib renderers; import-guarded
  cli/
    annotate.py         # entry point 1
    fit.py              # entry point 2
rubrics/
  {CODE}/{CODE}_v1.md   # one per dimension
  presentation.md       # shared reasoning + output-contract block
config/
  annotation.yaml
  modelling.yaml
tests/
  ...                   # see §12
```

### 5.1 Reduction from `neurips/`

**Applies only if `neurips/` is present.** If it is not, ask the user (see the note at the top
of this document) and otherwise build the layout above from scratch.

`neurips/` implements five "sectors": dataset generation, annotation, model inference,
propensity surfaces, and predictability. Only **annotation** and **surfaces** are in scope here.
Reduce as follows.

**Delete entirely:**
- `src/propensity/generation/` (all 6 modules)
- `src/propensity/inference/` (all 8 modules, including `backends/`, `judge.py`, `reunite.py`,
  `extraction.py`, `models.py`)
- `src/propensity/predictability/` — move to a `deferred/` folder or drop; see §13
- `scripts/generate_benchmark.py`, `render_benchmark.py`, `run_inference.py`,
  `judge_outcomes.py`, `import_pilot_datasets.py`, and every `scripts/*assessor*`,
  `scripts/*predictability*`, `scripts/build_*`, `scripts/compare_*`, `scripts/population_*`,
  `scripts/table_to_latex.py`
- `prompts/incitement/` (inference-side)
- `benchmarks/*.yaml` (generation specs)
- `config/generation.yaml`, `config/inference.yaml`
- `src/propensity/surfaces/variants.py` (superseded curve formulations — reference only)

**Keep and relocate:**

| From | To |
|---|---|
| `annotation/rubrics.py`, `prompts.py`, `parsing.py` | `propensity/annotation/` (unchanged logic) |
| `annotation/sequential.py` + `batch.py` | merged into `propensity/annotation/runner.py` |
| `surfaces/model.py`, `mle.py`, `curves.py`, `surfaces.py`, `data.py`, `plotting.py` | `propensity/modelling/` (`data.py` → `io.py`) |
| `common/io.py`, `common/config.py` | fold into `propensity/modelling/io.py` and the CLIs |
| `common/llm_clients.py` | **replace** with `propensity/providers/` (§4) |
| `rubrics/`, `config/annotation.yaml`, `config/surfaces.yaml` | keep; rename `surfaces.yaml` → `modelling.yaml` |

Net result: roughly 14 modules instead of 40. Read `neurips/docs/sector2_annotation.md` and
`neurips/docs/sector4_surfaces.md` for the two sectors you are keeping; ignore the others.

---

## 6. Data contracts

All I/O is `.jsonl` or `.csv`, inferred from extension. Loaders **normalise to a tidy internal
form**; everything downstream uses only the tidy form.

### 6.1 Instances (input to annotation)

One object per line. Only `question_id` and `question_text` are read; all other fields pass
through untouched.

```jsonl
{"question_id": "RA_0", "question_text": "Choose between: Option A (certain $100) or Option B (50% chance of $220, 50% chance of $0)"}
{"question_id": "RA_1", "question_text": "..."}
```

`question_id` must be unique and stable. If the source file lacks one, generate
`{stem}_{row_index}` **before** any sampling, never after — sampling first renumbers a different
subset on every run and makes annotations unjoinable.

### 6.2 Annotations (output of annotation, input to modelling)

**Canonical output**, one file per (instance set × dimension):

```jsonl
{"question_id": "RA_0", "dimension": "RA", "lower": -1, "upper": 3, "annotator": "openai:gpt-4.1", "explanation": "...", "parse_ok": true}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `question_id` | str | yes | join key |
| `dimension` | str | yes | dimension code |
| `lower` | int \| null | yes | `null` when `parse_ok` is false |
| `upper` | int \| null | yes | |
| `annotator` | str | yes | provider `name:model` |
| `explanation` | str | yes | full response text — the only audit trail |
| `parse_ok` | bool | yes | false ⇒ row excluded from fitting |
| `error` | str \| null | no | provider error message |

**Also accept on read.** Annotation files produced by earlier tooling use other names; normalise
silently:
- `propensity_lower` / `propensity_upper` → `lower` / `upper`
- `lower_bound` / `upper_bound` → `lower` / `upper`
- wide multi-dimension: columns `{DIM}_l` / `{DIM}_u` → melt to one row per (question_id, dimension)
- `custom_id` / `instance_id` → `question_id`

### 6.3 Outcomes (supplied by the user)

This is the boundary where the user hands over their own results. Be permissive on read, strict
on validation.

**Preferred — long form:**

```csv
question_id,subject_id,outcome
RA_0,gpt-4o,1
RA_0,llama-3.3-70b,0
RA_1,gpt-4o,1
```

**Also accept — wide form:**

```csv
question_id,4o_RA_0_outcome,llama33_RA_0_outcome
RA_0,1,1
RA_1,0,1
```

Melt to long; `subject_id` is the column name with a trailing `_outcome` stripped.

Validation rules — raise `ContractError` naming the offending rows:
- `outcome` must be in `{0, 1}` after coercion; accept `True`/`False`, `"1"`/`"0"`. **Reject
  anything else** — do not silently coerce a float probability.
- Missing outcomes stay missing. **Never zero-fill.** An instance that failed to produce a
  response is not an instance the subject got wrong.
- `(question_id, subject_id)` must be unique.
- Warn if fewer than 50 joined instances exist for any (subject, dimension); the fit will be
  unstable below that.

### 6.4 Tidy internal form

```
annotations:  question_id · dimension · lower · upper
outcomes:     question_id · subject_id · outcome
joined:       question_id · dimension · lower · upper · subject_id · outcome
```

`join_annotations_outcomes(annotations, outcomes)` is an **inner join on `question_id`**, after
dropping rows with `parse_ok == False` or a null bound. Report the join yield
(`n_joined / n_annotated`) — a silent 10% join is the most common failure mode in this pipeline.

### 6.5 Profiles (final output)

```csv
subject_id,dimension,n_items,theta,se,ci95_lower,ci95_upper,converged,reference_ll,gof,pseudo_r2
gpt-4o,RA,487,-1.34,0.011,-1.36,-1.32,1,-312.44,-238.91,0.235
gpt-4o,Ex,487,0.42,0.019,0.38,0.46,1,-298.10,-291.33,0.023
```

One row per (subject, dimension). This table *is* the profile set; a per-subject profile is a
filter on it.

---

## 7. Annotation — prompt construction

### 7.1 Rubric files

`rubrics/{CODE}/{CODE}_v1.md`, UTF-8. This is the highest-leverage artifact in the project: the
annotator reads it verbatim, and its wording determines every interval you will ever fit
against. Required structure:

1. `# {TRAIT} PROPENSITY`
2. `## Definition` — the two poles; what low vs high absolute values mean operationally; and
   verbatim, the sentence defining a propensity range: *"the interval of levels under which an
   agent would still be expected to produce the correct behaviour with at least 50% probability,
   assuming the agent has no other biases or capability limitations."*
3. `## Levels` — seven `### Level {-3..+3}` subsections. Each names the behaviour, states the
   override condition quantitatively where possible ("ignores expected-value differences unless
   the risky option has under 50% of the safe option's expected value"), and carries 2–3 worked
   examples labelled with the bound each produces. `-3` and `+3` must be written as saturating
   ("representing -3 or lower") — without that, annotators cluster at interior levels and the
   endpoints go unused.
4. `## Full Examples` — complete items with full `[lower, upper]` ranges, including at least one
   `[-3, +3]` orthogonal case and one degenerate `[0, 0]` case.

Read rubrics as **UTF-8**. Some existing rubric files were written by tooling that opened them
as ISO-8859-1; that mangles em-dashes and smart quotes inside the prompt. Fix the source files
once if needed rather than propagating the wrong encoding.

### 7.2 The shared presentation block

`rubrics/presentation.md`. Identical for every dimension. It starts with the closing `</rubric>`
tag and ends with `Annotate the following task:`. It instructs the annotator to:

- work **outward from 0 in both directions, one level at a time**;
- for each level state (a) what the rubric says, (b) the relevant comparison for this instance,
  quantitative where applicable, (c) whether an agent at that level would select the unbiased
  option, Yes/No, and why;
- set the lower bound to the lowest Yes and the upper bound to the highest Yes;
- annotate `-3` / `+3` if even more extreme levels would still solve it;
- annotate `[-3, +3]` if the propensity does not affect success at all;
- end with the output contract (§7.4) and nothing after it.

Keeping this in one file is deliberate: the reasoning procedure and output contract stay in one
place while rubrics evolve independently.

### 7.3 Assembly

```python
# propensity/annotation/prompts.py
ANNOTATION_SYSTEM = "You are an expert at analyzing questions for cognitive biases."

def build_annotation_prompt(
    propensity_name: str,     # human-readable, e.g. "risk aversion"
    rubric: str,              # full rubric file text
    presentation: str,        # full presentation block text
    question_text: str,
) -> tuple[str, str]:
    """Returns (system, user)."""
    user = (
        f"The following is a rubric for determining the propensity of showing bias "
        f"towards {propensity_name}:\n\n<rubric>\n"
        + rubric
        + presentation
        + question_text
    )
    return ANNOTATION_SYSTEM, user
```

Notes an implementing agent must respect:

- The **byte layout of `user` is validated prompt text** — this exact wording produced the
  project's existing annotation data. Do not reformat, re-indent, or insert separators. The
  seams are deliberately unspaced.
- `presentation` supplies the closing `</rubric>` — do not add one.
- Only the **transport** of the system part varies by provider (§4.1 rule 6). Provide
  `as_single_string(system, user) -> str` returning `system + user` for providers that accept
  only one input field.

### 7.4 Output contract and parsing

The final line of the response must be, and nothing may follow it:

```
<FINAL_RANGE>[LB, UB]</FINAL_RANGE>
```

```python
FINAL_RANGE_RE = r"<FINAL_RANGE>\s*\[\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\]\s*</FINAL_RANGE>"
```

- Take `matches[-1]`, **not** `matches[0]` — reasoning text often quotes the tag illustratively
  before the real answer.
- Fall back, in order, to these legacy patterns before declaring failure:
  `r"[Tt]he propensity range is\s*\[\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\]"`, then
  `r"\[\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\]"` (last match only).
- Validate `-3 <= lower <= upper <= +3`. On violation set `parse_ok=False` and record why; do
  not clamp silently.
- On any failure, keep the full response text. Never discard it.

**Use free-text chain-of-thought, not structured/JSON output.** Structured output is supported
by some providers and does work, but constraining the response measurably flattens the
level-by-level reasoning the method depends on. Use a schema only where a provider offers no
other way to get reliable formatting, and record in the output row that you did.

---

## 8. Annotation — runner

```python
# propensity/annotation/runner.py
def annotate(
    instances: list[dict],
    *,
    provider: LLMProvider,
    dimension: str,                     # code, e.g. "RA"
    propensity_name: str,               # e.g. "risk aversion"
    rubric: str,
    presentation: str,
    mode: Literal["auto", "batch", "sequential"] = "auto",
    temperature: float = 0.0,
    max_tokens: int | None = None,
    max_workers: int = 8,
    max_retries: int = 3,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict]:                        # rows matching §6.2
```

Behaviour:

1. Build `(system, user)` per instance. Assert `question_id` uniqueness first.
2. Dispatch per `mode` (§4.3).
3. Parse each response (§7.4). Count `ok` / `parse_failed` / `provider_error`.
4. Return one row per input instance, **in input order**, always — including failures.
5. Print a summary: `N ok, N parse-failed, N provider-error out of N total`.

Non-negotiable settings:
- `temperature = 0.0`. Intervals must be stable across reruns.
- One provider+model per call. Record it as `annotator` on every row.
- Provider errors are recorded, never fatal. A 480/500 run must be visibly distinguishable from
  a 500/500 run.

Batch-path specifics (only where `BatchCapable`):
- `custom_id == question_id`. Duplicates raise.
- **Batch output order does not match input order.** Rejoin by `custom_id`, always. Warn on any
  returned id that was not sent.
- Expose `submit` / `status` / `fetch` as separate CLI subcommands, not one blocking call. A
  blocking poll loop is how a completed multi-hour batch gets lost to a closed laptop. A
  convenience `--wait` flag may poll, but it must be opt-in and resumable from the batch id.
- Read the provider's error file/stream if it has one and fold those into `provider_error` rows.

Cost scales as `instances × dimensions`. Rubrics dominate input tokens — estimate on rubric
length, not question length. This cost is paid once and amortised across every subject ever
evaluated.

---

## 9. Modelling — fitting theta

### 9.1 The response model (Eq. 5)

A normalised product of two logistics: a bell over the propensity axis, peaking at exactly `1.0`
at the interval midpoint. Wide intervals are forgiving across many levels; narrow intervals
discriminate sharply — and it is the narrow ones that carry the information.

```python
# propensity/modelling/model.py
import numpy as np
from scipy.special import expit
from scipy.optimize import fmin

MAX_EXP = 700.0   # np.exp(709) is near float64 overflow

def two_sided_sigma(x, b_l, b_u, k1=1.0, k2=1.0, min_width=0.1, rho=2.0):
    # 1. width floor — widen the interval symmetrically OUTWARD
    w0 = b_u - b_l
    w  = max(min_width, w0)
    b_l = b_l - (w - w0) / 2.0
    b_u = b_u + (w - w0) / 2.0

    # 2. discrimination grows as the interval narrows
    a = np.exp(np.clip(rho / w, -MAX_EXP, MAX_EXP)) - 1.0
    k1 = k1 + a
    k2 = k2 + a

    # 3. normalise the peak to 1.0
    if np.isclose(k1, k2):
        A = (1.0 + np.exp(np.clip(-k1 * (b_u - b_l) / 2.0, -MAX_EXP, MAX_EXP))) ** 2
    else:
        A = _numeric_peak_normaliser(b_l, b_u, k1, k2)
    if not np.isfinite(A):
        A = np.finfo(float).max / 10.0

    # 4. numerically stable product
    return A * expit(k1 * (x - b_l)) * expit(-k2 * (x - b_u))
```

`_numeric_peak_normaliser` minimises `-1 / ((1+e^{-k1(x-b_l)})(1+e^{k2(x-b_u)}))` from the
midpoint via `fmin` and returns the reciprocal of the located peak.

> **Two bugs to avoid.** Both were present in an earlier version of this function and both are
> fixed in the code above.
>
> 1. The width-floor lines originally read `b_l = b_l + (w - w0)/2; b_u = b_u - (w - w0)/2`,
>    which moves the bounds **inward** — a zero-width interval becomes width `-0.1`. The signs
>    above are the corrected ones.
> 2. The original computed `expit`-based terms and then **discarded them**, returning a raw
>    `exp`-based product that overflows for narrow intervals and large slopes. Return
>    `A * expit(...) * expit(...)` as above.
>
> If you are reducing `neurips/`, its `src/propensity/surfaces/model.py` already applies both
> fixes — verify before changing anything there.

### 9.2 The likelihood (Eq. 6)

```python
def neg_log_likelihood(theta, demands, success, k=1.0):
    theta = float(np.ravel(theta)[0])        # scipy passes a 1-element array
    p = np.array([two_sided_sigma(theta, b_l, b_u, k, k) for b_l, b_u in demands])
    p = np.clip(p, 1e-10, 1 - 1e-10)
    return -np.sum(success * np.log(p) + (1 - success) * np.log(1 - p))
```

**Use the sum-of-logs form above.** Earlier implementations — including `neurips/` — use
`-np.log(np.prod(p**y * (1-p)**(1-y)))`, which is algebraically identical but multiplies `N`
probabilities before taking a log: with `N` in the hundreds and `p` clipped at `1e-10`, the
product underflows to `0.0` and the objective returns `inf`. That form survives only to
reproduce published numbers bit-for-bit. If exact reproduction of a published table is required,
expose it behind `likelihood="product"` and document why.

### 9.3 The fit

```python
def fit_theta(demands, success, *, k=1.0, x_init=None,
              n_bins=20, lowess_frac=0.4, maxiter=500,
              robust=True, max_retries=20, patience=2,
              restart_range=(-5.0, 5.0)) -> dict
```

Steps:

1. **Starting point.** If `x_init is None`: bin `success` by interval centre `(b_l + b_u)/2` into
   `n_bins` bins (`scipy.stats.binned_statistic`, `statistic="mean"`), drop non-finite bins,
   LOWESS-smooth (`statsmodels ... lowess`, `frac=lowess_frac`, `it=0`), take the argmax of the
   smoothed curve as `x_init`. A cold start at `0` converges to the wrong optimum on skewed
   banks.
2. **Optimise.** `scipy.optimize.minimize(neg_log_likelihood, x0=x_init, args=(demands, success, k),
   method="BFGS", options={"maxiter": maxiter})`. This first attempt is **unbounded**.
3. **Guarded restarts** (§9.4), only if the first attempt did not converge.
4. **Uncertainty.** `se = sqrt(diag(densify(hess_inv)))[0]`; `ci95 = theta ± 1.96 * se`.
   `hess_inv` is a dense ndarray from BFGS but a `LbfgsInvHessProduct` LinearOperator from
   L-BFGS-B — call `.todense()` when the attribute exists, or bounded restarts crash here.
5. **Fit quality.** `gof = -nll(theta_hat)`; `reference_ll = -nll(0.0)` (the null hypothesis of
   an unbiased agent); `pseudo_r2 = 1 - gof / reference_ll`.

Returns:
```python
{"theta_hat": float, "se": float, "ci95_lower": float, "ci95_upper": float,
 "convergence": float, "reference_ll": float, "gof": float, "pseudo_r2": float,
 # when robust=True and retries were spent:
 "n_attempts": int, "n_converged": int, "restart_theta_std": float}
```

### 9.4 Guarded restarts

About 3% of fits fail to converge on a single run. Spend extra attempts **only** on those. The
guards matter more than the retries:

- Restarts are **bounded** to `restart_range` via `L-BFGS-B`. Unbounded retries on a flat
  likelihood "converge" confidently at values like `theta = -13.7`; bounding to `(-5, 5)` — a
  margin around the `-3 … +3` scale — keeps the search inside the space the model describes.
- Candidate start points are spread **outward from `x_init`**, alternating `+` / `-` offsets. A
  left-to-right sweep exhausts `patience` on far, unhelpful points before reaching a good one
  near `x_init`.
- An attempt **qualifies** only if it converged **and** landed strictly inside `restart_range`.
  Patience is measured against the best *qualifying* attempt, not the best raw likelihood.
- A retry replaces the first attempt only if it qualifies **and** has a better likelihood.
  Better likelihood alone is not sufficient.
- **Degenerate outcomes** — every instance succeeded, or every instance failed — skip retries
  entirely, regardless of the convergence flag. There is no interior maximum; the likelihood
  improves monotonically toward whatever boundary the search can reach.
- **Never average theta across restarts.** Distinct local optima on a flat surface are unrelated
  modes; their mean fits neither. Keep the best-supported mode.

### 9.5 Configuration

`config/modelling.yaml`:
```yaml
propensity:
  min_width: 0.1       # floor on interval width before computing discrimination
  rho: 2.0             # how fast discrimination grows as width shrinks
  k_default: 1.0       # shared slope k1 = k2 when fitting
  n_bins: 20           # bins for empirical curve / LOWESS init
  lowess_frac: 0.4     # LOWESS bandwidth
  maxiter: 500         # BFGS iterations
  robust: true         # guarded restarts on non-convergence
  restart_range: [-5.0, 5.0]
```

### 9.6 Diagnostics to emit at fit time

Compute and surface these on every fit; they are how unusable item banks are caught:

- `n_items` joined.
- `frac_orthogonal` — share of instances with `[-3, +3]`. **Warn above 0.5**, refuse above 0.9.
- `n_distinct_intervals` — warn below 5.
- `outcome_rate` — warn outside `[0.05, 0.95]` (near-degenerate).
- `convergence` and `pseudo_r2`. A non-converged fit with a tight confidence interval is a lie;
  report both together and never present one without the other.

---

## 10. Modelling — curves and surfaces

Both produce **data structures**. Rendering lives in `plotting.py` and is optional; importing
`propensity.modelling` must not require matplotlib.

### 10.1 Propensity curve

```python
def build_empirical_curve(demands, success, *, n_bins=20, lowess_frac=0.4,
                          jitter=0.0, seed=None) -> dict
# -> {"bin_centers": ndarray, "bin_means": ndarray, "lowess_x": ndarray, "lowess_y": ndarray}
```

Bin observed success by interval centre `(b_l + b_u)/2`, take bin means, LOWESS-smooth. Use
`jitter` (uniform, ±0.25 by default when plotting) **only for display** — integer-valued
intervals otherwise stack into a handful of columns. Never jitter the data used for fitting.

The plot overlays: binned points, the LOWESS curve, a vertical line at `theta_hat`, dashed lines
at the confidence-interval bounds. X axis is the interval centre, Y is fraction of successes.

### 10.2 Propensity surface

```python
def build_empirical_surface(demands_int, success, *, r1=-3, r2=3) -> dict
# -> {"prob": DataFrame, "counts": DataFrame, "grid": ndarray}
```

Group by the integer pair `(b_l, b_u)`; compute mean success and count per cell; reindex over
the full product grid `r1..r2 × r1..r2`. Three cell states must be visually distinct:

| State | Condition | Render |
|---|---|---|
| observed | count > 0 | colour-mapped by mean success (red → yellow → green), count annotated |
| valid but unobserved | `b_l <= b_u`, count == 0 | neutral fill (e.g. `whitesmoke` via `cmap.set_under`) |
| impossible | `b_l > b_u` | blank |

Overlay the line `b_l + b_u = 2 * theta_hat` — the locus of intervals whose midpoint sits exactly
at the estimate — plus dashed lines for the confidence-interval bounds. This plot is how an item
bank with no informative cells is caught at a glance.

---

## 11. Profiles

```python
# propensity/modelling/profiles.py
def fit_profiles(
    annotations,                # tidy: question_id · dimension · lower · upper
    outcomes,                   # tidy: question_id · subject_id · outcome
    *,
    subjects: list[str] | None = None,     # default: all in outcomes
    dimensions: list[str] | None = None,   # default: all in annotations
    min_items: int = 30,
    **fit_kwargs,
) -> pd.DataFrame               # rows matching §6.5
```

For each `(subject_id, dimension)` pair: inner-join on `question_id`, build the `(N, 2)` demand
array and `(N,)` success array, call `fit_theta`, append a row. Skip pairs with fewer than
`min_items` joined instances, recording them with `theta = NaN` and a `skip_reason`, rather than
dropping them — a silently absent row reads as an unrun analysis.

Failures in one cell must not abort the sweep. Catch per cell, record, continue.

Optional helper: `profile_vector(profiles, subject_id) -> dict[str, float]` returning
`{dimension: theta}` for radar or parallel-coordinate rendering.

---

## 12. Acceptance tests

No test may make a network call, require credentials, or need a GPU. Use
`providers.mock.MockProvider` for everything in the annotation layer.

| # | Test | Assertion |
|---|---|---|
| T1 | Peak normalisation | `two_sided_sigma((b_l+b_u)/2, b_l, b_u, k, k) == 1.0 ± 1e-9` for `(b_l,b_u)` over `{(-3,3), (-2,2), (0,1), (-1,-1), (2,2)}` |
| T2 | Shape | Values decrease monotonically as `x` moves away from the midpoint in both directions; output is finite and in `[0, 1]` everywhere on `[-10, 10]` |
| T3 | Degenerate width | `b_l == b_u` returns finite values (exercises the width-floor sign fix, §9.1) |
| T4 | Likelihood stability | `neg_log_likelihood` is finite for `N = 1000` items with `p` at the clip floor (exercises the sum-vs-product fix, §9.2) |
| T5 | Recovery | Simulate outcomes from a known `theta* ∈ {-2, -0.5, 0, 1.5}` over 500 items with varied intervals; `abs(theta_hat - theta*) < 0.25` |
| T6 | Degenerate outcomes | All-1 and all-0 outcome vectors do not raise; `convergence` is reported honestly; no retries are spent |
| T7 | Path equivalence | Same instances through `mode="sequential"` and `mode="batch"` against `MockProvider` produce **identical prompts and identical rows** |
| T8 | Parser table | `<FINAL_RANGE>[-1, +2]</FINAL_RANGE>` → `(-1, 2)`; two tags → last wins; `[4, 1]` → `parse_ok=False`; no tag → legacy fallbacks tried, then `parse_ok=False` with text retained |
| T9 | Provider isolation | Importing `propensity.modelling` and `propensity.annotation` succeeds with **no vendor SDK installed**; only `propensity.providers.<name>` raises `ImportError` |
| T10 | Contract validation | Outcomes with a value of `0.7`, a duplicate `(question_id, subject_id)`, or a missing column each raise `ContractError` naming the offending rows |
| T11 | Legacy shapes | Wide outcomes, `propensity_lower/upper`, `lower_bound/upper_bound`, `{DIM}_l/{DIM}_u`, and `custom_id` all normalise to the tidy form (§6.4) |
| T12 | Join yield | A deliberate 50% id mismatch is reported, not silently dropped |

T7 is the highest-value integration test in the project: it exercises build → submit → poll →
fetch → parse → write with zero spend.

---

## 13. Deferred — do not build now

**Predictability / assessors.** The separate question of whether propensity demands improve
prediction of instance-level outcomes *on top of* capability demands — the empirical argument
that propensities add something capability profiles miss (§1.1). It needs scikit-learn, a
capability-annotation source, and a cross-validation protocol, and it is not required to produce
curves or profiles.

If it is added later, two conventions established by earlier work are load-bearing and must be
preserved:

- **Point estimates are the mean of per-fold metrics**, never one metric computed on predictions
  pooled across differently-trained fold models. Pooling inflates AUROC badly (one measured
  case: 0.78 pooled against a true mean-of-fold of 0.50). Brier score and expected calibration
  error are per-example averages and suffer far less.
- **No dataset or subject-identity feature.** One-hot subject IDs cannot generalise to unseen
  groups. A `dataset` column may ride along for slicing; it must never reach the estimator.

A reference implementation is at `neurips/src/propensity/predictability/`, if that folder is
present.

---

## 14. Build order

Each step is independently verifiable. Do not start the next until the current one passes its
tests.

1. **`modelling/model.py` + `mle.py`.** Pure math, no I/O, no network. Tests T1–T6. Getting this
   right first defines exactly what everything upstream must produce.
2. **`modelling/io.py`.** Loaders, normalisers, validators, join. Tests T10–T12. If the user has
   real annotation or outcome files, validate the loaders against them at this point.
3. **`modelling/profiles.py` + `curves.py` + `surfaces.py`.** The full fit path, end to end, from
   files to a profile table. At this point the modelling half is complete and useful on its own,
   given annotations from any source.
4. **`providers/base.py` + `providers/mock.py`.** The protocol and the mock. Test T9.
5. **`annotation/`** — rubrics, prompts, parsing, then the runner's sequential path. Tests T7–T8
   against the mock.
6. **One real provider adapter** (`openai_compat`, which also covers self-hosted endpoints).
   Annotate 20 instances sequentially and **read every explanation by hand**. Rubric defects
   surface here and nowhere else.
7. **Remaining adapters + the batch path.** Each adapter is a separate, isolated addition; T7
   must still pass for every batch-capable one.
8. **Plotting**, last and optional.

### 14.1 End-to-end validation

The one check that exercises rubric quality, annotation fidelity and the fit simultaneously:
take outcomes from a subject **known** to sit at a given level — for example, a model the user
ran under an explicit system prompt instructing propensity level `+2` — fit `theta`, and compare.
Recovering approximately `+2` validates the chain. Run this per dimension before trusting any
number the pipeline produces about an uninstructed subject.

Producing those outcomes is the **user's** job — the pipeline does not run models. Document the
requirement; do not build the runner.
