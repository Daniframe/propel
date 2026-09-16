import numpy as np
import pytest
from scipy.optimize import minimize

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
def test_t6_degenerate_outcomes_do_not_raise_and_spend_no_retries(outcome):
    demands, _ = simulate(0.0, n_items=200, seed=3)
    success = np.full(len(demands), outcome)

    fit = fit_theta(demands, success)

    assert fit["n_attempts"] == 1
    assert fit["theta_hat"] == fit_theta(demands, success, robust=False)["theta_hat"]
    # "Honestly": exactly what the optimiser said about the one attempt that was made.
    x0 = _lowess_start(demands, success.astype(float), 20, 0.4)
    first = minimize(lambda t: neg_log_likelihood(t, demands, success), x0=x0, method="BFGS",
                     options={"maxiter": 500})
    assert fit["convergence"] == float(first.success)


def test_fit_reports_every_documented_field():
    demands, success = simulate(0.5, seed=2)
    fit = fit_theta(demands, success)
    assert set(fit) == {"theta_hat", "se", "ci95_lower", "ci95_upper", "convergence",
                        "reference_ll", "gof", "pseudo_r2",
                        "n_attempts", "n_converged", "restart_theta_std"}
    assert fit["ci95_lower"] < fit["theta_hat"] < fit["ci95_upper"]
    assert fit["se"] > 0
    assert fit["gof"] >= fit["reference_ll"]
    assert fit["pseudo_r2"] == pytest.approx(1 - fit["gof"] / fit["reference_ll"])


def test_robust_false_omits_restart_fields():
    demands, success = simulate(0.5, seed=2)
    assert "n_attempts" not in fit_theta(demands, success, robust=False)


def test_explicit_x_init_skips_lowess(monkeypatch):
    monkeypatch.setattr(mle, "_lowess_start", lambda *a: pytest.fail("LOWESS should not run"))
    demands, success = simulate(0.5, seed=2)
    fit_theta(demands, success, x_init=0.3)


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


# --- guarded restarts (§9.4) -------------------------------------------------------------

def test_no_retries_when_the_first_attempt_converges():
    demands, success = simulate(0.5, seed=2)
    single = fit_theta(demands, success, robust=False)
    assert single["convergence"] == 1.0
    fit = fit_theta(demands, success)
    assert fit["n_attempts"] == 1
    assert fit["theta_hat"] == single["theta_hat"]


def test_retries_happen_only_after_a_failed_first_attempt():
    demands, success = simulate_near_ceiling(seed=7)
    single = fit_theta(demands, success, robust=False)
    fit = fit_theta(demands, success)
    if single["convergence"] == 1.0:
        assert fit["n_attempts"] == 1
    else:
        assert fit["n_attempts"] > 1


@pytest.mark.parametrize("seed", [7, 11, 13])
def test_robust_is_never_worse_than_a_single_start(seed):
    demands, success = simulate_near_ceiling(seed=seed)
    single = fit_theta(demands, success, robust=False)
    fit = fit_theta(demands, success)
    assert fit["gof"] >= single["gof"] - 1e-9
    assert fit["n_converged"] <= fit["n_attempts"]
    assert fit["restart_theta_std"] >= 0.0


def _cripple_first_attempt(monkeypatch):
    """Makes the unbounded BFGS attempt stop after one iteration, so it never converges,
    while leaving the bounded restarts alone."""
    real = mle.minimize

    def crippled(fun, x0, method=None, options=None, **kwargs):
        if method == "BFGS":
            options = {**(options or {}), "maxiter": 1}
        return real(fun, x0, method=method, options=options, **kwargs)

    monkeypatch.setattr(mle, "minimize", crippled)


def test_a_qualifying_retry_replaces_an_unconverged_first_attempt(monkeypatch):
    demands, success = simulate(0.5, seed=4)
    _cripple_first_attempt(monkeypatch)
    first_only = fit_theta(demands, success, x_init=-2.5, robust=False)
    assert first_only["convergence"] == 0.0

    fit = fit_theta(demands, success, x_init=-2.5)

    assert fit["n_attempts"] > 1
    assert fit["convergence"] == 1.0
    assert fit["gof"] > first_only["gof"]
    assert np.isfinite(fit["se"]) and fit["se"] > 0  # L-BFGS-B's hess_inv was densified


def test_non_qualifying_retries_never_replace_the_first_attempt_and_patience_stops_them():
    demands, success = simulate(0.5, seed=4)
    # maxiter=1 also stops every restart short of convergence, so none qualifies.
    first_only = fit_theta(demands, success, x_init=-2.5, maxiter=1, robust=False)
    fit = fit_theta(demands, success, x_init=-2.5, maxiter=1, patience=3)
    assert fit["n_attempts"] == 1 + 3
    assert fit["theta_hat"] == first_only["theta_hat"]


def test_max_retries_caps_the_number_of_attempts():
    demands, success = simulate(0.5, seed=4)
    fit = fit_theta(demands, success, x_init=-2.5, maxiter=1, max_retries=5, patience=100)
    assert fit["n_attempts"] == 1 + 5


def test_restarts_stay_inside_a_custom_restart_range(monkeypatch):
    demands, success = simulate(0.5, seed=4)
    _cripple_first_attempt(monkeypatch)
    fit = fit_theta(demands, success, x_init=-2.5, restart_range=(-1.0, 1.0))
    assert -1.0 <= fit["theta_hat"] <= 1.0


def test_standard_error_densifies_a_bounded_optimiser_result():
    res = minimize(lambda x: (x[0] - 1.0) ** 2, x0=[0.0], method="L-BFGS-B", bounds=[(-5, 5)])
    assert hasattr(res.hess_inv, "todense")
    assert _standard_error(res.hess_inv) == pytest.approx(np.sqrt(0.5), rel=1e-2)


# --- diagnostics (§9.6) ------------------------------------------------------------------

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
