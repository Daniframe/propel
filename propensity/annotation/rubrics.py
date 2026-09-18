"""The rubrics, and the catalogue of dimensions they belong to.

The rubrics ship inside the package, in `propensity/rubrics/`:

    presentation.md              the reasoning procedure and output contract every rubric shares
    dimensions.yaml              the catalogue: each dimension's trait name, poles and version
    {CODE}/{CODE}_{version}.md   one rubric per dimension and version

Every function that takes `rubrics_dir` reads another directory with the same layout instead;
by default it reads the packaged one. A directory of your own needs its own presentation.md,
and a dimensions.yaml only if it should supply trait names and default versions.

A rubric is read as stored: nothing strips, reformats or re-encodes it, because its text is the
prompt, and whether a file ends in a newline changes every prompt built from it. Only Windows
line endings are read as plain newlines, so a checkout on any platform builds the same prompts.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..errors import ContractError

RUBRICS_DIR = Path(__file__).resolve().parent.parent / "rubrics"
PRESENTATION_FILE = "presentation.md"
CATALOGUE_FILE = "dimensions.yaml"
DEFAULT_VERSION = "v1"
_FIELDS = ("name", "negative", "positive", "version", "summary")
_REQUIRED = ("name", "negative", "positive", "version")


@dataclass(frozen=True)
class Dimension:
    """One catalogue entry.

    code: the dimension's short code, also its rubric folder's name.
    name: the trait as the prompt words it ("...showing bias towards {name}").
    negative, positive: what the -3 and +3 ends of the scale mean.
    version: the rubric version used unless another is asked for.
    summary: one line describing the trait.
    """

    code: str
    name: str
    negative: str
    positive: str
    version: str
    summary: str = ""


def load_dimensions(rubrics_dir=None) -> dict[str, Dimension]:
    """The catalogue of a rubrics directory, keyed by code; empty when it has no dimensions.yaml."""
    path = _root(rubrics_dir) / CATALOGUE_FILE
    if not path.exists():
        return {}
    try:
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ContractError(f"{path}: not valid YAML ({exc})") from None
    if not isinstance(entries, dict):
        raise ContractError(f"{path}: expected one entry per dimension code")

    dimensions = {}
    for code, entry in entries.items():
        if not isinstance(entry, dict):
            raise ContractError(f"{path}: entry {code!r} must be a mapping of {', '.join(_FIELDS)}",
                                rows=[code])
        unknown = sorted(set(entry) - set(_FIELDS))
        missing = [field for field in _REQUIRED if not str(entry.get(field) or "").strip()]
        if unknown or missing:
            problems = ([f"unknown field(s) {unknown}"] if unknown else []) + \
                       ([f"missing field(s) {missing}"] if missing else [])
            raise ContractError(f"{path}: entry {code!r} has {' and '.join(problems)}", rows=[code])
        dimensions[str(code)] = Dimension(code=str(code), **{k: str(v) for k, v in entry.items()})
    return dimensions


def get_dimension(code: str, rubrics_dir=None) -> Dimension:
    """One catalogue entry; ContractError naming the known codes when there is none."""
    dimensions = load_dimensions(rubrics_dir)
    if code not in dimensions:
        known = ", ".join(sorted(dimensions)) or "none"
        raise ContractError(f"no dimension {code!r} in the catalogue of {_root(rubrics_dir)}; "
                            f"known: {known}", rows=[code])
    return dimensions[code]


def rubric_path_for(code: str, rubrics_dir=None, version=None) -> Path:
    """Where one dimension's rubric lives: {rubrics_dir}/{CODE}/{CODE}_{version}.md. Without a
    version, the catalogue's current one (v1 for a dimension it does not list)."""
    return _root(rubrics_dir) / code / f"{code}_{version or _current_version(code, rubrics_dir)}.md"


def available_dimensions(rubrics_dir=None, version=None) -> list[str]:
    """Codes with at least one rubric file, or with a rubric of `version` when one is given."""
    root = _root(rubrics_dir)
    if not root.is_dir():
        return []
    return sorted(folder.name for folder in root.iterdir() if folder.is_dir() and (
        available_versions(folder.name, rubrics_dir) if version is None
        else (folder / f"{folder.name}_{version}.md").exists()))


def available_versions(code: str, rubrics_dir=None) -> list[str]:
    """The versions of one dimension's rubric on disk, oldest first (v2 before v10)."""
    folder = _root(rubrics_dir) / code
    versions = [path.stem[len(code) + 1:] for path in folder.glob(f"{code}_*.md")] if folder.is_dir() else []
    return sorted(versions, key=lambda v: [int(part) if part.isdigit() else part
                                           for part in re.split(r"(\d+)", v)])


def load_rubric(code: str, rubrics_dir=None, version=None) -> str:
    """The full text of one dimension's rubric; without a version, the catalogue's current one."""
    path = rubric_path_for(code, rubrics_dir, version)
    if not path.exists():
        versions = available_versions(code, rubrics_dir)
        if versions:
            raise ContractError(f"{path}: no rubric version {path.stem[len(code) + 1:]!r} for "
                                f"dimension {code!r}; versions found: {', '.join(versions)}")
        have = ", ".join(available_dimensions(rubrics_dir)) or "none"
        raise ContractError(f"{path}: no rubric for dimension {code!r}; rubrics found for: {have}")
    return _read(path)


def load_presentation(rubrics_dir=None) -> str:
    """The reasoning procedure and output contract every dimension shares.

    It opens with the closing `</rubric>` tag and ends with "Annotate the following task:", so
    the prompt adds neither.
    """
    return _read(_root(rubrics_dir) / PRESENTATION_FILE)


def check_rubric(text: str) -> list[str]:
    """The ways a rubric departs from the required structure; empty when it has none.

    Required: a `# ... PROPENSITY` title; `## Definition`, `## Levels` and `## Full examples`
    sections in that order; the definition's propensity-range sentence ("...with at least 50%
    probability..."); seven `### Level` headings from -3 to +3 in order, with -3 and +3 written
    as saturating ("-3 or below", "+3 or above"); and full examples that include an orthogonal
    [-3, +3] case and a degenerate [0, 0] case.
    """
    problems = []
    lines = text.splitlines()
    if not lines or not re.fullmatch(r"# .+ PROPENSITY\s*", lines[0]):
        problems.append("the first line is not a '# ... PROPENSITY' title")

    sections = [m.group(1).strip().lower() for m in re.finditer(r"(?m)^## (.+)$", text)]
    order = [name for name in ("definition", "levels", "full examples") if name in sections]
    for name in ("definition", "levels", "full examples"):
        if name not in sections:
            problems.append(f"no '## {name.capitalize()}' section")
    if order != sorted(order, key=sections.index):
        problems.append("the sections are not in the order Definition, Levels, Full examples")

    definition = _section(text, "definition")
    if "at least 50% probability" not in definition:
        problems.append("the definition does not state the propensity range (\"...with at least "
                        "50% probability...\")")

    levels = re.findall(r"(?m)^### Level ([+-]?\d)(.*)$", _section(text, "levels"))
    found = [int(level) for level, _ in levels]
    if found != [-3, -2, -1, 0, 1, 2, 3]:
        problems.append(f"the '### Level' headings are {found}, not -3 to +3 in order")
    else:
        if "or below" not in levels[0][1]:
            problems.append("the level -3 heading is not saturating ('### Level -3 or below: ...')")
        if "or above" not in levels[-1][1]:
            problems.append("the level +3 heading is not saturating ('### Level +3 or above: ...')")

    examples = _section(text, "full examples")
    if not re.search(r"\[\s*-3\s*,\s*\+?3\s*\]", examples):
        problems.append("the full examples have no orthogonal [-3, +3] case")
    if not re.search(r"\[\s*[+-]?0\s*,\s*[+-]?0\s*\]", examples):
        problems.append("the full examples have no degenerate [0, 0] case")
    return problems


def _section(text, name):
    """The body of a `## name` section, up to the next `## ` heading."""
    match = re.search(rf"(?ims)^## {re.escape(name)}\s*$(.*?)(?=^## |\Z)", text)
    return match.group(1) if match else ""


def _root(rubrics_dir) -> Path:
    return RUBRICS_DIR if rubrics_dir is None else Path(rubrics_dir)


def _current_version(code, rubrics_dir):
    entry = load_dimensions(rubrics_dir).get(code)
    return entry.version if entry else DEFAULT_VERSION


def _read(path: Path) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise ContractError(f"{path}: no such file") from None
    except UnicodeDecodeError as exc:
        raise ContractError(f"{path}: not valid UTF-8 ({exc.reason}). Rubrics must be UTF-8; a "
                            "file written as ISO-8859-1 mangles dashes and quotes inside the "
                            "prompt, so fix the file rather than the reader.") from None
