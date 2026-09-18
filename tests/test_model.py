import warnings

import numpy as np
import pytest

from propensity.modelling.model import _numeric_peak_normaliser, two_sided_sigma

T1_INTERVALS = [(-3, 3), (-2, 2), (0, 1), (-1, -1), (2, 2)]


def _raw_exp_formula(x, b_l, b_u, k1, k2, min_width=0.1, rho=2.0):
    """The pre-fix return statement (raw exp, no expit), with the corrected outward widening,
    so the comparison isolates the change to a numerically stable expit product."""
    w0 = b_u - b_l
    w = max(min_width, w0)
    b_l, b_u = b_l - (w - w0) / 2, b_u + (w - w0) / 2
    a = np.exp(np.clip(rho / w, -700, 700)) - 1
    k1, k2 = k1 + a, k2 + a
    if np.isclose(k1, k2):
        A = (1 + np.exp(np.clip(-k1 * (b_u - b_l) / 2, -700, 700))) ** 2
    else:
        A = _numeric_peak_normaliser(b_l, b_u, k1, k2)
    return A / ((1 + np.exp(-k1 * (x - b_l))) * (1 + np.exp(k2 * (x - b_u))))


@pytest.mark.parametrize("k", [0.5, 1.0, 3.0])
@pytest.mark.parametrize("b_l,b_u", T1_INTERVALS)
def test_t1_peak_is_one_at_the_midpoint(b_l, b_u, k):
    assert two_sided_sigma((b_l + b_u) / 2, b_l, b_u, k, k) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("b_l,b_u", T1_INTERVALS + [(-3, 0), (1, 3), (-2.5, 0.5)])
def test_t2_bell_shape_is_finite_bounded_and_falls_away_from_the_midpoint(b_l, b_u):
    mid = (b_l + b_u) / 2
    x = np.linspace(-10, 10, 4001)
    p = two_sided_sigma(x, b_l, b_u)

    assert np.all(np.isfinite(p))
    assert np.all(p >= 0.0) and np.all(p <= 1.0 + 1e-12)
    right = p[x >= mid]
    left = p[x <= mid][::-1]
    assert np.all(np.diff(right) <= 1e-12)
    assert np.all(np.diff(left) <= 1e-12)
    assert right[-1] < right[0] and left[-1] < left[0]


@pytest.mark.parametrize("b", [-3, -1, 0, 2.5, 3])
def test_t3_zero_width_interval_is_finite_and_widened_outward(b):
    p = two_sided_sigma(np.linspace(-10, 10, 4001), b, b)
    assert np.all(np.isfinite(p))
    # Widened outward to [b - 0.05, b + 0.05]. The old inward bug gave width -0.1 and
    # success probability 0 even at the interval itself.
    assert two_sided_sigma(b - 0.04, b, b) > 0.5
    assert two_sided_sigma(b + 0.04, b, b) > 0.5
    assert two_sided_sigma(b + 0.2, b, b) < 0.5


@pytest.mark.parametrize("b_l,b_u,k1,k2,x", [
    (-1.0, 1.0, 1.0, 1.0, 0.0),
    (-1.0, 1.0, 1.0, 1.0, 0.7),
    (-3.0, 2.0, 0.8, 1.2, -5.0),
    (0.0, 5.0, 2.0, 2.0, 4.0),
])
def test_expit_form_matches_the_raw_exp_formula_on_ordinary_inputs(b_l, b_u, k1, k2, x):
    assert two_sided_sigma(x, b_l, b_u, k1, k2) == pytest.approx(
        _raw_exp_formula(x, b_l, b_u, k1, k2), rel=1e-9, abs=1e-12)


def test_expit_form_does_not_overflow_on_narrow_intervals():
    b_l, b_u, x = -0.05, 0.05, -1.0
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        p = two_sided_sigma(x, b_l, b_u)
    assert not [w for w in caught if issubclass(w.category, RuntimeWarning)]
    assert 0.0 <= p <= 1.0


def test_symmetric_slopes_give_a_symmetric_bell():
    b_l, b_u = -2.0, 3.0
    mid = (b_l + b_u) / 2
    for d in (0.1, 0.5, 1.5):
        assert two_sided_sigma(mid - d, b_l, b_u) == pytest.approx(two_sided_sigma(mid + d, b_l, b_u), rel=1e-9)


def test_asymmetric_slopes_are_still_normalised_to_peak_one():
    x = np.linspace(-6, 6, 60001)
    p = two_sided_sigma(x, -2.0, 1.0, 0.5, 2.0)
    assert p.max() == pytest.approx(1.0, abs=1e-6)


def test_array_input_matches_scalar_calls():
    x = np.array([-4.0, -1.0, 0.0, 0.5, 2.0])
    p = two_sided_sigma(x, -1.0, 2.0)
    assert p == pytest.approx([two_sided_sigma(v, -1.0, 2.0) for v in x], rel=1e-12)
