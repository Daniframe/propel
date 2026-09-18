"""The prompt's byte layout, rubric loading, and the dimension catalogue."""

from pathlib import Path

import pytest

from propensity.annotation.prompts import (
    ANNOTATION_SYSTEM,
    as_single_string,
    build_annotation_prompt,
)
from propensity.annotation.rubrics import (
    RUBRICS_DIR,
    Dimension,
    available_dimensions,
    available_versions,
    check_rubric,
    get_dimension,
    load_dimensions,
    load_presentation,
    load_rubric,
    rubric_path_for,
)
from propensity.errors import ContractError
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


# --- against the rubrics that ship with the package --------------------------------------

def test_the_packaged_rubrics_are_the_default():
    assert RUBRICS_DIR == Path(__file__).resolve().parents[1] / "propensity" / "rubrics"
    assert load_rubric("RA") == load_rubric("RA", RUBRICS_DIR, "v1")
    assert load_presentation() == (RUBRICS_DIR / "presentation.md").read_text(encoding="utf-8")


def test_every_shipped_rubric_builds_a_prompt_that_ends_with_the_question():
    presentation = load_presentation()
    for code in available_dimensions():
        rubric = load_rubric(code)
        _, user = build_annotation_prompt("risk aversion", rubric, presentation, "THE QUESTION")
        assert user.count("</rubric>") == 1, code
        assert user.endswith("Annotate the following task:THE QUESTION"), code
        assert "<FINAL_RANGE>[LB, UB]</FINAL_RANGE>" in user, code


def test_the_shipped_rubrics_are_the_expected_set():
    assert available_dimensions() == ["BR", "Ex", "RA", "Ul"]  # TD is not written yet


def test_rubric_paths_follow_the_convention():
    assert rubric_path_for("RA", "rubrics") == Path("rubrics/RA/RA_v1.md")
    assert rubric_path_for("RA", "rubrics", "v2") == Path("rubrics/RA/RA_v2.md")
    assert rubric_path_for("RA") == RUBRICS_DIR / "RA" / "RA_v1.md"


def test_a_missing_rubric_says_which_ones_exist():
    with pytest.raises(ContractError, match="no rubric for dimension 'TD'.*BR, Ex, RA, Ul"):
        load_rubric("TD")


def test_a_missing_version_says_which_versions_exist():
    with pytest.raises(ContractError, match="no rubric version 'v9' for dimension 'RA'; versions found: v1"):
        load_rubric("RA", version="v9")


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


# --- the dimension catalogue ---------------------------------------------------------------

def catalogue_dir(tmp_path, entries, versions=("v1",)):
    """A rubrics directory with a catalogue, and a rubric file per code and version."""
    (tmp_path / "dimensions.yaml").write_text(entries, encoding="utf-8")
    for code in ("XX", "YY"):
        (tmp_path / code).mkdir(exist_ok=True)
        for version in versions:
            (tmp_path / code / f"{code}_{version}.md").write_text(f"{code} {version}", encoding="utf-8")
    return tmp_path


def test_the_packaged_catalogue_describes_every_dimension():
    catalogue = load_dimensions()
    assert sorted(catalogue) == ["BR", "Ex", "RA", "Ul"]
    assert catalogue["RA"] == Dimension(
        code="RA", name="risk aversion", negative="risk-seeking", positive="risk-averse",
        version="v1", summary=catalogue["RA"].summary)
    assert get_dimension("BR").name == "blue vs red colour preference"


def test_an_unknown_dimension_names_the_known_ones():
    with pytest.raises(ContractError, match="no dimension 'TD' in the catalogue.*known: BR, Ex, RA, Ul"):
        get_dimension("TD")


def test_the_catalogue_sets_the_version_read_by_default(tmp_path):
    rubrics = catalogue_dir(tmp_path, "XX: {name: x trait, negative: less, positive: more, version: v2}\n",
                            versions=("v1", "v2"))
    assert load_rubric("XX", rubrics) == "XX v2"               # the catalogue's version
    assert load_rubric("XX", rubrics, "v1") == "XX v1"         # unless another is asked for
    assert load_rubric("YY", rubrics) == "YY v1"               # not catalogued: v1


def test_versions_sort_by_number_not_by_text(tmp_path):
    rubrics = catalogue_dir(tmp_path, "{}", versions=("v10", "v2", "v1"))
    assert available_versions("XX", rubrics) == ["v1", "v2", "v10"]
    assert available_dimensions(rubrics, version="v10") == ["XX", "YY"]
    assert available_versions("ZZ", rubrics) == []


def test_a_directory_without_a_catalogue_has_no_dimensions(tmp_path):
    assert load_dimensions(tmp_path) == {}


@pytest.mark.parametrize("entries,match", [
    ("XX: {name: x, negative: a, positive: b}\n", r"missing field\(s\) \['version'\]"),
    ("XX: {name: x, negative: a, positive: b, version: v1, verison: v2}\n", r"unknown field\(s\) \['verison'\]"),
    ("XX: just a string\n", "must be a mapping"),
    ("- a list\n", "one entry per dimension code"),
    ("XX: [unclosed\n", "not valid YAML"),
])
def test_a_malformed_catalogue_is_refused_with_the_entry_named(tmp_path, entries, match):
    with pytest.raises(ContractError, match=match):
        load_dimensions(catalogue_dir(tmp_path, entries))


# --- the structure check -------------------------------------------------------------------

GOOD_RUBRIC = """# TEST PROPENSITY

## Definition
The range is where an agent succeeds with at least 50% probability.

## Levels
### Level -3 or below: extreme
### Level -2: strong
### Level -1: mild
### Level 0: none
### Level +1: mild
### Level +2: strong
### Level +3 or above: extreme

## Full Examples
- "a task the trait cannot affect" Propensity range: [-3, +3]
- "a task only the unbiased agent solves" Propensity range: [0, 0]
"""


def test_a_well_formed_rubric_passes_the_structure_check():
    assert check_rubric(GOOD_RUBRIC) == []


@pytest.mark.parametrize("edit,problem", [
    (lambda t: t.replace("# TEST PROPENSITY", "# Test"), "title"),
    (lambda t: t.replace("## Definition", "## Background"), "'## Definition'"),
    (lambda t: t.replace("at least 50% probability", "often"), "propensity range"),
    (lambda t: t.replace("### Level -2: strong\n", ""), "not -3 to +3 in order"),
    (lambda t: t.replace("Level -3 or below", "Level -3"), "level -3 heading is not saturating"),
    (lambda t: t.replace("Level +3 or above", "Level +3"), "level +3 heading is not saturating"),
    (lambda t: t.replace("[-3, +3]", "[-2, +3]"), "no orthogonal"),
    (lambda t: t.replace("[0, 0]", "[0, 1]"), "no degenerate"),
])
def test_the_structure_check_names_each_departure(edit, problem):
    problems = check_rubric(edit(GOOD_RUBRIC))
    assert len(problems) >= 1 and any(problem in found for found in problems), problems
