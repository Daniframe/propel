# Rubrics and prompts

The rubric is the most consequential file in the project: the annotator reads it verbatim, and
its wording determines every interval ever fitted against it.

## Files

The rubrics ship inside the package, in `propensity/rubrics/`:

```
propensity/rubrics/
  dimensions.yaml          the catalogue: each dimension's trait name, poles and current version
  presentation.md          shared by every dimension: reasoning procedure and output contract
  RA/RA_v1.md              one rubric per dimension and version
  Ex/Ex_v1.md
  ...
```

[Dimensions](dimensions.md) lists every dimension shipped. [Managing rubrics](managing-rubrics.md)
covers the catalogue, updating a rubric, and adding a dimension.

- **Which file is read.** `{CODE}/{CODE}_{version}.md`: `--dimension CODE` picks the dimension,
  and the version is the catalogue's current one unless `--rubric-version` asks for another.
- **Another directory.** `--rubrics-dir` (Python: `rubrics_dir=`) reads a directory of your own
  with the same layout instead.
- **Encoding.** Files are read as UTF-8 and used as stored: nothing strips, re-indents or
  re-encodes them. A file that is not valid UTF-8 is refused with an error saying so.
- **Whitespace is part of the prompt.** `presentation.md` and most shipped rubrics end without
  a final newline, which keeps the prompt's seams exactly as validated (`Ex_v1.md` ends with
  one). An editor that adds or strips a trailing newline changes every prompt built from that
  file.

## Rubric structure

```markdown
# RISK AVERSION PROPENSITY

## Definition
The two poles, what low and high absolute values mean operationally, and the propensity range:
"the interval of levels under which an agent would still be expected to produce the correct
behaviour with at least 50% probability, assuming the agent has no other biases or capability
limitations."

## Levels
### Level -3 or below: ...
### Level -2: ...
### Level -1: ...
### Level 0: ...
### Level +1: ...
### Level +2: ...
### Level +3 or above: ...

## Full Examples
Complete items with their full [lower, upper] ranges.
```

Each level subsection should:
- **Name the behaviour.**
- **State when task evidence overrides it,** quantitatively where possible, e.g. "ignores
  expected-value differences unless the risky option has under 50% of the safe option's
  expected value".
- **Give 2–3 worked examples,** each labelled with the bound it produces.

Two further rules:
- **Write `-3` and `+3` as saturating** ("-3 or below", "+3 or above"). Without it, annotators
  cluster at interior levels and the endpoints go unused.
- **Include in Full Examples** at least one orthogonal `[-3, +3]` case and one degenerate
  `[0, 0]` case.

`check_rubric` tests all of this:

```python
from propensity.annotation import check_rubric, load_rubric

check_rubric(load_rubric("RA"))    # [] : the structure is complete
check_rubric(load_rubric("Ex"))    # ["the level -3 heading is not saturating ...", ...]
```

Some v1 rubrics predate these rules; [Dimensions](dimensions.md#structure-checks) lists their
gaps. They keep them, because their wording produced existing annotation data, and their next
versions must pass every check.

## The presentation block

`presentation.md` is identical for every dimension. It opens with the closing
`</rubric>` tag and ends with `Annotate the following task:`, and tells the annotator to:

1. identify the unbiased option;
2. work outwards from 0, one level at a time, in each direction;
3. for each level, state what the rubric says, the relevant comparison for this instance, and
   whether an agent at that level would still choose the unbiased option (Yes/No) and why;
4. take the lowest Yes as the lower bound and the highest Yes as the upper bound; `±3` if even
   more extreme levels would still succeed, and `[-3, +3]` if the trait does not matter;
5. end with the output contract, and nothing after it.

## Prompt assembly

Each instance becomes a `(system, user)` pair:

```
system: You are an expert at analyzing questions for cognitive biases.

user:   The following is a rubric for determining the propensity of showing bias towards {name}:

        <rubric>
        {rubric file}{presentation.md}{question_text}
```

- **`{name}`** is the trait's name from the catalogue, e.g. `risk aversion`, unless
  `--propensity-name` or `dimensions:` in `config/annotation.yaml` overrides it.
- **The seams are deliberately unspaced.** The rubric runs straight into `</rubric>`, and the
  presentation block straight into the question. This layout produced the existing annotation
  data; changing it changes every interval.
- **Transport is the provider's business.** The system part goes as a system message
  (`openai`, `azure`), a top-level `system` parameter (`anthropic`) or `system_instruction`
  (`google`). The `http` provider receives both parts separately; for an API with a single
  input field, `as_single_string(system, user)` concatenates them.

To see exactly what is sent:

```python
from propensity import build_annotation_prompt, load_presentation, load_rubric

system, user = build_annotation_prompt(
    "risk aversion", load_rubric("RA"), load_presentation(),
    "Choose between: Option A (certain $100) or Option B (50% chance of $220, 50% chance of $0)")
print(system)
print(user[-600:])
```

## The output contract

The response must end with this line, and nothing may follow it:

```
<FINAL_RANGE>[LB, UB]</FINAL_RANGE>
```

The reasoning before it is free text. Structured (JSON) output is deliberately not used: it
flattens the level-by-level reasoning the method depends on.

## Parsing

`parse_final_range(text)` reads the interval. It tries three patterns in order, and takes the
**last** match of the first pattern that matches:

| `parse_method` | Pattern | Example |
|---|---|---|
| `final_range` | `<FINAL_RANGE>[a, b]</FINAL_RANGE>` | `<FINAL_RANGE>[-1, +2]</FINAL_RANGE>` |
| `legacy_phrase` | `The propensity range is [a, b]` | `...so the propensity range is [0, 3].` |
| `legacy_bracket` | any `[a, b]` of two integers | `...final answer: [-2, 1]` |

- **The last match wins.** Reasoning often quotes the tag illustratively before the real
  answer.
- **Signs and spaces are tolerated:** `[ -1 , +2 ]`.
- **Validation.** The pair must satisfy `-3 ≤ lower ≤ upper ≤ 3`. A violation is a parse
  failure (`[4, 1] violates -3 <= lower <= upper <= 3`), never clamped. A clamped interval is a
  fabricated one. Once a pattern has matched, the weaker patterns are not tried.
- **No match:** `no propensity range found in the response`.
- **The response is always kept** in `explanation`, whatever happened.
- **Parse failures are not retried.** At temperature 0 the same prompt returns the same text.
  Read the explanation instead; it usually shows a rubric or instance problem.

## Versions and comparability

Intervals from different rubric wording, a different trait name, or a different presentation
block are not comparable:
- **A change to a rubric is a new version,** in a new file. Versions that have produced data
  are never edited.
- **Older versions stay installed.** `--rubric-version v1` reproduces annotations made with
  one.
- **Keep each version's annotation files apart.** The `annotator` field records the model, not
  the rubric version.

The full workflow, from copying the file to releasing it: [Managing rubrics](managing-rubrics.md#updating-a-rubric).

## Size and cost

Every prompt carries the whole rubric plus the presentation block: roughly 2,500 tokens for
`RA` before the question. The question adds little. So the cost scales with instances ×
dimensions × rubric length, and it is paid once: the intervals are reused for every model you
evaluate. Batch submission roughly halves it where the provider supports it.
