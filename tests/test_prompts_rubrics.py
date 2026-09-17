"""The prompt's byte layout (§7.3) and rubric loading (§7.1)."""

from pathlib import Path

import pytest

from propensity.annotation.prompts import (
    ANNOTATION_SYSTEM,
    as_single_string,
    build_annotation_prompt,
)
from propensity.annotation.rubrics import (
    available_dimensions,
    load_presentation,
    load_rubric,
    rubric_path_for,
)
from propensity.errors import ContractError

REPO_RUBRICS = Path(__file__).resolve().parents[1] / "rubrics"
PREAMBLE = ("The following is a rubric for determining the propensity of showing bias "
            "towards risk aversion:\n\n<rubric>\n")


def test_the_prompt_is_the_four_pieces_and_nothing_else():
    rubric, presentation, question = "RUBRIC TEXT", "</rubric>\nprocedure", "Q?"
    system, user = build_annotation_prompt("risk aversion", rubric, presentation, question)

    assert system == ANNOTATION_SYSTEM
    assert user == PREAMBLE + rubric + presentation + question  # no separators at the seams
    assert user.startswith(PREAMBLE) and user.endswith(question)
    assert len(user) == len(PREAMBLE) + len(rubric) + len(presentation) + len(question)


def test_the_closing_rubric_tag_comes_from_the_presentation_block_only():
    _, user = build_annotation_prompt("risk aversion", "R", "</rubric>\nP", "Q")
    assert user.count("</rubric>") == 1  # the presentation block supplies it, the prompt does not
    assert user.count("<rubric>") == 1   # "</rubric>" does not contain "<rubric>"


def test_as_single_string_joins_without_a_separator():
    system, user = build_annotation_prompt("risk aversion", "R", "</rubric>", "Q")
    assert as_single_string(system, user) == system + user


def test_the_name_of_the_trait_is_the_only_moving_part_of_the_preamble():
    _, user = build_annotation_prompt("blue vs red colour preference", "R", "</rubric>", "Q")
    assert user.startswith("The following is a rubric for determining the propensity of showing "
                           "bias towards blue vs red colour preference:\n\n<rubric>\n")


# --- against the rubric files that ship with the repo ------------------------------------

def test_every_shipped_rubric_builds_a_prompt_that_ends_with_the_question():
    presentation = load_presentation(REPO_RUBRICS)
    for code in available_dimensions(REPO_RUBRICS):
        rubric = load_rubric(code, REPO_RUBRICS)
        _, user = build_annotation_prompt("risk aversion", rubric, presentation, "THE QUESTION")
        assert user.count("</rubric>") == 1, code
        assert user.endswith("Annotate the following task:THE QUESTION"), code
        assert "<FINAL_RANGE>[LB, UB]</FINAL_RANGE>" in user, code


def test_the_shipped_rubrics_are_the_expected_set():
    assert available_dimensions(REPO_RUBRICS) == ["BR", "Ex", "RA", "Ul"]  # TD is not written yet


def test_rubric_paths_follow_the_convention():
    assert rubric_path_for("RA", "rubrics") == Path("rubrics/RA/RA_v1.md")
    assert rubric_path_for("RA", "rubrics", "v2") == Path("rubrics/RA/RA_v2.md")


def test_a_missing_rubric_says_which_ones_exist():
    with pytest.raises(ContractError, match="no rubric for dimension 'TD'.*BR, Ex, RA, Ul"):
        load_rubric("TD", REPO_RUBRICS)


def test_rubrics_are_read_whole_and_untouched(tmp_path):
    (tmp_path / "XX").mkdir()
    body = "# XX PROPENSITY\n\n  indented \ttab\ttext  \nno final newline"
    (tmp_path / "XX" / "XX_v1.md").write_text(body, encoding="utf-8", newline="")
    assert load_rubric("XX", tmp_path) == body


def test_a_rubric_that_is_not_utf8_is_refused(tmp_path):
    (tmp_path / "XX").mkdir()
    (tmp_path / "XX" / "XX_v1.md").write_bytes(b"an em dash \x97 written as ISO-8859-1")
    with pytest.raises(ContractError, match="not valid UTF-8"):
        load_rubric("XX", tmp_path)


def test_a_missing_presentation_block_is_refused(tmp_path):
    with pytest.raises(ContractError, match="no such file"):
        load_presentation(tmp_path)


def test_no_rubrics_directory_means_no_dimensions(tmp_path):
    assert available_dimensions(tmp_path / "nowhere") == []
