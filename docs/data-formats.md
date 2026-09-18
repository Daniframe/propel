# Data formats

Every file is `.jsonl` (one JSON object per line) or `.csv`, chosen by extension. Anything else
raises `ContractError`. Files are read and written as UTF-8 with `\n` line endings.

Reading is permissive about shapes and column names. Validation is strict, and every
`ContractError` names the offending rows (also available as `error.rows`).

- [Identifiers](#identifiers)
- [Instances](#instances): input to annotation
- [Annotations](#annotations): output of annotation, input to fitting
- [Outcomes](#outcomes): your results, input to fitting
- [The join](#the-join)
- [Profiles](#profiles): output of fitting
- [Job files](#job-files): batch bookkeeping

## Identifiers

`question_id` and `subject_id` are always handled as strings:

- `7`, `7.0` and `"7"` are the same id, `"7"`.
- `"007"` stays `"007"` in JSONL and CSV alike (CSV cells are read as text). It does **not**
  match `7`.
- An integer id in one file joins the same id written as text in another.

## Instances

The tasks to annotate. One per row.

```jsonl
{"question_id": "RA_0", "question_text": "Choose between: Option A (certain $100) or Option B (50% chance of $220, 50% chance of $0)", "source": "bench-1"}
{"question_id": "RA_1", "question_text": "..."}
```

| Field | Required | Notes |
|---|---|---|
| `question_id` | on every row, or on none | unique, non-empty; the join key for everything downstream |
| `question_text` | yes | non-empty text; the only thing the annotator sees |
| anything else | no | passed through, untouched, onto every annotation row |

**A file without `question_id`** gets ids `{file stem}_{row index}`, numbered over the whole
file: `items.jsonl` gives `items_0`, `items_1`, and so on. Sample only **after** loading.
Numbering a sample instead would give different ids to different subsets, and the annotations
could never be joined back.

**CSV cells are read as text**, and `NA` or `null` stay literal text, never missing values.

**Rejected:**
- `question_id` on some rows but not others;
- an empty `question_id`;
- a missing or empty `question_text`;
- a duplicate `question_id`;
- an empty file.

## Annotations

### What `annotate` writes

One row per instance, in input order, always, including instances that failed.

```jsonl
{"question_id": "RA_0", "dimension": "RA", "lower": -1, "upper": 3, "annotator": "openai:gpt-4.1", "explanation": "Level 0: ...\n<FINAL_RANGE>[-1, +3]</FINAL_RANGE>", "parse_ok": true, "error": null, "parse_error": null, "parse_method": "final_range", "source": "bench-1"}
```

| Field | Type | Meaning |
|---|---|---|
| `question_id` | str | the instance |
| `dimension` | str | dimension code, e.g. `RA` |
| `lower`, `upper` | int or null | the demand interval; null unless `parse_ok` |
| `annotator` | str | `provider:model`, e.g. `anthropic:claude-haiku-4-5` |
| `explanation` | str | the annotator's full response, kept whatever happened; the audit trail |
| `parse_ok` | bool | a valid interval was read; false rows are excluded from fitting |
| `error` | str or null | the provider error, when the call itself failed |
| `parse_error` | str or null | why no valid interval was read |
| `parse_method` | str or null | `final_range`, `legacy_phrase` or `legacy_bracket` ([parsing](rubrics.md#parsing)) |
| other fields | any | copied from the instance |

A row is in exactly one of three states:

| State | `parse_ok` | `error` | `parse_error` |
|---|---|---|---|
| ok | true | null | null |
| parse-failed | false | null | set |
| provider-error | false | set | null |

### What `load_annotations` and `propel-fit` read

The format above, and older shapes, normalised on read:

| Shape | Recognised by | Notes |
|---|---|---|
| canonical | `lower`, `upper` | |
| legacy bounds | `propensity_lower`, `propensity_upper` | renamed to `lower`, `upper` |
| legacy bounds | `lower_bound`, `upper_bound` | renamed to `lower`, `upper` |
| wide, several dimensions | `{DIM}_l`, `{DIM}_u` column pairs | melted to one row per (question_id, dimension) |
| legacy ids | `custom_id` or `instance_id` | renamed to `question_id` when there is no `question_id` |

- **The dimension.** A file with bound columns but no `dimension` column needs the dimension
  given: `load_annotations(path, dimension="RA")`, or `--annotations RA=path` on the command
  line. For a file that has one, `dimension=` keeps only that dimension.
- **`parse_ok`.** Missing means true. Accepted values are `true`/`false`, `1`/`0` and
  `"1.0"`/`"0.0"`, case-insensitive. An empty value means false.
- **Bounds.** Numbers or numeric strings, including `"+3"`. Empty means null.

**Rejected** (`ContractError`):
- a usable row outside `-3 ≤ lower ≤ upper ≤ 3`;
- a duplicate (`question_id`, `dimension`);
- a missing `question_id` or dimension;
- a non-numeric bound;
- an unreadable `parse_ok`;
- no recognisable bound columns at all.

Rows with `parse_ok` false or a null bound are kept, and the join drops and counts them.

The tidy frame returned: `question_id · dimension · lower · upper · parse_ok`, with float
bounds.

## Outcomes

Your models' results: one 0/1 outcome per (instance, subject).

**Long form**, preferred:

```csv
question_id,subject_id,outcome
RA_0,gpt-4o,1
RA_0,llama-3.3-70b,0
RA_1,gpt-4o,
```

**Wide form**: one `{subject}_outcome` column per subject; the subject id is the column name
without `_outcome`. Other columns are ignored.

```csv
question_id,gpt-4o_outcome,llama-3.3-70b_outcome
RA_0,1,0
RA_1,,1
```

| Value | Read as |
|---|---|
| `1`, `0`, `1.0`, `0.0`, `true`, `false` (any case), JSON `true`/`false` | 1 or 0 |
| empty, `null`, NaN | missing: dropped, **never** counted as a failure |
| anything else, e.g. `0.7`, `yes`, `2` | rejected |

- A missing outcome means the subject produced no response, which is not the same as getting
  the instance wrong, so it is dropped rather than zero-filled.
- `custom_id` or `instance_id` also work as the id column.

**Rejected** (`ContractError`):
- a value that is not 0 or 1, including probabilities;
- a duplicate (`question_id`, `subject_id`);
- a missing id;
- neither long nor wide columns present.

The tidy frame returned: `question_id · subject_id · outcome`, with integer outcomes.

## The join

`join_annotations_outcomes` (and therefore `fit_profiles` and `propel-fit`) takes an inner
join on `question_id`, after dropping annotations that failed to parse or have a null bound.

It returns the joined frame `question_id · dimension · lower · upper · subject_id · outcome`
and a report:

| Key | Meaning |
|---|---|
| `n_annotation_rows` | annotation rows given |
| `n_unusable` | rows dropped: parse failed or a null bound |
| `per_dimension` | per dimension: `n_annotated`, `n_joined`, `yield` (joined ÷ annotated) |
| `n_outcome_ids` | distinct `question_id`s in the outcomes |
| `n_unmatched_outcome_ids` | outcome ids with no usable annotation |
| `cell_sizes` | instances per (subject, dimension) |

It warns (`DataWarning`) when a dimension's yield is below 0.9 or a cell has fewer than 50
instances. A low yield almost always means mismatched ids: check them before anything else.

## Profiles

The output of `fit_profiles` and `propel-fit`: one row per (subject, dimension), including cells
that could not be fitted.

```csv
subject_id,dimension,n_items,theta,se,ci95_lower,ci95_upper,converged,reference_ll,gof,pseudo_r2,skip_reason,frac_orthogonal,n_distinct_intervals,outcome_rate,n_attempts,n_converged,restart_theta_std,warnings
gpt-4o,RA,487,-1.34,0.011,-1.36,-1.32,1,-312.44,-238.91,0.235,,0.12,19,0.61,,,,
```

| Column | Meaning |
|---|---|
| `subject_id`, `dimension` | the cell |
| `n_items` | joined instances |
| `theta` | fitted level; empty when not fitted |
| `se` | standard error |
| `ci95_lower`, `ci95_upper` | `theta ± 1.96·se` |
| `converged` | 1 or 0; empty when not fitted. Read it with the interval |
| `reference_ll` | log-likelihood at `theta = 0` |
| `gof` | log-likelihood at `theta` |
| `pseudo_r2` | `1 − gof / reference_ll`; negative means worse than `theta = 0` |
| `skip_reason` | why a cell was not fitted (see below) |
| `frac_orthogonal` | share of `[-3, +3]` instances |
| `n_distinct_intervals` | distinct intervals in the cell |
| `outcome_rate` | share of successes |
| `n_attempts`, `n_converged`, `restart_theta_std` | restart statistics, when the fit used robust restarts |
| `warnings` | every diagnostic this cell triggered, joined by `; ` |

`skip_reason` values:

| Reason | When |
|---|---|
| `no instances after the join` | the subject has no outcomes for this dimension's instances |
| `only N joined instances, below min_items=M` | fewer than `min_items` (default 30) |
| `P% of instances are [-3, +3]; theta is not identified` | more than 90% orthogonal |
| `fit failed: …` | the optimiser raised; the sweep continues with the next cell |

In Python, `profiles.attrs["join_report"]` holds the join report.

## Job files

`propel-annotate submit --out RA.jsonl` writes `RA.jsonl.job.json` **before** any polling, so a
batch that takes hours can be picked up later from the job file alone.

```json
{
  "batch_id": "msgbatch_01...",
  "provider": "anthropic",
  "model": "claude-haiku-4-5",
  "provider_options": {"send_temperature": true},
  "dimension": "RA",
  "propensity_name": "risk aversion",
  "instances": "items.jsonl",
  "rubrics_dir": null,
  "rubric_version": "v1",
  "out": "RA.jsonl",
  "n_requests": 350,
  "prompts_sha256": "4f1c...",
  "submitted_at": "2026-09-18T10:02:11+00:00"
}
```

- **No credentials.** Provider options whose name contains `api_key`, `token`, `secret` or
  `password` are left out, so `status` and `fetch` need credentials in the environment.
- **`rubrics_dir`** is `null` for the packaged rubrics, and `rubric_version` is the version
  actually used, so the job is reproducible even after the catalogue moves to a newer version.
- **`prompts_sha256`.** A fingerprint of every prompt submitted. `fetch` rebuilds the prompts
  from `instances`, `rubrics_dir`, `rubric_version` and `propensity_name`, and refuses when the
  fingerprint differs, for example after the rubric files changed (see
  [Batch annotation](tutorials/04-batch-annotation.md)).
