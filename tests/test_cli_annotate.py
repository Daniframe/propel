"""The propel-annotate subcommands: run, submit, status and fetch."""

import json
import subprocess
import sys

import pytest

from propensity import providers
from propensity.cli.annotate import main
from propensity.modelling.io import read_table
from propensity.providers.mock import MockBatchProvider

CONFIG = """
provider: mock
model: mock-1
temperature: 0.0
max_tokens: null
max_workers: 4
max_retries: 2
poll_interval_s: 0
rubrics_dir: {rubrics}
dimensions:
  RA: risk aversion
"""


@pytest.fixture
def workspace(tmp_path):
    """Instances, a minimal rubric set, and a config that points at them."""
    rubrics = tmp_path / "rubrics"
    (rubrics / "RA").mkdir(parents=True)
    (rubrics / "RA" / "RA_v1.md").write_text("# RISK AVERSION PROPENSITY\n", encoding="utf-8")
    (rubrics / "presentation.md").write_text("</rubric>\nAnnotate the following task:",
                                             encoding="utf-8", newline="")

    (tmp_path / "items.jsonl").write_text("".join(
        json.dumps({"question_id": f"RA_{i}", "question_text": f"Q{i}?"}) + "\n"
        for i in range(3)), encoding="utf-8")

    (tmp_path / "annotation.yaml").write_text(CONFIG.format(rubrics=rubrics.as_posix()),
                                              encoding="utf-8")
    return tmp_path


@pytest.fixture
def stub_provider():
    """A provider that accepts credentials, for checking what a job file keeps."""
    saved = dict(providers._REGISTRY)

    class Stub(MockBatchProvider):
        name = "stub"

        def __init__(self, model="stub-1", *, api_key=None, base_url=None, **kwargs):
            super().__init__(model, **kwargs)
            self.api_key, self.base_url = api_key, base_url

    providers.register_provider("stub", Stub)
    yield
    providers._REGISTRY.clear()
    providers._REGISTRY.update(saved)


def argv(workspace, command, *extra, out="annotations.jsonl"):
    return [command, "--instances", str(workspace / "items.jsonl"), "--dimension", "RA",
            "--out", str(workspace / out), "--config", str(workspace / "annotation.yaml"), *extra]


def batching(workspace, *extra):
    """The mock's batches have to outlive the process, as a real provider's do."""
    return ["--provider-option", "batch=true",
            "--provider-option", f"state_path={workspace / 'batches.json'}", *extra]


def test_run_annotates_every_instance_and_writes_the_rows(workspace, capsys):
    assert main(argv(workspace, "run")) == 0
    printed = capsys.readouterr().out

    rows = read_table(workspace / "annotations.jsonl")
    assert len(rows) == 3
    assert rows["parse_ok"].all()
    assert rows["lower"].tolist() == [-1, -1, -1] and rows["upper"].tolist() == [2, 2, 2]
    assert rows["annotator"].tolist() == ["mock:mock-1"] * 3
    assert rows["dimension"].tolist() == ["RA"] * 3
    assert rows["question_text"].tolist() == ["Q0?", "Q1?", "Q2?"]  # passed through
    assert "3 ok, 0 parse-failed, 0 provider-error out of 3 total" in printed


def test_submit_writes_a_job_file_before_polling_then_status_and_fetch(workspace, capsys):
    assert main(argv(workspace, "submit", *batching(workspace))) == 0
    submitted = capsys.readouterr().out
    job_path = workspace / "annotations.jsonl.job.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))

    assert "submitted batch mock-batch-1 with 3 requests" in submitted
    assert f"next: propel-annotate status --job {job_path}" in submitted
    assert (job["dimension"], job["n_requests"], job["provider"]) == ("RA", 3, "mock")
    assert job["propensity_name"] == "risk aversion" and len(job["prompts_sha256"]) == 64
    assert not (workspace / "annotations.jsonl").exists()  # the job file comes first

    assert main(["status", "--job", str(job_path)]) == 0
    status = capsys.readouterr().out
    assert "batch mock-batch-1: completed" in status
    assert "3 requests for RA via mock:mock-1" in status

    assert main(["fetch", "--job", str(job_path)]) == 0
    fetched = capsys.readouterr().out
    assert "3 ok, 0 parse-failed, 0 provider-error out of 3 total" in fetched
    assert read_table(workspace / "annotations.jsonl")["parse_ok"].all()


def test_submit_with_wait_fetches_in_one_go(workspace, capsys):
    assert main(argv(workspace, "submit", "--wait", *batching(workspace))) == 0
    printed = capsys.readouterr().out
    assert "ended as completed" in printed
    assert len(read_table(workspace / "annotations.jsonl")) == 3


def test_fetch_refuses_prompts_that_no_longer_match_the_job(workspace, capsys):
    main(argv(workspace, "submit", *batching(workspace)))
    capsys.readouterr()
    job_path = workspace / "annotations.jsonl.job.json"
    (workspace / "items.jsonl").write_text(
        json.dumps({"question_id": "RA_0", "question_text": "a different question?"}) + "\n",
        encoding="utf-8")

    assert main(["fetch", "--job", str(job_path)]) == 2
    assert "no longer match" in capsys.readouterr().err
    assert not (workspace / "annotations.jsonl").exists()

    assert main(["fetch", "--job", str(job_path), "--force"]) == 0
    assert len(read_table(workspace / "annotations.jsonl")) == 1


def test_fetch_says_when_a_batch_is_not_ready(workspace, capsys):
    main(argv(workspace, "submit", *batching(workspace, "--provider-option", "states=running")))
    capsys.readouterr()
    assert main(["fetch", "--job", str(workspace / "annotations.jsonl.job.json")]) == 1
    assert "is running; nothing to fetch yet" in capsys.readouterr().out


def test_fetch_says_a_failed_batch_must_be_resubmitted(workspace, capsys):
    options = [*batching(workspace), "--provider-option", "states=failed"]
    assert main(argv(workspace, "submit", *options)) == 0
    assert main(["fetch", "--job", str(workspace / "annotations.jsonl.job.json")]) == 1
    assert "ended as failed; nothing to fetch. Submit it again." in capsys.readouterr().out


def test_a_batch_that_loses_an_id_still_writes_a_row_for_it(workspace):
    assert main(argv(workspace, "submit", "--wait", out="dropped.jsonl",
                     *batching(workspace, "--provider-option", "drop=RA_1"))) == 0
    rows = read_table(workspace / "dropped.jsonl")
    assert len(rows) == 3
    assert rows[rows.question_id == "RA_1"].iloc[0]["error"] == "missing from the batch output"


def test_credentials_never_reach_the_job_file(workspace, stub_provider):
    assert main(argv(workspace, "submit", "--provider", "stub", "--model", "stub-1",
                     "--provider-option", "api_key=sk-secret",
                     "--provider-option", "base_url=http://example.invalid",
                     "--provider-option", f"state_path={workspace / 'batches.json'}")) == 0
    job = json.loads((workspace / "annotations.jsonl.job.json").read_text(encoding="utf-8"))
    assert job["provider_options"] == {"base_url": "http://example.invalid",
                                       "state_path": str(workspace / "batches.json")}
    assert "sk-secret" not in json.dumps(job)


def test_a_dimension_with_no_name_in_words_is_refused(workspace, capsys):
    code = main(["run", "--instances", str(workspace / "items.jsonl"), "--dimension", "Ex",
                 "--out", str(workspace / "x.jsonl"),
                 "--config", str(workspace / "annotation.yaml")])
    assert code == 2
    assert "no name in words for dimension 'Ex'" in capsys.readouterr().err


def test_a_missing_rubric_is_refused(workspace, capsys):
    code = main(["run", "--instances", str(workspace / "items.jsonl"), "--dimension", "TD",
                 "--propensity-name", "delay of gratification",
                 "--out", str(workspace / "td.jsonl"),
                 "--config", str(workspace / "annotation.yaml")])
    assert code == 2
    assert "no rubric for dimension 'TD'" in capsys.readouterr().err


def test_the_packaged_rubrics_and_catalogue_need_no_configuration(workspace, monkeypatch):
    import propensity.cli.annotate as cli
    from propensity.annotation import load_rubric

    annotator = MockBatchProvider()
    monkeypatch.setattr(cli, "get_provider", lambda name, **options: annotator)
    out = workspace / "packaged.jsonl"
    assert main(["run", "--instances", str(workspace / "items.jsonl"), "--dimension", "RA",
                 "--out", str(out), "--provider", "mock", "--model", "mock-1",
                 "--config", str(workspace / "absent.yaml")]) == 0

    _, user = annotator.calls[0]
    assert user.startswith("The following is a rubric for determining the propensity of showing "
                           "bias towards risk aversion:")  # the catalogue's name
    assert load_rubric("RA") in user                        # the packaged rubric, current version
    assert read_table(out)["parse_ok"].tolist() == [True] * 3


def test_a_dimension_outside_the_catalogue_needs_a_name(workspace, capsys):
    assert main(["run", "--instances", str(workspace / "items.jsonl"), "--dimension", "TD",
                 "--out", str(workspace / "td.jsonl"), "--provider", "mock", "--model", "mock-1",
                 "--config", str(workspace / "absent.yaml")]) == 2
    assert "not in the dimension catalogue; pass --propensity-name" in capsys.readouterr().err


def test_an_unknown_provider_is_refused(workspace, capsys):
    assert main(argv(workspace, "run", "--provider", "nope")) == 2
    assert "unknown provider 'nope'" in capsys.readouterr().err


def test_a_malformed_provider_option_is_refused(workspace, capsys):
    assert main(argv(workspace, "run", "--provider-option", "justakey")) == 2
    assert "KEY=VALUE" in capsys.readouterr().err


def test_an_option_the_provider_does_not_take_is_refused_without_a_traceback(workspace, capsys):
    assert main(argv(workspace, "run", "--provider-option", "bse_url=http://x")) == 2
    err = capsys.readouterr().err
    assert "could not start the 'mock' provider" in err and "bse_url" in err
    assert "Traceback" not in err


def test_a_missing_sdk_is_reported_with_its_extra(workspace, capsys, monkeypatch):
    import propensity.cli.annotate as cli

    def missing(*args, **kwargs):
        raise ImportError('the \'openai\' provider needs the openai package: pip install "propel[openai]"')

    monkeypatch.setattr(cli, "get_provider", missing)
    assert main(argv(workspace, "run")) == 2
    assert 'pip install "propel[openai]"' in capsys.readouterr().err


def test_batch_mode_needs_a_batch_capable_provider(workspace, capsys):
    assert main(argv(workspace, "submit")) == 2  # the plain mock has no batch API
    assert "no batch API" in capsys.readouterr().err


def test_a_missing_job_file_is_refused(capsys):
    assert main(["status", "--job", "nowhere.job.json"]) == 2
    assert "no such job file" in capsys.readouterr().err


def test_flags_override_the_config_file(workspace):
    assert main(argv(workspace, "run", "--model", "mock-9")) == 0
    assert read_table(workspace / "annotations.jsonl")["annotator"].tolist() == ["mock:mock-9"] * 3


def test_the_module_entry_point_is_runnable():
    done = subprocess.run([sys.executable, "-m", "propensity.cli.annotate", "--help"],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0
    assert "propel-annotate" in done.stdout
