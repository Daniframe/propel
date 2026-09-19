"""Command-line entry points: `propel-annotate` and `propel-fit`."""

from pathlib import Path

import yaml


def load_config(path, section=None) -> dict:
    """Reads a YAML settings file, returning {} when it is not there.

    Command-line flags override whatever comes from here. Credentials never live in these
    files: each provider reads its own environment variables.
    """
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        settings = yaml.safe_load(f) or {}
    return dict(settings.get(section) or {}) if section else dict(settings)


def load_dotenv_if_available() -> bool:
    """Loads a .env file when python-dotenv is installed, for provider credentials.

    The file is looked for in the working directory, then in each directory above it. (Left
    to itself, python-dotenv would start from this module's folder, which for an installed
    package is inside the environment, never where the user works.) Variables already set in
    the environment are kept. Optional on purpose: the adapters read the environment, and how
    it got populated is not their business. Returns whether a file was found and loaded.
    """
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return False
    path = find_dotenv(usecwd=True)
    return bool(path) and bool(load_dotenv(path))
