"""PROPEL: annotate task instances with propensity demand intervals, and fit propensity levels.

Public API re-exports only.
"""

from .annotation import (
    annotate,
    build_annotation_prompt,
    load_presentation,
    load_rubric,
    parse_final_range,
)
from .errors import ContractError, DataWarning, ParseError, PropensityError, ProviderError
from .modelling import (
    build_empirical_curve,
    build_empirical_surface,
    build_interval_distribution,
    build_interval_tree,
    build_model_surface,
    fit_diagnostics,
    fit_profiles,
    fit_theta,
    join_annotations_outcomes,
    load_annotations,
    load_instances,
    load_outcomes,
    neg_log_likelihood,
    plot_interval_distribution,
    plot_interval_tree,
    plot_interval_trees,
    plot_model_surface,
    plot_propensity_curve,
    plot_propensity_surface,
    profile_vector,
    read_table,
    save_annotation_plots,
    save_profile_plots,
    two_sided_sigma,
    write_table,
)
from .providers import (
    BatchCapable,
    BatchRequest,
    Completion,
    LLMProvider,
    available_providers,
    get_provider,
    register_provider,
)
