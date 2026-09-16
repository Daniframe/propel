"""The propensity response model: CLAUDE.md §9.1, Eq. 5 of arXiv 2602.18182.

P(success | theta) for one item is a normalised product of two logistics: a bell over the
propensity axis that peaks at exactly 1.0 at the midpoint of the item's demand interval
[b_l, b_u]. Narrow intervals get steeper sides, so they discriminate more.
"""

import numpy as np
from scipy.optimize import fmin
from scipy.special import expit

MAX_EXP = 700.0  # np.exp(709) is near float64 overflow


def _numeric_peak_normaliser(b_l, b_u, k1, k2):
    """Returns A such that the product of the two logistics peaks at 1.0 when k1 != k2."""

    def neg_product(x):
        with np.errstate(over="ignore"):
            return -1.0 / ((1.0 + np.exp(-k1 * (x - b_l))) * (1.0 + np.exp(k2 * (x - b_u))))

    x_peak = fmin(neg_product, (b_l + b_u) / 2.0, disp=False)[0]
    return 1.0 / -neg_product(x_peak)


def two_sided_sigma(x, b_l, b_u, k1=1.0, k2=1.0, min_width=0.1, rho=2.0):
    """Eq. 5: probability that an agent at propensity level `x` succeeds on an item whose
    demand interval is [b_l, b_u].

    x: propensity level(s); scalar or array.
    b_l, b_u: the item's demand interval, b_l <= b_u.
    k1, k2: base slopes of the lower and upper logistic; the fit uses k1 == k2.
    min_width: intervals narrower than this are widened symmetrically outward to it, so
        the discrimination term e^(rho/w) stays finite.
    rho: how fast discrimination grows as the interval narrows (slope = k + e^(rho/w) - 1).

    Returns values in [0, 1], equal to 1.0 at the interval midpoint.
    """
    # 1. width floor: widen the interval symmetrically OUTWARD
    w0 = b_u - b_l
    w = max(min_width, w0)
    b_l = b_l - (w - w0) / 2.0
    b_u = b_u + (w - w0) / 2.0

    # 2. discrimination grows as the interval narrows
    a = np.exp(np.clip(rho / w, -MAX_EXP, MAX_EXP)) - 1.0
    k1 = k1 + a
    k2 = k2 + a

    # 3. normalise the peak to 1.0
    if np.isclose(k1, k2):
        A = (1.0 + np.exp(np.clip(-k1 * (b_u - b_l) / 2.0, -MAX_EXP, MAX_EXP))) ** 2
    else:
        A = _numeric_peak_normaliser(b_l, b_u, k1, k2)
    if not np.isfinite(A):
        A = np.finfo(float).max / 10.0

    # 4. numerically stable product
    return A * expit(k1 * (x - b_l)) * expit(-k2 * (x - b_u))
