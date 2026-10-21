"""PROPEL: annotate task instances with propensity demand intervals, and fit propensity levels.

Public API re-exports only. What `__all__` holds is stable: it changes as docs/stability.md
says, never quietly.
"""

# Defined before the imports below: the annotation runner records it on every row.
__version__ = "0.5.1"

from .annotation import (
    ANNOTATION_SYSTEM,
    Dimension,
    annotate,
    build_annotation_prompt,
    get_dimension,
    load_dimensions,
    load_presentation,
    load_rubric,
    parse_final_range,
)
from .errors import (
    ContractError,
    DataWarning,
    ParseError,
    PropensityDeprecationWarning,
    PropensityError,
    ProviderError,
)
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

# The stable API: docs/stability.md says what that promises, and how it may change.
__all__ = [
    "annotate", "ANNOTATION_SYSTEM", "available_providers", "BatchCapable", "BatchRequest",
    "build_annotation_prompt", "build_empirical_curve", "build_empirical_surface",
    "build_interval_distribution", "build_interval_tree", "build_model_surface", "Completion",
    "ContractError", "DataWarning", "Dimension", "fit_diagnostics", "fit_profiles", "fit_theta",
    "get_dimension", "get_provider", "join_annotations_outcomes", "LLMProvider",
    "load_annotations", "load_dimensions", "load_instances", "load_outcomes",
    "load_presentation", "load_rubric", "neg_log_likelihood", "parse_final_range", "ParseError",
    "plot_interval_distribution", "plot_interval_tree", "plot_interval_trees",
    "plot_model_surface", "plot_propensity_curve", "plot_propensity_surface", "profile_vector",
    "PropensityDeprecationWarning", "PropensityError", "ProviderError", "read_table",
    "register_provider", "save_annotation_plots", "save_profile_plots", "two_sided_sigma",
    "write_table",
]
