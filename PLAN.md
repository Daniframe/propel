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
| 5 | `annotation/` — rubrics, prompts, parsing, runner, the `annotate` entry point (T7–T8) | **Next** |
| 6 | `providers/openai_compat.py` and a live 20-instance check | Planned, needs credentials |
| 7 | The remaining adapters and the native batch paths | Planned |
| 8 | `plotting.py` and the documentation pass | Planned |

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

## Phase 5 — Annotation (T7–T8) · Next

- `build_annotation_prompt` follows §7.3 byte for byte, with `as_single_string` for providers
  that accept one field.
- The parser tries `<FINAL_RANGE>` (last match), then the legacy phrase, then a bare bracket
  (last match), and validates the bounds.
- `runner.py`: `build_requests`, `run_sequential` (thread pool with retries), `submit`, `collect`
  and `rows_from_completions`, with `annotate()` composing them. Both paths share the first and
  last, so identical prompts and rows hold by construction and T7 checks it. Rows come back in
  input order, with a summary line.
- `propel-annotate` subcommands: `run` (always sequential); `submit [--wait]`, which writes
  `<out>.job.json` *before* polling starts; `status --job`; and `fetch --job`, which rebuilds the
  prompts and refuses if their hash drifted since submission.
- Tests: T7 (scrambled order, unknown ID warns, missing ID becomes a provider-error row), T8, the
  prompt byte layout, retry behaviour, `batch` on a non-batch provider raising, the `auto`
  fallback being logged, and a CLI smoke run with `--provider mock`.

## Phase 6 — `openai_compat` and the live check · Planned

Lazy `import openai`. The constructor takes `model`, `api_key`, `api_key_env`, `base_url` and an
injectable `client` for tests; `complete` never raises. The batch class uses Files + Batches, maps
provider states onto `BatchState`, and folds the error file into error completions.

**Needs the user:** an API key or a self-hosted `base_url`, a model name and an instances file.
Twenty instances are annotated sequentially and every explanation is read by hand, which is where
rubric defects surface. No paid call happens without asking first.

## Phase 7 — The remaining adapters · Planned

`azure` (subclass; `model` is the deployment name), `anthropic` (top-level `system`, a default
`max_tokens`, Message Batches, and a clear error when a `question_id` does not fit Anthropic's
`custom_id` pattern), `google` (`system_instruction`, no batch) and `generic_http` (httpx plus
`build_payload` and `extract_text`). Each gets a fake-client test, T7 is re-run for every
batch-capable adapter, and a test asserts each adapter file is at most 120 lines.

## Phase 8 — Plotting and documentation · Planned

Port both renderers with guarded imports, so importing `propensity.modelling` never needs
matplotlib. The curve jitters by ±0.25 for display only; the surface shows its three cell states.
Add `propel-fit --plots DIR`. The README then covers installation, both entry points, the data
contracts, how to add a provider, the §14.1 validation requirement, the rubric gaps and the
missing TD rubric.

## Verification

- **Tests:** `C:\Users\Daniel\.venvs\propel\Scripts\python.exe -m pytest -q` after every phase.
  No network (enforced by the socket blocker), no credentials, no GPU.
- **Offline end to end**, from Phase 5: `propel-annotate run --provider mock` over sample
  instances, then simulated outcomes from a known theta, then `propel-fit`, checking that the
  profile recovers theta and that the yield and diagnostics are printed.
- **Real data**, from Phase 3: `fit_profiles` against `reproducibility/`, compared with the
  authors' published fits.
- **Live:** the Phase 6 hand review of twenty explanations.
- **Scientific:** the §14.1 incited-level round trip, already demonstrated by the reproduction.
