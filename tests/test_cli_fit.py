import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from propensity.cli.fit import main
from propensity.modelling.profiles import DIAGNOSTIC_COLUMNS, PROFILE_COLUMNS


def write_inputs(tmp_path, n_items=80, subjects=("model-a", "model-b"), dimension="RA",
                 legacy=True):
    """An annotations file and a wide outcomes file, in the shapes the CLI has to read."""
    rng = np.random.default_rng(0)
    lower = rng.integers(-3, 4, n_items)
    upper = np.array([rng.integers(lo, 4) for lo in lower])

    annotations = tmp_path / "annotations.jsonl"
    with open(annotations, "w", encoding="utf-8") as f:
        for i, (lo, hi) in enumerate(zip(lower, upper)):
            row = {"question_id": f"q{i}"}
            if legacy:  # no dimension column: the CLI needs CODE=path
                row |= {"propensity_lower": int(lo), "propensity_upper": int(hi)}
            else:
                row |= {"dimension": dimension, "lower": int(lo), "upper": int(hi), "parse_ok": True}
            f.write(json.dumps(row) + "\n")

    outcomes = tmp_path / "outcomes.csv"
    frame = pd.DataFrame({"question_id": [f"q{i}" for i in range(n_items)]})
    for subject in subjects:
        frame[f"{subject}_outcome"] = rng.integers(0, 2, n_items)
    frame.to_csv(outcomes, index=False)
    return annotations, outcomes


def run(tmp_path, *extra, annotations=None, outcomes=None, out=None, config="missing.yaml"):
    annotations = annotations or tmp_path / "annotations.jsonl"
    outcomes = outcomes or tmp_path / "outcomes.csv"
    out = out or tmp_path / "profiles.csv"
    argv = ["--annotations", str(annotations), "--outcomes", str(outcomes), "--out", str(out),
            "--config", str(tmp_path / config), *extra]
    return main(argv), out


def test_the_cli_writes_a_profile_table(tmp_path, capsys):
    annotations, outcomes = write_inputs(tmp_path)
    code, out = run(tmp_path, annotations=f"RA={annotations}")
    printed = capsys.readouterr().out

    assert code == 0
    table = pd.read_csv(out)
    assert list(table.columns) == PROFILE_COLUMNS + DIAGNOSTIC_COLUMNS
    assert sorted(table.subject_id) == ["model-a", "model-b"]
    assert set(table.dimension) == {"RA"}
    assert table.n_items.tolist() == [80, 80]
    assert "join yield RA: 80/80" in printed
    assert "fitted 2 of 2" in printed
    assert f"wrote {out}" in printed


def test_a_file_that_names_its_own_dimension_needs_no_code(tmp_path):
    annotations, _ = write_inputs(tmp_path, legacy=False)
    code, out = run(tmp_path)
    assert code == 0
    assert set(pd.read_csv(out).dimension) == {"RA"}


def test_a_legacy_file_without_a_code_is_an_error(tmp_path, capsys):
    write_inputs(tmp_path, legacy=True)
    code, _ = run(tmp_path)
    assert code == 2
    assert "dimension=" in capsys.readouterr().err


def test_subject_and_dimension_filters_reach_the_sweep(tmp_path):
    annotations, _ = write_inputs(tmp_path, legacy=False)
    code, out = run(tmp_path, "--subjects", "model-b")
    assert code == 0
    assert pd.read_csv(out).subject_id.tolist() == ["model-b"]


def test_the_config_file_supplies_settings_and_flags_win(tmp_path, capsys):
    write_inputs(tmp_path, legacy=False)
    (tmp_path / "modelling.yaml").write_text(
        "propensity:\n  likelihood: product\n  robust: false\nprofiles:\n  min_items: 500\n",
        encoding="utf-8")

    code, out = run(tmp_path, config="modelling.yaml")
    assert code == 0
    table = pd.read_csv(out)
    assert table.theta.isna().all()  # min_items 500 skips both cells
    assert table.skip_reason.str.contains("min_items=500").all()
    assert "fitted 0 of 2" in capsys.readouterr().out

    code, out = run(tmp_path, "--min-items", "10", config="modelling.yaml")
    assert code == 0
    table = pd.read_csv(out)
    assert table.theta.notna().all()
    assert table.n_attempts.isna().all()  # robust: false came from the config


def test_a_contract_error_is_reported_without_a_traceback(tmp_path, capsys):
    write_inputs(tmp_path, legacy=False)
    (tmp_path / "outcomes.csv").write_text(
        "question_id,subject_id,outcome\nq0,m,0.7\n", encoding="utf-8")
    code, _ = run(tmp_path)
    captured = capsys.readouterr()
    assert code == 2
    assert "outcomes must be 0 or 1" in captured.err
    assert "Traceback" not in captured.err


def test_low_join_yield_is_surfaced(tmp_path, capsys):
    annotations, _ = write_inputs(tmp_path, legacy=False)
    frame = pd.read_csv(tmp_path / "outcomes.csv")
    frame["question_id"] = [f"q{i + 40}" for i in range(len(frame))]  # half the ids miss
    frame.to_csv(tmp_path / "outcomes.csv", index=False)

    code, _ = run(tmp_path, "--min-items", "10")
    captured = capsys.readouterr()
    assert code == 0
    assert "low join yield" in captured.err
    assert "join yield RA: 40/80" in captured.out


def test_the_module_entry_point_is_runnable():
    done = subprocess.run([sys.executable, "-m", "propensity.cli.fit", "--help"],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0
    assert "propel-fit" in done.stdout


def test_plots_are_drawn_for_every_cell_when_asked(tmp_path, capsys):
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    write_inputs(tmp_path, legacy=False)
    code, _ = run(tmp_path, "--plots", str(tmp_path / "plots"))
    printed = capsys.readouterr().out

    assert code == 0
    assert sorted(p.name for p in (tmp_path / "plots").iterdir()) == [
        "RA_intervals.png", "RA_tree.png",  # one dimension, so no grid of trees
        "model-a_RA_curve.png", "model-a_RA_surface.png",
        "model-b_RA_curve.png", "model-b_RA_surface.png"]
    assert f"wrote 6 plots to {tmp_path / 'plots'}" in printed


def test_plots_without_matplotlib_fail_before_anything_is_fitted(tmp_path, capsys, monkeypatch):
    import propensity.cli.fit as fit_cli

    def missing():
        raise ImportError('plotting needs matplotlib and seaborn: pip install "propensity[plot]"')

    monkeypatch.setattr(fit_cli, "require_matplotlib", missing)
    write_inputs(tmp_path, legacy=False)
    code, out = run(tmp_path, "--plots", str(tmp_path / "plots"))

    assert code == 2
    assert 'pip install "propensity[plot]"' in capsys.readouterr().err
    assert not out.exists() and not (tmp_path / "plots").exists()
