import json
import warnings

import numpy as np
import pandas as pd
import pytest

from propensity.errors import ContractError, DataWarning
from propensity.modelling.io import (
    join_annotations_outcomes,
    load_annotations,
    load_instances,
    load_outcomes,
    read_table,
    write_table,
)


def jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def text(path, content):
    path.write_text(content, encoding="utf-8")
    return path


def records(frame):
    return frame.to_dict(orient="records")


def tidy_annotations(ids, dimension="RA", lower=-1.0, upper=2.0):
    return pd.DataFrame({"question_id": ids, "dimension": dimension, "lower": lower,
                         "upper": upper, "parse_ok": True})


def tidy_outcomes(ids, subject="m", outcome=1):
    return pd.DataFrame({"question_id": ids, "subject_id": subject, "outcome": outcome})


# --- T10: contract validation ------------------------------------------------------------

def test_t10_a_probability_outcome_is_rejected_and_named(tmp_path):
    path = text(tmp_path / "o.csv", "question_id,subject_id,outcome\nq1,gpt,1\nq2,gpt,0.7\nq3,gpt,0\n")
    with pytest.raises(ContractError, match="0 or 1") as err:
        load_outcomes(path)
    assert err.value.rows == [("q2", "gpt", "0.7")]
    assert "q2" in str(err.value)


def test_t10_a_duplicate_question_subject_pair_is_rejected_and_named(tmp_path):
    path = text(tmp_path / "o.csv", "question_id,subject_id,outcome\nq1,gpt,1\nq1,gpt,0\nq1,llama,1\n")
    with pytest.raises(ContractError, match="duplicate") as err:
        load_outcomes(path)
    assert err.value.rows == [("q1", "gpt")]


@pytest.mark.parametrize("content,column", [
    ("question_id,subject_id\nq1,gpt\n", "outcome"),
    ("question_id,outcome\nq1,1\n", "subject_id"),
    ("subject_id,outcome\ngpt,1\n", "question_id"),
    ("question_id,score\nq1,1\n", "outcome"),
])
def test_t10_a_missing_column_is_rejected_and_named(tmp_path, content, column):
    with pytest.raises(ContractError, match=column) as err:
        load_outcomes(text(tmp_path / "o.csv", content))
    assert column in err.value.rows


def test_t10_wide_outcomes_with_a_probability_are_rejected(tmp_path):
    path = text(tmp_path / "o.csv", "question_id,gpt_outcome\nq1,1\nq2,0.5\n")
    with pytest.raises(ContractError) as err:
        load_outcomes(path)
    assert err.value.rows == [("q2", "gpt", "0.5")]


# --- T11: legacy shapes normalise to the tidy form ---------------------------------------

def test_t11_wide_outcomes_melt_to_long_form(tmp_path):
    path = text(tmp_path / "o.csv", "question_id,4o_RA_0_outcome,llama33_RA_+2_outcome\nRA_0,1,1\nRA_1,0,1\n")
    assert records(load_outcomes(path)) == [
        {"question_id": "RA_0", "subject_id": "4o_RA_0", "outcome": 1},
        {"question_id": "RA_1", "subject_id": "4o_RA_0", "outcome": 0},
        {"question_id": "RA_0", "subject_id": "llama33_RA_+2", "outcome": 1},
        {"question_id": "RA_1", "subject_id": "llama33_RA_+2", "outcome": 1},
    ]


EXPECTED_RA = [
    {"question_id": "q1", "dimension": "RA", "lower": -1.0, "upper": 2.0, "parse_ok": True},
    {"question_id": "q2", "dimension": "RA", "lower": 0.0, "upper": 3.0, "parse_ok": True},
]


def test_t11_canonical_annotations(tmp_path):
    path = jsonl(tmp_path / "a.jsonl", [
        {"question_id": "q1", "dimension": "RA", "lower": -1, "upper": 2, "annotator": "openai:gpt-4.1",
         "explanation": "...", "parse_ok": True},
        {"question_id": "q2", "dimension": "RA", "lower": 0, "upper": 3, "annotator": "openai:gpt-4.1",
         "explanation": "...", "parse_ok": True},
    ])
    assert records(load_annotations(path)) == EXPECTED_RA


def test_t11_propensity_lower_upper(tmp_path):
    path = jsonl(tmp_path / "a.jsonl", [
        {"question_id": "q1", "propensity_lower": -1, "propensity_upper": 2, "raw_annotation_response": "..."},
        {"question_id": "q2", "propensity_lower": 0, "propensity_upper": 3, "raw_annotation_response": "..."},
    ])
    assert records(load_annotations(path, dimension="RA")) == EXPECTED_RA


def test_t11_lower_bound_upper_bound_in_csv(tmp_path):
    path = text(tmp_path / "a.csv", "question_id,lower_bound,upper_bound\nq1,-1,+2\nq2,0,3\n")
    assert records(load_annotations(path, dimension="RA")) == EXPECTED_RA


def test_t11_wide_dimension_columns_melt_to_one_row_per_dimension(tmp_path):
    path = jsonl(tmp_path / "a.jsonl", [
        {"question_id": "q1", "RA_l": -1, "RA_u": 2, "Ex_l": 0, "Ex_u": 0},
        {"question_id": "q2", "RA_l": 0, "RA_u": 3, "Ex_l": -3, "Ex_u": 3},
    ])
    assert records(load_annotations(path)) == EXPECTED_RA + [
        {"question_id": "q1", "dimension": "Ex", "lower": 0.0, "upper": 0.0, "parse_ok": True},
        {"question_id": "q2", "dimension": "Ex", "lower": -3.0, "upper": 3.0, "parse_ok": True},
    ]
    assert records(load_annotations(path, dimension="RA")) == EXPECTED_RA


@pytest.mark.parametrize("alias", ["custom_id", "instance_id"])
def test_t11_id_aliases_become_question_id(tmp_path, alias):
    path = jsonl(tmp_path / "a.jsonl", [{alias: "q1", "dimension": "RA", "lower": -1, "upper": 2},
                                        {alias: "q2", "dimension": "RA", "lower": 0, "upper": 3}])
    assert records(load_annotations(path)) == EXPECTED_RA


# --- T12: join yield ---------------------------------------------------------------------

def test_t12_a_half_mismatched_join_is_reported_and_warned():
    annotations = tidy_annotations([f"q{i}" for i in range(100)])
    outcomes = tidy_outcomes([f"q{i}" for i in range(50, 150)])

    with pytest.warns(DataWarning, match=r"RA: 50% \(50 of 100"):
        joined, report = join_annotations_outcomes(annotations, outcomes)

    assert len(joined) == 50
    assert report["per_dimension"]["RA"] == {"n_annotated": 100, "n_joined": 50, "yield": 0.5}
    assert report["n_unmatched_outcome_ids"] == 50


def test_a_complete_join_does_not_warn_about_yield():
    ids = [f"q{i}" for i in range(60)]
    with warnings.catch_warnings():
        warnings.simplefilter("error", DataWarning)
        joined, report = join_annotations_outcomes(tidy_annotations(ids), tidy_outcomes(ids))
    assert report["per_dimension"]["RA"]["yield"] == 1.0
    assert len(joined) == 60


# --- identifiers -------------------------------------------------------------------------

def test_leading_zero_ids_survive_both_formats(tmp_path):
    csv = text(tmp_path / "o.csv", "question_id,subject_id,outcome\n007,m,1\n")
    js = jsonl(tmp_path / "a.jsonl", [{"question_id": "007", "dimension": "RA", "lower": 0, "upper": 1}])
    assert load_outcomes(csv)["question_id"].tolist() == ["007"]
    assert load_annotations(js)["question_id"].tolist() == ["007"]


def test_integer_ids_in_json_join_string_ids_in_csv(tmp_path):
    annotations = load_annotations(jsonl(tmp_path / "a.jsonl", [
        {"question_id": i, "propensity_lower": -1, "propensity_upper": 1} for i in range(60)]), dimension="RA")
    outcomes = load_outcomes(text(tmp_path / "o.csv", "question_id,m_outcome\n" +
                                  "".join(f"{i},1\n" for i in range(60))))
    joined, report = join_annotations_outcomes(annotations, outcomes)
    assert report["per_dimension"]["RA"]["yield"] == 1.0
    assert len(joined) == 60


def test_join_rejects_duplicate_keys_in_frames_built_by_hand():
    ids = [f"q{i}" for i in range(60)]
    with pytest.raises(ContractError, match="duplicate"):
        join_annotations_outcomes(tidy_annotations(ids + ["q0"]), tidy_outcomes(ids))
    with pytest.raises(ContractError, match="duplicate") as err:
        join_annotations_outcomes(tidy_annotations(ids), tidy_outcomes(ids + ["q5"]))
    assert err.value.rows == [("q5", "m")]


def test_join_normalises_ids_in_frames_built_by_hand():
    annotations = tidy_annotations(list(range(60)))
    outcomes = tidy_outcomes([str(i) for i in range(60)])
    joined, _ = join_annotations_outcomes(annotations, outcomes)
    assert len(joined) == 60


# --- outcomes ----------------------------------------------------------------------------

def test_accepted_outcome_spellings(tmp_path):
    path = jsonl(tmp_path / "o.jsonl", [
        {"question_id": "a", "subject_id": "m", "outcome": True},
        {"question_id": "b", "subject_id": "m", "outcome": False},
        {"question_id": "c", "subject_id": "m", "outcome": "1"},
        {"question_id": "d", "subject_id": "m", "outcome": "0"},
        {"question_id": "e", "subject_id": "m", "outcome": 1.0},
        {"question_id": "f", "subject_id": "m", "outcome": 0},
        {"question_id": "g", "subject_id": "m", "outcome": "TRUE"},
    ])
    assert load_outcomes(path)["outcome"].tolist() == [1, 0, 1, 0, 1, 0, 1]


def test_missing_outcomes_are_dropped_not_zero_filled(tmp_path):
    path = text(tmp_path / "o.csv", "question_id,a_outcome,b_outcome\nq1,1,\nq2,,0\nq3,1,1\n")
    tidy = load_outcomes(path)
    assert sorted(map(tuple, tidy.to_numpy().tolist())) == [
        ("q1", "a", 1), ("q2", "b", 0), ("q3", "a", 1), ("q3", "b", 1)]


def test_outcomes_accept_a_dataframe():
    tidy = load_outcomes(pd.DataFrame({"question_id": ["q1"], "subject_id": ["m"], "outcome": [1]}))
    assert records(tidy) == [{"question_id": "q1", "subject_id": "m", "outcome": 1}]


# --- annotations -------------------------------------------------------------------------

def test_unparsed_rows_and_null_bounds_are_dropped_at_join_and_counted():
    annotations = pd.DataFrame({
        "question_id": ["q1", "q2", "q3"], "dimension": "RA",
        "lower": [-1.0, np.nan, 0.0], "upper": [2.0, np.nan, 1.0], "parse_ok": [True, False, True],
    })
    annotations.loc[2, "upper"] = np.nan
    joined, report = join_annotations_outcomes(annotations, tidy_outcomes(["q1", "q2", "q3"]), min_items=1)
    assert joined["question_id"].tolist() == ["q1"]
    assert report["n_unusable"] == 2


def test_failed_rows_are_not_validated_but_kept(tmp_path):
    path = jsonl(tmp_path / "a.jsonl", [
        {"question_id": "q1", "dimension": "RA", "lower": None, "upper": None, "parse_ok": False,
         "parse_error": "no range found"},
        {"question_id": "q2", "dimension": "RA", "lower": 4, "upper": 1, "parse_ok": False},
    ])
    tidy = load_annotations(path)
    assert tidy["parse_ok"].tolist() == [False, False]


@pytest.mark.parametrize("lower,upper", [(2, 1), (-4, 0), (0, 3.5)])
def test_invalid_intervals_are_rejected_and_named(tmp_path, lower, upper):
    path = jsonl(tmp_path / "a.jsonl", [{"question_id": "q1", "dimension": "RA", "lower": lower, "upper": upper}])
    with pytest.raises(ContractError, match="lower <= upper") as err:
        load_annotations(path)
    assert err.value.rows == [("q1", "RA", float(lower), float(upper))]


def test_non_numeric_bounds_are_rejected(tmp_path):
    path = text(tmp_path / "a.csv", "question_id,dimension,lower,upper\nq1,RA,low,2\n")
    with pytest.raises(ContractError, match="lower") as err:
        load_annotations(path)
    assert err.value.rows == [("q1", "low")]


def test_duplicate_annotations_are_rejected(tmp_path):
    path = jsonl(tmp_path / "a.jsonl", [
        {"question_id": "q1", "dimension": "RA", "lower": 0, "upper": 1},
        {"question_id": "q1", "dimension": "RA", "lower": 0, "upper": 2},
        {"question_id": "q1", "dimension": "Ex", "lower": 0, "upper": 2},
    ])
    with pytest.raises(ContractError, match="duplicate") as err:
        load_annotations(path)
    assert err.value.rows == [("q1", "RA")]


def test_a_file_without_dimensions_needs_one_to_be_named(tmp_path):
    path = jsonl(tmp_path / "a.jsonl", [{"question_id": "q1", "propensity_lower": 0, "propensity_upper": 1}])
    with pytest.raises(ContractError, match="dimension="):
        load_annotations(path)


def test_a_file_without_intervals_is_rejected(tmp_path):
    path = jsonl(tmp_path / "a.jsonl", [{"question_id": "q1", "dimension": "RA"}])
    with pytest.raises(ContractError, match="demand-interval"):
        load_annotations(path)


def test_asking_for_an_absent_dimension_is_rejected(tmp_path):
    path = jsonl(tmp_path / "a.jsonl", [{"question_id": "q1", "dimension": "RA", "lower": 0, "upper": 1}])
    with pytest.raises(ContractError, match="'Ul'"):
        load_annotations(path, dimension="Ul")


def test_small_cells_are_warned_about():
    ids = [f"q{i}" for i in range(20)]
    with pytest.warns(DataWarning, match="fewer than 50") as caught:
        join_annotations_outcomes(tidy_annotations(ids), tidy_outcomes(ids, subject="gpt"))
    assert "gpt/RA (20)" in str(caught[0].message)


def test_joined_rows_cover_every_subject_and_dimension():
    ids = [f"q{i}" for i in range(60)]
    annotations = pd.concat([tidy_annotations(ids, "RA"), tidy_annotations(ids, "Ex", 0.0, 0.0)])
    outcomes = pd.concat([tidy_outcomes(ids, "a", 1), tidy_outcomes(ids, "b", 0)])
    joined, report = join_annotations_outcomes(annotations, outcomes)
    assert list(joined.columns) == ["question_id", "dimension", "lower", "upper", "subject_id", "outcome"]
    assert len(joined) == 60 * 2 * 2
    assert report["cell_sizes"] == {("a", "Ex"): 60, ("a", "RA"): 60, ("b", "Ex"): 60, ("b", "RA"): 60}


# --- instances ---------------------------------------------------------------------------

def test_instances_without_ids_are_numbered_over_the_whole_file(tmp_path):
    path = jsonl(tmp_path / "bench.jsonl", [{"question_text": "A?", "options": ["x", "y"]},
                                            {"question_text": "B?", "difficulty": 3}])
    assert load_instances(path) == [
        {"question_id": "bench_0", "question_text": "A?", "options": ["x", "y"]},
        {"question_id": "bench_1", "question_text": "B?", "difficulty": 3},
    ]


def test_instance_fields_pass_through_and_ids_become_strings(tmp_path):
    path = jsonl(tmp_path / "i.jsonl", [{"question_id": 7, "question_text": "Q", "meta": {"k": [1, 2]}}])
    assert load_instances(path) == [{"question_id": "7", "question_text": "Q", "meta": {"k": [1, 2]}}]


def test_csv_instances_keep_text_that_looks_missing(tmp_path):
    path = text(tmp_path / "i.csv", "question_id,question_text,note\n001,NA,\n")
    assert load_instances(path) == [{"question_id": "001", "question_text": "NA", "note": ""}]


@pytest.mark.parametrize("rows,match", [
    ([{"question_id": "a", "question_text": "Q"}, {"question_text": "Q"}], "missing on rows"),
    ([{"question_id": "a", "question_text": "Q"}, {"question_id": "a", "question_text": "R"}], "duplicate"),
    ([{"question_id": "a", "question_text": ""}], "question_text"),
    ([{"question_id": "a"}], "question_text"),
    ([{"question_id": None, "question_text": "Q"}], "empty question_id"),
])
def test_bad_instances_are_rejected(tmp_path, rows, match):
    with pytest.raises(ContractError, match=match):
        load_instances(jsonl(tmp_path / "i.jsonl", rows))


# --- files -------------------------------------------------------------------------------

def test_unsupported_extensions_are_rejected(tmp_path):
    path = text(tmp_path / "a.txt", "question_id\n1\n")
    for load in (read_table, load_instances, load_annotations, load_outcomes):
        with pytest.raises(ContractError, match="unsupported"):
            load(path)


def test_invalid_json_is_reported_with_its_line_number(tmp_path):
    path = text(tmp_path / "a.jsonl", '{"question_id": "q1"}\n{broken\n')
    with pytest.raises(ContractError, match=r"a.jsonl:2"):
        read_table(path)
    path = text(tmp_path / "b.jsonl", '["q1", "text"]\n')
    with pytest.raises(ContractError, match=r"b.jsonl:1: expected a JSON object"):
        load_instances(path)


def test_write_table_round_trips_and_writes_nan_as_null(tmp_path):
    frame = pd.DataFrame({"question_id": ["q1", "q2"], "lower": [-1.0, np.nan], "parse_ok": [True, False]})
    path = write_table(frame, tmp_path / "out" / "a.jsonl")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[1]) == {"question_id": "q2", "lower": None, "parse_ok": False}

    csv_path = write_table(frame, tmp_path / "a.csv")
    assert b"\r" not in csv_path.read_bytes()
    assert read_table(csv_path)["question_id"].tolist() == ["q1", "q2"]


def test_write_table_keeps_nested_values_from_dict_records(tmp_path):
    rows = [{"question_id": "q1", "options": ["a", "b"], "score": np.int64(3)}]
    path = write_table(rows, tmp_path / "i.jsonl")
    assert json.loads(path.read_text(encoding="utf-8")) == {"question_id": "q1", "options": ["a", "b"], "score": 3}
