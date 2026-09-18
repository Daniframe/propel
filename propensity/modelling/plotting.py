"""Optional renderers for curves, surfaces and item banks.

Everything here draws the plain data structures that curves.py, surfaces.py and the fit produce.
matplotlib and seaborn are imported only when something is drawn, so importing
`propensity.modelling` never needs them. Nothing calls `plt.show()`: the caller decides where a
figure goes, and the `save_*` functions render straight to files with no display at all.

Grids share one convention. `b_l` runs across and `b_u` (or the interval length) up, and a cell
is in one of three states: occupied, coloured by its value and labelled; valid but empty, in
whitesmoke; or impossible, left blank.
"""

import logging
import math
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from .curves import build_empirical_curve
from .io import join_annotations_outcomes
from .surfaces import build_empirical_surface, build_interval_distribution, build_interval_tree

logger = logging.getLogger(__name__)

SUCCESS_COLOURS = ["#d7191c", "#ffff99", "#1a9641"]  # red, yellow, green: the paper's scale
DISTRIBUTION_COLOURS = "Reds"
UNOBSERVED_COLOUR = "whitesmoke"
INVALID_COLOUR = "lightgray"  # impossible cells, when asked to show them
UNOBSERVED = -1.0      # below the colour scale, so a valid but empty cell takes the "under" colour
DISPLAY_JITTER = 0.25  # integer intervals otherwise stack into a handful of columns
LEGEND_BELOW = {"loc": "upper center", "bbox_to_anchor": (0.5, -0.12), "frameon": False}


def require_matplotlib():
    """Imports what the renderers need, or raises an ImportError naming the extra."""
    try:
        import matplotlib
        import seaborn
    except ImportError:
        raise ImportError('plotting needs matplotlib and seaborn: pip install "propensity[plot]"') from None
    return matplotlib, seaborn


# --- one subject ---------------------------------------------------------------------------

def plot_propensity_curve(curve, *, theta=None, ci95=None, converged=True, incited=None,
                          r1=-3, r2=3, title=None, ax=None):
    """The propensity curve: the fraction of successes binned by interval centre, its
    LOWESS smooth, a solid line at theta and dashed lines at its 95% confidence bounds.

    curve: from `build_empirical_curve`, built with `jitter=0.25` for display.
    theta, ci95: the fit, as a level and a (lower, upper) pair. Leave theta None or NaN for a
        cell that was not fitted, and the data is drawn without an estimate.
    converged: False puts "did not converge" beside the estimate, since a tight interval around
        a failed fit misleads.
    incited: the level the subject was incited to, when known, drawn in grey.
    Returns the Axes, a new one unless `ax` is given.
    """
    require_matplotlib()
    ax = ax if ax is not None else _new_axes((8, 6))
    ax.plot(curve["bin_centers"], curve["bin_means"], "ok", label="Binned fraction of successes")
    ax.plot(curve["lowess_x"], curve["lowess_y"], "b-", label="LOWESS smooth")

    span = [r1, r2, *_finite(curve["bin_centers"])]  # jittered bins can sit past r1 or r2
    if incited is not None:
        ax.axvline(float(incited), color="grey", lw=2, label=f"Incited level = {float(incited):.2f}")
        span.append(float(incited))
    if _is_fitted(theta):
        ax.axvline(theta, color="orange", lw=2, label=_estimate_label(theta, ci95, converged))
        for bound in _finite(ci95):
            ax.axvline(bound, color="orange", ls="--", lw=1)
        span += [theta, *_finite(ci95)]

    ax.set_xlim(min(span) - 0.1, max(span) + 0.1)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel(r"Interval centre $(b_l + b_u)\,/\,2$")
    ax.set_ylabel("Fraction of successes")
    ax.grid(True)
    ax.set_axisbelow(True)
    ax.legend(loc="best")
    if title:
        ax.set_title(title)
    return ax


def plot_propensity_surface(surface, *, theta=None, ci95=None, converged=True, title=None, ax=None):
    """The propensity surface: success over the grid of interval bounds, `b_l` across and
    `b_u` up.

    The three cell states stay distinct: an observed cell is coloured red to green by its mean
    success and shows its count; a valid (`b_l <= b_u`) but unobserved cell is whitesmoke; an
    impossible cell (`b_l > b_u`) is left blank. A solid line marks `b_l + b_u = 2 * theta`, the
    intervals centred on the estimate, and dashed lines its 95% confidence bounds, all clipped
    to the grid. theta, ci95 and converged are as in `plot_propensity_curve`.
    Returns the Axes, a new one unless `ax` is given.
    """
    require_matplotlib()
    counts, grid = surface["counts"], np.asarray(surface["grid"])
    ax = ax if ax is not None else _new_axes((6, 6))
    _draw_cells(ax, surface["prob"], occupied=counts.to_numpy() > 0, valid=_ordered(counts),
                colours=_success_colours(), vmax=1, labels=counts.to_numpy().astype(str),
                colorbar_label="P(success)", square=True)
    ax.set_xlabel(r"Lower bound $b_l$")
    ax.set_ylabel(r"Upper bound $b_u$")

    if _is_fitted(theta):
        edge = (grid.min() - 0.5, grid.max() + 0.5)
        _centre_line(ax, theta, edge, edge[0], color="black", lw=2,
                     label=_estimate_label(theta, ci95, converged))
        for bound in _finite(ci95):
            _centre_line(ax, bound, edge, edge[0], color="black", lw=1, ls="--")
        ax.legend(**LEGEND_BELOW)  # inside the axes, some estimate's line would run under it
    if title:
        ax.set_title(title)
    return ax


def plot_model_surface(model_surface, *, title=None, colorbar=True, ax=None):
    """The success Eq. 5 predicts for one theta, over the grid of interval bounds: the surface
    `plot_propensity_surface` would converge to, on the same colour scale and orientation.

    model_surface: from `build_model_surface`. Built with `smooth=False`, it is drawn as the
    integer cells of the empirical surface; with `smooth=True`, as filled contours every 0.05,
    with labelled lines at 0.25, 0.5 and 0.75. Impossible intervals (`b_l > b_u`) are blank, and
    a line marks `b_l + b_u = 2 * theta`, where the predicted success is 1.
    Returns the Axes, a new one unless `ax` is given.
    """
    require_matplotlib()
    prob, grid, theta = model_surface["prob"], np.asarray(model_surface["grid"]), model_surface["theta"]
    values = np.ma.masked_invalid(prob.to_numpy(dtype=float))

    ax = ax if ax is not None else _new_axes((6, 6))
    if model_surface.get("smooth"):
        edges = grid
        mesh = ax.contourf(grid, grid, values, levels=np.linspace(0, 1, 21),
                           cmap=_success_colours(), vmin=0, vmax=1)
        lines = ax.contour(grid, grid, values, levels=[0.25, 0.5, 0.75], colors="black",
                           linewidths=0.6, alpha=0.6)
        ax.clabel(lines, fmt="%.2f", fontsize=8)
    else:
        half = (grid[1] - grid[0]) / 2 if len(grid) > 1 else 0.5
        edges = np.append(grid - half, grid[-1] + half)
        mesh = ax.pcolormesh(edges, edges, values, cmap=_success_colours(), vmin=0, vmax=1)
    if colorbar:
        ax.figure.colorbar(mesh, ax=ax, label="P(success)", fraction=0.046, pad=0.04,
                           ticks=np.linspace(0, 1, 6))
    ticks = np.arange(math.ceil(grid[0]), math.floor(grid[-1]) + 1)
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.set_aspect("equal")
    ax.set_xlabel(r"Lower bound $b_l$")
    ax.set_ylabel(r"Upper bound $b_u$")
    _centre_line(ax, theta, (edges[0], edges[-1]), 0.0, color="black", lw=2,
                 label=rf"$\theta$ = {theta:.2f}")
    ax.legend(**LEGEND_BELOW)
    if title:
        ax.set_title(title)
    return ax


# --- an item bank --------------------------------------------------------------------------

def plot_interval_distribution(distribution, *, proportion=True, cmap=DISTRIBUTION_COLOURS,
                               vmax=None, title=None, colorbar=True, ax=None):
    """How a bank's annotated intervals spread over the grid of bounds, `b_l` across and `b_u` up.

    distribution: from `build_interval_distribution`. An occupied cell is coloured by its share
    of the bank, or its count with `proportion=False`, and shows it; a valid but empty cell is
    whitesmoke; an impossible one is blank.
    vmax: the top of the colour scale, the fullest cell by default. Fix it to compare banks.
    Returns the Axes, a new one unless `ax` is given.
    """
    require_matplotlib()
    counts = distribution["counts"]
    values = distribution["proportions" if proportion else "counts"]
    ax = ax if ax is not None else _new_axes((6, 6))
    _draw_cells(ax, values, occupied=counts.to_numpy() > 0, valid=_ordered(counts),
                colours=_colormap(cmap), vmax=vmax, labels=_value_labels(values, proportion),
                colorbar_label=_share_label(proportion) if colorbar else None, square=True)
    ax.set_xlabel(r"Lower bound $b_l$")
    ax.set_ylabel(r"Upper bound $b_u$")
    if title:
        ax.set_title(title)
    return ax


def plot_interval_tree(tree, *, proportion=True, show_invalid=False, cmap=DISTRIBUTION_COLOURS,
                       vmax=None, title=None, colorbar=True, ax=None):
    """The "Christmas tree": a bank's intervals by centre across and length up.

    tree: from `build_interval_tree`. Zero-length intervals form the wide base and [-3, +3],
    the orthogonal interval, is the tip, so a bank crowded at the tip is visible at once. Cells
    are coloured and labelled as in `plot_interval_distribution`; a centre and length no interval
    with whole-numbered bounds can have is blank, like any other impossible cell.
    show_invalid: fill those impossible cells in light grey instead, so the whole grid stays
        visible. They are still never labelled, and stay distinct from empty valid cells.
    Returns the Axes, a new one unless `ax` is given.
    """
    require_matplotlib()
    counts = tree["counts"]
    values = tree["proportions" if proportion else "counts"]
    ax = ax if ax is not None else _new_axes((9, 5))
    _draw_cells(ax, values, occupied=counts.to_numpy() > 0, valid=tree["reachable"].to_numpy(),
                colours=_colormap(cmap), vmax=vmax, labels=_value_labels(values, proportion),
                colorbar_label=_share_label(proportion) if colorbar else None, square=False,
                invalid_colour=INVALID_COLOUR if show_invalid else None,
                xticklabels=[f"{centre:g}" for centre in tree["centres"]], annot_kws={"fontsize": 7})
    ax.set_xlabel(r"Interval centre $(b_l + b_u)\,/\,2$")
    ax.set_ylabel(r"Interval length $b_u - b_l$")
    if title:
        ax.set_title(title)
    return ax


def plot_interval_trees(trees, *, proportion=True, show_invalid=False, cmap=DISTRIBUTION_COLOURS,
                        title=None, nrows=None, ncols=None, figsize=None, figure=None):
    """Several banks' trees side by side, on one colour scale with one colour bar, for comparing
    datasets or dimensions.

    trees: {panel title: build_interval_tree(...)}, drawn in that order.
    show_invalid: as in `plot_interval_tree`, for every panel.
    nrows, ncols: the layout; by default the one with fewest empty slots, then the squarest.
    Returns the Figure, a new one unless `figure` is given.
    """
    require_matplotlib()
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    if not trees:
        raise ValueError("no trees to draw")
    nrows, ncols = _layout(len(trees), nrows, ncols)
    if figure is None:
        import matplotlib.pyplot as plt

        figure = plt.figure(figsize=figsize or _grid_size(nrows, ncols), layout="constrained")
    key = "proportions" if proportion else "counts"
    vmax = max(float(tree[key].to_numpy().max()) for tree in trees.values()) or 1.0

    axes = figure.subplots(nrows, ncols, squeeze=False).ravel()
    for ax, (name, tree) in zip(axes, trees.items()):
        plot_interval_tree(tree, proportion=proportion, show_invalid=show_invalid, cmap=cmap,
                           vmax=vmax, title=name, colorbar=False, ax=ax)
    for ax in axes[len(trees):]:
        ax.remove()
    figure.colorbar(ScalarMappable(Normalize(0, vmax), cmap=_colormap(cmap)),
                    ax=list(axes[:len(trees)]), shrink=0.9, label=_share_label(proportion))
    if title:
        figure.suptitle(title)
    return figure


# --- writing files ---------------------------------------------------------------------------

def save_profile_plots(profiles, annotations, outcomes, out_dir, *, n_bins=20, lowess_frac=0.4,
                       jitter=DISPLAY_JITTER, seed=0, dpi=100) -> list[Path]:
    """Draws the curve and the surface of every (subject, dimension) cell in `profiles` into
    `out_dir`, as `{subject}_{dimension}_curve.png` and `..._surface.png`.

    profiles: the table `fit_profiles` returned for these annotations and outcomes, whose join
        is repeated here without repeating its warnings.
    A cell that was not fitted is still drawn, without an estimate and with its skip reason in
    the title: its surface is how a bank with no informative cells is caught. A cell with no
    joined instances has nothing to draw. A plot that fails is logged and skipped, and the rest
    carry on. Returns the paths written.
    """
    require_matplotlib()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # fit_profiles already raised them for the same join
        joined, _ = join_annotations_outcomes(annotations, outcomes)
    cells = dict(tuple(joined.groupby(["subject_id", "dimension"]))) if len(joined) else {}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written, stems = [], set()
    for row in profiles.itertuples(index=False):
        cell = cells.get((row.subject_id, row.dimension))
        if cell is None or cell.empty:
            continue
        demands = cell[["lower", "upper"]].to_numpy(dtype=float)
        success = cell["outcome"].to_numpy(dtype=float)
        fit = {"theta": row.theta, "ci95": (row.ci95_lower, row.ci95_upper),
               "converged": pd.isna(row.converged) or int(row.converged) == 1}
        title = f"{row.subject_id} · {row.dimension} · {len(cell)} instances"
        if not _is_fitted(row.theta):
            title += f"\nnot fitted: {row.skip_reason}"
        stem = _unique_stem(f"{row.subject_id}_{row.dimension}", stems)
        where = f"{row.subject_id} / {row.dimension}"

        written += [
            _render(out_dir / f"{stem}_curve.png", (8, 6), f"the curve for {where}", dpi,
                    lambda figure: plot_propensity_curve(build_empirical_curve(
                        demands, success, n_bins=n_bins, lowess_frac=lowess_frac, jitter=jitter,
                        seed=seed), title=title, ax=figure.subplots(), **fit)),
            _render(out_dir / f"{stem}_surface.png", (7, 6), f"the surface for {where}", dpi,
                    lambda figure: plot_propensity_surface(build_empirical_surface(
                        demands, success), title=title, ax=figure.subplots(), **fit)),
        ]
    return [path for path in written if path is not None]


def save_annotation_plots(annotations, out_dir, *, dimensions=None, proportion=True,
                          show_invalid=False, dpi=100) -> list[Path]:
    """Draws how each dimension's annotated intervals spread, into `out_dir`: by bounds as
    `{dimension}_intervals.png` and by centre and length as `{dimension}_tree.png`, plus every
    dimension's tree on one colour scale as `interval_trees.png` when there are several.

    annotations: tidy, as `load_annotations` returns them. Rows that failed to parse or have a
        null bound are left out, as the fit leaves them out.
    dimensions: only these; every annotated dimension by default.
    show_invalid: fill the trees' impossible cells in light grey, as in `plot_interval_tree`.
    A plot that fails is logged and skipped, and the rest carry on. Returns the paths written.
    """
    require_matplotlib()
    usable = annotations[annotations["lower"].notna() & annotations["upper"].notna()]
    if "parse_ok" in usable.columns:
        usable = usable[usable["parse_ok"].astype(bool)]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written, stems, trees = [], set(), {}
    for dimension, rows in usable.groupby("dimension", sort=True):
        if dimensions is not None and dimension not in dimensions:
            continue
        demands = rows[["lower", "upper"]].to_numpy(dtype=float)
        try:
            distribution, tree = build_interval_distribution(demands), build_interval_tree(demands)
        except ValueError as exc:
            logger.warning("skipped the interval plots for %s: %s", dimension, exc)
            continue
        trees[str(dimension)] = tree
        title = f"{dimension} · {len(rows)} annotated instances"
        stem = _unique_stem(str(dimension), stems)
        written += [
            _render(out_dir / f"{stem}_intervals.png", (7, 6), f"the interval distribution for "
                    f"{dimension}", dpi, lambda figure: plot_interval_distribution(
                        distribution, proportion=proportion, title=title, ax=figure.subplots())),
            _render(out_dir / f"{stem}_tree.png", (9, 5), f"the interval tree for {dimension}",
                    dpi, lambda figure: plot_interval_tree(
                        tree, proportion=proportion, show_invalid=show_invalid, title=title,
                        ax=figure.subplots())),
        ]
    if len(trees) > 1:
        shape = _layout(len(trees), None, None)
        written.append(_render(
            out_dir / "interval_trees.png", _grid_size(*shape), "the interval trees", dpi,
            lambda figure: plot_interval_trees(trees, proportion=proportion,
                                               show_invalid=show_invalid, figure=figure,
                                               title="Annotated intervals by centre and length"),
            layout="constrained"))
    return [path for path in written if path is not None]


# --- helpers -----------------------------------------------------------------------------------

def _draw_cells(ax, values, *, occupied, valid, colours, vmax, labels, colorbar_label, square,
                invalid_colour=None, **heatmap_options):
    """A heatmap in the three cell states: occupied cells coloured by value and labelled, valid
    empty ones in whitesmoke, the rest blank, or filled with `invalid_colour` when one is given.
    `b_u`, or the length, grows upwards."""
    _, seaborn = require_matplotlib()
    shown = np.where(occupied, values.to_numpy(dtype=float), np.nan)  # NaN is masked: "bad"
    shown[valid & ~occupied] = UNOBSERVED
    if vmax is None:
        vmax = float(np.nanmax(np.where(occupied, shown, np.nan))) if occupied.any() else 1.0
    extremes = {"under": UNOBSERVED_COLOUR, **({"bad": invalid_colour} if invalid_colour else {})}
    seaborn.heatmap(pd.DataFrame(shown, index=values.index, columns=values.columns), ax=ax,
                    cmap=colours.with_extremes(**extremes), vmin=0, vmax=vmax,
                    square=square, fmt="", annot=np.where(occupied, labels, ""),
                    cbar=colorbar_label is not None,
                    cbar_kws={"label": colorbar_label, "fraction": 0.046, "pad": 0.04},
                    **heatmap_options)
    ax.invert_yaxis()
    ax.tick_params(axis="y", labelrotation=0)


def _render(path, size, what, dpi, draw, layout=None):
    """Draws onto a new off-screen figure and saves it, returning the path. A failure is logged
    and returns None, so one bad plot never stops the rest."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=size, layout=layout)
    FigureCanvasAgg(figure)  # renders to a file, with no display or GUI backend
    try:
        draw(figure)
        figure.savefig(path, dpi=dpi, bbox_inches="tight")
    except Exception as exc:
        logger.warning("skipped %s: %s: %s", what, type(exc).__name__, exc)
        return None
    return path


def _new_axes(size):
    import matplotlib.pyplot as plt

    return plt.subplots(figsize=size)[1]


def _success_colours():
    from matplotlib.colors import LinearSegmentedColormap

    return LinearSegmentedColormap.from_list("success", SUCCESS_COLOURS)


def _colormap(cmap):
    import matplotlib

    return matplotlib.colormaps[cmap] if isinstance(cmap, str) else cmap


def _ordered(frame):
    """Which cells of a b_u-by-b_l frame are valid intervals, b_l <= b_u."""
    lower, upper = np.meshgrid(frame.columns.to_numpy(), frame.index.to_numpy())
    return lower <= upper


def _value_labels(values, proportion):
    if not proportion:
        return values.to_numpy().astype(int).astype(str)
    label = np.vectorize(lambda share: f"{share:.2f}" if share >= 0.005 else "<.01", otypes=[object])
    return label(values.to_numpy(dtype=float))


def _share_label(proportion):
    return "Share of instances" if proportion else "Instances"


def _layout(n, nrows, ncols):
    """(rows, columns) for n panels. Unless given: fewest empty slots, then the squarest, then
    the fewest rows."""
    if nrows is None and ncols is None:
        scores = [(math.ceil(n / rows) * rows - n, abs(math.ceil(n / rows) - rows), rows)
                  for rows in range(1, n + 1)]
        nrows = min(scores)[2]
    nrows = nrows or math.ceil(n / ncols)
    ncols = ncols or math.ceil(n / nrows)
    if nrows * ncols < n:
        raise ValueError(f"a {nrows} x {ncols} grid cannot hold {n} panels")
    return nrows, ncols


def _grid_size(nrows, ncols):
    return (4.8 * ncols + 1, 3.4 * nrows + 0.6)


def _is_fitted(theta):
    return theta is not None and bool(np.isfinite(theta))


def _finite(values):
    if values is None:
        return []
    return [float(value) for value in values if value is not None and np.isfinite(value)]


def _estimate_label(theta, ci95, converged):
    bounds = _finite(ci95)
    label = rf"$\hat\theta$ = {theta:.2f}"
    if len(bounds) == 2:
        label += f", 95% CI [{bounds[0]:.2f}, {bounds[1]:.2f}]"
    return label if converged else label + "\n(the fit did not converge)"


def _centre_line(ax, level, edge, shift, **style):
    """The intervals centred on `level`, b_u = 2 * level - b_l, clipped exactly to `edge`.
    On a heatmap, cell centres sit half a cell in, so a bound value v is drawn at v - shift with
    shift = edge[0]; on value axes shift is 0. A level off the grid still gets its (empty) line,
    so its label reaches the legend."""
    low, high = edge
    start, end = max(low, 2 * level - high), min(high, 2 * level - low)
    b_l = np.array([start, end]) if start < end else np.array([])
    ax.plot(b_l - shift, 2 * level - b_l - shift, **style)


def _unique_stem(text, taken):
    """A filename-safe stem, kept distinct from the stems already taken."""
    stem = re.sub(r"[^A-Za-z0-9._+-]+", "_", text).strip("._") or "cell"  # keeps "_+2" readable
    candidate, n = stem, 1
    while candidate in taken:
        n += 1
        candidate = f"{stem}_{n}"
    taken.add(candidate)
    return candidate
