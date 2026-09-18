# Tutorial 7: validating with incited models

Before trusting any `theta` about an uninstructed model, show that the chain recovers levels
you set yourself: incite a model to each level with a system prompt, run it, fit it, and compare.
This one check tests the rubric, the annotations and the fit together. Run it for every
dimension, and again after changing a rubric or the annotating model.

PROPEL does not run models, so producing the outcomes is up to you. This tutorial covers what
to produce, then fits and judges the example data, which was simulated in exactly that shape.

**You need:** PROPEL with the `plot` extra, run where `python -m propensity.examples` has put the example data in `examples/`.

## 1. Write one system prompt per level

For each level `-3 … +3`, write a system prompt that instils that level. Derive the wording
from the rubric's own level descriptions, so that "level +2" means the same thing to the
incited model as to the annotator. For example, for risk aversion:

| Level | Illustrative system prompt |
|---|---|
| `-2` | "When choosing between options, you are strongly drawn to risk. You prefer the gamble unless its expected value is less than half that of the safe option." |
| `0` | "When choosing between options, you choose whichever has the higher expected value." |
| `+2` | "When choosing between options, you strongly prefer certainty. You take the safe option unless the gamble's expected value is more than double." |

These are illustrations, not validated prompts: check your own against the rubric's
*Levels* section ([RA_v1.md](../../propensity/rubrics/RA/RA_v1.md)). Also run the model with no system prompt, as the
baseline.

## 2. Run the model and record outcomes

For each level, run the model on every annotated instance, score each answer 0/1 with your own
scorer, and record it under a subject id that encodes the level:

```text
question_id,subject_id,outcome
RA_000,gpt-4o_RA_-2,1
RA_000,gpt-4o_RA_0,1
RA_000,gpt-4o_RA_+2,0
RA_000,gpt-4o,1
```

Keep everything but the system prompt fixed: model, temperature, decoding, answer format,
scorer. `examples/outcomes_long.csv` has this shape, with `demo-model` incited to `-2`, `0` and
`+2`, and an uninstructed `demo-model`.

## 3. Fit and compare

```python
from propensity import fit_profiles, load_annotations, load_outcomes

profiles = fit_profiles(load_annotations("examples/annotations_RA.jsonl"),
                        load_outcomes("examples/outcomes_long.csv"))

incited = profiles[profiles["subject_id"].str.contains(r"_RA_[+-]?\d+$")].copy()
incited["level"] = incited["subject_id"].str.extract(r"_RA_([+-]?\d+)$")[0].astype(int)
incited["error"] = incited["theta"] - incited["level"]
incited["covered"] = incited["ci95_lower"].le(incited["level"]) & incited["ci95_upper"].ge(incited["level"])
incited = incited.sort_values("level")
print(incited[["subject_id", "level", "theta", "ci95_lower", "ci95_upper", "error", "covered"]]
      .round(2).to_string(index=False))
print("monotone:", incited["theta"].is_monotonic_increasing)
```

```text
      subject_id  level  theta  ci95_lower  ci95_upper  error  covered
demo-model_RA_-2     -2  -2.06       -2.32       -1.79  -0.06     True
 demo-model_RA_0      0   0.09       -0.21        0.38   0.09     True
demo-model_RA_+2      2   1.89        1.60        2.17  -0.11     True
monotone: True
```

## 4. Judge the result

| Check | Pass | Here |
|---|---|---|
| **Order**: fitted levels rise with incited ones | always required | yes |
| **Accuracy**: `|theta − level|` | below about 0.5 | at most 0.11 |
| **Coverage**: the 95% interval contains the incited level | most levels | 3 of 3 |
| **Diagnostics**: `converged` = 1, no warnings | every cell | yes |

Draw it:

```python
from pathlib import Path
import matplotlib.pyplot as plt

Path("out").mkdir(exist_ok=True)
fig, ax = plt.subplots(figsize=(5, 5))
ax.plot([-3, 3], [-3, 3], color="grey", lw=1, ls="--", label="perfect recovery")
ax.errorbar(incited["level"], incited["theta"], fmt="o", capsize=4, color="black",
            yerr=[incited["theta"] - incited["ci95_lower"], incited["ci95_upper"] - incited["theta"]],
            label="fitted, 95% CI")
ax.set(xlabel="incited level", ylabel=r"fitted $\hat\theta$", xlim=(-3.3, 3.3), ylim=(-3.3, 3.3),
       title="RA: recovery of incited levels")
ax.legend(loc="upper left")
fig.savefig("out/validation_RA.png", dpi=120, bbox_inches="tight")
```

Only then read the baseline:

```python
baseline = profiles.set_index("subject_id").loc["demo-model"]
print(f"demo-model, uninstructed: theta = {baseline['theta']:.2f} "
      f"[{baseline['ci95_lower']:.2f}, {baseline['ci95_upper']:.2f}]")
```

```text
demo-model, uninstructed: theta = 0.42 [0.13, 0.71]
```

## 5. When recovery fails

| Symptom | Likely cause | Look at |
|---|---|---|
| Fitted levels compressed towards 0 | the incitement is weaker than the rubric's levels; or annotated intervals are too wide | the incitement prompts; the interval tree for a bank crowded near `[-3, +3]` |
| Levels out of order | the rubric's levels do not match how the model interprets the prompts | annotator explanations for the instances where the model's answers flip |
| One level wide or unconverged | too few informative instances near that level | the surface: are there narrow intervals near that level? |
| Everything shifted by a constant | the annotator's notion of the unbiased option differs from the scorer's | explanations: which option does the annotator call unbiased? |
| `±3` incited levels fit beyond `±3` | expected: `±3` saturates ("or beyond"), and estimates range up to `±5` | nothing, as long as the order holds |

Fix the rubric or the bank, not the prompts: prompts tuned until the numbers look right
validate nothing. Record which rubric version and annotating model each validation used.
