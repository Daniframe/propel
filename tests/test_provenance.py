"""Every annotation records what produced it: the rubric's version and text, and PROPEL's version."""

import hashlib
import json
import warnings

import pytest

import propensity
from propensity import annotate, get_provider, load_annotations, load_presentation, load_rubric
from propensity.annotation.runner import PROVENANCE_FIELDS, ROW_FIELDS, provenance, rows_from_completions
from propensity.cli.annotate import main
from propensity.errors import DataWarning
from propensity.modelling.io import read_table
from propensity.providers.base import Completion

INSTANCES = [{"question_id": f"RA_{i}", "question_text": f"Q{i}?"} for i in range(2)]


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_provenance_fields_close_the_canonical_row():
    assert PROVENANCE_FIELDS == ("rubric_version", "rubric_sha256", "propensity_version")
    assert ROW_FIELDS[-3:] == PROVENANCE_FIELDS


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_a_packaged_rubric_is_recognised_by_its_text(version):
    rubric = load_rubric("RA", version=version)
    assert provenance("RA", rubric) == {"rubric_version": version, "rubric_sha256": sha(rubric),
                                        "propensity_version": propensity.__version__}


def test_a_rubric_of_your_own_is_recorded_by_its_hash_or_the_version_you_give():
    assert provenance("RA", "MY RUBRIC")["rubric_version"] is None
    assert provenance("RA", "MY RUBRIC")["rubric_sha256"] == sha("MY RUBRIC")
    assert provenance("RA", "MY RUBRIC", "draft-3")["rubric_version"] == "draft-3"
    assert provenance("TD", load_rubric("RA"))["rubric_version"] is None  # another dimension's text


def test_every_row_records_it_failures_included(capsys):
    rows = annotate(INSTANCES, provider=get_provider("mock", model="m"), dimension="RA",
                    propensity_name="risk aversion", rubric=load_rubric("RA"),
                    presentation=load_presentation(), mode="sequential", max_workers=1)
    missing = rows_from_completions(INSTANCES, {"RA_0": Completion(text="", error="x")}, dimension="RA",
                                    annotator="x:y", rubric=load_rubric("RA"))
    for row in rows + missing:
        assert (row["rubric_version"], row["propensity_version"]) == ("v2", propensity.__version__)
        assert row["rubric_sha256"] == sha(load_rubric("RA"))


def test_rows_built_without_a_rubric_still_say_which_propel_made_them():
    rows = rows_from_completions(INSTANCES, {}, dimension="RA", annotator="x:y")
    assert {(r["rubric_version"], r["rubric_sha256"], r["propensity_version"]) for r in rows} == {
        (None, None, propensity.__version__)}


def test_the_command_line_records_the_version_it_used(tmp_path, capsys):
    (tmp_path / "items.jsonl").write_text("".join(json.dumps(i) + "\n" for i in INSTANCES), encoding="utf-8")
    common = ["--instances", str(tmp_path / "items.jsonl"), "--dimension", "RA", "--provider", "mock",
              "--model", "m", "--config", str(tmp_path / "absent.yaml")]
    assert main(["run", *common, "--out", str(tmp_path / "v2.jsonl")]) == 0
    assert main(["run", *common, "--rubric-version", "v1", "--out", str(tmp_path / "v1.jsonl")]) == 0
    assert set(read_table(tmp_path / "v2.jsonl")["rubric_version"]) == {"v2"}
    assert set(read_table(tmp_path / "v1.jsonl")["rubric_version"]) == {"v1"}


def annotation(qid, rubric_version, rubric_text):
    return {"question_id": qid, "dimension": "RA", "lower": -1, "upper": 2, "parse_ok": True,
            "rubric_version": rubric_version, "rubric_sha256": sha(rubric_text)}


def test_loading_annotations_from_two_rubrics_warns(tmp_path):
    path = tmp_path / "mixed.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in [annotation("a", "v1", "one"),
                                                              annotation("b", "v2", "two")]),
                    encoding="utf-8")
    with pytest.warns(DataWarning, match="RA come from 2 different rubrics \\(versions v1, v2\\)"):
        load_annotations(path)


def test_loading_annotations_from_one_rubric_is_quiet(tmp_path):
    path = tmp_path / "one.jsonl"
    path.write_text("".join(json.dumps(annotation(q, "v2", "two")) + "\n" for q in "ab"), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert len(load_annotations(path)) == 2
