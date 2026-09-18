# Example data

A small synthetic dataset for trying PROPEL without credentials or data of your own. The
[tutorials](https://github.com/Daniframe/propel/blob/main/docs/tutorials/README.md) use it
throughout. It ships with the package; copy it into a working directory with:

```bash
python -m propensity.examples            # writes examples/ here; --force overwrites
```

| File | Holds | Format |
|---|---|---|
| `items_RA.jsonl` | 120 risk-aversion instances: choices between a sure amount and a lottery | [instances](https://github.com/Daniframe/propel/blob/main/docs/data-formats.md#instances) |
| `annotations_RA.jsonl` | a demand interval for each; 3 marked as failed to parse | [annotations](https://github.com/Daniframe/propel/blob/main/docs/data-formats.md#annotations) |
| `outcomes_long.csv` | 0/1 outcomes for four subjects; 3 missing | [outcomes, long form](https://github.com/Daniframe/propel/blob/main/docs/data-formats.md#outcomes) |
| `outcomes_wide.csv` | the same outcomes | [outcomes, wide form](https://github.com/Daniframe/propel/blob/main/docs/data-formats.md#outcomes) |

**How it was made:**
- **The intervals** come from a fixed rule on each lottery's expected-value ratio, standing in
  for an LLM annotator.
- **The outcomes** are drawn from the response model at known levels:

| Subject | True level |
|---|---|
| `demo-model` | `+0.7` (uninstructed) |
| `demo-model_RA_-2` | `-2` (incited) |
| `demo-model_RA_0` | `0` (incited) |
| `demo-model_RA_+2` | `+2` (incited) |

Fitting it recovers `+1.89`, `-2.06` and `+0.09` for the incited subjects, and `+0.42`
`[0.13, 0.71]` for `demo-model`.

```bash
python -m propensity.examples.generate examples     # rebuilds the four data files, identically
```

The data is synthetic: use it to learn the tools, not to draw conclusions about any model.
