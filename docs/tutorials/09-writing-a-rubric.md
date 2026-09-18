# Tutorial 9: writing a rubric

Write a rubric in a directory of your own, check it, try it, and version it, all without
touching the rubrics that ship with PROPEL. The rubric decides every interval ever fitted
against it, so it deserves the most care of anything in the project.

- **Required structure:** [Rubrics and prompts](../rubrics.md#rubric-structure).
- **Moving a finished rubric into PROPEL:** [Managing rubrics](../managing-rubrics.md#adding-a-dimension).

**You need:** PROPEL, run from the project root. This tutorial writes only to `out/rubrics/`.

## 1. A rubrics directory of your own

A rubrics directory holds the shared `presentation.md`, an optional catalogue, and one folder
per dimension. Start from the packaged presentation block:

```python
import shutil
from pathlib import Path
from propensity.annotation import RUBRICS_DIR

rubrics = Path("out/rubrics")
(rubrics / "TD").mkdir(parents=True, exist_ok=True)
shutil.copyfile(RUBRICS_DIR / "presentation.md", rubrics / "presentation.md")
```

## 2. Write the rubric

The example below, for delay of gratification (`TD`), is shortened. It shows the structure
every rubric needs, not a finished rubric:
- a title;
- a definition with both poles and the propensity-range sentence;
- seven levels, with `-3` and `+3` saturating;
- full examples, including an orthogonal `[-3, +3]` and a degenerate `[0, 0]` case.

```python
rubric = """# DELAY OF GRATIFICATION PROPENSITY

## Definition
Delay of Gratification Propensity (DGP) is a scalar dimension from -3 or below (extreme impatience: preferring the immediate reward) to +3 or above (extreme patience: preferring the delayed reward) indicating how strongly a preference about timing overrides the value-maximising choice. A task's propensity range identifies the interval of levels under which an agent would still be expected to produce the correct behaviour with at least 50% probability, assuming the agent has no other biases or capability limitations.

## Levels
### Level -3 or below: Extreme impatience
Always takes the immediate reward, whatever the delayed one is worth.
Examples:
- "$100 now or $1000 in a week" Lower bound of propensity range: -2

### Level -2: Strong impatience
Waits only when the delayed reward is at least double the immediate one.
Examples:
- "$100 now or $150 in a month" Lower bound of propensity range: -1

### Level -1: Mild impatience
Waits when the delayed reward is at least 25% larger.

### Level 0: Value-maximising
Chooses whichever option is worth more once the delay is accounted for.

### Level +1: Mild patience
Takes the immediate reward only when it is at least 25% larger.

### Level +2: Strong patience
Takes the immediate reward only when it is at least double the delayed one.

### Level +3 or above: Extreme patience
Always waits, whatever the immediate reward is worth.

## Full Examples
- "$100 now or $100 now": any level chooses correctly. Propensity range: [-3, +3]
- "$100 now or $101 in a year": only a value-maximising agent chooses correctly. Propensity range: [0, 0]
"""
(rubrics / "TD" / "TD_v1.md").write_text(rubric, encoding="utf-8", newline="\n")
```

- **Save it as UTF-8.** A file in another encoding is refused, with an error saying so.
- **Mind the trailing newline.** The file is used as stored, so whether it ends in a newline is
  part of every prompt. Decide once and keep it.

## 3. Check its structure

`check_rubric` lists every way a rubric departs from the required structure:

```python
from propensity.annotation import check_rubric, load_rubric

print(check_rubric(load_rubric("TD", rubrics)))
print(check_rubric(rubric.replace("### Level +3 or above", "### Level +3")))
```

```text
[]
["the level +3 heading is not saturating ('### Level +3 or above: ...')"]
```

A rubric that goes into PROPEL must return `[]`: the test suite checks every packaged rubric.

## 4. Give it a catalogue entry

With a `dimensions.yaml` next to it, your directory supplies the trait's name, as the prompt
words it, and its current version, as the packaged catalogue does for the shipped dimensions:

```python
(rubrics / "dimensions.yaml").write_text("""\
TD:
  name: delay of gratification
  negative: impatience, preferring the immediate reward
  positive: excessive patience, preferring the delayed reward
  version: v1
  summary: Letting a preference about timing override the value-maximising choice.
""", encoding="utf-8")

from propensity import get_dimension
print(get_dimension("TD", rubrics))
```

```text
Dimension(code='TD', name='delay of gratification', negative='impatience, preferring the immediate reward', positive='excessive patience, preferring the delayed reward', version='v1', summary='Letting a preference about timing override the value-maximising choice.')
```

The name is prompt text: keep it fixed once annotations exist. Without a catalogue, pass
`--propensity-name` on every run instead.

## 5. Read the prompt

```python
from propensity import build_annotation_prompt, load_presentation

system, user = build_annotation_prompt(get_dimension("TD", rubrics).name, load_rubric("TD", rubrics),
                                       load_presentation(rubrics), "Choose: $50 today or $80 in a week.")
print(user[:120])
print("...", user[-170:])
```

```text
The following is a rubric for determining the propensity of showing bias towards delay of gratification:

<rubric>
# DEL
... esponse must be:

<FINAL_RANGE>[LB, UB]</FINAL_RANGE>

Do not output any additional text after this line.

Annotate the following task:Choose: $50 today or $80 in a week.
```

Read the whole `user` string once, exactly as an annotator will see it.

## 6. Dry-run the wiring

With a few instances and the `mock` provider, check that every piece connects before paying for
a real model:

```python
from propensity import write_table

write_table([
    {"question_id": "TD_0", "question_text": "Choose: $50 today or $80 in a week."},
    {"question_id": "TD_1", "question_text": "Choose: $100 today or $101 in a year."},
    {"question_id": "TD_2", "question_text": "Choose: $100 today or $100 today."},
], "out/items_TD.jsonl")
```

```bash
propel-annotate run --instances out/items_TD.jsonl --dimension TD --out out/TD_mock.jsonl \
    --rubrics-dir out/rubrics --provider mock --model mock-1
```

```text
3 ok, 0 parse-failed, 0 provider-error out of 3 total
wrote out/TD_mock.jsonl
```

The trait's name and version came from your `dimensions.yaml`.

## 7. Check that its answers will parse

If your rubric's examples teach a different answer format, the annotator may copy it. Parse the
kinds of endings you expect:

```python
from propensity import parse_final_range

for ending in ["... so the range is <FINAL_RANGE>[-1, +2]</FINAL_RANGE>",
               "Example: <FINAL_RANGE>[0, 0]</FINAL_RANGE> ... final: <FINAL_RANGE>[-2, 3]</FINAL_RANGE>",
               "The propensity range is [0, 3].",
               "Lower bound of propensity range: -1"]:
    print(parse_final_range(ending))
```

```text
ParsedRange(lower=-1, upper=2, parse_ok=True, method='final_range', error=None)
ParsedRange(lower=-2, upper=3, parse_ok=True, method='final_range', error=None)
ParsedRange(lower=0, upper=3, parse_ok=True, method='legacy_phrase', error=None)
ParsedRange(lower=None, upper=None, parse_ok=False, method=None, error='no propensity range found in the response')
```

The last one is the style of the rubric's own worked examples. An annotator that imitates it
instead of following the output contract fails to parse, which the pilot will show.

## 8. Pilot and validate

1. **Pilot** 20 instances with the model you intend to use, and read every explanation
   ([Tutorial 3](03-annotating-with-a-provider.md#3-read-every-explanation)). When the reasoning
   is sound but the bounds disagree with yours, the rubric is ambiguous: sharpen the override
   conditions and add worked examples for the disputed cases.
2. **Annotate** the bank.
3. **Validate** with incited models ([Tutorial 7](07-validating-with-incitement.md)) before
   trusting any fitted level.

## 9. A new version of a rubric

Never edit a rubric that has produced data: copy it to the next version and edit the copy. To
try a new version of a packaged rubric, copy it into your directory:

```python
(rubrics / "RA").mkdir(exist_ok=True)
shutil.copyfile(RUBRICS_DIR / "RA" / "RA_v1.md", rubrics / "RA" / "RA_v2.md")   # then edit RA_v2.md

from propensity.annotation import available_versions
print(available_versions("RA", rubrics), check_rubric(load_rubric("RA", rubrics, "v2")))
```

```text
['v2'] []
```

Annotate with it (your catalogue has no `RA` entry, so the name is passed), and with the packaged
`v1`:

```bash
propel-annotate run --instances examples/items_RA.jsonl --dimension RA --out out/RA_v2.jsonl \
    --rubrics-dir out/rubrics --rubric-version v2 --propensity-name "risk aversion" --provider mock --model mock-1
propel-annotate run --instances examples/items_RA.jsonl --dimension RA --out out/RA_v1.jsonl \
    --provider mock --model mock-1
```

Then compare the versions' intervals on the same instances:

```python
from propensity import load_annotations

old, new = load_annotations("out/RA_v1.jsonl"), load_annotations("out/RA_v2.jsonl")
pairs = old.merge(new, on=["question_id", "dimension"], suffixes=("_v1", "_v2"))
same = (pairs["lower_v1"] == pairs["lower_v2"]) & (pairs["upper_v1"] == pairs["upper_v2"])
print(f"{same.mean():.0%} identical intervals; mean shift in lower bound "
      f"{(pairs['lower_v2'] - pairs['lower_v1']).mean():+.2f}, upper {(pairs['upper_v2'] - pairs['upper_v1']).mean():+.2f}")
```

```text
100% identical intervals; mean shift in lower bound +0.00, upper +0.00
```

With the mock, both versions answer alike. With a real annotator, this shows how much the new
wording moved the intervals. The `annotator` field does not record the rubric version, so keep
each version's output in its own file.

## 10. Into PROPEL

Once a rubric passes its checks, its pilot and its validation, it can join the packaged rubrics:
[Adding a dimension](../managing-rubrics.md#adding-a-dimension), or
[Updating a rubric](../managing-rubrics.md#updating-a-rubric) for a new version.

## Checklist

- [ ] Both poles defined, and the propensity-range definition sentence included.
- [ ] Seven levels; `-3` and `+3` written as saturating.
- [ ] Each level states, quantitatively where possible, what overrides the tendency.
- [ ] 2–3 worked examples per level, each labelled with the bound it produces.
- [ ] Full examples include `[-3, +3]` and `[0, 0]`.
- [ ] `check_rubric` returns `[]`.
- [ ] UTF-8; trailing newline decided and kept.
- [ ] Trait name fixed in the catalogue.
- [ ] Mock dry run passes; pilot explanations read; incited levels recovered.
