"""Propensity profiles.

A profile is the vector of theta across dimensions for one subject. The table produced here
*is* the profile set; one subject's profile is a filter on it.
"""

import logging

import numpy as np
import pandas as pd

from .io import join_annotations_outcomes
from .mle import fit_diagnostics, fit_theta

logger = logging.getLogger(__name__)

# The profile table's columns, in order, then the diagnostics surfaced on every fit.
PROFILE_COLUMNS = ["subject_id", "dimension", "n_items", "theta", "se", "ci95_lower",
                   "ci95_upper", "converged", "reference_ll", "gof", "pseudo_r2"]
DIAGNOSTIC_COLUMNS = ["skip_reason", "frac_orthogonal", "n_distinct_intervals", "outcome_rate",
                      "n_attempts", "n_converged", "restart_theta_std", "warnings"]


def fit_profiles(annotations, outcomes, *, subjects=None, dimensions=None, min_items=30,
                 **fit_kwargs) -> pd.DataFrame:
    """Fits theta for every (subject, dimension) pair and returns one row each.

    annotations: tidy question_id · dimension · lower · upper (parse_ok honoured if present).
    outcomes: tidy question_id · subject_id · outcome.
    subjects: defaults to every subject in `outcomes`; dimensions to every one in `annotations`.
    min_items: cells with fewer joined instances are recorded but not fitted.
    fit_kwargs: passed to fit_theta, e.g. k, robust, likelihood, restart_range.

    A cell that cannot be fitted keeps its row, with theta = NaN and a `skip_reason`, because a
    silently absent row reads as an analysis nobody ran. A failure in one cell never stops the
    sweep. The join report is attached as `profiles.attrs["join_report"]`.
    """
    joined, report = join_annotations_outcomes(annotations, outcomes)
    if subjects is None:
        subjects = sorted(set(outcomes["subject_id"].astype(str)))
    if dimensions is None:
        dimensions = sorted(set(annotations["dimension"].astype(str)))

    cells = dict(tuple(joined.groupby(["subject_id", "dimension"]))) if len(joined) else {}
    rows = [_fit_cell(cells.get((subject, dimension)), subject, dimension, min_items, fit_kwargs)
            for subject in subjects for dimension in dimensions]

    profiles = pd.DataFrame(rows, columns=PROFILE_COLUMNS + DIAGNOSTIC_COLUMNS)
    profiles = profiles.astype({"n_items": "int64", "converged": "Int64",
                                "n_attempts": "Int64", "n_converged": "Int64"})
    profiles.attrs["join_report"] = report
    return profiles


def profile_vector(profiles, subject_id) -> dict:
    """{dimension: theta} for one subject, ready for a radar or parallel-coordinate plot."""
    rows = profiles[profiles["subject_id"] == subject_id]
    if rows.empty:
        raise KeyError(f"no rows for subject {subject_id!r}")
    return {str(d): float(t) for d, t in zip(rows["dimension"], rows["theta"])}


def _fit_cell(cell, subject, dimension, min_items, fit_kwargs):
    row = dict.fromkeys(PROFILE_COLUMNS + DIAGNOSTIC_COLUMNS)
    row.update(subject_id=subject, dimension=dimension, n_items=0, theta=np.nan, warnings="")
    if cell is None or cell.empty:
        row["skip_reason"] = "no instances after the join"
        return row

    demands = cell[["lower", "upper"]].to_numpy()
    success = cell["outcome"].to_numpy()
    diagnostics = fit_diagnostics(demands, success)
    row.update(n_items=diagnostics["n_items"], frac_orthogonal=diagnostics["frac_orthogonal"],
               n_distinct_intervals=diagnostics["n_distinct_intervals"],
               outcome_rate=diagnostics["outcome_rate"],
               warnings="; ".join(diagnostics["warnings"]))

    if diagnostics["n_items"] < min_items:
        row["skip_reason"] = (f"only {diagnostics['n_items']} joined instances, "
                              f"below min_items={min_items}")
        return row
    if diagnostics["refuse"]:
        row["skip_reason"] = (f"{diagnostics['frac_orthogonal']:.0%} of instances are [-3, +3]; "
                              "theta is not identified")
        return row

    try:
        fit = fit_theta(demands, success, **fit_kwargs)
    except Exception as exc:  # one bad cell must not abort the sweep
        logger.warning("fit failed for %s / %s: %s", subject, dimension, exc)
        row["skip_reason"] = f"fit failed: {type(exc).__name__}: {exc}"
        return row

    row.update(theta=fit["theta_hat"], se=fit["se"], ci95_lower=fit["ci95_lower"],
               ci95_upper=fit["ci95_upper"], converged=int(fit["convergence"]),
               reference_ll=fit["reference_ll"], gof=fit["gof"], pseudo_r2=fit["pseudo_r2"],
               n_attempts=fit.get("n_attempts"), n_converged=fit.get("n_converged"),
               restart_theta_std=fit.get("restart_theta_std"))
    # A non-converged fit with a tight interval misleads: say so in the same row.
    row["warnings"] = "; ".join(fit_diagnostics(demands, success, fit=fit)["warnings"])
    return row
