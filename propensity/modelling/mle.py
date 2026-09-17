"""Maximum-likelihood fit of one subject's propensity level theta on one dimension:
CLAUDE.md §9.2–9.4 and §9.6, Eq. 6 of arXiv 2602.18182.
"""

import numpy as np
from scipy.optimize import minimize

from .curves import build_empirical_curve
from .model import two_sided_sigma

P_CLIP = 1e-10
LIKELIHOODS = ("sum", "product")
_EDGE = 1e-6  # a restart this close to restart_range's bounds is hugging the boundary

# §9.6 thresholds
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
    published numbers bit for bit (CLAUDE.md §9.2).
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


def fit_theta(demands, success, *, k=1.0, x_init=None, n_bins=20, lowess_frac=0.4, maxiter=500,
              robust=True, max_retries=20, patience=2, restart_range=(-5.0, 5.0),
              likelihood="sum", min_width=0.1, rho=2.0) -> dict:
    """Fits theta by maximum likelihood (Eq. 6).

    demands: (N, 2) array-like of (b_l, b_u). success: (N,) array-like of 0/1.
    x_init: starting point; by default the argmax of the LOWESS-smoothed success curve over
        interval centres, because a cold start at 0 lands in the wrong optimum on skewed banks.
    robust: when the first (unbounded BFGS) attempt does not converge, try up to
        `max_retries` bounded restarts (§9.4). Never on all-0 or all-1 outcomes, which have no
        interior maximum to find.

    Returns theta_hat, se, ci95_lower, ci95_upper, convergence, reference_ll (log-likelihood
    of theta = 0, the unbiased agent), gof (log-likelihood at theta_hat) and pseudo_r2; with
    robust=True also n_attempts, n_converged and restart_theta_std.
    """
    demands, success = _as_arrays(demands, success)
    if likelihood not in LIKELIHOODS:
        raise ValueError(f"likelihood must be one of {LIKELIHOODS}, got {likelihood!r}")

    def objective(theta):
        return neg_log_likelihood(theta, demands, success, k, likelihood=likelihood,
                                  min_width=min_width, rho=rho)

    if x_init is None:
        x_init = _lowess_start(demands, success, n_bins, lowess_frac)

    first = minimize(objective, x0=x_init, method="BFGS", options={"maxiter": maxiter})
    attempts = [first]

    low, high = restart_range

    def qualifies(res):
        # Converged AND strictly inside the range: a flat likelihood can "converge" on the boundary.
        return bool(res.success) and low + _EDGE < res.x[0] < high - _EDGE

    degenerate = bool(np.all(success == success[0]))
    if robust and not first.success and not degenerate and max_retries > 0:
        # Spread starts outward from x_init, alternating sides: a left-to-right sweep can use up
        # `patience` on far, unhelpful points before reaching a good one near x_init.
        span = high - low
        offsets = np.linspace(span / max_retries, span, max_retries)
        starts = [float(np.clip(x_init + (off if i % 2 == 0 else -off), low, high))
                  for i, off in enumerate(offsets)]

        best_qualifying_nll = None
        stall = 0
        for start in starts:
            res = minimize(objective, x0=start, method="L-BFGS-B", bounds=[restart_range],
                           options={"maxiter": maxiter})
            attempts.append(res)
            if qualifies(res) and (best_qualifying_nll is None or res.fun < best_qualifying_nll - 1e-9):
                best_qualifying_nll = res.fun
                stall = 0
            else:
                stall += 1
            # Stop at the first trustworthy attempt: exploring further finds more distinct modes
            # on these near-flat surfaces, which moved results away from the published ones.
            if qualifies(res) or stall >= patience:
                break

    # A retry replaces the first attempt only if it qualifies AND fits better. Never average
    # across attempts: distinct optima on a flat surface are unrelated modes.
    best = first
    qualifying = [a for a in attempts[1:] if qualifies(a)]
    if qualifying:
        candidate = min(qualifying, key=lambda r: r.fun)
        if candidate.fun < first.fun:
            best = candidate

    theta_hat = float(best.x[0])
    se = _standard_error(best.hess_inv)
    gof = -float(best.fun)
    reference_ll = -float(objective(0.0))
    result = {
        "theta_hat": theta_hat,
        "se": se,
        "ci95_lower": theta_hat - 1.96 * se,
        "ci95_upper": theta_hat + 1.96 * se,
        "convergence": float(bool(best.success)),
        "reference_ll": reference_ll,
        "gof": gof,
        "pseudo_r2": 1.0 - gof / reference_ll,
    }
    if robust:
        result["n_attempts"] = len(attempts)
        result["n_converged"] = sum(bool(a.success) for a in attempts)
        result["restart_theta_std"] = float(np.std([a.x[0] for a in attempts]))
    return result


def fit_diagnostics(demands, success, fit=None) -> dict:
    """§9.6: the checks that catch unusable item banks. Pass the fit_theta result as `fit` to
    also flag a fit that did not converge. `refuse` is True when the bank is too orthogonal
    for theta to be identified at all.
    """
    demands, success = _as_arrays(demands, success)
    n_items = len(success)
    frac_orthogonal = float(np.mean((demands[:, 0] <= -3) & (demands[:, 1] >= 3)))
    n_distinct = int(np.unique(demands, axis=0).shape[0])
    outcome_rate = float(success.mean())

    warnings = []
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

    return {
        "n_items": n_items,
        "frac_orthogonal": frac_orthogonal,
        "n_distinct_intervals": n_distinct,
        "outcome_rate": outcome_rate,
        "refuse": frac_orthogonal > ORTHOGONAL_REFUSE,
        "warnings": warnings,
    }


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
    """§9.3 step 1: argmax of the LOWESS-smoothed, binned success curve over interval centres."""
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
