import numpy as np
import pandas as pd
import pytest

from propensity import DataWarning, fit_profiles, profile_vector, two_sided_sigma
from propensity.modelling import profiles as profiles_module
from propensity.modelling.profiles import DIAGNOSTIC_COLUMNS, PROFILE_COLUMNS


def make_data(thetas, n_items=200, seed=0):
    """Builds tidy annotations and outcomes for {(subject, dimension): theta}.

    Each dimension annotates its own instances, as a benchmark per dimension does, so a
    subject's outcome on an instance is driven by that dimension's demands.
    """
    rng = np.random.default_rng(seed)
    annotations, outcomes = [], []
    for dimension in sorted({d for _, d in thetas}):
        lower = rng.integers(-3, 4, n_items)
        upper = np.array([rng.integers(lo, 4) for lo in lower])
        for i, (lo, hi) in enumerate(zip(lower, upper)):
            annotations.append({"question_id": f"{dimension}_{i}", "dimension": dimension,
                                "lower": float(lo), "upper": float(hi), "parse_ok": True})
        for (subject, dim), theta in thetas.items():
            if dim != dimension:
                continue
            p = np.clip([two_sided_sigma(theta, lo, hi) for lo, hi in zip(lower, upper)], 0.0, 1.0)
            for i, outcome in enumerate(rng.binomial(1, p)):
                outcomes.append({"question_id": f"{dimension}_{i}", "subject_id": subject,
                                 "outcome": int(outcome)})
    return pd.DataFrame(annotations), pd.DataFrame(outcomes)


def test_a_profile_table_recovers_every_subject_and_dimension():
    thetas = {("model-a", "RA"): -1.5, ("model-a", "Ex"): 1.0,
              ("model-b", "RA"): 2.0, ("model-b", "Ex"): 0.0}
    annotations, outcomes = make_data(thetas, seed=1)

    table = fit_profiles(annotations, outcomes)

    assert list(table.columns) == PROFILE_COLUMNS + DIAGNOSTIC_COLUMNS
    assert len(table) == 4
    assert table["n_items"].tolist() == [200] * 4
    for (subject, dimension), theta in thetas.items():
        row = table[(table.subject_id == subject) & (table.dimension == dimension)].iloc[0]
        assert abs(row.theta - theta) < 0.25, f"{subject}/{dimension}"
        assert row.ci95_lower < row.theta < row.ci95_upper
        assert row.skip_reason is None
        assert np.isfinite(row.gof) and np.isfinite(row.reference_ll)


def test_a_fit_worse_than_the_unbiased_null_is_flagged():
    """Zero-width intervals leave the likelihood with a peak about 0.1 wide at each integer. A
    gradient method started outside it settles on a plateau and reports convergence, so the
    diagnostics have to say that the fit lost to theta = 0."""
    thetas = {("model-a", "RA"): -1.5, ("model-a", "Ex"): 1.0,
              ("model-b", "RA"): 2.0, ("model-b", "Ex"): 0.0}
    annotations, outcomes = make_data(thetas, seed=1)
    table = fit_profiles(annotations, outcomes)
    row = table[(table.subject_id == "model-b") & (table.dimension == "Ex")].iloc[0]

    assert row.converged == 1
    assert row.pseudo_r2 < 0
    assert row.gof < row.reference_ll
    assert "worse than theta = 0" in row.warnings


def test_the_join_report_rides_along():
    annotations, outcomes = make_data({("m", "RA"): 0.5})
    table = fit_profiles(annotations, outcomes)
    report = table.attrs["join_report"]
    assert report["per_dimension"]["RA"]["yield"] == 1.0
    assert report["n_unusable"] == 0


def test_cells_below_min_items_are_recorded_rather_than_dropped():
    annotations, outcomes = make_data({("m", "RA"): 0.0}, n_items=20)
    with pytest.warns(DataWarning, match="fewer than 50"):
        table = fit_profiles(annotations, outcomes, min_items=30)

    assert len(table) == 1
    row = table.iloc[0]
    assert np.isnan(row.theta)
    assert "below min_items=30" in row.skip_reason
    assert row.n_items == 20  # the diagnostics are still filled in
    assert row.outcome_rate > 0
    assert pd.isna(row.converged)


def test_an_orthogonal_bank_is_refused():
    annotations = pd.DataFrame({"question_id": [f"q{i}" for i in range(60)], "dimension": "RA",
                                "lower": -3.0, "upper": 3.0, "parse_ok": True})
    outcomes = pd.DataFrame({"question_id": [f"q{i}" for i in range(60)], "subject_id": "m",
                             "outcome": 1})
    table = fit_profiles(annotations, outcomes)

    row = table.iloc[0]
    assert np.isnan(row.theta)
    assert "not identified" in row.skip_reason
    assert row.frac_orthogonal == 1.0


def test_a_cell_with_no_joined_instances_still_has_a_row():
    annotations, outcomes = make_data({("m", "RA"): 0.0, ("m", "Ex"): 0.0})
    outcomes = outcomes[outcomes.question_id.str.startswith("RA")]  # nothing for Ex

    with pytest.warns(DataWarning, match="Ex: 0%"):
        table = fit_profiles(annotations, outcomes)

    assert set(table.dimension) == {"RA", "Ex"}
    empty = table[table.dimension == "Ex"].iloc[0]
    assert empty.n_items == 0 and np.isnan(empty.theta)
    assert empty.skip_reason == "no instances after the join"


def test_one_failing_cell_does_not_abort_the_sweep(monkeypatch):
    annotations, outcomes = make_data({("m", "RA"): 0.0, ("m", "Ex"): 1.0})
    real_fit = profiles_module.fit_theta
    calls = {"n": 0}

    def explode_on_the_first_cell(demands, success, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("optimiser exploded")
        return real_fit(demands, success, **kwargs)

    monkeypatch.setattr(profiles_module, "fit_theta", explode_on_the_first_cell)
    table = fit_profiles(annotations, outcomes)

    assert len(table) == 2 and calls["n"] == 2  # the sweep carried on
    failed = table[table.skip_reason.notna()]
    assert len(failed) == 1
    assert "fit failed: RuntimeError: optimiser exploded" in failed.iloc[0].skip_reason
    assert np.isfinite(table[table.skip_reason.isna()].iloc[0].theta)


def test_subject_and_dimension_filters():
    annotations, outcomes = make_data({("model-a", "RA"): 0.0, ("model-b", "RA"): 1.0,
                                       ("model-a", "Ex"): 0.0, ("model-b", "Ex"): 1.0})
    table = fit_profiles(annotations, outcomes, subjects=["model-b"], dimensions=["RA"])
    assert len(table) == 1
    assert table.iloc[0].subject_id == "model-b" and table.iloc[0].dimension == "RA"


def test_fit_arguments_reach_fit_theta():
    annotations, outcomes = make_data({("m", "RA"): 0.5}, n_items=60, seed=4)
    robust = fit_profiles(annotations, outcomes)
    single = fit_profiles(annotations, outcomes, robust=False, likelihood="product")

    assert robust.iloc[0].n_attempts >= 1
    assert pd.isna(single.iloc[0].n_attempts)  # robust=False reports no restart counters
    assert single.iloc[0].theta == pytest.approx(robust.iloc[0].theta, abs=0.05)


def test_non_convergence_is_reported_in_the_same_row_as_the_interval():
    annotations, outcomes = make_data({("m", "RA"): 0.0}, n_items=80, seed=5)
    table = fit_profiles(annotations, outcomes, maxiter=1, robust=False)
    row = table.iloc[0]
    assert row.converged == 0
    assert "did not converge" in row.warnings


def test_profile_vector_gives_one_subject_across_dimensions():
    thetas = {("m", "RA"): -1.5, ("m", "Ex"): 1.0}
    annotations, outcomes = make_data(thetas, seed=2)
    table = fit_profiles(annotations, outcomes)

    vector = profile_vector(table, "m")
    assert set(vector) == {"RA", "Ex"}
    assert vector["RA"] == pytest.approx(-1.5, abs=0.25)
    with pytest.raises(KeyError):
        profile_vector(table, "nobody")
