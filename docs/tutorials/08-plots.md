# Tutorial 8: plots

Draw every figure PROPEL offers, as files or in a notebook, and combine them. How to read each
figure: [Plots](../plots.md).

**You need:** PROPEL with the `plot` extra, run where `python -m propensity.examples` has put the example data in `examples/`.

## 1. Data to draw

```python
import warnings
from pathlib import Path
from propensity import fit_profiles, join_annotations_outcomes, load_annotations, load_outcomes

Path("out/figures").mkdir(parents=True, exist_ok=True)
annotations = load_annotations("examples/annotations_RA.jsonl")
outcomes = load_outcomes("examples/outcomes_long.csv")
profiles = fit_profiles(annotations, outcomes).set_index("subject_id")

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    joined, _ = join_annotations_outcomes(annotations, outcomes)
cell = joined[joined["subject_id"] == "demo-model_RA_+2"]
demands, success = cell[["lower", "upper"]].to_numpy(), cell["outcome"].to_numpy()

fit = profiles.loc["demo-model_RA_+2"]
estimate = {"theta": fit["theta"], "ci95": (fit["ci95_lower"], fit["ci95_upper"]),
            "converged": fit["converged"] == 1}
```

`estimate` packs the three arguments every subject figure takes.

## 2. Propensity curve

```python
import matplotlib.pyplot as plt
from propensity import build_empirical_curve, plot_propensity_curve

curve = build_empirical_curve(demands, success, n_bins=20, lowess_frac=0.4, jitter=0.25, seed=0)
ax = plot_propensity_curve(curve, incited=2, title="demo-model at +2", **estimate)
ax.figure.savefig("out/figures/curve.png", dpi=150, bbox_inches="tight")
```

| Parameter | Effect |
|---|---|
| `jitter=0.25` | spreads integer interval centres so the bins do not stack; display only, never used by the fit |
| `n_bins`, `lowess_frac` | bin count and smoothing bandwidth |
| `incited=2` | adds a grey line at the level the subject was incited to |
| `converged=False` | adds "(the fit did not converge)" to the legend |
| `theta=None` | draws the data alone, for a cell that was not fitted |

## 3. Propensity surface

```python
from propensity import build_empirical_surface, plot_propensity_surface

surface = build_empirical_surface(demands, success)
print(surface["counts"].loc[3].to_dict())       # b_u = 3: how many instances per lower bound
ax = plot_propensity_surface(surface, title="demo-model at +2", **estimate)
ax.figure.savefig("out/figures/surface.png", dpi=150, bbox_inches="tight")
```

```text
{-3: 39, -2: 17, -1: 15, 0: 7, 1: 0, 2: 0, 3: 0}
```

`build_empirical_surface` needs whole-numbered bounds within `[-3, 3]`, which is what
annotators produce. `prob` and `counts` are plain DataFrames, indexed by `b_u` down the rows
and `b_l` across the columns.

## 4. Model surface, discrete and smooth

What the response model predicts at the fitted level, next to what was observed:

```python
from propensity import build_model_surface, plot_model_surface

fig, (observed, predicted, smooth) = plt.subplots(1, 3, figsize=(20, 6), layout="constrained")
plot_propensity_surface(surface, title="observed", ax=observed, **estimate)
plot_model_surface(build_model_surface(fit["theta"]), title="model, cells", ax=predicted)
plot_model_surface(build_model_surface(fit["theta"], smooth=True, resolution=0.05),
                   title="model, smooth=True", ax=smooth)
fig.savefig("out/figures/observed_vs_model.png", dpi=120, bbox_inches="tight")
```

- **`smooth=False`** (default) uses the same integer cells as the observed surface, for a cell
  by cell comparison.
- **`smooth=True`** draws filled contours, with labelled lines at 0.25, 0.5 and 0.75.
- **`k`, `min_width`, `rho`** in `build_model_surface` are the response model's parameters,
  at the fit's defaults.

## 5. How the bank's intervals spread

These describe the annotations alone, with no subject involved. Leave out the rows that failed
to parse:

```python
from propensity import build_interval_distribution, plot_interval_distribution

usable = annotations[annotations["parse_ok"]][["lower", "upper"]].to_numpy()
distribution = build_interval_distribution(usable)
print(distribution["n_items"], distribution["counts"].to_numpy().sum())

fig, (shares, counts) = plt.subplots(1, 2, figsize=(14, 6), layout="constrained")
plot_interval_distribution(distribution, title="share of the bank", ax=shares)
plot_interval_distribution(distribution, proportion=False, cmap="Blues", title="counts", ax=counts)
fig.savefig("out/figures/intervals.png", dpi=120, bbox_inches="tight")
```

```text
117 117
```

`vmax` fixes the top of the colour scale, so that separate figures of different banks can be
compared.

## 6. The interval tree

```python
from propensity import build_interval_tree, plot_interval_tree

tree = build_interval_tree(usable)
print(int(tree["reachable"].to_numpy().sum()), "reachable cells; tip count:", tree["counts"].loc[6, 0.0])

fig, (plain, grid) = plt.subplots(2, 1, figsize=(9, 10), layout="constrained")
plot_interval_tree(tree, title="show_invalid=False", ax=plain)
plot_interval_tree(tree, show_invalid=True, title="show_invalid=True", ax=grid)
fig.savefig("out/figures/tree.png", dpi=120, bbox_inches="tight")
```

```text
28 reachable cells; tip count: 39
```

The tip, `[-3, +3]`, holds 39 of the 117 intervals, a third of the bank: instances that say
nothing about `theta`.

## 7. Several banks side by side

`plot_interval_trees` puts several trees on one colour scale, with one colour bar:

```python
import numpy as np
from propensity import plot_interval_trees

rng = np.random.default_rng(3)
pairs = np.sort(rng.integers(-3, 4, (200, 2)), axis=1)      # a bank of random intervals
figure = plot_interval_trees({"RA (examples)": tree, "random bank": build_interval_tree(pairs)},
                             title="Two banks", show_invalid=True)
figure.savefig("out/figures/trees.png", dpi=120, bbox_inches="tight")
```

- **Layout.** Panels are laid out with the fewest empty slots, then the squarest grid. `nrows`
  or `ncols` overrides it.
- **An existing figure.** `figure=` draws into one you made, e.g. with `layout="constrained"`.

## 8. Everything at once

```python
from propensity import save_annotation_plots, save_profile_plots

fitted = profiles.reset_index()
written = save_profile_plots(fitted, annotations, outcomes, "out/all")
written += save_annotation_plots(annotations, "out/all", show_invalid=True)
print(len(written), sorted(path.name for path in written)[:3])
```

```text
10 ['RA_intervals.png', 'RA_tree.png', 'demo-model_RA_+2_RA_curve.png']
```

These render off-screen and need no display, so they work on a server. The command line does
the same with `--plots`:

```bash
propel-fit --annotations examples/annotations_RA.jsonl --outcomes examples/outcomes_long.csv \
    --out out/profiles.csv --plots out/cli_plots
```

## 9. In a notebook

Without `ax`, each function opens a new figure through pyplot, which a notebook displays:

```python
ax = plot_propensity_curve(curve, **estimate)       # in Jupyter, the figure appears below
```

In a script, call `plt.show()` to open a window, or `savefig` as above. On a machine without a
display, set `MPLBACKEND=Agg` before drawing through pyplot.

Every function returns the matplotlib `Axes` (or `Figure`, for `plot_interval_trees`), so
titles, labels, fonts and sizes can be changed afterwards with plain matplotlib.
