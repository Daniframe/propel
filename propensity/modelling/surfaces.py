"""The empirical propensity surface: CLAUDE.md §10.2.

A data structure only. Rendering lives in plotting.py, so importing this never needs matplotlib.
"""

import numpy as np
import pandas as pd


def build_empirical_surface(demands_int, success, *, r1=-3, r2=3) -> dict:
    """Observed success aggregated onto the integer grid of interval bounds.

    demands_int: (N, 2) array-like of whole-numbered (b_l, b_u) inside [r1, r2].
    success: (N,) array-like of 0/1.

    Returns:
        prob: mean success per cell, NaN where nothing was observed
        counts: number of observations per cell
        grid: the integer values used for both axes

    Both frames are indexed by b_u down the rows and b_l across the columns, the orientation
    plotting.py draws. The three cell states of §10.2 follow from them: observed is
    `counts > 0`; valid but unobserved is `b_l <= b_u` with `counts == 0`; impossible is
    `b_l > b_u`. This surface is how an item bank with no informative cells is spotted.
    """
    demands = np.asarray(demands_int, dtype=float)
    success = np.asarray(success, dtype=float)
    if demands.ndim != 2 or demands.shape[1] != 2:
        raise ValueError(f"demands must have shape (N, 2), got {demands.shape}")
    if success.shape != (demands.shape[0],):
        raise ValueError(f"success must have shape ({demands.shape[0]},), got {success.shape}")
    if not np.all(np.isfinite(demands)):
        raise ValueError("demands contain NaN or infinite bounds")
    if not np.all(demands == np.round(demands)):
        raise ValueError("the surface is an integer grid; round the demand bounds first")
    if demands.size and (demands.min() < r1 or demands.max() > r2):
        raise ValueError(f"demand bounds must lie within [{r1}, {r2}]")

    observations = pd.DataFrame({
        "b_l": demands[:, 0].astype(int),
        "b_u": demands[:, 1].astype(int),
        "success": success,
    })
    grid = np.arange(r1, r2 + 1)
    every_cell = pd.MultiIndex.from_product([grid, grid], names=["b_u", "b_l"])
    by_cell = observations.groupby(["b_u", "b_l"])["success"]

    counts = by_cell.size().reindex(every_cell, fill_value=0).unstack()
    prob = by_cell.mean().reindex(every_cell).unstack()
    return {"prob": prob, "counts": counts, "grid": grid}
