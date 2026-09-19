"""The public API: what is exported, what the docs promise, and how a name is retired.

docs/stability.md is the promise; these tests keep it and the code from drifting apart. A name
leaving `__all__`, a column changing place, or the page falling behind all fail here.
"""

import re
import warnings
from pathlib import Path

import pytest

import propensity
from propensity import annotation, modelling, providers
from propensity._deprecation import warn_deprecated
from propensity.annotation.runner import ROW_FIELDS
from propensity.errors import PropensityDeprecationWarning
from propensity.modelling.profiles import DIAGNOSTIC_COLUMNS, PROFILE_COLUMNS

STABILITY = Path(__file__).resolve().parents[1] / "docs" / "stability.md"


def documented_lists():
    """The three `text` blocks of docs/stability.md: exports, row fields, profile columns."""
    blocks = re.findall(r"```text\n(.*?)```", STABILITY.read_text(encoding="utf-8"), re.S)
    assert len(blocks) == 3, f"expected three lists in {STABILITY.name}, found {len(blocks)}"
    return [block.split() for block in blocks]


@pytest.mark.parametrize("module", [propensity, annotation, modelling, providers])
def test_every_exported_name_exists(module):
    assert module.__all__ == sorted(module.__all__, key=str.lower), f"{module.__name__}: sort __all__"
    assert len(set(module.__all__)) == len(module.__all__), f"{module.__name__}: duplicate names"
    missing = [name for name in module.__all__ if not hasattr(module, name)]
    assert not missing, f"{module.__name__}: {missing}"


def test_star_import_gives_exactly_the_stable_api():
    namespace = {}
    exec("from propensity import *", namespace)  # noqa: S102
    assert sorted(n for n in namespace if not n.startswith("__")) == sorted(propensity.__all__)


def test_the_submodules_export_what_the_package_does():
    from_submodules = set(annotation.__all__) | set(modelling.__all__) | set(providers.__all__)
    only_at_top = set(propensity.__all__) - from_submodules
    assert only_at_top <= {"ContractError", "DataWarning", "ParseError",
                           "PropensityDeprecationWarning", "PropensityError", "ProviderError"}


def test_the_documented_api_is_the_exported_one():
    exports, _, _ = documented_lists()
    assert exports == sorted(propensity.__all__, key=str.lower), (
        "docs/stability.md lists a different API; update the page or the exports")


def test_the_documented_file_columns_are_the_real_ones():
    _, row_fields, profile_columns = documented_lists()
    assert row_fields == list(ROW_FIELDS)
    assert profile_columns == PROFILE_COLUMNS + DIAGNOSTIC_COLUMNS


def test_a_deprecation_reaches_the_user_by_default():
    assert issubclass(PropensityDeprecationWarning, FutureWarning)  # DeprecationWarning is hidden
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        warn_deprecated("old_name()", instead="new_name()", removed_in="0.3.0")
    assert len(caught) == 1 and caught[0].category is PropensityDeprecationWarning
    assert str(caught[0].message) == ("old_name() is deprecated and will be removed in 0.3.0; "
                                      "use new_name() instead")


def test_nothing_is_deprecated_yet():
    # When something is, list it here and in the changelog, and give it a removal version.
    source = (Path(propensity.__file__).parent).rglob("*.py")
    users = [path.name for path in source
             if "warn_deprecated(" in path.read_text(encoding="utf-8") and path.name != "_deprecation.py"]
    assert users == []
