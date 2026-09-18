"""Surfaces over the grid of demand intervals, and what an item bank looks like.

- `build_empirical_surface`: observed success per interval, for one subject.
- `build_model_surface`: the success Eq. 5 predicts per interval, for a given theta.
- `build_interval_distribution` and `build_interval_tree`: how a bank's annotated intervals
  spread, by bounds or by centre and length, before any subject is involved.

Data structures only. Rendering lives in plotting.py, so importing this never needs matplotlib.
"""

import numpy as np
import pandas as pd

from .model import two_sided_sigma


def build_empirical_surface(demands_int, success, *, r1=-3, r2=3) -> dict:
    """Observed success aggregated onto the integer grid of interval bounds.

    demands_int: (N, 2) array-like of whole-numbered (b_l, b_u) inside [r1, r2].
    success: (N,) array-like of 0/1.

    Returns:
        prob: mean success per cell, NaN where nothing was observed
        counts: number of observations per cell
        grid: the integer values used for both axes

    Both frames are indexed by b_u down the rows and b_l across the columns, the orientation
    plotting.py draws. The three cell states follow from them: observed is
    `counts > 0`; valid but unobserved is `b_l <= b_u` with `counts == 0`; impossible is
    `b_l > b_u`. This surface is how an item bank with no informative cells is spotted.
    """
    demands = _integer_demands(demands_int, r1, r2)
    success = np.asarray(success, dtype=float)
    if success.shape != (demands.shape[0],):
        raise ValueError(f"success must have shape ({demands.shape[0]},), got {success.shape}")

    observations = pd.DataFrame({"b_l": demands[:, 0], "b_u": demands[:, 1], "success": success})
    grid = np.arange(r1, r2 + 1)
    every_cell = pd.MultiIndex.from_product([grid, grid], names=["b_u", "b_l"])
    by_cell = observations.groupby(["b_u", "b_l"])["success"]

    counts = by_cell.size().reindex(every_cell, fill_value=0).unstack()
    prob = by_cell.mean().reindex(every_cell).unstack()
    return {"prob": prob, "counts": counts, "grid": grid}


def build_interval_distribution(demands_int, *, r1=-3, r2=3) -> dict:
    """How a bank's annotated intervals spread over the grid of bounds.

    demands_int: (N, 2) array-like of whole-numbered (b_l, b_u) inside [r1, r2].

    Returns counts and proportions (of all N) per cell, in the orientation of
    `build_empirical_surface` (b_u down the rows, b_l across), plus grid and n_items. A bank
    whose intervals crowd into a few cells, or into [r1, r2] itself, cannot locate theta.
    """
    demands = _integer_demands(demands_int, r1, r2)
    grid = np.arange(r1, r2 + 1)
    every_cell = pd.MultiIndex.from_product([grid, grid], names=["b_u", "b_l"])
    counts = (pd.DataFrame({"b_l": demands[:, 0], "b_u": demands[:, 1]})
              .groupby(["b_u", "b_l"]).size().reindex(every_cell, fill_value=0).unstack())
    return {"counts": counts, "proportions": counts / max(len(demands), 1), "grid": grid,
            "n_items": len(demands)}


def build_interval_tree(demands_int, *, r1=-3, r2=3) -> dict:
    """The same distribution by interval centre and length: the "Christmas tree".

    Lengths 0 to r2 - r1 run down the rows and centres r1 to r2, in steps of 0.5, across the
    columns. Drawn with length 0 at the bottom, the cells an interval can occupy form a tree:
    every level is the centre of a zero-length interval, and only the middle one of [r1, r2].

    Returns counts and proportions per cell, centres, lengths, n_items, and `reachable`: whether
    an interval with whole-numbered bounds inside [r1, r2] can have that centre and length. An
    even length needs a whole centre and an odd one a half, so half the cells inside the tree's
    outline are unreachable, not merely unobserved.
    """
    demands = _integer_demands(demands_int, r1, r2)
    centres = np.arange(2 * r1, 2 * r2 + 1) / 2
    lengths = np.arange(0, r2 - r1 + 1)
    every_cell = pd.MultiIndex.from_product([lengths, centres], names=["length", "centre"])
    counts = (pd.DataFrame({"length": demands[:, 1] - demands[:, 0],
                            "centre": (demands[:, 0] + demands[:, 1]) / 2})
              .groupby(["length", "centre"]).size().reindex(every_cell, fill_value=0).unstack())

    centre, length = np.meshgrid(centres, lengths)
    lower = centre - length / 2
    reachable = (lower >= r1) & (centre + length / 2 <= r2) & (lower == np.round(lower))
    return {"counts": counts, "proportions": counts / max(len(demands), 1),
            "reachable": pd.DataFrame(reachable, index=counts.index, columns=counts.columns),
            "centres": centres, "lengths": lengths, "n_items": len(demands)}


def build_model_surface(theta, *, smooth=False, resolution=0.05, k=1.0, min_width=0.1, rho=2.0,
                        r1=-3, r2=3) -> dict:
    """The probability of success Eq. 5 predicts for a subject at `theta`, over the grid of
    interval bounds: what `build_empirical_surface` would show with unlimited data.

    smooth: False gives the integer grid of the empirical surface, cell for cell; True gives a
        continuous surface sampled every `resolution`, which plotting.py draws as contours.
    k, min_width, rho: as in `two_sided_sigma`, so this is exactly the model the fit uses.

    Returns prob (b_u down the rows, b_l across; NaN where b_l > b_u), grid, theta and smooth.
    The surface peaks at 1 along b_l + b_u = 2 * theta, and narrow intervals fall away fastest.
    """
    step = resolution if smooth else 1
    grid = np.round(np.arange(r1, r2 + step / 2, step), 10)
    prob = np.full((len(grid), len(grid)), np.nan)
    for row, b_u in enumerate(grid):
        for column, b_l in enumerate(grid[grid <= b_u]):
            prob[row, column] = two_sided_sigma(theta, b_l, b_u, k, k, min_width, rho)
    frame = pd.DataFrame(prob, index=pd.Index(grid, name="b_u"), columns=pd.Index(grid, name="b_l"))
    return {"prob": frame, "grid": grid, "theta": float(theta), "smooth": bool(smooth)}


def _integer_demands(demands_int, r1, r2):
    """An (N, 2) integer array of bounds, after checking they belong on the grid."""
    demands = np.asarray(demands_int, dtype=float)
    if demands.ndim != 2 or demands.shape[1] != 2:
        raise ValueError(f"demands must have shape (N, 2), got {demands.shape}")
    if not np.all(np.isfinite(demands)):
        raise ValueError("demands contain NaN or infinite bounds")
    if not np.all(demands == np.round(demands)):
        raise ValueError("the surface is an integer grid; round the demand bounds first")
    if demands.size and (demands.min() < r1 or demands.max() > r2):
        raise ValueError(f"demand bounds must lie within [{r1}, {r2}]")
    return demands.astype(int)
