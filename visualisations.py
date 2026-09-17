from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
import matplotlib.pyplot as plt
from matplotlib.pyplot import axes
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

import math

def _best_grid(n: int) -> tuple[int, int]:
    """
    Plot-friendly grid.
    """
    if n < 1:
        raise ValueError("n must be positive")

    best = None

    for nrows in range(1, n + 1):
        ncols = math.ceil(n / nrows)

        score = (
            nrows * ncols - n,     # empty cells
            abs(ncols - nrows),    # squareness
            nrows                  # fewer rows
        )

        if best is None or score < best[0]:
            best = (score, nrows, ncols)

    return best[1], best[2] #type: ignore

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

def propensity_probability(theta, b_l, b_u, a):
    r = (b_u - b_l) / 2
    a_prime = a + np.exp(1 / r) - 1

    norm = sigmoid(a_prime * r) ** -2

    return (
        norm
        * sigmoid(a_prime * (theta - b_l))
        * sigmoid(a_prime * (b_u - theta))
    )

def theoretical_subject_propensity_surface(
        a: float = 1.0,
        theta: float = 0,
        min: int = -5,
        max: int = 5,
        cmap: str = "viridis"

    ) -> axes.Axes:

    # Grid of interval bounds
    b_l_vals = np.linspace(min, max, 300)
    b_u_vals = np.linspace(min, max, 300)

    BL, BU = np.meshgrid(b_l_vals, b_u_vals)

    # Compute probabilities
    P = np.full_like(BL, np.nan, dtype=float)

    valid = BU > BL

    r = (BU[valid] - BL[valid]) / 2
    a_prime = a + np.exp(1 / r) - 1

    norm = sigmoid(a_prime * r) ** -2

    P[valid] = (
        norm
        * sigmoid(a_prime * (theta - BL[valid]))
        * sigmoid(a_prime * (BU[valid] - theta))
    )

    fig, ax = plt.subplots()
    im = ax.imshow(
        P,
        extent = (min, max, min, max),
        origin = "lower",
        aspect = "equal",
        cmap = cmap
    )

    plt.colorbar(im, label = "P(success)", ax = ax)
    ax.set(
        xlabel = r"$b_l$",
        ylabel = r"$b_u$",
        title = fr"Agent characteristic surface ($\theta={theta}$, $a={a}$)")

    return ax

def _jim_index(
        min_level: int,
        max_level: int,
        mode: str
    ):
    
    if mode == "bound":
        levels = range(min_level, max_level + 1)

        full_index = pd.MultiIndex.from_product(
            [levels, levels],
            names = ["low", "up"]
        )

        return full_index, levels, levels

    elif mode == "centre":
        centres = np.arange(min_level, max_level + 0.5, 0.5)
        lengths = np.arange(0, max_level - min_level + 1)

        full_index = pd.MultiIndex.from_product(
            [lengths, centres],
            names = ["length", "centre"]
        )

        return full_index, lengths, centres

    else:
        raise NotImplementedError

def _joint_interval_matrix(
    low_vals: ArrayLike,
    up_vals: ArrayLike,
    min_level: int = -3,
    max_level: int = 3,
    mode: str = "bound",
    proportion: bool = True
    ) -> tuple[pd.DataFrame, pd.DataFrame, range, range]:
    
    low_vals = np.asarray(low_vals)
    up_vals = np.asarray(up_vals)

    if len(low_vals) != len(up_vals):
        raise ValueError("Arrays must have the same length")
    
    df = pd.DataFrame({
        "low": low_vals,
        "up": up_vals
    })

    df["centre"] = (df["up"] + df["low"]) / 2
    df["length"] = df["up"] - df["low"]

    full_index, row_index, col_index = _jim_index(min_level, max_level, mode = mode)

    if mode == "bound":
        gby_colnames = ["low", "up"]
    else:
        gby_colnames = ["length", "centre"]

    counts = (
        df.groupby(gby_colnames)
            .size()
            .reindex(full_index, fill_value = 0)
            .reset_index(name = "count")
    )

    total = counts["count"].sum()
    counts["prop"] = counts["count"] / total if total > 0 else 0

    values = "prop" if proportion else "count"

    if mode == "bound":
        row_colname, col_colname = "up", "low"
    else:
        row_colname, col_colname = "length", "centre"

    mat = counts.pivot(
        index = row_colname,
        columns = col_colname,
        values = values
    )

    mat = mat.reindex(
        index = row_index,
        columns = col_index,
        fill_value = 0
    )

    return counts, mat, row_index, col_index #type: ignore

def interval_distribution(
    low_vals: ArrayLike,
    up_vals: ArrayLike,
    min_level: int = -3,
    max_level: int = 3,
    proportion: bool = True,
    cmap: str = "Reds",
    title: str = "Interval distribution",
    xlabel: str = "Lower bound",
    ylabel: str = "Upper bound",
    colorbar: bool = True,
    ax = None
    ) -> axes.Axes:

    counts, mat, levels, _ = _joint_interval_matrix(
        low_vals = low_vals,
        up_vals = up_vals,
        min_level = min_level,
        max_level = max_level,
        proportion = proportion
    )

    # levels = range(min_level, max_level + 1)

    if ax is None:
        fig, ax = plt.subplots()
    else:
        fig = ax.figure

    im = ax.imshow(
        mat.values,
        origin = "lower",
        vmin = 0,
        vmax = mat.values.max() if mat.values.max() > 0 else 1,
        cmap = cmap,
        aspect = "equal")
    
    cmap_obj = plt.cm.get_cmap(cmap).copy()
    cmap_obj.set_bad("lightgray")

    levels_arr = np.array(list(levels))
    low_grid, up_grid = np.meshgrid(levels_arr, levels_arr)

    invalid_mask = low_grid > up_grid

    masked_mat = np.ma.masked_where(invalid_mask, mat.values)

    im = ax.imshow(
        masked_mat,
        origin = "lower",
        vmin = 0,
        vmax = masked_mat.max() if masked_mat.max() > 0 else 1,
        cmap = cmap_obj,
        aspect = "equal"
    )

    ax.set(
        title = title,
        xlabel = xlabel,
        ylabel = ylabel
    )

    ax.set_xticks(range(max_level - min_level + 1))
    ax.set_yticks(range(max_level - min_level + 1))
    ax.set_xticklabels(str(l) for l in levels)
    ax.set_yticklabels(str(l) for l in levels)

    if colorbar:
        fig.colorbar(im, ax = ax)

    return ax

def interval_distribution_xmas(
    low_vals: ArrayLike,
    up_vals: ArrayLike,
    min_level: int = -3,
    max_level: int = 3,
    proportion: bool = True,
    cmap: str = "Reds",
    title: str = "Interval distribution",
    xlabel: str = "Interval centre",
    ylabel: str = "Interval length",
    colorbar: bool = True,
    ax = None,
    vmin: float = 0,
    vmax: float | None = None,
    ) -> axes.Axes:

    counts, mat, lengths, centres = _joint_interval_matrix(
        low_vals = low_vals,
        up_vals = up_vals,
        min_level = min_level,
        max_level = max_level,
        proportion = proportion,
        mode = "centre"
    )

    C, R = np.meshgrid(centres, lengths)

    valid = (
        (C - R / 2 >= min_level) &
        (C + R / 2 <=  max_level)
    )

    cmap_obj = plt.cm.get_cmap(cmap).copy()
    cmap_obj.set_bad("lightgray")

    masked_mat = np.ma.masked_where(~valid, mat.values)

    if ax is None:
        fig, ax = plt.subplots()
    else:
        fig = ax.figure

    im = ax.imshow(
        masked_mat,
        origin = "lower",
        cmap = cmap_obj,
        vmin = vmin,
        vmax = vmax,
        aspect = "auto"
    )

    norm = im.norm

    for i in range(masked_mat.shape[0]):
        for j in range(masked_mat.shape[1]):
            if valid[i, j]:
                value = masked_mat[i, j]

                ax.text(
                    j,
                    i,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white" if norm(value) > 0.5 else "black",
                    rotation = 90
                )

    ax.set(
        title = title,
        xlabel = xlabel,
        ylabel = ylabel
    )

    ax.set_xticks(np.arange(len(centres)))
    ax.set_xticklabels([f"{c:.1f}" for c in centres], rotation=90)

    ax.set_yticks(np.arange(len(lengths)))
    ax.set_yticklabels(str(l) for l in lengths)

    if colorbar:
        fig.colorbar(im, ax = ax)

    return ax


def interval_distribution_xmas_grid(
    low_vals: list[np.ndarray],
    up_vals: list[np.ndarray],
    min_level: int = -3,
    max_level: int = 3,
    proportion: bool = True,
    cmap: str = "Reds",
    titles: list[str] | None = None,
    xlabels: list[str] | None = None,
    ylabels: list[str] | None = None,
    suptitle: str = "Interval distribution",
    nrows: int | None = None,
    ncols: int | None = None,
    figsize: tuple[int, int] | None = None
):

    for lv, uv in zip(low_vals, up_vals): #type: ignore
        assert lv.shape == uv.shape

    global_max = 0
    n = len(low_vals)

    for i in range(n):
        _, mat, _, _ = _joint_interval_matrix(
            low_vals[i],
            up_vals[i],
            mode = "centre"
        )

        global_max = max(global_max, mat.values.max())

    sm = ScalarMappable(
        norm = Normalize(vmin = 0, vmax = global_max),
        cmap = cmap
    )

    sm.set_array([])

    if nrows is None or ncols is None:
        nrows, ncols = _best_grid(n)

    if titles is None:
        titles = ["Distribution"] * n
    
    if xlabels is None:
        xlabels = ["Interval centre"] * n

    if ylabels is None:
        ylabels = ["Interval width"] * n

    fig, axes = plt.subplots(
        nrows = nrows, ncols = ncols, figsize = figsize,
        constrained_layout = True
    )

    if ncols > 1 and nrows > 1:
        axes = axes.ravel()  
    else:
        axes = [axes]

    for title, ax, lv, uv, xlab, ylab in zip(
        titles, axes, low_vals, up_vals, xlabels, ylabels):
        ax = interval_distribution_xmas(
            low_vals = lv,
            up_vals = uv,
            min_level = min_level,
            max_level = max_level,
            proportion = proportion,
            cmap = cmap,
            title = title,
            xlabel = xlab,
            ylabel = ylab,
            colorbar = False,
            ax = ax,
            vmax = global_max
        )

    fig.colorbar(
        sm,
        ax = axes,
        location = "right",
        shrink = 0.9,
        label = "Proportion" if proportion else "Counts"
    )

    fig.suptitle(suptitle)
    return fig