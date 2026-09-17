"""Fitting propensity levels from demand intervals and outcomes.

Never imports matplotlib: the renderers in plotting.py import it only when they draw.
"""

from .curves import build_empirical_curve
from .io import (
    join_annotations_outcomes,
    load_annotations,
    load_instances,
    load_outcomes,
    read_table,
    write_table,
)
from .mle import fit_diagnostics, fit_theta, neg_log_likelihood
from .model import two_sided_sigma
from .plotting import (
    plot_interval_distribution,
    plot_interval_tree,
    plot_interval_trees,
    plot_model_surface,
    plot_propensity_curve,
    plot_propensity_surface,
    save_annotation_plots,
    save_profile_plots,
)
from .profiles import fit_profiles, profile_vector
from .surfaces import (
    build_empirical_surface,
    build_interval_distribution,
    build_interval_tree,
    build_model_surface,
)
