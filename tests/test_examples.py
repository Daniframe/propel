"""The example data that ships with the package, its copier, and its generator."""

import subprocess
import sys
from pathlib import Path

import propensity
from propensity import load_annotations, load_instances, load_outcomes
from propensity.examples import EXAMPLES_DIR, FILES, copy_examples
from propensity.examples import generate
from propensity.examples.__main__ import main

DATA = ("items_RA.jsonl", "annotations_RA.jsonl", "outcomes_long.csv", "outcomes_wide.csv")


def test_the_example_files_ship_with_the_package_and_load():
    assert EXAMPLES_DIR == Path(propensity.__file__).resolve().parent / "examples"
    assert all((EXAMPLES_DIR / name).is_file() for name in FILES)
    assert len(load_instances(EXAMPLES_DIR / "items_RA.jsonl")) == 120
    assert len(load_annotations(EXAMPLES_DIR / "annotations_RA.jsonl")) == 120
    long, wide = (load_outcomes(EXAMPLES_DIR / name) for name in ("outcomes_long.csv", "outcomes_wide.csv"))
    assert set(long["subject_id"]) == set(wide["subject_id"]) == {
        "demo-model", "demo-model_RA_-2", "demo-model_RA_0", "demo-model_RA_+2"}


def test_copying_writes_every_file_and_keeps_what_is_already_there(tmp_path):
    done = copy_examples(tmp_path / "examples")
    assert sorted(path.name for path in done["written"]) == sorted(FILES) and not done["kept"]
    for name in FILES:
        assert (tmp_path / "examples" / name).read_bytes() == (EXAMPLES_DIR / name).read_bytes()

    (tmp_path / "examples" / "items_RA.jsonl").write_bytes(b"mine\n")
    done = copy_examples(tmp_path / "examples")
    assert [path.name for path in done["kept"]] == list(FILES)
    assert (tmp_path / "examples" / "items_RA.jsonl").read_bytes() == b"mine\n"

    copy_examples(tmp_path / "examples", overwrite=True)
    assert (tmp_path / "examples" / "items_RA.jsonl").read_bytes() != b"mine\n"


def test_the_command_copies_into_the_directory_it_is_given(tmp_path, capsys):
    assert main([str(tmp_path / "data")]) == 0
    assert f"wrote {len(FILES)} example files" in capsys.readouterr().out
    assert main([str(tmp_path / "data")]) == 0
    assert "--force overwrites it" in capsys.readouterr().out


def test_the_module_is_runnable(tmp_path):
    done = subprocess.run([sys.executable, "-m", "propensity.examples", str(tmp_path / "x")],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert (tmp_path / "x" / "items_RA.jsonl").is_file()


def test_the_generator_reproduces_the_shipped_files_byte_for_byte(tmp_path, capsys):
    generate.main(tmp_path)
    for name in DATA:
        assert (tmp_path / name).read_bytes() == (EXAMPLES_DIR / name).read_bytes(), name
