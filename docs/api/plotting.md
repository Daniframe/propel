# `propensity.modelling.plotting`

Figures for curves, surfaces and item banks. How to read each: [Plots](../plots.md).

- **Imports.** matplotlib and seaborn are imported on first draw. Without them, every function
  raises `ImportError: plotting needs matplotlib and seaborn: pip install "propensity[plot]"`.
- **Return values.** Every `plot_*` function draws on `ax` when given, or on a new pyplot
  figure, and returns the `Axes`. `plot_interval_trees` returns the `Figure`.
- **Display.** Nothing calls `plt.show()`.

## `plot_propensity_curve`

```python
plot_propensity_curve(curve, *, theta=None, ci95=None, converged=True, incited=None,
                      r1=-3, r2=3, title=None, ax=None)
```

| Parameter | Meaning |
|---|---|
| `curve` | from `build_empirical_curve` (build it with `jitter=0.25` for display) |
| `theta` | the fitted level; None or NaN draws no estimate |
| `ci95` | `(lower, upper)`; non-finite bounds are skipped |
| `converged` | `False` adds "(the fit did not converge)" to the legend |
| `incited` | a known incited level, drawn as a grey line |
| `r1`, `r2` | the x-range to show at least; it widens to keep every bin, `theta` and the bounds in view |
| `title` | axes title |
| `ax` | axes to draw on |

## `plot_propensity_surface`

```python
plot_propensity_surface(surface, *, theta=None, ci95=None, converged=True, title=None, ax=None)
```

`surface` comes from `build_empirical_surface`, and `theta`, `ci95` and `converged` are as for
the curve.

- **Cells:** red-to-green by success, labelled with counts; pale grey when valid but empty;
  blank when impossible.
- **Lines:** `b_l + b_u = 2·theta` (solid) and the bounds (dashed), clipped to the grid.
- **An estimate off the grid** draws no line, and still appears in the legend below the axes.

## `plot_model_surface`

```python
plot_model_surface(model_surface, *, title=None, colorbar=True, ax=None)
```

`model_surface` comes from `build_model_surface`. With `smooth=False` it is drawn as cells on
the integer grid; with `smooth=True`, as filled contours every 0.05 with labelled lines at 0.25,
0.5 and 0.75. Colours match `plot_propensity_surface`. `colorbar=False` omits the colour bar.

## `plot_interval_distribution`

```python
plot_interval_distribution(distribution, *, proportion=True, cmap="Reds", vmax=None, title=None,
                           colorbar=True, ax=None)
```

| Parameter | Meaning |
|---|---|
| `distribution` | from `build_interval_distribution` |
| `proportion` | `True`: colour and label by share of the bank; `False`: by count |
| `cmap` | a matplotlib colormap name or object |
| `vmax` | top of the colour scale; the fullest cell by default. Fix it to compare banks |
| `colorbar` | draw the colour bar |

A share below 0.005 is labelled `<.01`.

## `plot_interval_tree`

```python
plot_interval_tree(tree, *, proportion=True, show_invalid=False, cmap="Reds", vmax=None,
                   title=None, colorbar=True, ax=None)
```

`tree` comes from `build_interval_tree`, and the other parameters are as for the distribution.
`show_invalid=True` fills the cells no whole-numbered interval can occupy in light grey, instead
of leaving them blank; they are still never labelled.

## `plot_interval_trees`

```python
plot_interval_trees(trees, *, proportion=True, show_invalid=False, cmap="Reds", title=None,
                    nrows=None, ncols=None, figsize=None, figure=None) -> Figure
```

| Parameter | Meaning |
|---|---|
| `trees` | `{panel title: build_interval_tree(...)}`, drawn in order |
| `nrows`, `ncols` | layout. Neither given: fewest empty slots, then the squarest, then the fewest rows. One given: the other follows |
| `figsize` | for a new figure; default scales with the layout |
| `figure` | draw into this `Figure` instead of a new one (e.g. `Figure(layout="constrained")`) |
| `title` | figure title |

- **One colour scale.** Every panel shares one `vmax` (the fullest cell across all trees) and
  one colour bar.
- **Empty slots** are removed.

**Raises** `ValueError` for no trees, or for a layout too small for them.

## Files

### `save_profile_plots`

```python
save_profile_plots(profiles, annotations, outcomes, out_dir, *, n_bins=20, lowess_frac=0.4,
                   jitter=0.25, seed=0, dpi=100) -> list[Path]
```

Writes `{subject}_{dimension}_curve.png` and `…_surface.png` for every row of `profiles` (as
returned by `fit_profiles` for these annotations and outcomes) that has joined data.

- **Unfitted cells** are drawn without an estimate, with the skip reason in the title.
- **Warnings.** The join is repeated without repeating its warnings.
- **Failures.** A figure that fails is logged and skipped.
- **Returns** the paths written.

### `save_annotation_plots`

```python
save_annotation_plots(annotations, out_dir, *, dimensions=None, proportion=True,
                      show_invalid=False, dpi=100) -> list[Path]
```

Writes, per dimension, `{dimension}_intervals.png` and `{dimension}_tree.png`; with two or more
dimensions, also `interval_trees.png`.

- **What is plotted.** Rows that failed to parse or have a null bound are excluded.
- **`dimensions`** restricts the output.
- **A dimension with non-integer bounds** is logged and skipped.
- **Returns** the paths written.

Both render off-screen through the Agg backend: no display is needed.

### `require_matplotlib`

```python
require_matplotlib() -> tuple[module, module]
```

Imports and returns `(matplotlib, seaborn)`, or raises the `ImportError` above. Useful to fail
early, before long work that ends in a figure.

## Constants

| Name | Value | Used for |
|---|---|---|
| `SUCCESS_COLOURS` | `["#d7191c", "#ffff99", "#1a9641"]` | success scale, red → yellow → green |
| `DISTRIBUTION_COLOURS` | `"Reds"` | default colormap for bank figures |
| `UNOBSERVED_COLOUR` | `"whitesmoke"` | valid but empty cells |
| `INVALID_COLOUR` | `"lightgray"` | impossible cells with `show_invalid=True` |
| `DISPLAY_JITTER` | `0.25` | curve jitter in `save_profile_plots` |
