"""Maximum-likelihood fit of one subject's propensity level theta on one dimension:
Eq. 6 of arXiv 2602.18182.

The likelihood is searched on a grid and then refined locally, rather than by a gradient
method from a smoothed starting point. Two properties of this model make a gradient method
unsafe. Every annotated interval contains 0, so near theta = 0 the model predicts p = 1 on
every item; each failure is then pinned at log(P_CLIP) and the gradient vanishes, leaving a
plateau that BFGS reports as convergence. And the integer bounds and the e^(rho/w) slope term
give the surface several local maxima - a median of seven on real banks - so where a local
method lands is decided by where it started.

Uncertainty comes from the profile likelihood, for the same reason: an inverse-Hessian
standard error is the curvature of whatever point the optimiser stopped at, and on a plateau
BFGS returns the identity, which prints as se = 1.000 no matter what the data say.
"""

import warnings

import numpy as np
from scipy.optimize import brentq, minimize_scalar

from ..errors import PropensityDeprecationWarning
from .model import two_sided_sigma

P_CLIP = 1e-10
LIKELIHOODS = ("sum", "product")

# The search: 3,201 points over [-8, +8] is a step of 0.005, wide enough to show that a fit
# wants to run past the -3..+3 scale and fine enough that the local refine only polishes.
GRID_RANGE = (-8.0, 8.0)
GRID_POINTS = 3201
# Half of the 95% chi-square quantile on one degree of freedom: the profile-likelihood cutoff.
CHI2_95_HALF = 1.9207294123884402
_LEGACY = {"x_init": None, "n_bins": 20, "lowess_frac": 0.4, "maxiter": 500, "robust": True,
           "max_retries": 20, "patience": 2, "restart_range": (-5.0, 5.0)}

# Diagnostic thresholds: see fit_diagnostics
MIN_ITEMS_WARN = 50
ORTHOGONAL_WARN = 0.5
ORTHOGONAL_REFUSE = 0.9
MIN_DISTINCT_INTERVALS = 5
OUTCOME_RATE_RANGE = (0.05, 0.95)


def neg_log_likelihood(theta, demands, success, k=1.0, *, likelihood="sum", min_width=0.1, rho=2.0):
    """Eq. 6 negative log-likelihood of `theta`, given (N, 2) demand intervals and (N,)
    binary outcomes.

    likelihood="sum" is the stable form. "product" multiplies N probabilities before taking
    the log, which underflows to inf for N in the hundreds; it survives only to reproduce
    published numbers bit for bit.
    """
    theta = float(np.ravel(theta)[0])  # scipy passes a 1-element array
    success = np.asarray(success, dtype=float)
    p = np.array([two_sided_sigma(theta, b_l, b_u, k, k, min_width, rho) for b_l, b_u in demands])
    p = np.clip(p, P_CLIP, 1 - P_CLIP)
    if likelihood == "sum":
        return -np.sum(success * np.log(p) + (1 - success) * np.log(1 - p))
    if likelihood == "product":
        with np.errstate(divide="ignore"):
            return -np.log(np.prod(p**success * (1 - p) ** (1 - success)))
    raise ValueError(f"likelihood must be one of {LIKELIHOODS}, got {likelihood!r}")


def fit_theta(demands, success, *, k=1.0, grid_range=GRID_RANGE, grid_points=GRID_POINTS,
              refine=True, likelihood="sum", min_width=0.1, rho=2.0, **legacy) -> dict:
    """Fits theta by maximum likelihood (Eq. 6), by global search and a local refine.

    demands: (N, 2) array-like of (b_l, b_u). success: (N,) array-like of 0/1.
    grid_range, grid_points: the search. The grid is wider than the -3..+3 scale so that a fit
        wanting to leave it is visible rather than silently pinned to a boundary.
    refine: polish the grid maximum within one grid step, so the estimate is not quantised.

    Returns theta_hat; the profile-likelihood interval as ci95_lower / ci95_upper, with se as
    its half-width expressed as a standard error (NaN when an end is open); convergence, 1.0
    when the maximum is interior to the grid and both ends of the interval are closed;
    reference_ll (the log-likelihood of theta = 0, the unbiased agent), gof (at theta_hat) and
    pseudo_r2; identified, 0.0 when the data cannot locate theta at all; and n_local_maxima,
    how many maxima the grid found, which is how flat and multi-modal this surface is.

    The keyword arguments of the previous optimiser (x_init, robust, restart_range and the
    rest) are accepted and ignored: a global search needs no starting point and no restarts.
    """
    demands, success = _as_arrays(demands, success)
    if likelihood not in LIKELIHOODS:
        raise ValueError(f"likelihood must be one of {LIKELIHOODS}, got {likelihood!r}")
    _warn_about_legacy(legacy)

    def objective(theta):
        return neg_log_likelihood(theta, demands, success, k, likelihood=likelihood,
                                  min_width=min_width, rho=rho)

    thetas = np.linspace(grid_range[0], grid_range[1], int(grid_points))
    curve = _nll_on_grid(demands, success, thetas, k, likelihood, min_width, rho)
    best = int(np.argmin(curve))
    theta_hat, nll_hat = float(thetas[best]), float(curve[best])

    step = float(thetas[1] - thetas[0])
    if refine and 0 < best < len(thetas) - 1:
        local = minimize_scalar(objective, bounds=(theta_hat - step, theta_hat + step),
                                method="bounded")
        if local.success and local.fun <= nll_hat:
            theta_hat, nll_hat = float(local.x), float(local.fun)

    lower, upper = _profile_interval(objective, thetas, curve, theta_hat, nll_hat)
    closed = np.isfinite(lower) and np.isfinite(upper)
    interior = grid_range[0] < theta_hat < grid_range[1]
    # Every outcome the same way leaves nothing for the likelihood to locate: it improves
    # monotonically towards whichever boundary the search can reach.
    degenerate = bool(np.all(success == success[0]))

    gof = -nll_hat
    reference_ll = -float(objective(0.0))
    return {
        "theta_hat": theta_hat,
        "se": float((upper - lower) / (2 * 1.96)) if closed else float("nan"),
        "ci95_lower": lower,
        "ci95_upper": upper,
        "convergence": float(closed and interior and not degenerate),
        "reference_ll": reference_ll,
        "gof": gof,
        "pseudo_r2": 1.0 - gof / reference_ll if reference_ll else float("nan"),
        "identified": float(not degenerate and closed),
        "n_local_maxima": _count_local_maxima(curve),
        "n_grid_points": len(thetas),
    }


def fit_diagnostics(demands, success, fit=None) -> dict:
    """The checks that catch unusable item banks. Pass the fit_theta result as `fit` to
    also flag a fit that did not converge. `refuse` is True when the bank is too orthogonal
    for theta to be identified at all.
    """
    demands, success = _as_arrays(demands, success)
    n_items = len(success)
    frac_orthogonal = float(np.mean((demands[:, 0] <= -3) & (demands[:, 1] >= 3)))
    n_distinct = int(np.unique(demands, axis=0).shape[0])
    outcome_rate = float(success.mean())

    # Every outcome identical is a column with nothing in it to fit. It is nearly always a
    # pipeline failure - an API error, a judge that returned nothing - rather than a subject
    # that genuinely never succeeded, and theta is not identified either way.
    degenerate = bool(np.all(success == success[0]))

    warnings = []
    if degenerate:
        warnings.append(f"every outcome is a {'success' if success[0] else 'failure'}; "
                        "theta is not identified")
    if n_items < MIN_ITEMS_WARN:
        warnings.append(f"only {n_items} items; the fit is unstable below {MIN_ITEMS_WARN}")
    if frac_orthogonal > ORTHOGONAL_REFUSE:
        warnings.append(f"{frac_orthogonal:.0%} of items are [-3, +3]; theta is not identified")
    elif frac_orthogonal > ORTHOGONAL_WARN:
        warnings.append(f"{frac_orthogonal:.0%} of items are [-3, +3] and carry no information")
    if n_distinct < MIN_DISTINCT_INTERVALS:
        warnings.append(f"only {n_distinct} distinct intervals")
    if not OUTCOME_RATE_RANGE[0] <= outcome_rate <= OUTCOME_RATE_RANGE[1]:
        warnings.append(f"success rate {outcome_rate:.1%} is near-degenerate")
    if fit is not None and not fit["convergence"]:
        warnings.append("fit did not converge; its confidence interval is not trustworthy")
    pseudo_r2 = (fit or {}).get("pseudo_r2")
    if pseudo_r2 is not None and np.isfinite(pseudo_r2) and pseudo_r2 < 0:
        # Zero-width intervals make the likelihood spiky, and a gradient method can settle on a
        # plateau outside the peak, reporting convergence all the same.
        warnings.append(f"fit explains the data worse than theta = 0 (pseudo_r2 = {pseudo_r2:.2f})")

    if degenerate:
        refuse_reason = (f"every outcome is a {'success' if success[0] else 'failure'}; "
                         "theta is not identified")
    elif frac_orthogonal > ORTHOGONAL_REFUSE:
        refuse_reason = f"{frac_orthogonal:.0%} of instances are [-3, +3]; theta is not identified"
    else:
        refuse_reason = None

    return {
        "n_items": n_items,
        "frac_orthogonal": frac_orthogonal,
        "n_distinct_intervals": n_distinct,
        "outcome_rate": outcome_rate,
        "degenerate_outcomes": degenerate,
        "refuse": refuse_reason is not None,
        "refuse_reason": refuse_reason,
        "warnings": warnings,
    }


def _nll_on_grid(demands, success, thetas, k, likelihood, min_width, rho):
    """The negative log-likelihood at every grid point.

    Items that share an interval share a probability, and annotated banks have few distinct
    intervals, so the work is one vectorised call per distinct interval rather than per item.
    The result equals neg_log_likelihood evaluated point by point.
    """
    intervals, inverse = np.unique(demands, axis=0, return_inverse=True)
    successes = np.bincount(inverse, weights=success, minlength=len(intervals))
    failures = np.bincount(inverse, weights=1 - success, minlength=len(intervals))

    total = np.zeros_like(thetas, dtype=float)
    for row, (b_l, b_u) in enumerate(intervals):
        p = np.clip(two_sided_sigma(thetas, b_l, b_u, k, k, min_width, rho), P_CLIP, 1 - P_CLIP)
        total -= successes[row] * np.log(p) + failures[row] * np.log(1 - p)
    if likelihood == "product":
        # The product form's only difference is that it overflows to inf; reproduce that.
        total = np.where(total > -np.log(np.finfo(float).tiny), np.inf, total)
    return total


def _profile_interval(objective, thetas, curve, theta_hat, nll_hat):
    """The 95% profile-likelihood interval: where the likelihood falls by the chi-square cutoff.

    An end that the grid never reaches is returned as -inf or +inf, which says what it means:
    the data do not bound theta on that side. It is not a number to put a +- in front of.
    """
    cutoff = nll_hat + CHI2_95_HALF
    bounds = []
    for side in (-1, 1):
        mask = (thetas > theta_hat) if side > 0 else (thetas < theta_hat)
        outside = np.flatnonzero(mask & (curve > cutoff))
        if outside.size == 0:
            bounds.append(side * np.inf)
            continue
        crossing = outside[0] if side > 0 else outside[-1]
        inner = max(theta_hat, thetas[crossing - 1]) if side > 0 else min(theta_hat, thetas[crossing + 1])
        try:
            bounds.append(float(brentq(lambda t: objective(t) - cutoff, inner, thetas[crossing])))
        except ValueError:  # the crossing is not bracketed after the local refine moved theta_hat
            bounds.append(float(thetas[crossing]))
    return bounds[0], bounds[1]


def _count_local_maxima(curve):
    """Local maxima of the likelihood, which are local minima of its negative."""
    interior = (curve[1:-1] < curve[:-2]) & (curve[1:-1] <= curve[2:])
    return int(np.count_nonzero(interior)) or 1


def _warn_about_legacy(passed):
    unknown = set(passed) - set(_LEGACY)
    if unknown:
        raise TypeError(f"fit_theta got unexpected keyword argument(s) {sorted(unknown)}")
    used = sorted(name for name, default in _LEGACY.items() if passed.get(name, default) != default)
    if used:
        warnings.warn(
            f"fit_theta ignores {', '.join(used)}: it searches the whole grid and refines "
            "locally, so there is no starting point to choose and no restart to spend. "
            "Set grid_range and grid_points instead.",
            PropensityDeprecationWarning, stacklevel=3)


def _as_arrays(demands, success):
    demands = np.asarray(demands, dtype=float)
    success = np.asarray(success, dtype=float)
    if demands.ndim != 2 or demands.shape[1] != 2:
        raise ValueError(f"demands must have shape (N, 2), got {demands.shape}")
    if success.shape != (demands.shape[0],):
        raise ValueError(f"success must have shape ({demands.shape[0]},), got {success.shape}")
    if len(success) == 0:
        raise ValueError("no items to fit")
    if not np.all(np.isfinite(demands)):
        raise ValueError("demands contain NaN or infinite bounds")
    if not np.all((success == 0) | (success == 1)):
        raise ValueError("success must contain only 0 and 1")
    return demands, success


def _lowess_start(demands, success, n_bins, lowess_frac):
    """The starting point: the argmax of the LOWESS-smoothed, binned success curve over
    interval centres."""
    curve = build_empirical_curve(demands, success, n_bins=n_bins, lowess_frac=lowess_frac)
    smoothed = curve["lowess_y"]
    if len(smoothed) < 2 or not np.all(np.isfinite(smoothed)):  # nothing to take an argmax of
        return float(np.median((demands[:, 0] + demands[:, 1]) / 2))
    return float(curve["lowess_x"][np.argmax(smoothed)])


def _standard_error(hess_inv):
    # BFGS gives a dense ndarray; L-BFGS-B (bounded restarts) a LinearOperator to densify.
    dense = hess_inv.todense() if hasattr(hess_inv, "todense") else hess_inv
    variance = float(np.diag(np.atleast_2d(np.asarray(dense)))[0])
    return float(np.sqrt(variance)) if variance >= 0 else float("nan")
