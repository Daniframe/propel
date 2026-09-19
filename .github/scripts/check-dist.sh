#!/usr/bin/env bash
# Check built distributions the way a user meets them: install the wheel into a fresh virtual
# environment, run the sdist's test suite against that installation (the sdist's own source
# package is removed first), and smoke-test the commands from an empty directory.
#
#   .github/scripts/check-dist.sh DIST_DIR EXTRAS [CONSTRAINTS]
#
# EXTRAS is e.g. "all,dev" or "dev" (core only). Runs on Linux, macOS and Windows (Git Bash).
set -euo pipefail

dist=$(cd "$1" && pwd)
extras=$2
constraints=${3:-}
work=$(mktemp -d)

# Git Bash hands Python POSIX paths it cannot read, so anything passed to Python is converted.
native() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi; }

python -m venv "$(native "$work")/venv"
if [ -x "$work/venv/bin/python" ]; then bin="$work/venv/bin"; else bin="$work/venv/Scripts"; fi
py="$bin/python"
"$py" -m pip install --quiet --upgrade pip

wheel=$(native "$(ls "$dist"/propensity-*.whl)")
sdist=$(native "$(ls "$dist"/propensity-*.tar.gz)")
if [ -n "$constraints" ]; then
  "$py" -m pip install --quiet "$wheel[$extras]" -c "$(native "$constraints")"
else
  "$py" -m pip install --quiet "$wheel[$extras]"
fi
"$py" -c "import sys, propensity; print('installed propensity', propensity.__version__, 'on Python', sys.version.split()[0])"

# The sdist's tests, run against the installed wheel.
"$py" - "$sdist" "$(native "$work")/sdist" <<'EOF'
import shutil, sys, tarfile
from pathlib import Path
archive, target = sys.argv[1], Path(sys.argv[2])
with tarfile.open(archive) as tar:
    tar.extractall(target.parent / "unpacked", filter="data")
root = next((target.parent / "unpacked").iterdir())
shutil.move(str(root), target)
shutil.rmtree(target / "propensity")  # so the tests import the installed package
EOF
(cd "$work/sdist" && "$py" -c "import propensity; assert 'site-packages' in propensity.__file__, propensity.__file__" \
  && "$py" -m pytest -q -W error -p no:cacheprovider)

# The commands, from an empty directory.
mkdir "$work/user" && cd "$work/user"
"$bin/propel-annotate" --version
"$bin/propel-fit" --version
"$py" -m propensity.examples
"$bin/propel-annotate" run --instances examples/items_RA.jsonl --dimension RA --out out/RA.jsonl \
  --provider mock --model mock-1
plots=""  # a plain string: macOS's bash 3.2 rejects an empty array under set -u
if "$py" -c "import matplotlib" 2>/dev/null; then plots="--plots out/plots"; fi
"$bin/propel-fit" --annotations examples/annotations_RA.jsonl --outcomes examples/outcomes_long.csv \
  --out out/profiles.csv $plots
"$py" -c "import pandas as pd; print(pd.read_csv('out/profiles.csv')[['subject_id', 'theta', 'ci95_lower', 'ci95_upper']].round(2).to_string(index=False))"
