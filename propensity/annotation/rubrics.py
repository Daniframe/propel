"""Locating and loading rubric files: CLAUDE.md §7.1.

A rubric is the highest-leverage artifact in the project. The annotator reads it verbatim, and
its wording determines every interval ever fitted against it, so nothing here strips,
reformats or re-encodes: files are read as UTF-8 and handed on exactly as they are. The seams
in the assembled prompt (§7.3) are deliberately unspaced and come from these files.
"""

from pathlib import Path

from ..errors import ContractError

DEFAULT_RUBRICS_DIR = "rubrics"
PRESENTATION_FILE = "presentation.md"
DEFAULT_VERSION = "v1"


def rubric_path_for(code: str, rubrics_dir=DEFAULT_RUBRICS_DIR, version=DEFAULT_VERSION) -> Path:
    """The canonical location of one dimension's rubric: rubrics/{CODE}/{CODE}_{version}.md."""
    return Path(rubrics_dir) / code / f"{code}_{version}.md"


def available_dimensions(rubrics_dir=DEFAULT_RUBRICS_DIR, version=DEFAULT_VERSION) -> list[str]:
    """Dimension codes that have a rubric of this version."""
    root = Path(rubrics_dir)
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir()
                  if d.is_dir() and rubric_path_for(d.name, rubrics_dir, version).exists())


def load_rubric(code: str, rubrics_dir=DEFAULT_RUBRICS_DIR, version=DEFAULT_VERSION) -> str:
    """The full text of one dimension's rubric."""
    path = rubric_path_for(code, rubrics_dir, version)
    if not path.exists():
        have = ", ".join(available_dimensions(rubrics_dir, version)) or "none"
        raise ContractError(f"{path}: no rubric for dimension {code!r}; rubrics found for: {have}")
    return _read(path)


def load_presentation(rubrics_dir=DEFAULT_RUBRICS_DIR) -> str:
    """The shared reasoning and output-contract block every dimension uses (§7.2).

    It opens with the closing `</rubric>` tag and ends with "Annotate the following task:", so
    the prompt adds neither.
    """
    return _read(Path(rubrics_dir) / PRESENTATION_FILE)


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
