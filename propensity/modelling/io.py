"""Loading, normalising and joining the pipeline's files: CLAUDE.md §6.

Every loader returns the tidy internal form (§6.4), whatever shape the file came in:

    instances:    list of dicts with a string question_id and question_text
    annotations:  question_id · dimension · lower · upper · parse_ok
    outcomes:     question_id · subject_id · outcome
    joined:       question_id · dimension · lower · upper · subject_id · outcome

Reading is permissive about shapes and column names; validation is strict and raises
ContractError naming the offending rows. Identifiers are always strings, so "007" survives
and an integer id in one file still joins the same id written as text in another.
"""

import json
import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from ..errors import ContractError, DataWarning
from .mle import MIN_ITEMS_WARN

logger = logging.getLogger(__name__)

SCALE = (-3.0, 3.0)
YIELD_WARN = 0.9

_ID_ALIASES = ("custom_id", "instance_id")
_BOUND_ALIASES = (("lower", "upper"), ("propensity_lower", "propensity_upper"),
                  ("lower_bound", "upper_bound"))
_OUTCOME_SUFFIX = "_outcome"
_TRUE_STRINGS = {"1", "1.0", "true"}
_FALSE_STRINGS = {"0", "0.0", "false"}


# --- files -------------------------------------------------------------------------------

def read_table(path) -> pd.DataFrame:
    """Reads a .jsonl or .csv file. JSON values keep their types; CSV cells are read as
    strings, and are coerced later only where a contract says how."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return pd.DataFrame(_read_jsonl(path), dtype=object)
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str)
    raise ContractError(f"{path}: unsupported file type {path.suffix!r}; expected .jsonl or .csv")


def write_table(data, path) -> Path:
    """Writes a DataFrame or a list of dicts as .jsonl (NaN becomes null) or .csv."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in (".jsonl", ".csv"):
        raise ContractError(f"{path}: unsupported file type {path.suffix!r}; expected .jsonl or .csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".csv":
        frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
        frame.to_csv(path, index=False, lineterminator="\n")
        return path
    records = data.to_dict(orient="records") if isinstance(data, pd.DataFrame) else data
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps({k: _json_value(v) for k, v in record.items()}, ensure_ascii=False) + "\n")
    return path


def load_instances(path) -> list[dict]:
    """§6.1: reads instances to annotate. Only question_id and question_text are read; every
    other field passes through untouched.

    A file with no question_id column gets ids "{stem}_{row_index}", numbered over the whole
    file. Sample only after loading: numbering a sample instead would give different ids to
    different subsets, and the annotations could never be joined back.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        records = _read_jsonl(path)
    elif suffix == ".csv":
        # keep_default_na=False: a question that reads "NA" is text, not a missing value.
        records = pd.read_csv(path, dtype=str, keep_default_na=False).to_dict(orient="records")
    else:
        raise ContractError(f"{path}: unsupported file type {path.suffix!r}; expected .jsonl or .csv")
    if not records:
        raise ContractError(f"{path}: no instances")

    has_id = ["question_id" in r for r in records]
    if not any(has_id):
        records = [{"question_id": f"{path.stem}_{i}", **r} for i, r in enumerate(records)]
    elif not all(has_id):
        rows = [i for i, present in enumerate(has_id) if not present]
        raise ContractError(f"{path}: question_id is missing on rows {_preview(rows)}", rows=rows)

    bad_ids = [i for i, r in enumerate(records) if _as_id(r["question_id"]) is None]
    if bad_ids:
        raise ContractError(f"{path}: empty question_id on rows {_preview(bad_ids)}", rows=bad_ids)
    for r in records:
        r["question_id"] = _as_id(r["question_id"])

    bad_text = [r["question_id"] for r in records
                if not isinstance(r.get("question_text"), str) or not r["question_text"].strip()]
    if bad_text:
        raise ContractError(f"{path}: missing or empty question_text for {_preview(bad_text)}", rows=bad_text)

    seen, duplicates = set(), []
    for r in records:
        if r["question_id"] in seen:
            duplicates.append(r["question_id"])
        seen.add(r["question_id"])
    if duplicates:
        raise ContractError(f"{path}: duplicate question_id {_preview(duplicates)}", rows=duplicates)
    return records


# --- annotations -------------------------------------------------------------------------

def load_annotations(source, *, dimension=None) -> pd.DataFrame:
    """§6.2: reads annotations in the canonical form or any legacy shape, and returns the tidy
    question_id · dimension · lower · upper · parse_ok frame.

    Legacy shapes, normalised silently: propensity_lower/propensity_upper and
    lower_bound/upper_bound for lower/upper; custom_id or instance_id for question_id; wide
    files with {DIM}_l/{DIM}_u columns, melted to one row per (question_id, dimension).

    dimension: for a file without a dimension column, the dimension of every row; for any
        other file, keep only this dimension.

    Rows that failed to parse (parse_ok false, or a null bound) are kept and flagged;
    join_annotations_outcomes drops them and says how many.
    """
    frame, name = _frame(source)
    frame = _rename_id(frame, name)

    bounds = next(((lo, hi) for lo, hi in _BOUND_ALIASES
                   if lo in frame.columns and hi in frame.columns), None)
    if bounds is not None:
        frame = frame.rename(columns={bounds[0]: "lower", bounds[1]: "upper"})
        if "dimension" not in frame.columns:
            if dimension is None:
                raise ContractError(f"{name}: no 'dimension' column; pass dimension= to say which "
                                    "dimension this file annotates", rows=["dimension"])
            frame["dimension"] = dimension
    else:
        wide = _wide_dimensions(frame.columns)
        if not wide:
            raise ContractError(
                f"{name}: no demand-interval columns; expected lower/upper, "
                "propensity_lower/propensity_upper, lower_bound/upper_bound or {DIM}_l/{DIM}_u",
                rows=["lower", "upper"])
        frame = _melt_wide_annotations(frame, wide)

    frame["dimension"] = [None if _is_missing(d) else str(d) for d in frame["dimension"]]
    if dimension is not None:
        frame = frame[frame["dimension"] == dimension].copy()
        if frame.empty:
            raise ContractError(f"{name}: no annotations for dimension {dimension!r}", rows=[dimension])

    frame["question_id"] = [_as_id(q) for q in frame["question_id"]]
    missing = frame.index[frame["question_id"].isna() | frame["dimension"].isna()].tolist()
    if missing:
        raise ContractError(f"{name}: missing question_id or dimension on rows {_preview(missing)}", rows=missing)

    frame["parse_ok"] = (_coerce(frame["parse_ok"], _as_bool, name, "parse_ok", frame)
                         if "parse_ok" in frame.columns else True)
    frame["lower"] = _coerce(frame["lower"], _as_bound, name, "lower", frame)
    frame["upper"] = _coerce(frame["upper"], _as_bound, name, "upper", frame)
    tidy = frame[["question_id", "dimension", "lower", "upper", "parse_ok"]].reset_index(drop=True)
    tidy = tidy.astype({"lower": float, "upper": float, "parse_ok": bool})
    _validate_annotations(tidy, name)
    return tidy


def _melt_wide_annotations(frame, dims):
    parts = []
    for dim in dims:
        part = pd.DataFrame({
            "question_id": frame["question_id"].to_numpy(),
            "dimension": dim,
            "lower": frame[f"{dim}_l"].to_numpy(),
            "upper": frame[f"{dim}_u"].to_numpy(),
        })
        if "parse_ok" in frame.columns:
            part["parse_ok"] = frame["parse_ok"].to_numpy()
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def _wide_dimensions(columns):
    """Dimension codes with both {DIM}_l and {DIM}_u columns, in file order."""
    names = {str(c) for c in columns}
    return [c[:-2] for c in map(str, columns) if c.endswith("_l") and len(c) > 2 and f"{c[:-2]}_u" in names]


def _validate_annotations(tidy, name):
    usable = tidy["parse_ok"] & tidy["lower"].notna() & tidy["upper"].notna()
    low, high = SCALE
    bad = tidy[usable & ~((low <= tidy["lower"]) & (tidy["lower"] <= tidy["upper"]) & (tidy["upper"] <= high))]
    if not bad.empty:
        rows = list(bad[["question_id", "dimension", "lower", "upper"]].itertuples(index=False, name=None))
        raise ContractError(f"{name}: intervals must satisfy -3 <= lower <= upper <= 3; got {_preview(rows)}",
                            rows=rows)
    _reject_duplicates(tidy, ["question_id", "dimension"], name)


def _reject_duplicates(frame, key, name):
    duplicated = frame[frame.duplicated(key, keep=False)]
    if not duplicated.empty:
        rows = sorted(set(duplicated[key].itertuples(index=False, name=None)))
        raise ContractError(f"{name}: duplicate ({', '.join(key)}) {_preview(rows)}", rows=rows)


# --- outcomes ----------------------------------------------------------------------------

def load_outcomes(source) -> pd.DataFrame:
    """§6.3: reads the user's outcomes and returns the tidy question_id · subject_id · outcome
    frame.

    Long form has question_id, subject_id and outcome columns. Wide form has question_id and
    one {subject}_outcome column per subject; subject_id is the column name without the
    suffix. Outcomes must be 0 or 1 (True/False and "1"/"0" are accepted; probabilities are
    not). Missing outcomes are dropped, never zero-filled: an instance that produced no
    response is not an instance the subject got wrong.
    """
    frame, name = _frame(source)
    frame = _rename_id(frame, name)

    present = {"subject_id", "outcome"} & set(frame.columns)
    if present:
        absent = sorted({"subject_id", "outcome"} - present)
        if absent:
            raise ContractError(f"{name}: missing column(s) {absent}", rows=absent)
        long = frame[["question_id", "subject_id", "outcome"]].reset_index(drop=True)
    else:
        wide = [c for c in frame.columns
                if isinstance(c, str) and c.endswith(_OUTCOME_SUFFIX) and len(c) > len(_OUTCOME_SUFFIX)]
        if not wide:
            raise ContractError(
                f"{name}: missing column(s) ['outcome', 'subject_id']; expected long form "
                "(question_id, subject_id, outcome) or wide form ({subject}_outcome columns)",
                rows=["outcome", "subject_id"])
        long = frame.melt(id_vars="question_id", value_vars=wide, var_name="subject_id", value_name="outcome")
        long["subject_id"] = [s[: -len(_OUTCOME_SUFFIX)] for s in long["subject_id"]]

    long["question_id"] = [_as_id(q) for q in long["question_id"]]
    long["subject_id"] = [_as_id(s) for s in long["subject_id"]]
    missing = long.index[long["question_id"].isna() | long["subject_id"].isna()].tolist()
    if missing:
        raise ContractError(f"{name}: missing question_id or subject_id on rows {_preview(missing)}", rows=missing)

    values, bad = [], []
    for qid, sid, value in zip(long["question_id"], long["subject_id"], long["outcome"]):
        try:
            values.append(_as_outcome(value))
        except ValueError:
            bad.append((qid, sid, value))
    if bad:
        raise ContractError(f"{name}: outcomes must be 0 or 1; got {_preview(bad)}", rows=bad)
    long["outcome"] = values
    _reject_duplicates(long, ["question_id", "subject_id"], name)

    n_missing = int(long["outcome"].isna().sum())
    if n_missing:
        logger.info("%s: dropped %d missing outcomes (not counted as failures)", name, n_missing)
    tidy = long[long["outcome"].notna()].reset_index(drop=True)
    return tidy.astype({"outcome": "int64"})


# --- join --------------------------------------------------------------------------------

def join_annotations_outcomes(annotations, outcomes, *, min_items=MIN_ITEMS_WARN, min_yield=YIELD_WARN):
    """§6.4: inner join on question_id, after dropping annotations that failed to parse or
    have a null bound.

    Returns (joined, report). The report gives, per dimension, the join yield: the share of
    usable annotated instances that found at least one outcome. A silent partial join is the
    most common failure in this pipeline, so a DataWarning is raised when any yield is below
    `min_yield`, or when any (subject, dimension) cell has fewer than `min_items` instances.
    """
    _require_columns(annotations, ["question_id", "dimension", "lower", "upper"], "annotations")
    _require_columns(outcomes, ["question_id", "subject_id", "outcome"], "outcomes")
    annotations = annotations.reset_index(drop=True)
    annotations["question_id"] = [_as_id(q) for q in annotations["question_id"]]
    outcomes = outcomes.reset_index(drop=True)
    outcomes["question_id"] = [_as_id(q) for q in outcomes["question_id"]]

    parse_ok = (pd.Series([_as_bool(v) for v in annotations["parse_ok"]], index=annotations.index)
                if "parse_ok" in annotations.columns else True)
    usable_mask = parse_ok & annotations["lower"].notna() & annotations["upper"].notna()
    usable = annotations.loc[usable_mask, ["question_id", "dimension", "lower", "upper"]]
    # Loaded frames are already checked; frames built by hand may not be, and a duplicate key
    # would silently repeat rows in the join.
    _reject_duplicates(usable, ["question_id", "dimension"], "annotations")
    _reject_duplicates(outcomes, ["question_id", "subject_id"], "outcomes")
    joined = usable.merge(outcomes[["question_id", "subject_id", "outcome"]], on="question_id", how="inner")
    joined = joined.reset_index(drop=True)

    outcome_ids = set(outcomes["question_id"])
    per_dimension = {}
    for dim, group in usable.groupby("dimension", sort=True):
        ids = set(group["question_id"])
        n_joined = len(ids & outcome_ids)
        per_dimension[dim] = {"n_annotated": len(ids), "n_joined": n_joined, "yield": n_joined / len(ids)}
    cell_sizes = {cell: int(n) for cell, n in joined.groupby(["subject_id", "dimension"], sort=True).size().items()}
    report = {
        "n_annotation_rows": len(annotations),
        "n_unusable": int((~usable_mask).sum()),
        "per_dimension": per_dimension,
        "n_outcome_ids": len(outcome_ids),
        "n_unmatched_outcome_ids": len(outcome_ids - set(usable["question_id"])),
        "cell_sizes": cell_sizes,
    }

    if not per_dimension:
        warnings.warn("no usable annotations to join", DataWarning, stacklevel=2)
    low = {d: r for d, r in per_dimension.items() if r["yield"] < min_yield}
    if low:
        detail = "; ".join(f"{d}: {r['yield']:.0%} ({r['n_joined']} of {r['n_annotated']} annotated "
                           "instances have outcomes)" for d, r in low.items())
        warnings.warn(f"low join yield, check that question_ids match. {detail}", DataWarning, stacklevel=2)
    small = [f"{s}/{d} ({n})" for (s, d), n in cell_sizes.items() if n < min_items]
    if small:
        warnings.warn(f"fewer than {min_items} instances, so the fit will be unstable: {_preview(small)}",
                      DataWarning, stacklevel=2)
    for d, r in per_dimension.items():
        logger.info("join yield %s: %d/%d (%.0f%%)", d, r["n_joined"], r["n_annotated"], 100 * r["yield"])
    return joined, report


# --- helpers -----------------------------------------------------------------------------

def _read_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ContractError(f"{path}:{line_no}: not valid JSON ({exc.msg})", rows=[line_no]) from exc
            if not isinstance(record, dict):
                raise ContractError(f"{path}:{line_no}: expected a JSON object per line", rows=[line_no])
            records.append(record)
    return records


def _frame(source):
    if isinstance(source, pd.DataFrame):
        return source.copy(), "<DataFrame>"
    return read_table(source), str(source)


def _rename_id(frame, name):
    if "question_id" in frame.columns:
        return frame
    for alias in _ID_ALIASES:
        if alias in frame.columns:
            return frame.rename(columns={alias: "question_id"})
    raise ContractError(f"{name}: missing column 'question_id' (or custom_id / instance_id)", rows=["question_id"])


def _require_columns(frame, columns, what):
    absent = [c for c in columns if c not in frame.columns]
    if absent:
        raise ContractError(f"{what}: missing column(s) {absent}", rows=absent)


def _coerce(series, convert, name, column, frame):
    values, bad = [], []
    for qid, value in zip(frame["question_id"], series):
        try:
            values.append(convert(value))
        except ValueError:
            bad.append((qid, value))
    if bad:
        raise ContractError(f"{name}: invalid {column} values {_preview(bad)}", rows=bad)
    return values


def _is_missing(value):
    return value is None or (np.ndim(value) == 0 and bool(pd.isna(value)))


def _as_id(value):
    if _is_missing(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        return str(bool(value))
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))  # 7.0 from a numeric column is the id 7
    text = str(value)
    return text if text.strip() else None


def _as_outcome(value):
    if _is_missing(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return None
        if text in _TRUE_STRINGS:
            return 1
        if text in _FALSE_STRINGS:
            return 0
        raise ValueError(value)
    if isinstance(value, (int, float, np.integer, np.floating)) and float(value) in (0.0, 1.0):
        return int(value)
    raise ValueError(value)


def _as_bool(value):
    if _is_missing(value):
        return False  # unknown parse status: treat as unusable
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = str(value).strip().lower()
    if text in _TRUE_STRINGS:
        return True
    if text in _FALSE_STRINGS:
        return False
    raise ValueError(value)


def _as_bound(value):
    if _is_missing(value):
        return np.nan
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(value)
    if isinstance(value, str) and not value.strip():
        return np.nan
    return float(value)  # accepts "+3"; raises ValueError on anything non-numeric


def _json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if _is_missing(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _preview(items, limit=10):
    items = list(items)
    shown = ", ".join(map(repr, items[:limit]))
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")
