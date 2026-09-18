# Managing rubrics

How PROPEL's rubrics are organised, how to update one, and how to add a dimension. What a rubric
must contain is in [Rubrics and prompts](rubrics.md#rubric-structure). [Tutorial 9](tutorials/09-writing-a-rubric.md)
works through an example.

- [Where they live](#where-they-live)
- [The catalogue](#the-catalogue)
- [Three rules](#three-rules)
- [Updating a rubric](#updating-a-rubric)
- [Adding a dimension](#adding-a-dimension)
- [Retiring a version or a dimension](#retiring-a-version-or-a-dimension)
- [What the tests guard](#what-the-tests-guard)
- [Conventions for a growing catalogue](#conventions-for-a-growing-catalogue)
- [Rubrics outside the package](#rubrics-outside-the-package)

## Where they live

The rubrics ship inside the package, so installing PROPEL installs every dimension and every
version:

```
propensity/rubrics/
  dimensions.yaml          the catalogue: one entry per dimension
  presentation.md          the reasoning procedure and output contract, shared by every dimension
  RA/
    RA_v1.md               one file per version; old versions stay
    RA_v2.md
  Ex/
    Ex_v1.md
  ...
```

- **Default location.** Everything reads from here unless you pass `rubrics_dir` (Python) or
  `--rubrics-dir` (command line).
- **Finding it.** `propensity.annotation.RUBRICS_DIR` is the installed location.
- **Browsing.** [Dimensions](dimensions.md) lists what ships.

## The catalogue

`propensity/rubrics/dimensions.yaml` has one entry per dimension, keyed by its code:

```yaml
RA:
  name: risk aversion
  negative: risk-seeking
  positive: risk-averse
  version: v1
  summary: Preferring certain outcomes to uncertain ones beyond what expected value justifies.
```

| Field | Required | Meaning |
|---|---|---|
| the key, e.g. `RA` | yes | the dimension's code: its folder name, its file prefix, and what `--dimension` takes |
| `name` | yes | the trait as the prompt words it: "…showing bias towards **risk aversion**" |
| `negative` | yes | what the `-3` end of the scale means |
| `positive` | yes | what the `+3` end of the scale means |
| `version` | yes | the rubric version used unless another is asked for |
| `summary` | no, but expected | one line for the documentation |

**How the catalogue is used:**
- **The trait name** comes from `name`, unless `--propensity-name`, or `dimensions:` in
  `config/annotation.yaml`, overrides it.
- **The version** comes from `version`, unless `--rubric-version` (or `version=` in Python)
  asks for another.
- **Validation.** A missing field, an unknown field, or a malformed file is refused with an
  error naming the entry.

In Python:

```python
from propensity import get_dimension, load_dimensions

get_dimension("RA")          # Dimension(code='RA', name='risk aversion', ..., version='v1', ...)
sorted(load_dimensions())    # ['BR', 'Ex', 'RA', 'Ul']
```

## Three rules

1. **Never edit a rubric file that has produced annotations.** Its text is the prompt: any edit,
   even whitespace or a trailing newline, changes every interval annotated with it. A change is
   a new version, in a new file.
2. **Never change a dimension's `name` once annotations exist.** The name is inserted into every
   prompt. If it must change, treat it like a new rubric version: annotate again.
3. **Treat `presentation.md` as part of every rubric.** It is shared by all dimensions, so
   changing it changes every prompt of every dimension. Change it only in a release that bumps
   every dimension's version, and say so in the release notes.

Annotations are comparable only when made with the same rubric version, trait name and
presentation block. Keep each version's annotation files apart: the `annotator` field records
the model, not the rubric version.

## Updating a rubric

Suppose `RA` is at `v1` and needs better worked examples.

**1. Copy the current version to the next one**, and edit only the copy:

```bash
cp propensity/rubrics/RA/RA_v1.md propensity/rubrics/RA/RA_v2.md
```

**2. Check its structure.** A new version must pass every check, including any its predecessor
was exempt from:

```python
from propensity.annotation import check_rubric, load_rubric

print(check_rubric(load_rubric("RA", version="v2")))    # [] when the structure is complete
```

**3. Pilot it.** Annotate a sample of 20 instances with the new version, and read every
explanation ([Tutorial 3](tutorials/03-annotating-with-a-provider.md#3-read-every-explanation)):

```bash
propel-annotate run --instances pilot_RA.jsonl --dimension RA --rubric-version v2 --out RA_v2_pilot.jsonl \
    --provider anthropic --model claude-haiku-4-5
```

Compare its intervals with the previous version's on the same instances
([how](tutorials/09-writing-a-rubric.md#9-a-new-version-of-a-rubric)). Every change
in an interval should be one you intended.

**4. Validate it** with incited models, on annotations made with the new version
([Tutorial 7](tutorials/07-validating-with-incitement.md)). A version that does not recover
incited levels does not ship.

**5. Make it current** in `dimensions.yaml`:

```yaml
RA:
  ...
  version: v2
```

**6. Pin its bytes** in `tests/test_rubric_files.py`. Add the file's SHA-256 to
`PINNED_SHA256`:

```bash
python -c "import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())" propensity/rubrics/RA/RA_v2.md
```

**7. Regenerate the catalogue page**, then run the tests:

```bash
python docs/make_dimensions.py
pytest -q
```

**8. Record it** in the release notes: what changed, why, and that annotations made with `v1`
stay valid for `v1` but are not comparable with `v2`.

Keep `RA_v1.md`: it is how anyone reproduces annotations made with it
(`--rubric-version v1`).

## Adding a dimension

Suppose the new dimension is delay of gratification, with code `TD`.

**1. Choose its identity:**
- **a code:** short, unique and permanent; it is typed on every command line and stored in
  every annotation;
- **a trait name:** the words the prompt will use, permanent once annotations exist;
- **the poles:** what `-3` and `+3` mean, with `0` the unbiased, instrumentally rational agent.

**2. Write the rubric** as `propensity/rubrics/TD/TD_v1.md`, starting from the template below.
Model it on a complete rubric such as `RA_v1.md`.

**3. Add it to the catalogue:**

```yaml
TD:
  name: delay of gratification
  negative: impatience, preferring the immediate reward
  positive: excessive patience, preferring the delayed reward
  version: v1
  summary: Letting a preference about timing override the value-maximising choice.
```

**4. Check it.** `check_rubric(load_rubric("TD"))` must return `[]`. New rubrics are held to
every rule.

**5. Pilot, compare with your own judgement, and validate with incited models**, exactly as for
a new version (steps 3 and 4 above).

**6. Pin, regenerate and test** (steps 6 and 7 above). The tests fail until the rubric is
pinned, catalogued and listed in the docs, so none of these can be forgotten.

### Template

```markdown
# DELAY OF GRATIFICATION PROPENSITY

## Definition
Delay of Gratification Propensity (DGP) is a scalar dimension from -3 or below (<what -3 means>)
to +3 or above (<what +3 means>) indicating how strongly <the tendency> overrides <what the
task's objective requires>. Lower absolute values indicate a weak bias that moderate incentives
override; higher absolute values indicate a strong or extreme bias that only very large
incentives (±2) or nothing at all (±3) override. A task's propensity range identifies the
interval of levels under which an agent would still be expected to produce the correct behaviour
with at least 50% probability, assuming the agent has no other biases or capability limitations.

## Levels
### Level -3 or below: <name>
<The behaviour. When, if ever, task evidence overrides it; quantitatively where possible.>

Examples:
- "<instance>" Lower bound of propensity range: <bound>
- "<instance>" Lower bound of propensity range: <bound>

### Level -2: <name>
### Level -1: <name>
### Level 0: <the unbiased, instrumentally rational agent>
### Level +1: <name>
### Level +2: <name>
### Level +3 or above: <name>

## Full Examples
- "<instance the trait cannot affect>" Propensity range: [-3, +3]
- "<instance only the unbiased agent solves>" Propensity range: [0, 0]
- "<further instances covering the scale>" Propensity range: [<lower>, <upper>]
```

## Retiring a version or a dimension

- **Superseded versions stay.** Moving the catalogue's `version` to the new one is all that
  retiring an old version takes. The file remains, so older annotations can be reproduced and
  audited.
- **Withdrawing a dimension** removes its catalogue entry and its folder together. Do it in a
  release whose notes say so: anyone holding annotations for it needs the previous release to
  re-annotate.

## What the tests guard

`tests/test_rubric_files.py` fails when:

| Check | Catches |
|---|---|
| every rubric file and `presentation.md` has a pinned SHA-256 | any edit, including an editor adding or removing a trailing newline |
| every file is UTF-8 with `\n` line endings | encoding accidents that would change the prompt |
| every rubric passes `check_rubric` | a missing section, level or example. Only the gaps recorded in `KNOWN_GAPS` are exempt, and nothing may be added there |
| every folder is catalogued, and every entry's version exists | a rubric the CLI cannot name, or a catalogue entry pointing at nothing |
| trait names are unique, and poles and summaries given | two dimensions that would build indistinguishable prompts |
| `docs/dimensions.md` matches the catalogue | documentation that has fallen behind |
| `presentation.md` opens with `</rubric>` and ends with `Annotate the following task:` | a broken prompt seam |

## Conventions for a growing catalogue

With many dimensions, consistency matters as much as any single rubric:

- **One scale.** `0` is always the unbiased, instrumentally rational agent; `±1` a bias moderate
  evidence overrides; `±2` one only severe evidence overrides; `±3` one nothing overrides.
- **One structure.** Every rubric has the same sections, level headings and example labels, so
  annotators (and reviewers) read every dimension the same way.
- **Self-contained.** A rubric never refers to another dimension's rubric.
- **Poles named from the rubric.** `negative` and `positive` in the catalogue use the rubric's
  own words for its `-3` and `+3` levels.
- **Reviewed.** Before a dimension or version ships, a second person reads the rubric and its
  pilot explanations.
- **Recorded.** Each release's notes list the dimensions and versions it adds or changes.

## Rubrics outside the package

To try a rubric without touching the package, keep it in a directory of your own with the same
layout, and point `--rubrics-dir` (or `rubrics_dir=`) at it:

```
my_rubrics/
  presentation.md          required: copy it from propensity.annotation.RUBRICS_DIR
  dimensions.yaml          optional: trait names and current versions for these dimensions
  TD/TD_v1.md
```

- **The directory replaces the packaged one** for that run. A dimension you want from the
  package needs its files copied in too.
- **Without a `dimensions.yaml`,** pass `--propensity-name`, and the version defaults to `v1`
  unless `--rubric-version` says otherwise.
- **Moving it into PROPEL** later is [Adding a dimension](#adding-a-dimension).
