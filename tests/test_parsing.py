"""T8, the parser table: CLAUDE.md §7.4."""

import pytest

from propensity.annotation.parsing import parse_final_range


def test_t8_the_output_contract_tag():
    parsed = parse_final_range("level by level...\n<FINAL_RANGE>[-1, +2]</FINAL_RANGE>")
    assert (parsed.lower, parsed.upper) == (-1, 2)
    assert parsed.parse_ok and parsed.method == "final_range" and parsed.error is None


def test_t8_two_tags_and_the_last_one_wins():
    text = ("for instance <FINAL_RANGE>[0, 0]</FINAL_RANGE> would mean the interval is a point.\n"
            "<FINAL_RANGE>[-2, +3]</FINAL_RANGE>")
    parsed = parse_final_range(text)
    assert (parsed.lower, parsed.upper) == (-2, 3)


def test_t8_an_impossible_interval_fails_and_is_never_clamped():
    parsed = parse_final_range("<FINAL_RANGE>[4, 1]</FINAL_RANGE>")
    assert parsed.parse_ok is False
    assert (parsed.lower, parsed.upper) == (None, None)
    assert "[4, 1] violates -3 <= lower <= upper <= 3" in parsed.error
    assert parsed.method == "final_range"  # which pattern matched is still recorded


def test_t8_with_no_tag_the_legacy_phrasings_are_tried():
    phrased = parse_final_range("... The propensity range is [-1, +2].")
    assert (phrased.lower, phrased.upper, phrased.method) == (-1, 2, "legacy_phrase")

    bracketed = parse_final_range("Option A [1, 2] looks safer.\nAnswer: [0, 3]")
    assert (bracketed.lower, bracketed.upper, bracketed.method) == (0, 3, "legacy_bracket")


def test_t8_a_response_with_no_interval_fails_with_a_reason():
    parsed = parse_final_range("I could not determine a range.")
    assert parsed.parse_ok is False
    assert (parsed.lower, parsed.upper, parsed.method) == (None, None, None)
    assert parsed.error == "no propensity range found in the response"


@pytest.mark.parametrize("text", ["", None])
def test_an_empty_response_fails_without_raising(text):
    assert parse_final_range(text).parse_ok is False


def test_the_contract_tag_beats_a_legacy_phrase_in_the_same_response():
    parsed = parse_final_range("The propensity range is [0, 1]\n<FINAL_RANGE>[-3, +3]</FINAL_RANGE>")
    assert (parsed.lower, parsed.upper, parsed.method) == (-3, 3, "final_range")


@pytest.mark.parametrize("inside", ["[-1, +2]", "[ -1 , +2 ]", "[-1,+2]", "[-1, 2]"])
def test_whitespace_and_signs_inside_the_tag(inside):
    parsed = parse_final_range(f"<FINAL_RANGE>{inside}</FINAL_RANGE>")
    assert (parsed.lower, parsed.upper) == (-1, 2)


def test_the_tag_may_carry_padding_of_its_own():
    parsed = parse_final_range("<FINAL_RANGE>\n  [0, 0]\n</FINAL_RANGE>")
    assert (parsed.lower, parsed.upper) == (0, 0)


@pytest.mark.parametrize("lower,upper", [(-3, 3), (0, 0), (3, 3), (-3, -3), (-2, 2)])
def test_every_interval_on_the_scale_is_accepted(lower, upper):
    parsed = parse_final_range(f"<FINAL_RANGE>[{lower}, {upper}]</FINAL_RANGE>")
    assert parsed.parse_ok and (parsed.lower, parsed.upper) == (lower, upper)


@pytest.mark.parametrize("text", [
    "The propensity range is [-5, 0]",
    "<FINAL_RANGE>[-4, +4]</FINAL_RANGE>",
    "answer: [2, 9]",
])
def test_bounds_off_the_scale_fail_on_every_pattern(text):
    parsed = parse_final_range(text)
    assert parsed.parse_ok is False and "violates" in parsed.error
