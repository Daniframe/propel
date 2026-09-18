import warnings

import numpy as np
import pytest

from propensity import (
    build_empirical_curve,
    build_empirical_surface,
    build_interval_distribution,
    build_interval_tree,
    build_model_surface,
    two_sided_sigma,
)


def simulate(theta, n_items=400, seed=0):
    rng = np.random.default_rng(seed)
    lower = rng.integers(-3, 4, n_items)
    upper = np.array([rng.integers(lo, 4) for lo in lower])
    demands = np.column_stack([lower, upper]).astype(float)
    p = np.clip([two_sided_sigma(theta, lo, hi) for lo, hi in demands], 0.0, 1.0)
    return demands, rng.binomial(1, p)


# --- curve ------------------------------------------------------------------------------

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


# --- surface ----------------------------------------------------------------------------

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


# --- how a bank's intervals spread -------------------------------------------------------

BANK = np.array([[-1, 2], [-1, 2], [0, 0], [-3, 3], [2, 3]], dtype=float)


def test_the_interval_distribution_counts_each_interval_in_the_surface_orientation():
    distribution = build_interval_distribution(BANK)
    counts, shares = distribution["counts"], distribution["proportions"]

    assert (counts.index.name, counts.columns.name) == ("b_u", "b_l")
    assert counts.shape == (7, 7) and distribution["n_items"] == 5
    assert (counts.loc[2, -1], counts.loc[0, 0], counts.loc[3, -3], counts.loc[3, 2]) == (2, 1, 1, 1)
    assert counts.to_numpy().sum() == 5
    assert shares.loc[2, -1] == pytest.approx(0.4) and shares.to_numpy().sum() == pytest.approx(1)


def test_the_tree_places_each_interval_by_centre_and_length():
    tree = build_interval_tree(BANK)
    counts = tree["counts"]

    assert (counts.index.name, counts.columns.name) == ("length", "centre")
    assert list(tree["lengths"]) == list(range(7))
    assert list(tree["centres"]) == [c / 2 for c in range(-6, 7)]
    assert (counts.loc[3, 0.5], counts.loc[0, 0.0], counts.loc[6, 0.0], counts.loc[1, 2.5]) == (2, 1, 1, 1)
    assert counts.to_numpy().sum() == 5 and tree["proportions"].to_numpy().sum() == pytest.approx(1)


def test_the_tree_s_reachable_cells_are_exactly_the_valid_integer_intervals():
    reachable = build_interval_tree(BANK)["reachable"]
    assert reachable.to_numpy().sum() == 28  # the valid (b_l, b_u) pairs on a 7-level grid
    assert reachable.loc[0].sum() == 7 and reachable.loc[0, -3.0]  # the base: every level, zero length
    assert reachable.loc[6].sum() == 1 and reachable.loc[6, 0.0]  # the tip: [-3, +3] only
    assert not reachable.loc[1, 0.0]         # odd length, whole centre: no integer bounds
    assert reachable.loc[1, 0.5] and not reachable.loc[2, 2.5]  # [2.5 - 1, 2.5 + 1] leaves the grid
    counts = build_interval_tree(BANK)["counts"].to_numpy()
    assert counts[~reachable.to_numpy()].sum() == 0


def test_the_two_views_of_a_bank_agree():
    rng = np.random.default_rng(4)
    lower = rng.integers(-3, 4, 300)
    bank = np.column_stack([lower, [rng.integers(lo, 4) for lo in lower]]).astype(float)
    distribution, tree = build_interval_distribution(bank), build_interval_tree(bank)
    for b_u in range(-3, 4):
        for b_l in range(-3, b_u + 1):
            assert distribution["counts"].loc[b_u, b_l] == tree["counts"].loc[b_u - b_l, (b_l + b_u) / 2]


def test_an_empty_bank_has_empty_views_and_no_division_by_zero():
    empty = np.empty((0, 2))
    assert build_interval_distribution(empty)["proportions"].to_numpy().sum() == 0
    assert build_interval_tree(empty)["n_items"] == 0


@pytest.mark.parametrize("build", [build_interval_distribution, build_interval_tree])
def test_bank_views_reject_what_the_surface_rejects(build):
    with pytest.raises(ValueError, match="integer grid"):
        build(np.array([[0.0, 1.5]]))
    with pytest.raises(ValueError, match=r"within \[-3, 3\]"):
        build(np.array([[-4.0, 1.0]]))


# --- the surface the model predicts ------------------------------------------------------

def test_the_model_surface_is_eq5_on_every_valid_interval():
    surface = build_model_surface(0.7, smooth=True, resolution=0.5, k=1.3)
    prob = surface["prob"]
    assert list(surface["grid"]) == [v / 2 for v in range(-6, 7)] and surface["theta"] == 0.7
    for b_u in prob.index:
        for b_l in prob.columns:
            if b_l <= b_u:
                assert prob.loc[b_u, b_l] == pytest.approx(two_sided_sigma(0.7, b_l, b_u, 1.3, 1.3))
            else:
                assert np.isnan(prob.loc[b_u, b_l])


def test_smooth_chooses_between_the_integer_grid_and_a_continuous_one():
    discrete, continuous = build_model_surface(0.3), build_model_surface(0.3, smooth=True)
    assert discrete["smooth"] is False and list(discrete["grid"]) == list(range(-3, 4))
    assert continuous["smooth"] is True and len(continuous["grid"]) == 121  # every 0.05
    assert continuous["grid"][0] == -3 and continuous["grid"][-1] == 3
    shared = discrete["prob"].loc[2, -1]
    assert continuous["prob"].loc[2.0, -1.0] == pytest.approx(shared)  # same model, same point


def test_the_model_surface_peaks_on_intervals_centred_on_theta():
    prob = build_model_surface(1.0)["prob"]
    assert list(prob.index) == list(range(-3, 4))
    for b_l, b_u in [(1, 1), (0, 2), (-1, 3)]:
        assert prob.loc[b_u, b_l] == pytest.approx(1.0)
    assert prob.loc[0, -3] < 0.5 and prob.loc[3, 2] < 0.5  # intervals that exclude theta fail
