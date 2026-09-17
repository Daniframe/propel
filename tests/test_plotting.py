"""The optional renderers: CLAUDE.md §10. Figures are drawn off-screen and inspected, not eyeballed."""

import logging
import subprocess
import sys
import warnings

import numpy as np
import pandas as pd
import pytest

from propensity import (
    build_empirical_curve,
    build_empirical_surface,
    build_interval_distribution,
    build_interval_tree,
    build_model_surface,
    fit_profiles,
    plot_interval_distribution,
    plot_interval_tree,
    plot_interval_trees,
    plot_model_surface,
    plot_propensity_curve,
    plot_propensity_surface,
    save_annotation_plots,
    save_profile_plots,
    two_sided_sigma,
)
from propensity.modelling.plotting import _layout

PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def new_axes():
    """Axes on a bare Figure: no pyplot state, no window."""
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    from matplotlib.figure import Figure

    return lambda: Figure().subplots()


def simulate(theta, n_items=300, seed=0):
    rng = np.random.default_rng(seed)
    lower = rng.integers(-3, 4, n_items)
    upper = np.array([rng.integers(lo, 4) for lo in lower])
    demands = np.column_stack([lower, upper]).astype(float)
    p = np.clip([two_sided_sigma(theta, lo, hi) for lo, hi in demands], 0.0, 1.0)
    return demands, rng.binomial(1, p)


def legend_text(ax):
    return " ".join(text.get_text() for text in ax.get_legend().get_texts())


def vertical_lines(ax):
    """(x, linestyle) for every vertical line on the axes."""
    return sorted((line.get_xdata()[0], line.get_linestyle()) for line in ax.get_lines()
                  if len(set(line.get_xdata())) == 1 and len(line.get_xdata()) == 2)


# --- without matplotlib ------------------------------------------------------------------

def test_drawing_without_matplotlib_names_the_extra_that_installs_it():
    script = (
        "import sys\n"
        "class Blocker:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('matplotlib', 'seaborn'):\n"
        "            raise ImportError('blocked')\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "import numpy as np\n"
        "from propensity.modelling import build_empirical_curve, plot_propensity_curve\n"
        "curve = build_empirical_curve(np.array([[0.0, 1.0], [-1.0, 2.0]]), np.array([1, 0]))\n"
        "try:\n"
        "    plot_propensity_curve(curve)\n"
        "except ImportError as exc:\n"
        "    print(exc)\n"
    )
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert 'pip install "propel[plot]"' in done.stdout


# --- the curve (§10.1) -------------------------------------------------------------------

def test_the_curve_shows_the_bins_the_smooth_the_estimate_and_its_interval(new_axes):
    demands, success = simulate(0.5)
    curve = build_empirical_curve(demands, success, jitter=0.25, seed=0)
    ax = plot_propensity_curve(curve, theta=0.4, ci95=(0.2, 0.6), ax=new_axes())

    points, smooth = ax.get_lines()[:2]
    assert points.get_marker() == "o" and points.get_linestyle() == "None"
    np.testing.assert_array_equal(points.get_xdata(), curve["bin_centers"])
    np.testing.assert_array_equal(smooth.get_ydata(), curve["lowess_y"])
    assert vertical_lines(ax) == [(0.2, "--"), (0.4, "-"), (0.6, "--")]
    assert "0.40" in legend_text(ax) and "[0.20, 0.60]" in legend_text(ax)
    assert "did not converge" not in legend_text(ax)
    assert "Interval centre" in ax.get_xlabel() and ax.get_ylim() == (-0.05, 1.05)


def test_a_fit_that_did_not_converge_says_so_beside_its_interval(new_axes):
    demands, success = simulate(0.5)
    ax = plot_propensity_curve(build_empirical_curve(demands, success), theta=0.4,
                               ci95=(0.39, 0.41), converged=False, ax=new_axes())
    assert "did not converge" in legend_text(ax)


def test_an_unfitted_cell_is_drawn_without_an_estimate(new_axes):
    demands, success = simulate(0.5, n_items=12)
    ax = plot_propensity_curve(build_empirical_curve(demands, success), theta=np.nan,
                               ci95=(np.nan, np.nan), title="not fitted", ax=new_axes())
    assert vertical_lines(ax) == [] and len(ax.get_lines()) == 2
    assert ax.get_title() == "not fitted"


def test_the_incited_level_is_drawn_when_known_and_kept_in_view(new_axes):
    demands, success = simulate(2.0)
    ax = plot_propensity_curve(build_empirical_curve(demands, success), theta=1.9,
                               ci95=(1.8, 2.0), incited=3.5, ax=new_axes())
    assert (3.5, "-") in vertical_lines(ax)
    assert ax.get_xlim()[1] > 3.5


def test_plotting_without_axes_opens_a_new_figure():
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    import matplotlib.pyplot as plt

    demands, success = simulate(0.0)
    ax = plot_propensity_curve(build_empirical_curve(demands, success))
    surface_ax = plot_propensity_surface(build_empirical_surface(demands, success))
    assert ax.figure is not surface_ax.figure
    plt.close("all")


# --- the surface (§10.2) -----------------------------------------------------------------

def three_state_surface():
    """(b_l, b_u) = (-1, 1) three times, two successes; (0, 0) twice, no success. Every other
    valid cell is unobserved, and (2, -2) and the like are impossible."""
    demands = np.array([[-1, 1]] * 3 + [[0, 0]] * 2, dtype=float)
    return build_empirical_surface(demands, np.array([1, 1, 0, 0, 0]))


def cell(values, b_l, b_u, low=-3):
    return values[b_u - low, b_l - low]  # rows are b_u, columns b_l


def test_the_three_cell_states_are_drawn_distinctly(new_axes):
    from matplotlib.colors import to_rgba

    ax = plot_propensity_surface(three_state_surface(), ax=new_axes())
    mesh = ax.collections[0]
    values = mesh.get_array()

    assert cell(values, -1, 1) == pytest.approx(2 / 3)  # observed: coloured by mean success
    assert cell(values, 0, 0) == 0.0
    unobserved = cell(values, -3, 3)                     # valid but unobserved: whitesmoke
    assert unobserved < 0 and mesh.cmap(mesh.norm(unobserved)) == to_rgba("whitesmoke")
    assert cell(values.mask, 2, -2) and cell(values.mask, 3, 0)  # impossible: blank
    assert not cell(values.mask, -3, 3)
    assert mesh.cmap(mesh.norm(1.0)) != to_rgba("whitesmoke")


def test_only_observed_cells_carry_a_count(new_axes):
    ax = plot_propensity_surface(three_state_surface(), ax=new_axes())
    assert sorted(text.get_text() for text in ax.texts if text.get_text()) == ["2", "3"]


def test_the_upper_bound_grows_upwards(new_axes):
    ax = plot_propensity_surface(three_state_surface(), ax=new_axes())
    bottom, top = ax.get_ylim()
    assert bottom < top
    labels = [label.get_text() for label in ax.get_yticklabels()]
    positions = list(ax.get_yticks())
    assert [labels[i] for i in np.argsort(positions)] == [str(v) for v in range(-3, 4)]


@pytest.mark.parametrize("theta", [0.5, -2.2, 3.4])
def test_the_estimate_line_is_the_locus_of_centred_intervals_clipped_to_the_grid(new_axes, theta):
    ci95 = (theta - 0.1, theta + 0.05)
    ax = plot_propensity_surface(three_state_surface(), theta=theta, ci95=ci95, ax=new_axes())
    for line, level in zip(ax.get_lines(), (theta, *ci95)):
        b_l, b_u = line.get_xdata() - 3.5, line.get_ydata() - 3.5  # back from cell coordinates
        np.testing.assert_allclose(b_l + b_u, 2 * level)
        assert np.all((b_l >= -3.5) & (b_l <= 3.5) & (b_u >= -3.5) & (b_u <= 3.5))
        assert np.isclose(np.abs(np.concatenate([b_l, b_u])), 3.5).any()  # reaches the edge
    assert [line.get_linestyle() for line in ax.get_lines()] == ["-", "--", "--"]


@pytest.mark.parametrize("theta,ci95,drawn", [
    (4.8, (4.6, 5.0), [False, False, False]),  # all three off the grid
    (3.6, (3.4, 3.8), [False, True, False]),   # only the lower bound crosses the grid
])
def test_an_estimate_off_the_grid_draws_no_line_but_still_names_itself(new_axes, theta, ci95, drawn):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # an unlabelled legend would warn here
        ax = plot_propensity_surface(three_state_surface(), theta=theta, ci95=ci95,
                                     converged=False, ax=new_axes())
    assert [len(line.get_xdata()) > 0 for line in ax.get_lines()] == drawn
    assert f"{theta:.2f}" in legend_text(ax) and "did not converge" in legend_text(ax)


# --- the surface the model predicts ------------------------------------------------------

def test_the_discrete_model_surface_draws_eq5_cell_by_cell_with_theta_s_line(new_axes):
    model = build_model_surface(0.5)
    ax = plot_model_surface(model, ax=new_axes())
    values = ax.collections[0].get_array()

    np.testing.assert_allclose(values.filled(np.nan), model["prob"].to_numpy(), equal_nan=True)
    assert values.mask.sum() == np.isnan(model["prob"].to_numpy()).sum()  # impossible: blank
    (line,) = ax.get_lines()
    np.testing.assert_allclose(line.get_xdata() + line.get_ydata(), 1.0)  # value axes, no shift
    assert "0.50" in legend_text(ax)
    assert list(ax.get_xticks()) == list(range(-3, 4))


@pytest.mark.parametrize("smooth", [False, True])
def test_the_model_surface_shares_the_empirical_surface_s_colours(new_axes, smooth):
    model_ax = plot_model_surface(build_model_surface(0.0, smooth=smooth), ax=new_axes())
    empirical_ax = plot_propensity_surface(three_state_surface(), ax=new_axes())
    model_colours, empirical_colours = model_ax.collections[0].cmap, empirical_ax.collections[0].cmap
    assert all(model_colours(x) == empirical_colours(x) for x in (0.0, 0.3, 0.5, 1.0))


def test_the_discrete_model_surface_has_the_empirical_grid_s_cells(new_axes):
    ax = plot_model_surface(build_model_surface(0.0), ax=new_axes())
    assert ax.get_xlim() == (-3.5, 3.5) and ax.get_ylim() == (-3.5, 3.5)


def test_the_smooth_model_surface_is_drawn_as_labelled_contours(new_axes):
    from matplotlib.collections import QuadMesh
    from matplotlib.contour import ContourSet

    ax = plot_model_surface(build_model_surface(-0.4, smooth=True), ax=new_axes())
    contours = [artist for artist in ax.collections if isinstance(artist, ContourSet)]
    filled = [contour for contour in contours if contour.filled]
    lines = [contour for contour in contours if not contour.filled]

    assert not any(isinstance(artist, QuadMesh) for artist in ax.collections)  # no cells
    assert len(filled) == 1 and np.allclose(filled[0].levels, np.linspace(0, 1, 21))
    assert len(lines) == 1 and list(lines[0].levels) == [0.25, 0.5, 0.75]
    assert {"0.25", "0.50", "0.75"} <= {text.get_text() for text in ax.texts}
    (line,) = ax.get_lines()
    np.testing.assert_allclose(line.get_xdata() + line.get_ydata(), -0.8)
    assert ax.get_xlim() == (-3.0, 3.0)


# --- an item bank ------------------------------------------------------------------------

BANK = np.array([[-1, 2], [-1, 2], [0, 0], [-3, 3]], dtype=float)


def labels(ax):
    return sorted(text.get_text() for text in ax.texts if text.get_text())


def test_the_interval_distribution_draws_the_three_cell_states(new_axes):
    from matplotlib.colors import to_rgba

    ax = plot_interval_distribution(build_interval_distribution(BANK), ax=new_axes())
    mesh = ax.collections[0]
    values = mesh.get_array()

    assert cell(values, -1, 2) == pytest.approx(0.5)                     # occupied
    assert cell(values, 1, 1) < 0
    assert mesh.cmap(mesh.norm(cell(values, 1, 1))) == to_rgba("whitesmoke")  # valid, empty
    assert cell(values.mask, 2, -2)                                        # impossible
    assert labels(ax) == ["0.25", "0.25", "0.50"]
    assert mesh.norm.vmax == pytest.approx(0.5)  # the fullest cell tops the scale by default
    assert mesh.colorbar.ax.get_ylabel() == "Share of instances"
    assert ax.get_ylim()[0] < ax.get_ylim()[1]  # b_u grows upwards


def test_the_interval_distribution_can_count_and_take_a_fixed_scale(new_axes):
    ax = plot_interval_distribution(build_interval_distribution(BANK), proportion=False, vmax=10,
                                    colorbar=False, ax=new_axes())
    assert labels(ax) == ["1", "1", "2"]
    assert ax.collections[0].norm.vmax == 10 and ax.collections[0].colorbar is None


def test_a_share_too_small_to_print_is_not_shown_as_zero(new_axes):
    bank = np.array([[0, 0]] * 300 + [[-1, 1]], dtype=float)  # 1 in 301 rounds to 0.00
    ax = plot_interval_distribution(build_interval_distribution(bank), ax=new_axes())
    assert labels(ax) == ["1.00", "<.01"]


def test_the_tree_blanks_unreachable_cells_and_stands_on_its_base(new_axes):
    tree = build_interval_tree(BANK)
    ax = plot_interval_tree(tree, proportion=False, ax=new_axes())
    values = ax.collections[0].get_array()
    column = {centre: j for j, centre in enumerate(tree["centres"])}

    assert values[3, column[0.5]] == 2 and values[6, column[0.0]] == 1  # [-1, 2] twice; the tip
    assert values[2, column[0.0]] < 0                                   # reachable, empty
    assert values.mask[1, column[0.0]] and values.mask[6, column[0.5]]  # unreachable
    assert ax.get_ylim()[0] < ax.get_ylim()[1]  # length 0 at the bottom
    assert [label.get_text() for label in ax.get_xticklabels()][:3] == ["-3", "-2.5", "-2"]
    assert labels(ax) == ["1", "1", "2"]


def test_several_trees_share_one_colour_scale_and_one_colour_bar():
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    from matplotlib.figure import Figure

    trees = {"RA": build_interval_tree(BANK),
             "Ex": build_interval_tree(np.array([[0, 0]] * 3, dtype=float)),
             "Ul": build_interval_tree(BANK[:1])}
    figure = plot_interval_trees(trees, proportion=False, nrows=2, figure=Figure(layout="constrained"))

    panels = [ax for ax in figure.axes if ax.get_title()]
    assert [ax.get_title() for ax in panels] == ["RA", "Ex", "Ul"]
    assert {ax.collections[0].norm.vmax for ax in panels} == {3.0}  # Ex's fullest cell, for all
    (colour_bar,) = [ax for ax in figure.axes if not ax.get_title()]  # the empty fourth slot is gone
    assert colour_bar.get_ylabel() == "Instances"


@pytest.mark.parametrize("show_invalid,expected", [(False, (0.0, 0.0, 0.0, 0.0)), (True, "lightgray")])
def test_the_tree_s_invalid_cells_can_be_shown(new_axes, show_invalid, expected):
    from matplotlib.colors import to_rgba

    tree = build_interval_tree(BANK)
    ax = plot_interval_tree(tree, show_invalid=show_invalid, ax=new_axes())
    colours = ax.collections[0].get_facecolor().reshape(len(tree["lengths"]), len(tree["centres"]), 4)
    column = {centre: j for j, centre in enumerate(tree["centres"])}

    assert tuple(colours[1, column[0.0]]) == to_rgba(expected)       # unreachable: odd length
    assert tuple(colours[6, column[3.0]]) == to_rgba(expected)       # unreachable: off the grid
    assert tuple(colours[2, column[0.0]]) == to_rgba("whitesmoke")   # reachable and empty, either way
    assert labels(ax) == ["0.25", "0.25", "0.50"]                    # invalid cells are never labelled


def test_showing_invalid_cells_reaches_every_tree_drawn(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    import propensity.modelling.plotting as plotting

    seen, draw = [], plotting.plot_interval_tree
    monkeypatch.setattr(plotting, "plot_interval_tree",
                        lambda *args, **kwargs: seen.append(kwargs["show_invalid"]) or draw(*args, **kwargs))
    annotations, _ = bank({})
    both = pd.concat([annotations, annotations.assign(dimension="Ex")])
    save_annotation_plots(both, tmp_path, show_invalid=True)
    assert seen == [True] * 4  # each dimension's own tree, then both panels of the grid


def test_trees_need_at_least_one_tree():
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    with pytest.raises(ValueError, match="no trees"):
        plot_interval_trees({})


@pytest.mark.parametrize("n,nrows,ncols,expected", [
    (1, None, None, (1, 1)), (3, None, None, (1, 3)), (4, None, None, (2, 2)),
    (6, None, None, (2, 3)), (3, 2, None, (2, 2)), (5, None, 2, (3, 2)),
])
def test_the_grid_layout_leaves_the_fewest_empty_slots_then_is_squarest(n, nrows, ncols, expected):
    assert _layout(n, nrows, ncols) == expected


def test_a_grid_too_small_for_its_panels_is_refused():
    with pytest.raises(ValueError, match="cannot hold 5"):
        _layout(5, 2, 2)


# --- saving every cell -------------------------------------------------------------------

def bank(subjects, n_items=120, seed=0):
    """Tidy annotations and outcomes, with a known theta per subject and item count."""
    rng = np.random.default_rng(seed)
    lower = rng.integers(-3, 4, n_items)
    upper = np.array([rng.integers(lo, 4) for lo in lower])
    annotations = pd.DataFrame({"question_id": [f"q{i}" for i in range(n_items)], "dimension": "RA",
                                "lower": lower.astype(float), "upper": upper.astype(float),
                                "parse_ok": True})
    rows = []
    for subject, (theta, n) in subjects.items():
        p = np.clip([two_sided_sigma(theta, lo, hi) for lo, hi in zip(lower, upper)], 0, 1)
        outcome = rng.binomial(1, p)
        rows += [{"question_id": f"q{i}", "subject_id": subject, "outcome": int(outcome[i])}
                 for i in range(n)]
    return annotations, pd.DataFrame(rows)


def fit_quietly(annotations, outcomes):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return fit_profiles(annotations, outcomes)


def test_every_cell_gets_a_curve_and_a_surface_even_when_it_was_not_fitted(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    annotations, outcomes = bank({"org/model:a": (1.0, 120), "org/model_a": (-1.0, 120),
                                  "tiny_+2": (0.0, 10)})
    profiles = fit_quietly(annotations, outcomes)
    assert profiles.set_index("subject_id").loc["tiny_+2", "skip_reason"].startswith("only 10")

    written = save_profile_plots(profiles, annotations, outcomes, tmp_path / "plots")

    assert sorted(path.name for path in written) == [
        "org_model_a_RA_2_curve.png", "org_model_a_RA_2_surface.png",  # names kept distinct
        "org_model_a_RA_curve.png", "org_model_a_RA_surface.png",
        "tiny_+2_RA_curve.png", "tiny_+2_RA_surface.png"]  # a signed level stays legible
    assert all(path.read_bytes().startswith(PNG) for path in written)


def test_a_cell_with_nothing_joined_has_nothing_to_draw(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    annotations, outcomes = bank({"a": (0.0, 60)})
    outcomes = pd.concat([outcomes, pd.DataFrame(
        [{"question_id": "elsewhere", "subject_id": "ghost", "outcome": 1}])], ignore_index=True)
    profiles = fit_quietly(annotations, outcomes)
    written = save_profile_plots(profiles, annotations, outcomes, tmp_path)
    assert sorted(path.name for path in written) == ["a_RA_curve.png", "a_RA_surface.png"]


def test_a_plot_that_cannot_be_drawn_is_logged_and_the_rest_carry_on(tmp_path, caplog):
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    annotations, outcomes = bank({"a": (0.0, 60)})
    annotations.loc[0, "lower"] = -0.5  # not on the integer grid the surface needs
    profiles = fit_quietly(annotations, outcomes)
    with caplog.at_level(logging.WARNING):
        written = save_profile_plots(profiles, annotations, outcomes, tmp_path)
    assert [path.name for path in written] == ["a_RA_curve.png"]
    assert "skipped the surface for a / RA" in caplog.text


# --- saving the bank's plots -------------------------------------------------------------

def test_each_dimension_gets_a_distribution_and_a_tree_and_several_share_a_grid(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    annotations = pd.DataFrame({
        "question_id": [f"q{i}" for i in range(6)],
        "dimension": ["RA", "RA", "RA", "Ex/v2", "Ul", "Gone"],
        "lower": [-1.0, 0.0, None, 0.0, 1.0, -3.0],
        "upper": [2.0, 0.0, None, 1.0, 1.0, 3.0],
        "parse_ok": [True, True, False, True, True, False]})  # "Gone" has nothing usable

    written = save_annotation_plots(annotations, tmp_path)

    assert sorted(path.name for path in written) == [
        "Ex_v2_intervals.png", "Ex_v2_tree.png", "RA_intervals.png", "RA_tree.png",
        "Ul_intervals.png", "Ul_tree.png", "interval_trees.png"]
    assert all(path.read_bytes().startswith(PNG) for path in written)


def test_one_dimension_gets_no_grid_and_a_filter_picks_dimensions(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    annotations, _ = bank({})
    other = annotations.assign(dimension="Ex")
    written = save_annotation_plots(pd.concat([annotations, other]), tmp_path, dimensions=["Ex"])
    assert sorted(path.name for path in written) == ["Ex_intervals.png", "Ex_tree.png"]


def test_a_dimension_off_the_grid_is_logged_and_the_rest_carry_on(tmp_path, caplog):
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    annotations, _ = bank({})
    broken = annotations.assign(dimension="Ex")
    broken.loc[0, "lower"] = -0.5
    with caplog.at_level(logging.WARNING):
        written = save_annotation_plots(pd.concat([annotations, broken]), tmp_path)
    assert sorted(path.name for path in written) == ["RA_intervals.png", "RA_tree.png"]
    assert "skipped the interval plots for Ex" in caplog.text
