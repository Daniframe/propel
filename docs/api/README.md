# API reference

Everything below is importable from the top-level package: `from propensity import fit_theta`.
Submodules hold the rest (constants, adapter classes, lower-level helpers).

| Package | Contents | Page |
|---|---|---|
| `propensity.annotation` | rubrics, prompt assembly, parsing, the annotation runner | [annotation](annotation.md) |
| `propensity.modelling` | file I/O and validation, the response model, the fit, curves, surfaces, profiles | [modelling](modelling.md) |
| `propensity.modelling.plotting` | every figure | [plotting](plotting.md) |
| `propensity.providers` | the provider protocol, the registry, the shipped adapters | [providers](providers.md) |
| `propensity.errors` | exceptions and warnings | [errors](errors.md) |

## Top-level names

| Name | Kind | Page |
|---|---|---|
| `annotate` | function | [annotation](annotation.md#annotate) |
| `build_annotation_prompt` | function | [annotation](annotation.md#build_annotation_prompt) |
| `load_rubric`, `load_presentation` | function | [annotation](annotation.md#rubrics) |
| `load_dimensions`, `get_dimension` | function | [annotation](annotation.md#the-catalogue) |
| `Dimension` | dataclass | [annotation](annotation.md#dimension) |
| `parse_final_range` | function | [annotation](annotation.md#parse_final_range) |
| `read_table`, `write_table` | function | [modelling](modelling.md#read_table-write_table) |
| `load_instances` | function | [modelling](modelling.md#load_instances) |
| `load_annotations` | function | [modelling](modelling.md#load_annotations) |
| `load_outcomes` | function | [modelling](modelling.md#load_outcomes) |
| `join_annotations_outcomes` | function | [modelling](modelling.md#join_annotations_outcomes) |
| `two_sided_sigma` | function | [modelling](modelling.md#two_sided_sigma) |
| `neg_log_likelihood` | function | [modelling](modelling.md#neg_log_likelihood) |
| `fit_theta` | function | [modelling](modelling.md#fit_theta) |
| `fit_diagnostics` | function | [modelling](modelling.md#fit_diagnostics) |
| `fit_profiles`, `profile_vector` | function | [modelling](modelling.md#fit_profiles) |
| `build_empirical_curve` | function | [modelling](modelling.md#build_empirical_curve) |
| `build_empirical_surface`, `build_model_surface` | function | [modelling](modelling.md#surfaces) |
| `build_interval_distribution`, `build_interval_tree` | function | [modelling](modelling.md#surfaces) |
| `plot_propensity_curve`, `plot_propensity_surface`, `plot_model_surface` | function | [plotting](plotting.md) |
| `plot_interval_distribution`, `plot_interval_tree`, `plot_interval_trees` | function | [plotting](plotting.md) |
| `save_profile_plots`, `save_annotation_plots` | function | [plotting](plotting.md#files) |
| `get_provider`, `register_provider`, `available_providers` | function | [providers](providers.md#registry) |
| `LLMProvider`, `BatchCapable` | protocol | [providers](providers.md#protocol) |
| `Completion`, `BatchRequest` | dataclass | [providers](providers.md#protocol) |
| `PropensityError`, `ContractError`, `ProviderError`, `ParseError`, `DataWarning` | exception, warning | [errors](errors.md) |

## Conventions

- **Arrays.** `demands` is an `(N, 2)` array-like of `(b_l, b_u)` pairs, and `success` an `(N,)`
  array-like of 0/1.
- **Keyword-only.** Keyword arguments after `*` in a signature must be passed by name.
- **Data before drawing.** Functions that build data (`build_*`, `fit_*`, `load_*`) never touch
  matplotlib; only `plot_*` and `save_*` do.
- **Nothing is cached** and no module-level state is kept, except the provider registry.
