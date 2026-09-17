"""propel-fit: annotations plus outcomes produce a propensity profile table (CLAUDE.md §6.5).

    propel-fit --annotations RA=annotations.jsonl --outcomes outcomes.csv --out profiles.csv

Each --annotations entry is either a path, for a file that names its own dimension, or
CODE=path for a single-dimension file that does not. Settings come from config/modelling.yaml
when it is present, and the flags below override it.
"""

import argparse
import logging
import sys
import warnings

import pandas as pd

from ..errors import PropensityError
from ..modelling.io import load_annotations, load_outcomes, write_table
from ..modelling.profiles import fit_profiles
from . import load_config

DEFAULT_CONFIG = "config/modelling.yaml"
# config/modelling.yaml key -> fit_theta argument
FIT_SETTINGS = {"k_default": "k", "n_bins": "n_bins", "lowess_frac": "lowess_frac",
                "maxiter": "maxiter", "robust": "robust", "restart_range": "restart_range",
                "likelihood": "likelihood", "min_width": "min_width", "rho": "rho"}


def build_parser():
    parser = argparse.ArgumentParser(prog="propel-fit", description=__doc__.splitlines()[0])
    parser.add_argument("--annotations", nargs="+", required=True, metavar="[CODE=]PATH",
                        help="annotation files; prefix with CODE= for files without a dimension column")
    parser.add_argument("--outcomes", required=True, help="outcomes file, long or wide form")
    parser.add_argument("--out", required=True, help="where to write the profile table (.csv or .jsonl)")
    parser.add_argument("--subjects", nargs="+", help="only these subjects (default: all in the outcomes)")
    parser.add_argument("--dimensions", nargs="+", help="only these dimensions (default: all annotated)")
    parser.add_argument("--min-items", type=int, help="cells below this are recorded but not fitted")
    parser.add_argument("--likelihood", choices=("sum", "product"),
                        help="'product' only to reproduce published numbers (§9.2)")
    parser.add_argument("--no-robust", action="store_true", help="a single fit attempt, no guarded restarts")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"settings file (default: {DEFAULT_CONFIG})")
    return parser


def resolve_settings(args):
    """Function defaults, overridden by the config file, overridden by the flags."""
    config = load_config(args.config, "propensity")
    fit_kwargs = {arg: config[key] for key, arg in FIT_SETTINGS.items() if key in config}
    if "restart_range" in fit_kwargs:
        fit_kwargs["restart_range"] = tuple(fit_kwargs["restart_range"])
    if args.likelihood:
        fit_kwargs["likelihood"] = args.likelihood
    if args.no_robust:
        fit_kwargs["robust"] = False

    min_items = args.min_items
    if min_items is None:
        min_items = load_config(args.config, "profiles").get("min_items", 30)
    return fit_kwargs, min_items


def read_annotations(entries):
    """Loads every --annotations entry and concatenates them into one tidy frame."""
    frames = []
    for entry in entries:
        code, sep, path = entry.partition("=")
        frames.append(load_annotations(path if sep else entry, dimension=code if sep else None))
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


def report(profiles, out_path):
    """Prints the join yield and a diagnostics summary, the checks that catch unusable banks."""
    join = profiles.attrs["join_report"]
    for dimension, counts in join["per_dimension"].items():
        print(f"join yield {dimension}: {counts['n_joined']}/{counts['n_annotated']} "
              f"annotated instances have outcomes ({counts['yield']:.0%})")
    if join["n_unusable"]:
        print(f"{join['n_unusable']} annotation rows were unusable (failed to parse, or a null bound)")
    if join["n_unmatched_outcome_ids"]:
        print(f"{join['n_unmatched_outcome_ids']} outcome question_ids have no annotation")

    fitted = profiles["theta"].notna()
    print(f"fitted {int(fitted.sum())} of {len(profiles)} (subject, dimension) cells")
    skipped = profiles.loc[~fitted, ["subject_id", "dimension", "skip_reason"]]
    for row in skipped.head(10).itertuples(index=False):
        print(f"  skipped {row.subject_id} / {row.dimension}: {row.skip_reason}")
    if len(skipped) > 10:
        print(f"  ... and {len(skipped) - 10} more")

    flagged = profiles[fitted & (profiles["warnings"].astype(str) != "")]
    if len(flagged):
        print(f"{len(flagged)} fitted cells carry diagnostics warnings, for instance:")
        for row in flagged.head(3).itertuples(index=False):
            print(f"  {row.subject_id} / {row.dimension}: {row.warnings}")
    not_converged = profiles[fitted & (profiles["converged"] == 0)]
    if len(not_converged):
        print(f"{len(not_converged)} fitted cells did not converge; read their confidence "
              "intervals with that in mind")
    print(f"wrote {out_path}")


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    args = build_parser().parse_args(argv)
    fit_kwargs, min_items = resolve_settings(args)
    try:
        annotations = read_annotations(args.annotations)
        outcomes = load_outcomes(args.outcomes)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            profiles = fit_profiles(annotations, outcomes, subjects=args.subjects,
                                    dimensions=args.dimensions, min_items=min_items, **fit_kwargs)
        for warning in caught:  # diagnostics go to stderr; the report below is the result
            print(f"warning: {warning.message}", file=sys.stderr)
        write_table(profiles, args.out)
    except PropensityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report(profiles, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
