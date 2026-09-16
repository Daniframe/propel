"""Rubric files are validated prompt text (CLAUDE.md §7): the annotator reads them verbatim,
so any change to them changes every prompt built from them. These tests make that deliberate.
"""

import hashlib
from pathlib import Path

import pytest

RUBRICS = Path(__file__).resolve().parents[1] / "rubrics"

# Copied from neurips/rubrics with only CRLF -> LF. Update a hash only when you mean to change
# what annotators read, and remember that annotations made before and after are not comparable.
PINNED_SHA256 = {
    "RA/RA_v1.md": "eaf6978d3d2228b914ef69333308ec4330bacd6ca3b992ae2e031ba0408cd540",
    "Ex/Ex_v1.md": "dc446ddc4a78c7246f35065dc5873656c4e4028d1a34b05b2a46a30a64635b03",
    "Ul/Ul_v1.md": "0e31ec68be25ae8812d41b2a89f1199f99a229683fdd8d6a3360bdc7b1fa6b7a",
    "BR/BR_v1.md": "98c3fbd56d568fb0ad5b3a4c4a81b9e93a3fe6f8d9070e49285365c48a6fa9c2",
    "presentation.md": "ac528f3004e2501bbc0335d8931f237dd006ffdee8a21744816c73398d6f46a1",
}


@pytest.mark.parametrize("relpath", sorted(PINNED_SHA256))
def test_rubric_bytes_are_pinned(relpath):
    digest = hashlib.sha256((RUBRICS / relpath).read_bytes()).hexdigest()
    assert digest == PINNED_SHA256[relpath], (
        f"rubrics/{relpath} changed. If that was deliberate, update PINNED_SHA256; "
        "check first that no editor added or removed a final newline."
    )


@pytest.mark.parametrize("relpath", sorted(PINNED_SHA256))
def test_rubric_is_utf8_with_unix_line_endings(relpath):
    data = (RUBRICS / relpath).read_bytes()
    data.decode("utf-8")
    assert b"\r" not in data


def test_every_rubric_file_is_pinned():
    found = {p.relative_to(RUBRICS).as_posix() for p in RUBRICS.rglob("*.md")}
    assert found == set(PINNED_SHA256)


def test_presentation_block_opens_and_closes_as_the_prompt_expects():
    # §7.2: it closes the <rubric> tag the prompt opens, and the question follows it directly.
    text = (RUBRICS / "presentation.md").read_text(encoding="utf-8")
    assert text.startswith("</rubric>")
    assert text.endswith("Annotate the following task:")
    assert "<FINAL_RANGE>[LB, UB]</FINAL_RANGE>" in text
