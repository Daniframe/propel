import warnings

import numpy as np
import pytest

from propensity import build_empirical_curve, build_empirical_surface, two_sided_sigma


def simulate(theta, n_items=400, seed=0):
    rng = np.random.default_rng(seed)
    lower = rng.integers(-3, 4, n_items)
    upper = np.array([rng.integers(lo, 4) for lo in lower])
    demands = np.column_stack([lower, upper]).astype(float)
    p = np.clip([two_sided_sigma(theta, lo, hi) for lo, hi in demands], 0.0, 1.0)
    return demands, rng.binomial(1, p)


# --- curve (§10.1) -----------------------------------------------------------------------

def test_curve_returns_bins_and_a_smooth_over_interval_centres():
    demands, success = simulate(0.5)
    curve = build_empirical_curve(demands, success, n_bins=20)

    assert set(curve) == {"bin_centers", "bin_means", "lowess_x", "lowess_y"}
    assert len(curve["bin_centers"]) == 20 and len(curve["bin_means"]) == 20
    assert len(curve["lowess_x"]) == len(curve["lowess_y"])
    assert np.all(np.diff(curve["lowess_x"]) >= 0)  # LOWESS returns x sorted
    assert np.all(np.isfinite(curve["lowess_y"]))
    observed = np.isfinite(curve["bin_means"])
    assert np.all(curve["bin_means"][observed] >= 0) and np.all(curve["bin_means"][observed] <= 1)


def test_empty_bins_are_nan_not_zero():
    # Two tight clusters of centres leave the bins between them empty.
    demands = np.array([[-3.0, -3.0]] * 20 + [[3.0, 3.0]] * 20)
    curve = build_empirical_curve(demands, np.ones(40), n_bins=10)
    assert np.isnan(curve["bin_means"][4])
    assert np.isfinite(curve["bin_means"][0]) and np.isfinite(curve["bin_means"][-1])


@pytest.mark.parametrize("theta", [-2.0, 0.0, 1.5])
def test_the_smoothed_curve_peaks_near_the_true_theta(theta):
    demands, success = simulate(theta, n_items=600, seed=3)
    curve = build_empirical_curve(demands, success)
    peak = curve["lowess_x"][np.argmax(curve["lowess_y"])]
    assert abs(peak - theta) < 0.6


def test_jitter_is_for_display_only_repeatable_and_non_destructive():
    demands, success = simulate(0.5)
    original = demands.copy()
    plain = build_empirical_curve(demands, success)
    jittered = build_empirical_curve(demands, success, jitter=0.25, seed=7)
    again = build_empirical_curve(demands, success, jitter=0.25, seed=7)

    assert np.array_equal(demands, original)  # the caller's array is untouched
    assert not np.allclose(plain["bin_centers"], jittered["bin_centers"])
    assert np.allclose(jittered["bin_centers"], again["bin_centers"])
    assert np.allclose(jittered["bin_means"], again["bin_means"], equal_nan=True)


def test_a_single_populated_bin_has_nothing_to_smooth_and_warns_about_nothing():
    demands = np.tile([[0.0, 1.0]], (5, 1))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        curve = build_empirical_curve(demands, np.array([1, 1, 0, 1, 1]))
    assert not [w for w in caught if issubclass(w.category, RuntimeWarning)]
    assert len(curve["lowess_x"]) == 1
    assert curve["lowess_y"][0] == pytest.approx(0.8)


# --- surface (§10.2) ---------------------------------------------------------------------

def test_surface_covers_the_whole_grid_in_the_plotted_orientation():
    demands, success = simulate(0.5)
    surface = build_empirical_surface(demands, success)

    assert set(surface) == {"prob", "counts", "grid"}
    assert list(surface["grid"]) == list(range(-3, 4))
    assert surface["prob"].shape == (7, 7) and surface["counts"].shape == (7, 7)
    assert surface["prob"].index.name == "b_u" and surface["prob"].columns.name == "b_l"
    assert list(surface["counts"].index) == list(range(-3, 4))


def test_counts_account_for_every_observation_and_prob_is_the_cell_mean():
    demands = np.array([[-1.0, 2.0], [-1.0, 2.0], [-1.0, 2.0], [0.0, 0.0]])
    success = np.array([1, 0, 1, 0])
    surface = build_empirical_surface(demands, success)

    assert surface["counts"].to_numpy().sum() == 4
    assert surface["counts"].loc[2, -1] == 3
    assert surface["prob"].loc[2, -1] == pytest.approx(2 / 3)
    assert surface["prob"].loc[0, 0] == 0.0


def test_the_three_cell_states_are_distinguishable():
    demands = np.array([[-1.0, 2.0], [0.0, 0.0]])
    surface = build_empirical_surface(demands, np.array([1, 0]))
    prob, counts, grid = surface["prob"], surface["counts"], surface["grid"]
    b_l = counts.columns.to_numpy()[None, :]
    b_u = counts.index.to_numpy()[:, None]

    observed = counts.to_numpy() > 0
    impossible = b_l > b_u
    unobserved = (b_l <= b_u) & ~observed

    assert observed.sum() == 2
    assert np.all(np.isfinite(prob.to_numpy()[observed]))
    assert np.all(np.isnan(prob.to_numpy()[unobserved]))
    assert np.all(np.isnan(prob.to_numpy()[impossible])) and np.all(counts.to_numpy()[impossible] == 0)
    assert observed.sum() + unobserved.sum() + impossible.sum() == len(grid) ** 2


def test_a_custom_range_sets_the_grid():
    surface = build_empirical_surface(np.array([[-1.0, 1.0]]), np.array([1]), r1=-2, r2=2)
    assert list(surface["grid"]) == [-2, -1, 0, 1, 2]
    assert surface["counts"].shape == (5, 5)


@pytest.mark.parametrize("demands,success,match", [
    ([[0.0, 1.5]], [1], "integer grid"),
    ([[-4.0, 1.0]], [1], r"within \[-3, 3\]"),
    ([[0.0, 4.0]], [1], r"within \[-3, 3\]"),
    ([[0.0, 1.0]], [1, 0], "shape"),
    ([0.0, 1.0], [1], "shape"),
    ([[0.0, np.nan]], [1], "NaN"),
])
def test_bad_surface_inputs_are_rejected(demands, success, match):
    with pytest.raises(ValueError, match=match):
        build_empirical_surface(np.asarray(demands, dtype=float), np.asarray(success))
