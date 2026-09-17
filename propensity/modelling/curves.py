"""The empirical propensity curve: CLAUDE.md §10.1.

A data structure only. Rendering lives in plotting.py, so importing this never needs matplotlib.
"""

import numpy as np
from scipy.stats import binned_statistic
from statsmodels.nonparametric.smoothers_lowess import lowess


def build_empirical_curve(demands, success, *, n_bins=20, lowess_frac=0.4, jitter=0.0,
                          seed=None) -> dict:
    """Observed success binned by interval centre, with a LOWESS smooth of those bins.

    demands: (N, 2) array-like of (b_l, b_u). success: (N,) array-like of 0/1.
    jitter: half-width of a uniform jitter added to both bounds, **for display only**, because
        integer-valued intervals otherwise stack into a handful of columns; ±0.25 is the usual
        choice when plotting. Never jitter the data used for fitting. `seed` makes it repeatable.

    Returns bin_centers, bin_means (NaN for an empty bin), lowess_x and lowess_y. With fewer
    than two populated bins there is nothing to smooth, and the LOWESS arrays are just those
    bins.
    """
    demands = np.asarray(demands, dtype=float)
    success = np.asarray(success, dtype=float)
    if jitter:
        rng = np.random.default_rng(seed)
        demands = demands + 2.0 * jitter * (rng.random(demands.shape) - 0.5)

    centres = (demands[:, 0] + demands[:, 1]) / 2
    bin_means, edges, _ = binned_statistic(centres, success, statistic="mean", bins=n_bins)
    bin_centres = (edges[:-1] + edges[1:]) / 2

    populated = np.isfinite(bin_means) & np.isfinite(bin_centres)
    if populated.sum() < 2:
        lowess_x, lowess_y = bin_centres[populated], bin_means[populated]
    else:
        smoothed = lowess(bin_means[populated], bin_centres[populated], frac=lowess_frac, it=0)
        lowess_x, lowess_y = smoothed[:, 0], smoothed[:, 1]

    return {"bin_centers": bin_centres, "bin_means": bin_means,
            "lowess_x": lowess_x, "lowess_y": lowess_y}
