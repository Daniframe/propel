# PROPEL — implementation plan

The phased plan for building the pipeline specified in [CLAUDE.md](CLAUDE.md), with the status of
each phase. Phases follow the build order of CLAUDE.md §14, so each one is independently
verifiable and nothing starts before the previous phase's tests pass.

## Status at a glance

| Phase | Scope | Status |
|---|---|---|
| 0 | Environment, packaging, configs, rubrics, test scaffolding | **Done** |
| 1 | `modelling/model.py` + `mle.py` — the response model and the fit (T1–T6) | **Done** |
| 2 | `modelling/io.py` — loaders, validators, join (T10–T12) | **Done** |
| — | Reproducibility data and a reproduction of the paper's Tables 2 and 3 | **Done** (out of band) |
| 3 | `curves.py`, `surfaces.py`, `profiles.py`, the `fit` entry point | **Done** |
| 4 | `providers/base.py` + `mock.py` + registry (T9) | **Done** |
| 5 | `annotation/` — rubrics, prompts, parsing, runner, the `annotate` entry point (T7–T8) | **Done** |
| 6 | `providers/openai_compat.py` and a live 20-instance check | Adapter **done**; live check run on llama3 — pipeline passed, rubric verdict needs a stronger model |
| 7 | The remaining adapters and the native batch paths | **Done**; no live call made to any of them |
| 8 | `plotting.py` and the documentation pass | **Done** |

Every phase ends with the full test suite green and a stop for review. Commits are the user's.

## Context

CLAUDE.md specifies a propensity measurement pipeline (arXiv:2602.18182) with two independent
entry points: **`annotate`** (instances plus a rubric produce a demand interval `[lower, upper]`
per instance, through any LLM provider) and **`fit`** (annotations plus user-supplied binary
outcomes produce a propensity level `theta` per subject and trait, with curves, surfaces and
profiles). Running subject models, generating items and judging outcomes are all out of scope.

`neurips/` is the reduction baseline: its algorithms and prompt text are the reference, its
package structure and its Azure-only client are not. It stays local and is never committed. The
result is the `propensity` package in the private `Daniframe/propel` repo, passing acceptance
tests T1–T12 with no network access.

What the initial exploration of `neurips/` found:

- `surfaces/model.py` already carries both §9.1 fixes (outward widening, and returning the
  `expit`-based product).
- `surfaces/mle.py` uses the underflow-prone product likelihood and defaults to `robust=False`.
- `annotation/prompts.py` is the *old* prompt, asking for "The propensity range is [..]". The
  current block, ending in the `<FINAL_RANGE>` contract, is `rubrics/presentation.txt`.
- The rubrics are valid UTF-8 with no mojibake, with Windows line endings. RA, Ul, BR and
  `presentation.txt` have **no final newline**, which is what makes the §7.3 prompt seams
  unspaced, so their bytes have to be preserved.
- Fixtures use integer `question_id`s, and pandas turns `"007"` into `7`. Either can silently
  break the join.

## Decisions

Settled with the user: rubrics are copied **verbatim as v1** (line endings only), with their
§7.1 gaps listed in the README; **TD is left out** for now; the virtual environment lives at
`C:\Users\Daniel\.venvs\propel`, outside OneDrive; trait names are RA "risk aversion", Ex
"extraversion", Ul "ultracrepidarianism", BR "blue vs red colour preference" and TD "delay of
gratification", set in `config/annotation.yaml`.

Chosen while building, all still open to revision:

1. **Layout.** The flat §5 layout sits at the repo root. The only additions are `pyproject.toml`,
   `tests/conftest.py` and `propensity/cli/__init__.py`, which holds the YAML settings loader
   both entry points share. The distribution is `propel`, the import is `propensity`, and the
   console scripts are `propel-annotate` and `propel-fit`.
2. **Presentation block.** `rubrics/presentation.txt` became `rubrics/presentation.md` with the
   same bytes. `tests/test_rubric_files.py` pins the SHA-256 of every rubric file, so any edit,
   including an editor adding a final newline, fails until the change is made deliberately.
3. **Likelihood.** Sum-of-logs is the default; `likelihood="product"` is kept for bit-for-bit
   reproduction of published numbers. `fit_theta` uses the spec defaults (`robust=True`,
   `restart_range=(-5, 5)`).
4. **Annotation rows.** The §6.2 fields come first, then the instance's other fields passed
   through unchanged (§6.1), plus `parse_error` and `parse_method`.
5. **Retries.** Provider errors are retried with exponential backoff; parse failures are not,
   because at temperature 0 the model returns the same answer.
6. **Batch detection.** `isinstance(p, BatchCapable)` stays truthful: adapters come as separate
   batch and non-batch classes, and a custom `base_url` is probed once rather than assumed.
7. **Provider isolation (T9).** Adapter modules import cleanly without their SDK because vendor
   imports are lazy; the `ImportError`, with a `pip install "propel[<extra>]"` hint, appears when
   a provider is constructed.
8. **Strict reads.** `question_id` is always a string on read, and JSONL is parsed with `json`
   rather than pandas. Inverted or out-of-range bounds, and duplicate keys, raise `ContractError`
   naming the offending rows.
9. **Profile table.** The §6.5 columns come first, then `skip_reason`, `frac_orthogonal`,
   `n_distinct_intervals`, `outcome_rate`, `n_attempts`, `n_converged`, `restart_theta_std` and
   `warnings`.
10. **Config.** Config files hold no credentials, only provider, model and options; each adapter
    owns its default environment-variable names.
11. **seaborn** stays, in the `[plot]` extra only, so figures match the paper's.

## Target layout, and where each file comes from

| New | From |
|---|---|
| `propensity/modelling/model.py` | `neurips/src/propensity/surfaces/model.py` (helper renamed `_numeric_peak_normaliser`, unused helpers dropped) |
| `propensity/modelling/mle.py` | `surfaces/mle.py` (sum-of-logs, spec defaults, §9.6 diagnostics) |
| `propensity/modelling/curves.py`, `surfaces.py`, `plotting.py` | `surfaces/curves.py`, `surfaces.py`, `plotting.py` (jitter becomes a float amplitude; the surface returns `prob`/`counts`/`grid` and the render sentinel moves into `plotting.py`) |
| `propensity/modelling/io.py` | new, informed by `surfaces/data.py` and `common/io.py` |
| `propensity/modelling/profiles.py` | new, replacing `surfaces/aggregate.py`, whose model × incitement-level column naming is neurips-specific |
| `propensity/annotation/rubrics.py` | `annotation/rubrics.py`, plus `load_presentation` and trait names from config |
| `propensity/annotation/prompts.py`, `parsing.py`, `runner.py` | new, following §7.3, §7.4 and §8; the neurips versions are the old prompt, a first-match parser and OpenAI-shaped clients |
| `propensity/providers/*`, `errors.py`, `cli/*` | new |
| `rubrics/*`, `config/*` | `neurips/rubrics/*` and `neurips/config/*`, with credential placeholders removed and `surfaces.yaml` renamed `modelling.yaml` |

Not carried over: `common/llm_clients.py`, `common/config.py`, `annotation/sequential.py`,
`annotation/batch.py`, the old prompt template, `aggregate.py` and the scripts.

---

## Phase 0 — Environment and scaffolding · Done

- [pyproject.toml](pyproject.toml): core dependencies numpy, scipy, pandas, statsmodels, pyyaml;
  one extra per provider SDK (`openai`, `azure`, `anthropic`, `google`, `http`) plus `plot` and
  `dev`.
- [propensity/errors.py](propensity/errors.py): `ParseError`, `ProviderError`, `ContractError`
  (carrying `.rows`), a `PropensityError` base and a `DataWarning` category.
- [config/annotation.yaml](config/annotation.yaml) and
  [config/modelling.yaml](config/modelling.yaml), with no credentials in either.
- `rubrics/`: the four rubrics and `presentation.md`, copied with only line endings changed and
  hash-pinned by [tests/test_rubric_files.py](tests/test_rubric_files.py).
- [tests/conftest.py](tests/conftest.py): an autouse fixture that blocks socket connections, so
  any test that reaches for the network fails.
- The README gained a development section and the list of §7.1 rubric gaps.

Deviation: the console scripts are not declared yet, since their modules arrive in phases 3 and 5.

## Phase 1 — `model.py` and `mle.py` (T1–T6) · Done

- [model.py](propensity/modelling/model.py): `two_sided_sigma`, ported unchanged in logic, with
  `_numeric_peak_normaliser` for asymmetric slopes.
- [mle.py](propensity/modelling/mle.py): `neg_log_likelihood` (sum-of-logs, with the product form
  available), `fit_theta` (LOWESS start, unbounded BFGS first, guarded bounded restarts, no
  retries on degenerate outcomes, densified `hess_inv`) and `fit_diagnostics` for §9.6.
- Tests: T1–T6 plus the useful regression cases from the neurips suite, and sum equals product on
  small banks.

Deviations from the plan as written:

- The LOWESS fallback triggers below **2** populated bins, not 3: LOWESS handles two points and
  only misbehaves with one.
- `min_width` and `rho` are plumbed through `neg_log_likelihood` and `fit_theta`, otherwise those
  two settings in `modelling.yaml` would do nothing.
- The restart counters are returned whenever `robust=True`, with `n_attempts = 1` if no retry ran,
  so the profile table's columns stay fixed.

Two findings worth remembering:

- **A zero-width interval makes the likelihood spiky.** `[-2, -2]` widens to `[-2.05, -1.95]`
  with a very steep slope, leaving a plateau 0.1 wide with cliffs on both sides. When the true
  level sits on an integer, BFGS stops on the plateau and reports "precision loss", so
  `convergence = 0` even though the estimate is within 0.05. It follows from the paper's
  `min_width = 0.1` and `rho = 2`.
- **Integer intervals create local optima**, which is why the LOWESS starting point matters.

## Phase 2 — `io.py` (T10–T12) · Done

[io.py](propensity/modelling/io.py) provides `read_table`, `write_table`, `load_instances`,
`load_annotations`, `load_outcomes` and `join_annotations_outcomes`, normalising every legacy
shape in §6.2 and §6.3 to the tidy form, and returning `(joined, report)` with the per-dimension
join yield. Tests cover T10–T12 plus identifier handling, outcome coercion and validation. The
suite passes on both pandas 3.0 and pandas 2.2 with warnings raised as errors.

Deviations: the tidy annotation frame keeps a `parse_ok` column so the join can drop and count
failed rows; interval bounds may be any real value in [-3, 3], not only integers, so averaged
annotations still load; and the join re-checks for duplicate keys, since a hand-built frame may
not have been through the loaders.

## Interlude — Reproducibility data and a reproduction · Done

Not part of the original plan; requested mid-build. `reproducibility/` (gitignored) holds the
inputs for the paper's Tables 2 and 3, taken from the local `prop-meas-anon` copy of the original
project: four annotation files, the `*_complete.csv` outcomes, the authors' derived fits, the
tables parsed from the arXiv source, a manifest with checksums, and two scripts. All 384 published
cells have the data they need.

Refitting all 384 cells with the Phase 1–2 code reproduced **375 (98%)** exactly at the printed
two decimals under the original settings (`likelihood="product"`, `robust=False`), and 350 (91%)
under PROPEL's defaults, where the differences are mostly the guarded restarts finding a better
optimum. See `reproducibility/README.md` for the per-dataset breakdown and the five observations
about the published tables. This also satisfies the §14.1 end-to-end check ahead of schedule: the
data contains subjects incited to known levels, and the fits recover them.

## Phase 3 — Curves, surfaces, profiles and `fit` · Done

- [curves.py](propensity/modelling/curves.py): `build_empirical_curve`, binned success by
  interval centre plus a LOWESS smooth. `jitter` is a display-only amplitude, repeatable through
  `seed`, and it never touches the caller's array. `mle._lowess_start` now delegates to this, so
  the binning exists in one place.
- [surfaces.py](propensity/modelling/surfaces.py): `build_empirical_surface`, returning
  `prob`, `counts` and `grid` indexed by b_u against b_l, the orientation plotting will draw. It
  rejects non-integer bounds and bounds off the grid, so the counts always account for every
  observation, and the three §10.2 cell states follow from `counts` and the grid.
- [profiles.py](propensity/modelling/profiles.py): `fit_profiles` and `profile_vector`. A cell
  that cannot be fitted keeps its row with `theta = NaN` and a `skip_reason` (too few items, an
  orthogonal bank, no joined instances, or a failed fit), and the join report rides along in
  `profiles.attrs["join_report"]`.
- [cli/fit.py](propensity/cli/fit.py) and [cli/__init__.py](propensity/cli/__init__.py) for the
  shared YAML loading, wired as `propel-fit`. Flags override the config file, which overrides the
  function defaults; the report goes to stdout and diagnostics to stderr, and a `ContractError`
  exits 2 without a traceback.
- Tests: 36 new, 165 in total, covering the three surface cell states, multi-subject recovery,
  every skip path, a failing cell not aborting the sweep, and the CLI end to end.

**A new finding, and a new diagnostic.** A bank with many zero-width intervals leaves the
likelihood with a peak about 0.1 wide at each integer level. A gradient method started outside
that peak settles on a plateau and reports convergence, which produces a negative pseudo-R²:
the fit explains the data worse than theta = 0 does. `fit_diagnostics` now says so, and on the
paper's data it flags 17 of 392 cells. Whether `fit_theta` should also spend restarts on such
fits is a change to §9.4, so it is left for the user to decide.

**Real-data check.** `propel-fit` over the four paper datasets fits 392 cells and reproduces
`reproducibility/reproduce.py` exactly (largest difference 0.00 across the 384 published cells),
so `fit_profiles` subsumes that script's loop.

## Phase 4 — Providers: protocol, registry and mock (T9) · Done

- [base.py](propensity/providers/base.py): `Completion`, `BatchRequest`, `BatchState` and the
  `LLMProvider` / `BatchCapable` protocols, exactly as §4.2 defines them. Both are
  `runtime_checkable`, so `isinstance` sorts batch-capable providers from the rest; `issubclass`
  raises on a protocol with data members, so nothing uses it.
- [providers/__init__.py](propensity/providers/__init__.py): the registry —
  `register_provider`, `get_provider` and `available_providers`. Adapter modules register
  themselves as they are imported, so adding one changes no core module, and an unknown name
  raises `ProviderError` listing what is available. Nothing is cached and nothing is shared, so
  two providers coexist in one process.
- [mock.py](propensity/providers/mock.py): `MockProvider` (sequential only) and
  `MockBatchProvider` (batch-capable), shipped in the package rather than the tests. Responses
  can be a fixed string, a mapping, a callable or a prebuilt `Completion`, keyed by the prompt
  so that the sequential and batch paths answer identically. The mock records every
  `(system, user)` it receives and counts attempts per key; `transient_failures` exercises
  bounded retry; the batch one scrambles result order, drops ids, invents unknown ids, and can
  walk a scripted sequence of poll states or fail outright.
- Tests: 25 new, 190 in total. **T9** runs in a subprocess with a meta-path blocker for openai,
  anthropic, google, httpx, matplotlib and seaborn, and first proves the blocker bites so the
  test cannot pass merely because an SDK is absent.

The other half of T9, an `ImportError` naming the extra that installs a missing SDK, arrives
with the first real adapter in Phase 6; there is no vendor code to exercise it yet.

## Phase 5 — Annotation (T7–T8) · Done

- [rubrics.py](propensity/annotation/rubrics.py): `rubric_path_for`, `load_rubric`,
  `load_presentation` and `available_dimensions`. Files are read as UTF-8 and handed on with
  nothing stripped or reformatted, because the prompt's seams come from them. A missing rubric
  says which dimensions do have one, which is how the absent TD rubric reports itself.
- [prompts.py](propensity/annotation/prompts.py): `build_annotation_prompt` exactly as §7.3
  writes it, plus `as_single_string` for a provider with one input field. A test asserts the
  assembled prompt is the four pieces and nothing else, and that the closing `</rubric>` comes
  only from the presentation block.
- [parsing.py](propensity/annotation/parsing.py): `<FINAL_RANGE>` first, then the two legacy
  phrasings, always taking the **last** match, and recording which pattern matched. Bounds off
  the scale fail rather than being clamped, and nothing raises: a failure is a `ParsedRange`
  with a reason, since the runner must never die mid-run.
- [runner.py](propensity/annotation/runner.py): `build_requests`, `run_sequential` (thread pool
  with bounded retry on provider errors, none on parse failures), `submit`, `wait_for_batch`,
  `collect` and `rows_from_completions`, with `annotate()` composing them. Both paths share the
  first and the last, so identical prompts and rows hold by construction. Rows come back one
  per instance in input order, with the response text always kept, and a failed batch is
  recorded on every row rather than raised.
- [cli/annotate.py](propensity/cli/annotate.py): `run`, `submit [--wait]`, `status` and `fetch`,
  wired as `propel-annotate`. `submit` writes `<out>.job.json` **before** polling starts;
  `fetch` rebuilds the prompts and refuses if their hash drifted, unless forced. Credentials
  are filtered out of the job file.
- Tests: 73 new, 263 in total. **T7** checks that the sequential and batch paths give identical
  prompts and identical rows, with the batch results scrambled; **T8** is the parser table. Also
  covered: a dropped id becoming a provider-error row, an id that was never sent being reported
  and dropped, retries stopping at the bound, and every CLI subcommand.

Two things this phase changed outside its own scope:

- The mock gained an optional `state_path`. A real batch lives on the provider's side, which is
  what lets submit, status and fetch be separate commands; without persistence the mock could
  not stand in for that, and the resumable flow could not be tested end to end. This puts
  `mock.py` at 148 lines, over the ≤120 the spec sets for adapters. The rule is there to catch a
  leaking vendor abstraction, so the line-count test in Phase 7 will cover the vendor adapters
  and exempt the mock, whose extra length is all test scripting.
- [tests/test_end_to_end.py](tests/test_end_to_end.py) now runs the §14.1 check offline, with
  simulation standing in for inciting: annotate 200 instances with a scripted mock annotator,
  write the rows, load them back, draw outcomes for two subjects at known levels, and fit. Both
  levels come back within 0.25, and the run warns about nothing.

## Phase 6 — `openai_compat` and the live check · Adapter done, rubric check open

[openai_compat.py](propensity/providers/openai_compat.py) ships two classes so that
`isinstance(p, BatchCapable)` stays truthful: `OpenAICompatProvider` for one call at a time and
`OpenAIBatchProvider` for Files plus Batches. The SDK is imported lazily inside the constructor,
so the module imports without `openai` present and the `ImportError` names the extra that
installs it. `complete` never raises: a provider exception comes back as a `Completion` with
`error` set, and so does an empty response. `base_url` points the same adapter at a self-hosted
server or a gateway, `api_key_env` chooses the environment variable, and `request_options` is
merged into every request for a model that wants something else, such as
`max_completion_tokens`.

`get_provider("openai", batch=None)` skips the probe for the official endpoint, which has a
batch API, and probes a custom `base_url` once with `batches.list(limit=1)` rather than
discovering at submit time that there is none.

Tests: 27 new, 290 in total, all against a fake client standing in for the slice of the SDK the
adapter touches. They cover the request body, the failure paths, client construction from the
environment, every batch status mapping, the error file being folded into rows, and the probe
being called exactly once — and never for the official endpoint. The two tests that need the
real SDK skip when it is absent, so the suite stays green with no vendor package installed.

**The live check ran locally on 2026-09-17**, with `llama3:latest` (8B) through Ollama and nothing
spent; `live_check/REVIEW.md` (kept local and untracked) has the full write-up and every explanation.
The pipeline passed: 20 of 20 completed and parsed, and the legacy fallbacks recovered the five
responses that broke the output contract. The model did not: its "unbiased option" was the first
guaranteed option listed in 19 of 20 items, so it never did the expected-value arithmetic the
rubric presupposes, and the run cannot say anything about rubric quality. The one rubric point
it prompted is an asymmetry in the RA ±1 worked examples (20% at level −1, 10% at level +1). The
rubric check stays open: it needs a model that can do the arithmetic, and GPT-4.1 on the same 20
items would be the most informative, since the published annotations came from it.

On the ≤120-line rule for adapters: this file is 136 lines and `mock.py` is 148, but both are 93
lines of code — the rest is docstrings and the blank lines PEP 8 asks for. The rule exists to
catch a leaking abstraction, so the line-count test in Phase 7 will measure code lines.

## Phase 7 — The remaining adapters · Done

Four more adapters, each registering itself and importing its SDK lazily. All vendor-specific
choices were checked against current vendor documentation and against the installed SDKs
(openai 3.14, anthropic 1.6, google-genai 2.24).

- [azure_openai.py](propensity/providers/azure_openai.py): a subclass of the OpenAI adapter.
  - `model` is the deployment name.
  - It talks to Azure's v1 API at `{endpoint}/openai/v1/` through the plain OpenAI client, as
    Microsoft now documents. `api_version` switches to `AzureOpenAI` for a resource still on
    dated API versions.
  - The endpoint comes from `endpoint=` or `AZURE_OPENAI_ENDPOINT`, and the key from
    `AZURE_OPENAI_API_KEY`. A missing endpoint is named before any call.
  - It is batch-capable by default and never probed, because a probe cannot tell a Global Batch
    deployment from a standard one. `batch=False` opts a standard deployment out.
  - Batch lines carry `"url": "/v1/chat/completions"`, while `batches.create` is told
    `/chat/completions`.
- [anthropic.py](propensity/providers/anthropic.py):
  - `system` is a top-level parameter.
  - `max_tokens` defaults to **16000**, not the planned 4096: current models think before
    answering, the thinking counts against `max_tokens`, and 16000 stays under the SDK's limit
    for non-streaming calls.
  - Message Batches are on by default. A `question_id` outside `^[a-zA-Z0-9_-]{1,64}$` is refused
    before anything is sent.
  - Errored, cancelled and expired batch results become error rows. A `refusal` or `max_tokens`
    stop becomes an error, with the text kept in `raw`.
  - Server-side model fallbacks are deliberately not enabled: they would swap the annotating
    model and make the `annotator` field false.
  - In SDK 1.x `temperature` is no longer a keyword of `messages.create()` (passing it is a
    `TypeError`), though the API still takes it. The adapter sends it through `extra_body`, which
    puts the same JSON on the wire; batch params carry it directly.
- [google.py](propensity/providers/google.py):
  - The system part travels as `system_instruction`.
  - The SDK's automatic function-calling loop is switched off: no tools are passed, and with it
    on, every call goes through that loop and the SDK logs a warning.
  - An empty response names its finish reason (`SAFETY`, `MAX_TOKENS`).
  - Not batch-capable.
- [generic_http.py](propensity/providers/generic_http.py): a URL, extra headers, and a bearer
  key from `api_key` or `api_key_env`.
  - `build_payload` and `extract_text` are callables, or `"module:function"` strings so they can
    come from YAML or `--provider-option`.
  - Every failure comes back as a `Completion`: HTTP status, bad JSON, or an unexpected shape.
  - Not batch-capable.

**Temperature, a deviation from §8 made explicit.** §8 fixes temperature at 0, but current models
refuse it:
- Anthropic's Opus 4.7 and later and Fable return a 400 for any temperature, and Sonnet 5 for any
  value other than the default.
- OpenAI's reasoning models accept only the default.

Every adapter now takes `send_temperature`:
- **By default it is `True`.** §8 holds, and a model that rejects temperature fails loudly as
  provider-error rows.
- **`send_temperature=False` leaves temperature out** and logs a warning that intervals may vary
  between reruns.

Nothing drops temperature silently. The OpenAI adapter also gained `batch_endpoint`, for Azure,
and an extra-specific install hint.

**Tests:** 72 new, 362 in total, all green with warnings as errors. In the environment with no
vendor SDK and pandas 2, 351 pass and 11 skip, and every skip is a test that drives a real SDK.
- [tests/fakes.py](tests/fakes.py) has fake clients for all four SDK shapes. Batch output is
  built from what was actually submitted, then shuffled.
- One test file per adapter covers request shape, credentials from the environment, and every
  failure and batch-status path.
- One test per adapter drives the **real installed SDK over an in-memory `MockTransport`** and
  asserts the wire JSON, URL path and auth header. This catches wrong SDK usage that fakes cannot,
  such as the `temperature` removal above.
- [tests/test_adapters.py](tests/test_adapters.py):
  - the registry lists all six adapters, and `isinstance(p, BatchCapable)` is truthful for each;
  - **T7** for openai, azure and anthropic through `annotate()`: identical rows, including a parse
    failure, and identical request JSON on both paths, while the batch output comes back out of
    order;
  - **T9** adapter by adapter: with every SDK blocked, each module still imports, and constructing
    each adapter raises an `ImportError` naming its own extra;
  - the **line budget**: at most 120 code lines, counting every physical line of a statement but
    no docstrings, comments or blanks. The counter has its own test. The mock fits the budget, so
    it is measured with the rest rather than exempted as Phase 5 proposed.

| Adapter | Lines | Code lines |
|---|---|---|
| `openai_compat.py` | 149 | 106 |
| `mock.py` | 148 | 96 |
| `anthropic.py` | 125 | 87 |
| `google.py` | 72 | 48 |
| `generic_http.py` | 69 | 44 |
| `azure_openai.py` | 53 | 29 |

**Not verified:** none of the four has made a live call. Their request and batch shapes are checked
against current documentation and the real SDKs only, so a first run on each should be small, with
credentials.

## Phase 8 — Plotting and documentation · Done

[plotting.py](propensity/modelling/plotting.py) draws the plain structures from `curves.py`,
`surfaces.py` and the fit, and imports matplotlib and seaborn only when it draws. Importing
`propensity.modelling` still needs neither, and T9 still blocks both while importing it. Drawing
without them raises an `ImportError` naming `pip install "propel[plot]"`, as the adapters do.

- **`plot_propensity_curve`** (§10.1): binned success against interval centre, the LOWESS
  smooth, a solid line at theta and dashed lines at its confidence bounds, and the incited level
  in grey when given. The x-axis widens to keep jittered bins and an out-of-range estimate in view.
- **`plot_propensity_surface`** (§10.2): the three cell states stay distinct. Observed cells are
  coloured red to green and show their count, valid but unobserved cells are whitesmoke, and
  impossible cells are blank. `b_u` grows upwards, and the `b_l + b_u = 2θ` lines are clipped to
  the grid exactly rather than sampled. The legend sits below the axes: inside them, the θ̂ line
  of some mid-range estimate always ran underneath it. An estimate off the grid (|θ̂| > 3.5)
  draws no line but still gets its legend entry, so its value is never lost.
- **Non-converged fits** get "(the fit did not converge)" beside the estimate on both plots,
  since §9.6 forbids showing a tight interval without its convergence status.
- **`save_profile_plots(profiles, annotations, outcomes, out_dir)`** writes
  `{subject}_{dimension}_curve.png` and `..._surface.png` for every cell with joined data.
  - Unfitted cells are drawn too, without an estimate and with the skip reason in the title,
    because a surface is how a bank with no informative cells is caught.
  - It renders through `Figure` and the Agg canvas, so no display or GUI backend is needed.
  - Filenames are made safe but keep signed levels such as `_+2`, and colliding names get a
    suffix.
  - A plot that fails is logged and skipped; the rest carry on.
- **`propel-fit --plots DIR`** checks for matplotlib before fitting, so a long fit never fails at
  its last step.

Deviations and fixes:
- Drawing the paper's RiskAv surfaces with warnings as errors caught an estimate off the grid
  whose confidence bound was on it. Only the unlabelled dashed bound was drawn, so the legend
  warned and the θ̂ value appeared nowhere. Fixed as above, with a test for that case.
- The neurips renderer's `cmap.set_under` is pending deprecation in matplotlib 3.11, which a run
  with warnings as errors caught. It is now `with_extremes(under=...)`, and the `plot` extra is
  pinned to `matplotlib>=3.5` and `seaborn>=0.12`.
- The README's `http` example exposed a real bug: a console script does not put the working
  directory on `sys.path`, so `myformat:build_payload` could not be found and the CLI crashed with
  a traceback. `generic_http` now also accepts `path/to/file.py:function`, splitting on the last
  colon so Windows drive letters work. A name that cannot be loaded raises a `ProviderError`,
  which the CLI prints as one line. This puts `generic_http.py` at 57 code lines.

[README.md](README.md) was rewritten for people using the pipeline. It covers installation and
extras, a quick start, the annotation CLI (run versus submit, status and fetch), the provider
table with credentials, batching and temperature, the data contracts, the fit CLI, the profile
columns, the diagnostics and their thresholds, reading the plots, the §14.1 validation
requirement, the Python API, adding a provider, and the rubric gaps and missing TD. Every command
and name in it was checked against the code.

**Tests:** 23 new, 385 in total, all green with warnings as errors. With no vendor SDK, no
matplotlib and pandas 2, 358 pass and 27 skip. With matplotlib added to that environment, the
plotting, fit CLI and provider tests all pass under pandas 2 as well.
- [tests/test_plotting.py](tests/test_plotting.py) inspects the drawn artists rather than
  comparing images. It checks each cell's state and colour, that only observed cells carry
  counts, the axis orientation, that the estimate lines satisfy `b_l + b_u = 2θ` and reach the
  grid edge, the convergence label, unfitted and empty cells, filename collisions, and failure
  isolation.
- The fit CLI tests cover `--plots` writing every cell, and failing before the fit when matplotlib
  is missing.
- The `generic_http` tests cover the file-path form, with a Windows drive letter, and the clear
  error.

**Checked by hand:** `propel-annotate` run, submit, status and fetch through the installed console
scripts with the mock, and `propel-fit --plots` on the paper's local RiskAv data: 96 cells and
192 figures in under a minute. The figures were inspected. Incited `+2` fits at 2.27 and `-2` at
-1.94, and the surfaces show at a glance how few cells that bank covers.

### Addendum: the figures from `visualisations.py`

The user's `visualisations.py`, which is untracked, had four more figures. Each is now in the
package, split the way the curve and surface already are: data in
[surfaces.py](propensity/modelling/surfaces.py) and drawing in
[plotting.py](propensity/modelling/plotting.py). No module was added, so the §5 layout stands.

| `visualisations.py` | Now |
|---|---|
| `interval_distribution` | `build_interval_distribution` + `plot_interval_distribution` |
| `interval_distribution_xmas` | `build_interval_tree` + `plot_interval_tree` |
| `interval_distribution_xmas_grid`, `_best_grid` | `plot_interval_trees`, `_layout` (same rule: fewest empty slots, then squarest, then fewest rows) |
| `theoretical_subject_propensity_surface`, `propensity_probability` | `build_model_surface` + `plot_model_surface` |

What changed on the way in:
- **One set of drawing conventions.** Every grid now follows the empirical surface: `b_l`, or
  the interval centre, across; `b_u`, or the length, up; and the three cell states (occupied and
  labelled, valid but empty in whitesmoke, impossible blank). A shared helper draws all four
  heatmaps, and a shared renderer writes every file off-screen.
- **The tree's unreachable cells are blank.** An integer interval with an even length has a
  whole centre, and one with an odd length a half. The original showed the other cells as 0.00,
  as if they could have been occupied. At the user's request, `show_invalid=True` fills them
  light grey instead, the original's fill for masked cells. They stay unlabelled and distinct
  from empty valid cells (whitesmoke). The option passes through `plot_interval_trees` and
  `save_annotation_plots`.
- **The model surface is Eq. 5 itself.** `propensity_probability` equals `two_sided_sigma` to
  within 6e-16, but it had no width floor and divided by zero at `b_l = b_u`, which is why the
  original left the diagonal out. `build_model_surface` calls `two_sided_sigma`, so it is exactly
  the model the fit uses, diagonal included. It uses the empirical surface's red-to-green scale
  rather than viridis. At the user's request it takes `smooth`:
  - `False`, the default: the empirical surface's integer grid, drawn as cells, cell for cell.
  - `True`: a continuous grid every `resolution` (0.05), drawn as filled contours with labelled
    lines at 0.25, 0.5 and 0.75.

  The flag travels with the data, so `plot_model_surface` draws whichever it is given.
- **Distributions keep the original's `Reds` scale** and its share-of-bank values, labelled in
  occupied cells. A share that would print as 0.00 shows as `<.01`.
- **Bugs not carried over:**
  - `plt.cm.get_cmap`, removed in matplotlib 3.9, so the script no longer ran on the installed
    3.11;
  - a duplicated `imshow` in the distribution plot;
  - the grid's shared maximum ignoring the level range and the proportion or count choice;
  - one-row and one-column grids breaking the axes handling;
  - unused grid slots left as empty axes.
- **`save_annotation_plots(annotations, out_dir)`** writes `{dimension}_intervals.png` and
  `{dimension}_tree.png` for each dimension, plus `interval_trees.png` when there are several.
  Rows that failed to parse are excluded, as in the fit. `propel-fit --plots` now calls it too.

**Tests:** 34 new, including `smooth` and `show_invalid`, 420 in total, all green with warnings
as errors. With minimal dependencies, 375 pass and 45 skip.
- The builders are checked against hand counts. The tree has exactly 28 reachable cells, the valid
  pairs on a 7-level grid, and it agrees with the bounds view cell for cell on a random bank. The
  model surface equals `two_sided_sigma` at every valid interval and peaks at 1 on intervals
  centred on theta.
- The renderers are checked through their artists: cell states, labels, `<.01`, scale and
  orientation. The model surface has the same colours and cell edges as the empirical surface,
  several trees share one `vmax` and one colour bar, and empty grid slots are removed.
- Saving is checked for per-dimension files, the grid only with several dimensions, the
  dimension filter, excluded parse failures, and failure isolation.

**Checked by hand:** trees, distributions and the tree grid for the paper's four GPT-4.1
annotation files, and model surfaces at steps 0.05 and 1, all inspected as images.

## Verification

- **Tests:** `C:\Users\Daniel\.venvs\propel\Scripts\python.exe -m pytest -q -W error` after every
  phase. No network (enforced by the socket blocker), no credentials, no GPU. A second environment
  with only the core dependencies and pandas 2 checks that the suite skips cleanly what it lacks.
- **Offline end to end**, from Phase 5: `propel-annotate run --provider mock` over sample
  instances, then simulated outcomes from a known theta, then `propel-fit`, checking that the
  profile recovers theta and that the yield and diagnostics are printed.
- **Real data**, from Phase 3: `fit_profiles` against `reproducibility/`, compared with the
  authors' published fits.
- **Live:** the Phase 6 hand review of twenty explanations.
- **Scientific:** the §14.1 incited-level round trip, already demonstrated by the reproduction.
