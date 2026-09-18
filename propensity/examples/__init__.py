"""The synthetic example data the tutorials use, shipped with the package.

    python -m propensity.examples [DIR] [--force]

copies it into DIR (default `examples`), so the tutorials run from any working directory.
"""

import shutil
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent
FILES = ("items_RA.jsonl", "annotations_RA.jsonl", "outcomes_long.csv", "outcomes_wide.csv",
         "README.md")


def copy_examples(dest="examples", *, overwrite: bool = False) -> dict[str, list[Path]]:
    """Copy the example files into `dest`, creating it if needed. A file already there is kept
    unless `overwrite` is true. Returns {"written": [...], "kept": [...]}."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    done = {"written": [], "kept": []}
    for name in FILES:
        target = dest / name
        if target.exists() and not overwrite:
            done["kept"].append(target)
            continue
        shutil.copyfile(EXAMPLES_DIR / name, target)
        done["written"].append(target)
    return done
