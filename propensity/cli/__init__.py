"""Command-line entry points: `propel-annotate` and `propel-fit`."""

from pathlib import Path

import yaml


def load_config(path, section=None) -> dict:
    """Reads a YAML settings file, returning {} when it is not there.

    Command-line flags override whatever comes from here. Credentials never live in these
    files: each provider adapter reads its own environment variables (CLAUDE.md §4.1).
    """
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        settings = yaml.safe_load(f) or {}
    return dict(settings.get(section) or {}) if section else dict(settings)
