# Tutorial 11: troubleshooting

Find the message, then read across. The command-line tools print errors on one line starting
with `error:` and exit with code 2; the same messages come from the Python functions as
exceptions.

- [Installation](#installation)
- [Starting an annotation run](#starting-an-annotation-run)
- [Annotation results](#annotation-results)
- [Batches](#batches)
- [Loading and joining](#loading-and-joining)
- [Fitting](#fitting)
- [Plots](#plots)
- [Shells](#shells)

## Installation

| Message | Cause | Fix |
|---|---|---|
| `the 'openai' provider needs the openai package: pip install "propel[openai]"` (or `anthropic`, `google`, `azure`, `http`) | the provider's SDK is not installed | run the `pip install` it names |
| `plotting needs matplotlib and seaborn: pip install "propel[plot]"` | a figure was requested without the `plot` extra | `pip install "propel[plot]"` |
| `propel-annotate: command not found` | the environment where PROPEL is installed is not active | activate it, or run `python -m propensity.cli.annotate` |

## Starting an annotation run

| Message | Cause | Fix |
|---|---|---|
| `no provider or model; pass --provider and --model, or set them in config/annotation.yaml` | neither the flags nor the config name them | pass `--provider` and `--model` |
| `no name in words for dimension 'TD': it is not in the dimension catalogue; pass --propensity-name, …` | a code the catalogue does not list, so it has no trait name for the prompt | check the code against [Dimensions](../dimensions.md); for a rubric of your own, pass `--propensity-name "…"` or add a `dimensions.yaml` |
| `…/XX/XX_v1.md: no rubric for dimension 'XX'; rubrics found for: BR, Ex, RA, Ul` | a misspelt code, or a rubrics directory without it | check `--dimension`, and `--rubrics-dir` if you pass one |
| `…/RA/RA_v9.md: no rubric version 'v9' for dimension 'RA'; versions found: v1, v2` | a version that does not exist | pick one of those listed, or drop `--rubric-version` to use the current one |
| `…/dimensions.yaml: entry 'TD' has missing field(s) ['version']` (or `unknown field(s)`) | a malformed catalogue entry | fix the entry ([format](../managing-rubrics.md#the-catalogue)) |
| `…: not valid UTF-8 (…)` | a rubric saved in another encoding | re-save the file as UTF-8 |
| `unknown provider 'x'; available: anthropic, azure, google, http, mock, openai` | misspelt provider | use one of the names listed |
| `--provider-option takes KEY=VALUE, got 'x'` | an option without `=` | write it as `KEY=VALUE` |
| `could not start the 'google' provider: TypeError: … unexpected keyword argument 'batch'` | an option that provider does not take (here, `google` has no batching) | remove it, or check the spelling ([options](../providers.md)) |
| `could not start the 'openai' provider: OpenAIError: Missing credentials …` | no key in the environment | set `OPENAI_API_KEY`. For a local server that needs none, pass `--provider-option api_key=local` |
| `the 'azure' provider needs the resource endpoint: pass endpoint=... or set AZURE_OPENAI_ENDPOINT` | no Azure endpoint | set `AZURE_OPENAI_ENDPOINT` |
| `….jsonl: duplicate question_id 'RA_7'` | two instances share an id | make ids unique before annotating |
| `….jsonl: missing or empty question_text for 'RA_7'` | an instance has no text | fix or remove it |
| `….jsonl: question_id is missing on rows 3, 9` | only some rows have ids | give every row an id, or none (ids are then generated) |

## Annotation results

The run finished, but the summary line reports failures. Look at the `error` and `parse_error`
fields of the failed rows.

| `error` / `parse_error` | Cause | Fix |
|---|---|---|
| a 400 error mentioning `temperature` on every row | the model rejects a temperature parameter | `--provider-option send_temperature=false` |
| `Unsupported parameter: 'max_tokens'` (OpenAI) | a reasoning model wants `max_completion_tokens` | leave `max_tokens` unset; pass `request_options: {max_completion_tokens: 16000}` in the config |
| `RateLimitError`, `429`, `overloaded` | too many parallel calls | lower `--max-workers`, then rerun the failures ([recipe](03-annotating-with-a-provider.md#6-rerun-the-failures)) |
| `stopped at max_tokens before finishing; raise max_tokens` | the reasoning outgrew the cap | raise `max_tokens` in the config, then rerun those instances |
| `the provider returned an empty response (finish reason MAX_TOKENS)` | same, on Gemini | as above |
| `the provider returned an empty response (finish reason SAFETY)`, `the model declined the request` | the provider refused the instance | reword it, or annotate it with another model |
| `no propensity range found in the response` | the annotator ignored the output contract, stopped early, or lost the rubric to a short context window | read the explanation. Use a stronger model; for local servers, raise the context window |
| `[4, 1] violates -3 <= lower <= upper <= 3` | the annotator produced an impossible interval | read the explanation; usually a weak annotator or a rubric ambiguity |

**All intervals are the same.** An annotator that cannot follow the rubric often answers
alike. So does the `mock` provider, which answers `[-1, 2]` unless scripted. Read a sample of
the explanations.

**Nonsense intervals from a local model.** Check the server's context window: the `RA` prompt
is about 2,500 tokens, and a truncated prompt fails silently.

## Batches

| Message | Cause | Fix |
|---|---|---|
| `provider 'openai' has no batch API; use mode='sequential'` | the provider, or this server, cannot batch | use `propel-annotate run` |
| the same, for `azure` with `batch=false` | batching turned off for a standard deployment | use `run`, or a Global Batch deployment |
| `Message Batches takes custom_ids of 1 to 64 letters, digits, '-' or '_', and these question_ids do not fit: […]` | Anthropic rejects these ids | rename the instances (keep a mapping), or use `run` |
| `batch … is running; nothing to fetch yet` (exit 1) | not finished | wait and run `fetch` again |
| `batch … ended as failed; nothing to fetch. Submit it again.` | the provider failed or cancelled the batch | check the provider's console (quota, invalid request), then `submit` again |
| `the prompts no longer match the ones submitted as …` | the instances file, rubric or trait name changed since `submit` | submit again. `--force` only when the change cannot affect the prompts |
| `…: no such job file` | wrong `--job` path | use the `.job.json` path that `submit` printed |
| rows with `missing from the batch output` | the batch lost those instances | rerun them with `run` |
| `batch … returned N id(s) that were never sent` | the output contained unknown ids | nothing to do: they are dropped |
| `KeyError: "no such batch 'mock-batch-1'"` | a `mock` batch across commands without `state_path` | add `--provider-option state_path=out/mock.json` to `submit` |

## Loading and joining

| Message | Cause | Fix |
|---|---|---|
| `…: no 'dimension' column; pass dimension= to say which dimension this file annotates` | a legacy file without dimensions | `--annotations RA=file.jsonl`, or `load_annotations(path, dimension="RA")` |
| `…: no demand-interval columns; expected lower/upper, …` | not an annotation file, or unrecognised column names | pass the annotation file, or rename its columns ([shapes](../data-formats.md#what-load_annotations-and-propel-fit-read)) |
| `…: intervals must satisfy -3 <= lower <= upper <= 3; got …` | an out-of-range or inverted interval marked as parsed | fix those rows, or set their `parse_ok` to false |
| `…: duplicate (question_id, dimension) …` | the same instance annotated twice for one dimension | keep one row per instance and dimension |
| `…: outcomes must be 0 or 1; got ('q7', 'gpt-4o', '0.7')` | a probability or score instead of an outcome | threshold it yourself, deliberately |
| `…: duplicate (question_id, subject_id) …` | two outcomes for one instance and subject | reduce them to one (first try, majority, …) |
| `…: missing column(s) ['outcome', 'subject_id']; expected long form …` | neither long nor wide columns | rename the columns ([outcomes](../data-formats.md#outcomes)) |
| warning `low join yield, check that question_ids match. RA: 48% …` | the ids in the two files differ | compare a few ids from each file ([Tutorial 5](05-preparing-outcomes.md#5-make-the-ids-match)) |
| warning `no usable annotations to join` | every annotation failed to parse | inspect the annotation run |

To see which ids fail to join:

<!-- no-run -->
```python
from propensity import load_annotations, load_outcomes

annotated = set(load_annotations("out/RA.jsonl")["question_id"])
answered = set(load_outcomes("results.csv")["question_id"])
print(sorted(annotated - answered)[:10], sorted(answered - annotated)[:10])
```

## Fitting

These appear in the profile table's `skip_reason` and `warnings` columns
([Diagnostics](../concepts.md#diagnostics)).

| Message | Meaning | What to do |
|---|---|---|
| `no instances after the join` | this subject has no outcomes on this dimension's instances | expected when subjects cover different dimensions; otherwise check the ids |
| `only 23 joined instances, below min_items=30` | too few instances to fit | annotate more, or lower `--min-items` knowingly |
| `95% of instances are [-3, +3]; theta is not identified` | the bank barely measures this trait | build a bank with informative instances |
| `only 40 items; the fit is unstable below 50` | small cell | read the interval widely |
| `60% of items are [-3, +3] and carry no information` | many uninformative instances | the estimate rests on the rest; check the interval tree |
| `only 3 distinct intervals` | too little variety | check the annotator; see the interval distribution |
| `success rate 98.0% is near-degenerate` | nearly all successes or failures | `theta` sits wherever the likelihood is flat; do not interpret it |
| `fit did not converge; its confidence interval is not trustworthy` | the optimiser failed, even after restarts | do not report the interval; inspect the curve and the surface |
| `fit explains the data worse than theta = 0 (pseudo_r2 = -0.4)` | the fit settled on a poor optimum | inspect the curve; try `restart_range` or more instances |
| `fit failed: …` | the optimiser raised on this cell | the message says why; the other cells are unaffected |

## Plots

| Message | Cause | Fix |
|---|---|---|
| `skipped the surface for …: ValueError: the surface is an integer grid; round the demand bounds first` | non-integer bounds, usually from a legacy file | the curve is still drawn. Round the bounds yourself if that is legitimate for your data |
| `skipped the interval plots for XX: …` | the same, for the bank figures | as above |
| `demand bounds must lie within [-3, 3]` | bounds beyond the scale passed to a surface builder | check the data, or pass `r1`, `r2` |
| a figure window never appears, or `no display` errors | drawing through pyplot on a machine without a display | use the `save_*` functions, or set `MPLBACKEND=Agg` |

## Shells

| Symptom | Fix |
|---|---|
| a multi-line command fails in PowerShell | replace the trailing `\` with a backtick `` ` ``, or join the lines |
| `export: command not found` on Windows | `$env:NAME = "value"` in PowerShell, `set NAME=value` in cmd |
| a key set in one terminal is missing in another | environment variables are per session; use a `.env` file with the `dotenv` extra |
