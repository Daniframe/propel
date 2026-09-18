"""python -m propensity.examples [DIR] [--force]: copy the example data into DIR."""

import argparse
import sys

from . import copy_examples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m propensity.examples",
        description="Copy PROPEL's synthetic example data into a directory.")
    parser.add_argument("dir", nargs="?", default="examples",
                        help="where to put the files (default: examples)")
    parser.add_argument("--force", action="store_true", help="overwrite files already there")
    args = parser.parse_args(argv)

    done = copy_examples(args.dir, overwrite=args.force)
    for path in done["kept"]:
        print(f"kept {path.as_posix()} (already there; --force overwrites it)")
    print(f"wrote {len(done['written'])} example files to {args.dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
