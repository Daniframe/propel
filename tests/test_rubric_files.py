"""The rubrics that ship with the package, and their catalogue.

A rubric is prompt text: the annotator reads it verbatim, so any change to it changes every
prompt built from it. These tests make every change deliberate, keep the catalogue and the
files in step, and hold every new rubric to the required structure.
"""

import hashlib
import importlib.util
from pathlib import Path

import pytest

from propensity.annotation.rubrics import (
    RUBRICS_DIR,
    available_dimensions,
    available_versions,
    check_rubric,
    load_dimensions,
    rubric_path_for,
)

ROOT = Path(__file__).resolve().parents[1]

# Update a hash only when you mean to change what annotators read, and remember that annotations
# made before and after the change are not comparable. A new version is a new file and a new pin.
PINNED_SHA256 = {
    "RA/RA_v1.md": "eaf6978d3d2228b914ef69333308ec4330bacd6ca3b992ae2e031ba0408cd540",
    "Ex/Ex_v1.md": "dc446ddc4a78c7246f35065dc5873656c4e4028d1a34b05b2a46a30a64635b03",
    "Ul/Ul_v1.md": "0e31ec68be25ae8812d41b2a89f1199f99a229683fdd8d6a3360bdc7b1fa6b7a",
    "BR/BR_v1.md": "98c3fbd56d568fb0ad5b3a4c4a81b9e93a3fe6f8d9070e49285365c48a6fa9c2",
    "presentation.md": "ac528f3004e2501bbc0335d8931f237dd006ffdee8a21744816c73398d6f46a1",
}

# Rubrics that predate the structural checks, and the checks they are known to fail. They stay
# as they are because their wording produced existing annotation data; their next versions must
# pass everything. Nothing may be added here.
KNOWN_GAPS = {
    "BR/BR_v1.md": ("propensity range",),
    "Ex/Ex_v1.md": ("level -3 heading", "level +3 heading", "orthogonal", "degenerate"),
    "Ul/Ul_v1.md": ("orthogonal", "degenerate"),
}


def rubric_files():
    return sorted(path.relative_to(RUBRICS_DIR).as_posix() for path in RUBRICS_DIR.glob("*/*.md"))


# --- bytes ---------------------------------------------------------------------------------

@pytest.mark.parametrize("relpath", sorted(PINNED_SHA256))
def test_rubric_bytes_are_pinned(relpath):
    digest = hashlib.sha256((RUBRICS_DIR / relpath).read_bytes()).hexdigest()
    assert digest == PINNED_SHA256[relpath], (
        f"{relpath} changed. If that was deliberate, update PINNED_SHA256; "
        "check first that no editor added or removed a final newline.")


def test_every_rubric_file_is_pinned():
    assert {*rubric_files(), "presentation.md"} == set(PINNED_SHA256)


@pytest.mark.parametrize("relpath", sorted(PINNED_SHA256))
def test_rubric_is_utf8_with_unix_line_endings(relpath):
    data = (RUBRICS_DIR / relpath).read_bytes()
    data.decode("utf-8")
    assert b"\r" not in data


def test_the_presentation_block_opens_and_closes_as_the_prompt_expects():
    # It closes the <rubric> tag the prompt opens, and the question follows it directly.
    text = (RUBRICS_DIR / "presentation.md").read_text(encoding="utf-8")
    assert text.startswith("</rubric>")
    assert text.endswith("Annotate the following task:")
    assert "<FINAL_RANGE>[LB, UB]</FINAL_RANGE>" in text


# --- structure -----------------------------------------------------------------------------

@pytest.mark.parametrize("relpath", rubric_files())
def test_every_rubric_has_the_required_structure(relpath):
    problems = check_rubric((RUBRICS_DIR / relpath).read_text(encoding="utf-8"))
    known = KNOWN_GAPS.get(relpath, ())
    unexpected = [problem for problem in problems if not any(gap in problem for gap in known)]
    assert not unexpected, f"{relpath}: {unexpected}"
    assert len(problems) == len(known), f"{relpath} fixed a known gap: remove it from KNOWN_GAPS"


# --- the catalogue -------------------------------------------------------------------------

def test_every_rubric_folder_is_catalogued_and_every_entry_has_its_rubric():
    catalogue = load_dimensions()
    assert sorted(catalogue) == available_dimensions()
    for code, dimension in catalogue.items():
        assert dimension.code == code
        assert rubric_path_for(code).exists(), f"{code}: no rubric for its version {dimension.version}"
        assert dimension.version in available_versions(code)


def test_trait_names_are_unique_and_poles_are_given():
    catalogue = load_dimensions()
    names = [dimension.name for dimension in catalogue.values()]
    assert len(names) == len(set(names))
    for dimension in catalogue.values():
        assert dimension.negative and dimension.positive and dimension.summary, dimension.code


def test_the_catalogue_page_in_the_docs_is_up_to_date():
    spec = importlib.util.spec_from_file_location("make_dimensions", ROOT / "docs" / "make_dimensions.py")
    make_dimensions = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make_dimensions)
    page = (ROOT / "docs" / "dimensions.md").read_text(encoding="utf-8")
    assert page == make_dimensions.render(), "run: python docs/make_dimensions.py"
