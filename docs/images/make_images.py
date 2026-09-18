"""Render the figures shown in docs/plots.md from the example data.

    python docs/images/make_images.py
"""

import warnings
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from propensity import (
    build_empirical_curve,
    build_empirical_surface,
    build_interval_distribution,
    build_interval_tree,
    build_model_surface,
    fit_profiles,
    join_annotations_outcomes,
    load_annotations,
    load_outcomes,
    plot_interval_distribution,
    plot_interval_tree,
    plot_model_surface,
    plot_propensity_curve,
    plot_propensity_surface,
)

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent.parent / "examples"


def save(name, size, draw):
    figure = Figure(figsize=size)
    FigureCanvasAgg(figure)
    draw(figure.subplots())
    figure.savefig(HERE / name, dpi=72, bbox_inches="tight")


def main():
    annotations = load_annotations(EXAMPLES / "annotations_RA.jsonl")
    outcomes = load_outcomes(EXAMPLES / "outcomes_long.csv")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        profiles = fit_profiles(annotations, outcomes).set_index("subject_id")
        joined, _ = join_annotations_outcomes(annotations, outcomes)

    subject = "demo-model_RA_+2"
    cell = joined[joined["subject_id"] == subject]
    demands, success = cell[["lower", "upper"]].to_numpy(), cell["outcome"].to_numpy()
    fit = profiles.loc[subject]
    estimate = {"theta": fit["theta"], "ci95": (fit["ci95_lower"], fit["ci95_upper"])}
    title = f"{subject} · RA"

    save("curve.png", (8, 5), lambda ax: plot_propensity_curve(
        build_empirical_curve(demands, success, jitter=0.25, seed=0), incited=2, title=title,
        ax=ax, **estimate))
    save("surface.png", (7, 6), lambda ax: plot_propensity_surface(
        build_empirical_surface(demands, success), title=title, ax=ax, **estimate))
    save("model_surface.png", (7, 6), lambda ax: plot_model_surface(
        build_model_surface(fit["theta"]), title="Eq. 5 at the fitted theta", ax=ax))
    save("model_surface_smooth.png", (7, 6), lambda ax: plot_model_surface(
        build_model_surface(fit["theta"], smooth=True), title="Eq. 5, smooth=True", ax=ax))

    usable = annotations[annotations["parse_ok"]][["lower", "upper"]].to_numpy()
    save("intervals.png", (7, 6), lambda ax: plot_interval_distribution(
        build_interval_distribution(usable), title="RA · 117 annotated instances", ax=ax))
    save("tree.png", (9, 5), lambda ax: plot_interval_tree(
        build_interval_tree(usable), title="RA · 117 annotated instances", ax=ax))
    save("tree_invalid.png", (9, 5), lambda ax: plot_interval_tree(
        build_interval_tree(usable), show_invalid=True, title="show_invalid=True", ax=ax))
    print(f"wrote the figures to {HERE}")


if __name__ == "__main__":
    main()
