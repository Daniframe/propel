import numpy as np
import pytest
from scipy.optimize import minimize

from propensity.errors import PropensityDeprecationWarning
from propensity.modelling import mle
from propensity.modelling.mle import (
    _lowess_start,
    _standard_error,
    fit_diagnostics,
    fit_theta,
    neg_log_likelihood,
)
from propensity.modelling.model import two_sided_sigma


def simulate(theta, n_items=500, seed=0):
    """Integer demand intervals in [-3, 3], as annotators produce them, with outcomes drawn
    from Eq. 5 at the given theta."""
    rng = np.random.default_rng(seed)
    lower = rng.integers(-3, 4, n_items)
    upper = np.array([rng.integers(lo, 4) for lo in lower])
    demands = np.column_stack([lower, upper]).astype(float)
    # The peak can exceed 1.0 by an ulp, which rng.binomial rejects.
    p = np.clip([two_sided_sigma(theta, lo, hi) for lo, hi in demands], 0.0, 1.0)
    return demands, rng.binomial(1, p)


def simulate_near_ceiling(n_items=300, seed=0, n_failures=15):
    """Almost every item succeeds regardless of its interval, as in the unstable Ul fits:
    the likelihood is nearly flat and a single BFGS run can stop anywhere."""
    rng = np.random.default_rng(seed)
    centres = rng.uniform(-3, 3, n_items)
    half_widths = rng.uniform(0.5, 1.5, n_items)
    demands = np.column_stack([centres - half_widths, centres + half_widths])
    success = np.ones(n_items, dtype=int)
    success[rng.choice(n_items, size=n_failures, replace=False)] = 0
    return demands, success


# --- likelihood --------------------------------------------------------------------------

def test_t4_likelihood_is_finite_at_the_clip_floor_for_1000_items():
    demands = np.tile([[2.0, 2.0]], (1000, 1))  # narrow intervals far from theta: p ~ 0
    success = np.ones(1000)
    nll = neg_log_likelihood(-3.0, demands, success)
    assert np.isfinite(nll)
    assert nll == pytest.approx(-1000 * np.log(1e-10))
    # The product form underflows here, which is why it is not the default.
    assert np.isinf(neg_log_likelihood(-3.0, demands, success, likelihood="product"))


def test_neg_log_likelihood_matches_hand_computation():
    demands = np.array([[-1.0, 1.0], [0.0, 2.0]])
    p0 = two_sided_sigma(0.3, -1.0, 1.0)
    p1 = two_sided_sigma(0.3, 0.0, 2.0)
    assert neg_log_likelihood(0.3, demands, [1, 0]) == pytest.approx(-np.log(p0 * (1 - p1)), rel=1e-12)


def test_sum_and_product_forms_agree_when_the_product_does_not_underflow():
    demands, success = simulate(0.5, n_items=40, seed=5)
    for theta in (-1.0, 0.0, 0.7):
        assert neg_log_likelihood(theta, demands, success) == pytest.approx(
            neg_log_likelihood(theta, demands, success, likelihood="product"), rel=1e-9)


def test_min_width_and_rho_reach_the_model():
    demands = np.array([[0.0, 0.0], [-1.0, 2.0]])
    success = np.array([1, 0])
    p = [two_sided_sigma(0.02, lo, hi, 1.0, 1.0, min_width=0.5, rho=1.0) for lo, hi in demands]
    expected = -(np.log(p[0]) + np.log(1 - p[1]))
    assert neg_log_likelihood(0.02, demands, success, min_width=0.5, rho=1.0) == pytest.approx(expected)


def test_unknown_likelihood_form_is_rejected():
    with pytest.raises(ValueError, match="likelihood"):
        neg_log_likelihood(0.0, [[0, 1]], [1], likelihood="mean")


# --- fit ---------------------------------------------------------------------------------

@pytest.mark.parametrize("theta_true", [-2.0, -0.5, 0.0, 1.5])
def test_t5_recovers_a_known_theta(theta_true):
    demands, success = simulate(theta_true, n_items=500, seed=0)
    fit = fit_theta(demands, success)
    assert abs(fit["theta_hat"] - theta_true) < 0.25


@pytest.mark.parametrize("outcome", [0, 1])
def test_t6_degenerate_outcomes_do_not_raise_and_are_reported_as_unidentified(outcome):
    demands, _ = simulate(0.0, n_items=200, seed=3)
    success = np.full(len(demands), outcome)

    fit = fit_theta(demands, success)

    assert np.isfinite(fit["theta_hat"])          # it returns something rather than raising
    assert fit["identified"] == 0.0               # but says the data cannot locate theta
    assert fit["convergence"] == 0.0
    assert fit_diagnostics(demands, success)["refuse"]


def test_fit_reports_every_documented_field():
    demands, success = simulate(0.5, seed=2)
    fit = fit_theta(demands, success)
    assert set(fit) == {"theta_hat", "se", "ci95_lower", "ci95_upper", "convergence",
                        "reference_ll", "gof", "pseudo_r2", "identified", "n_local_maxima",
                        "n_grid_points"}
    assert fit["ci95_lower"] < fit["theta_hat"] < fit["ci95_upper"]
    assert fit["se"] > 0
    assert fit["gof"] >= fit["reference_ll"]
    assert fit["pseudo_r2"] == pytest.approx(1 - fit["gof"] / fit["reference_ll"])


def test_the_legacy_optimiser_arguments_are_accepted_and_announced():
    demands, success = simulate(0.5, seed=2)
    with pytest.warns(PropensityDeprecationWarning, match="searches the whole grid"):
        fit = fit_theta(demands, success, x_init=-2.5, robust=False, restart_range=(-4.0, 4.0))
    assert fit["theta_hat"] == fit_theta(demands, success)["theta_hat"]   # and change nothing


def test_an_unknown_keyword_is_still_a_TypeError():
    demands, success = simulate(0.5, seed=2)
    with pytest.raises(TypeError, match="unexpected keyword"):
        fit_theta(demands, success, not_an_argument=1)


def test_product_likelihood_gives_the_same_theta_on_small_banks():
    demands, success = simulate(-1.0, n_items=60, seed=8)
    a = fit_theta(demands, success)
    b = fit_theta(demands, success, likelihood="product")
    # The objectives agree to ~1e-9; the thetas only to the optimiser's own tolerance.
    assert b["theta_hat"] == pytest.approx(a["theta_hat"], abs=1e-3)


def test_identical_intervals_do_not_break_the_starting_point():
    demands = np.tile([[0.0, 1.0]], (60, 1))
    success = np.random.default_rng(1).binomial(1, 0.7, 60)
    fit = fit_theta(demands, success)
    assert np.isfinite(fit["theta_hat"])


@pytest.mark.parametrize("demands,success,match", [
    ([[0, 1], [1, 2]], [1, 0.5], "only 0 and 1"),
    ([[0, 1], [1, 2]], [1], "shape"),
    ([0, 1, 2], [1, 0, 1], "shape"),
    ([[0, np.nan]], [1], "NaN"),
    (np.empty((0, 2)), [], "no items"),
])
def test_bad_inputs_are_rejected(demands, success, match):
    with pytest.raises(ValueError, match=match):
        fit_theta(demands, success)


# --- global search and profile intervals ---------------------------------------------------

def test_the_fit_finds_the_best_point_on_a_dense_grid():
    """No point anywhere on the scale may fit better than the one reported."""
    demands, success = simulate(-1.5, n_items=300, seed=5)
    fit = fit_theta(demands, success)
    grid = np.linspace(-8, 8, 4001)
    best = min(neg_log_likelihood(t, demands, success) for t in grid)
    assert -fit["gof"] <= best + 1e-6


def test_a_gradient_method_started_at_the_plateau_is_beaten_by_the_global_search():
    """The reviewer's C1: every interval contains 0, so near 0 the model predicts p = 1 on
    every item, each failure is pinned at the clip, the gradient vanishes, and BFGS stops."""
    demands = np.tile([[-3.0, 3.0]], (200, 1))
    demands[:40] = [-1.0, 1.0]
    success = np.zeros(len(demands))
    success[:150] = 1

    stuck = minimize(lambda t: neg_log_likelihood(t, demands, success), x0=0.0, method="BFGS")
    fit = fit_theta(demands, success)

    assert stuck.success                      # it reports convergence
    assert -fit["gof"] < stuck.fun - 1.0      # on a point the global search beats by nats


def test_the_profile_interval_is_where_the_likelihood_falls_by_the_chi_square_cutoff():
    demands, success = simulate(0.8, n_items=400, seed=6)
    fit = fit_theta(demands, success)
    cutoff = -fit["gof"] + mle.CHI2_95_HALF
    for end in (fit["ci95_lower"], fit["ci95_upper"]):
        assert neg_log_likelihood(end, demands, success) == pytest.approx(cutoff, abs=1e-4)
    inside = (fit["ci95_lower"] + fit["ci95_upper"]) / 2
    assert neg_log_likelihood(inside, demands, success) < cutoff


def test_an_unbounded_side_is_infinite_rather_than_a_number():
    """A bank that cannot bound theta must not report a tight interval around it. With every
    item failed, the likelihood improves the further out theta goes: there is no upper end."""
    demands = np.tile([[-3.0, 3.0]], (120, 1))
    success = np.zeros(len(demands))
    fit = fit_theta(demands, success)
    assert np.isinf(fit["ci95_lower"]) or np.isinf(fit["ci95_upper"])
    assert np.isnan(fit["se"])
    assert fit["identified"] == 0.0


def test_the_standard_error_is_the_interval_half_width():
    demands, success = simulate(-0.4, n_items=250, seed=7)
    fit = fit_theta(demands, success)
    assert fit["se"] == pytest.approx((fit["ci95_upper"] - fit["ci95_lower"]) / (2 * 1.96))


def test_local_maxima_are_counted():
    demands, success = simulate(0.5, n_items=200, seed=2)
    assert fit_theta(demands, success)["n_local_maxima"] >= 1


def test_a_finer_grid_does_not_move_the_estimate():
    demands, success = simulate(1.2, n_items=300, seed=9)
    coarse = fit_theta(demands, success, grid_points=801)
    fine = fit_theta(demands, success, grid_points=6401)
    assert coarse["theta_hat"] == pytest.approx(fine["theta_hat"], abs=1e-3)


# --- diagnostics --------------------------------------------------------------------------

def test_diagnostics_on_a_healthy_bank_have_no_warnings():
    demands, success = simulate(0.5, seed=2)
    diag = fit_diagnostics(demands, success, fit=fit_theta(demands, success))
    assert diag["n_items"] == 500
    assert diag["n_distinct_intervals"] > 5
    assert not diag["refuse"]
    assert diag["warnings"] == []


def test_diagnostics_flag_orthogonal_banks_and_refuse_above_90_percent():
    informative = np.array([[0, 0], [-1, 1], [1, 2], [-2, 0], [0, 3]] * 12, dtype=float)
    success = np.tile([1, 0], 30)
    mostly_orthogonal = np.vstack([np.tile([[-3.0, 3.0]], (40, 1)), informative[:20]])
    diag = fit_diagnostics(mostly_orthogonal, success)
    assert diag["frac_orthogonal"] == pytest.approx(40 / 60)
    assert not diag["refuse"]
    assert any("carry no information" in w for w in diag["warnings"])

    nearly_all = np.vstack([np.tile([[-3.0, 3.0]], (57, 1)), informative[:3]])
    diag = fit_diagnostics(nearly_all, success)
    assert diag["refuse"]
    assert any("not identified" in w for w in diag["warnings"])


def test_diagnostics_flag_small_banks_few_intervals_skewed_outcomes_and_non_convergence():
    demands = np.tile([[0.0, 1.0], [-1.0, 2.0]], (15, 1))
    success = np.ones(30)
    success[0] = 0  # 29/30 successes, above the 0.95 cut-off
    diag = fit_diagnostics(demands, success, fit={"convergence": 0.0})
    text = " | ".join(diag["warnings"])
    assert "only 30 items" in text
    assert "only 2 distinct intervals" in text
    assert "near-degenerate" in text
    assert "did not converge" in text
