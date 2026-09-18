"""What every adapter owes the core: registration, the line budget, path equivalence, and
imports that name the extra to install."""

import ast
import io
import json
import random
import subprocess
import sys
import tokenize
from pathlib import Path

import pytest
from fakes import FakeAnthropicClient, FakeGenAIClient, FakeHTTPClient, FakeOpenAIClient

from propensity import providers
from propensity.annotation.prompts import build_annotation_prompt
from propensity.annotation.runner import annotate
from propensity.providers import BatchCapable, LLMProvider, available_providers, get_provider

ADAPTER_MODULES = ("openai_compat", "azure_openai", "anthropic", "google", "generic_http", "mock")
MAX_CODE_LINES = 120


def test_every_adapter_registers_itself():
    assert available_providers() == ["anthropic", "azure", "google", "http", "mock", "openai"]


@pytest.mark.parametrize("name,kwargs,batch_capable", [
    ("openai", {"client": FakeOpenAIClient()}, True),
    ("azure", {"client": FakeOpenAIClient()}, True),
    ("anthropic", {"client": FakeAnthropicClient()}, True),
    ("google", {"client": FakeGenAIClient()}, False),
    ("http", {"client": FakeHTTPClient(), "url": "http://x", "build_payload": dict,
              "extract_text": str}, False),
    ("mock", {}, False),
])
def test_every_adapter_satisfies_the_protocol_and_says_truthfully_whether_it_batches(
        name, kwargs, batch_capable):
    provider = get_provider(name, model="m", **kwargs)
    assert isinstance(provider, LLMProvider)
    assert isinstance(provider, BatchCapable) is batch_capable
    assert provider.name == name


# --- the line budget: code lines, not docstrings, comments or blanks ---------------------

def code_lines(source: str) -> int:
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.update(range(first.lineno, first.end_lineno + 1))
    lines = set()
    skipped = (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
               tokenize.ENDMARKER)
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type not in skipped:
            lines.update(range(token.start[0], token.end[0] + 1))
    return len(lines - docstrings)


def test_the_line_counter_skips_docstrings_comments_and_blanks_only():
    source = ('"""Module\ndocstring."""\n\n# a comment\nimport os  # trailing\n\n\n'
              'def f(a,\n      b):\n    """Doc."""\n    text = """not a\ndocstring"""\n'
              '    return a\n')
    assert code_lines(source) == 6  # import, the two-line def, the two-line string, return


@pytest.mark.parametrize("module", ADAPTER_MODULES)
def test_every_adapter_stays_within_the_line_budget(module):
    path = Path(providers.__file__).with_name(f"{module}.py")
    count = code_lines(path.read_text(encoding="utf-8"))
    assert count <= MAX_CODE_LINES, f"{module}.py has {count} code lines; the abstraction is leaking"


# --- T7, for every batch-capable adapter -------------------------------------------------

RUBRIC, PRESENTATION, NAME = "RUBRIC", "</rubric>\nAnnotate the following task:", "risk aversion"
INSTANCES = [{"question_id": f"RA_{i}", "question_text": f"Q{i}?", "source": "bench"}
             for i in range(6)]
ANSWERS = {build_annotation_prompt(NAME, RUBRIC, PRESENTATION, instance["question_text"])[1]:
           f"Level by level for {instance['question_id']}.\n"
           + ("no range given" if i == 5 else f"<FINAL_RANGE>[{-(i % 4)}, {i % 3}]</FINAL_RANGE>")
           for i, instance in enumerate(INSTANCES)}
BATCH_SEED = 4


def folded(params):
    """Anthropic's request as it goes over the wire: the SDK merges extra_body into the JSON."""
    params = dict(params)
    extra_body = params.pop("extra_body", {})
    return {**params, **extra_body}


T7_ADAPTERS = {
    "openai": (lambda seed: FakeOpenAIClient(respond=lambda body: ANSWERS[body["messages"][1]["content"]], seed=seed),
               lambda client: client.bodies,
               lambda client: [line["body"] for line in client.uploaded_lines()]),
    "azure": (lambda seed: FakeOpenAIClient(respond=lambda body: ANSWERS[body["messages"][1]["content"]], seed=seed),
              lambda client: client.bodies,
              lambda client: [line["body"] for line in client.uploaded_lines()]),
    "anthropic": (lambda seed: FakeAnthropicClient(respond=lambda params: ANSWERS[params["messages"][0]["content"]], seed=seed),
                  lambda client: [folded(params) for params in client.params],
                  lambda client: [request["params"] for request in client.submitted[-1]]),
}


def run(provider, mode):
    return annotate(INSTANCES, provider=provider, dimension="RA", propensity_name=NAME,
                    rubric=RUBRIC, presentation=PRESENTATION, mode=mode, max_workers=1,
                    retry_backoff=0, poll_interval=0)


@pytest.mark.parametrize("name", sorted(T7_ADAPTERS))
def test_t7_every_batch_capable_adapter_sends_identical_requests_and_returns_identical_rows(name):
    make_client, sent_one_by_one, sent_in_batch = T7_ADAPTERS[name]
    order = list(range(len(INSTANCES)))
    random.Random(BATCH_SEED).shuffle(order)
    assert order != sorted(order), "the batch output must come back out of order"

    sequential_client, batch_client = make_client(0), make_client(BATCH_SEED)
    sequential = get_provider(name, model="model-x", client=sequential_client)
    batch = get_provider(name, model="model-x", client=batch_client)
    assert isinstance(batch, BatchCapable)

    sequential_rows, batch_rows = run(sequential, "sequential"), run(batch, "batch")

    assert sequential_rows == batch_rows
    as_bytes = [json.dumps(request, sort_keys=True).encode() for request in sent_one_by_one(sequential_client)]
    assert as_bytes == [json.dumps(request, sort_keys=True).encode() for request in sent_in_batch(batch_client)]
    assert [row["question_id"] for row in batch_rows] == [i["question_id"] for i in INSTANCES]
    assert [row["parse_ok"] for row in batch_rows] == [True] * 5 + [False]
    assert {row["annotator"] for row in batch_rows} == {f"{name}:model-x"}


# --- T9, adapter by adapter --------------------------------------------------------------

MISSING_SDK_SCRIPT = """
import sys

class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("openai", "anthropic", "google", "httpx"):
            raise ImportError(f"{name} is blocked for this test")

sys.meta_path.insert(0, Blocker())
sys.modules.pop("google", None)

from propensity.providers import get_provider  # every adapter module imports without its SDK

cases = {"openai": {}, "azure": {"endpoint": "https://x.openai.azure.com"}, "anthropic": {},
         "google": {}, "http": {"url": "http://x", "build_payload": dict, "extract_text": str}}
for name, kwargs in cases.items():
    try:
        get_provider(name, model="m", **kwargs)
    except ImportError as exc:
        print(name, "|", exc)
    else:
        print(name, "| constructed without its SDK")
"""


def test_t9_each_adapter_names_the_extra_that_installs_its_sdk():
    done = subprocess.run([sys.executable, "-c", MISSING_SDK_SCRIPT], capture_output=True,
                          text=True, check=False)
    assert done.returncode == 0, done.stderr
    messages = dict(line.split(" | ", 1) for line in done.stdout.strip().splitlines())
    assert sorted(messages) == ["anthropic", "azure", "google", "http", "openai"]
    for name, message in messages.items():
        assert f'pip install "propel[{name}]"' in message, message
