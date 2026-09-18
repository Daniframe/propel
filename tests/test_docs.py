"""The tutorials run as written: every runnable code block, in order, on the example data.

`python` blocks are executed in one namespace per tutorial. In `bash` blocks, each command
starting with `propel-annotate`, `propel-fit` or `python` is run, and must exit 0 unless the
line ends with `# exits N`; other commands are illustration only. A block preceded by
`<!-- no-run -->` is skipped (it needs credentials or a real model). Output blocks (`text`)
are never run.
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from propensity import providers

ROOT = Path(__file__).resolve().parents[1]
TUTORIALS = ROOT / "docs" / "tutorials"
FENCE = re.compile(r"(<!-- no-run -->[ \t]*\n)?```(\w*)[^\n]*\n(.*?)```", re.S)
COMMANDS = {"propel-annotate": "propensity.cli.annotate", "propel-fit": "propensity.cli.fit"}
# tutorial -> whether it draws figures, and so needs the plot extra
RUNNABLE = {
    "01-offline-walkthrough.md": True,
    "02-command-line.md": True,
    "04-batch-annotation.md": False,
    "05-preparing-outcomes.md": False,
    "06-fitting-and-diagnostics.md": False,
    "07-validating-with-incitement.md": True,
    "08-plots.md": True,
    "09-writing-a-rubric.md": False,
    "10-adding-a-provider.md": False,
}


def blocks(path):
    for match in FENCE.finditer(path.read_text(encoding="utf-8")):
        skipped, language, body = match.groups()
        if not skipped:
            yield language, body


def command_lines(body):
    """Logical lines, with backslash continuations joined."""
    lines, current = [], ""
    for raw in body.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            current += line[:-1] + " "
            continue
        current = (current + line).strip()
        if current:
            lines.append(current)
        current = ""
    return lines


def run_command(line, cwd, env):
    expected = re.search(r"#\s*exits (\d+)\s*$", line)
    words = shlex.split(line, comments=True)
    if not words:
        return
    if words[0] in COMMANDS:
        words = [sys.executable, "-m", COMMANDS[words[0]], *words[1:]]
    elif words[0] == "python":
        words = [sys.executable, *words[1:]]
    else:
        return
    done = subprocess.run(words, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    assert done.returncode == (int(expected.group(1)) if expected else 0), (
        f"{line}\nstdout:\n{done.stdout}\nstderr:\n{done.stderr}")


LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)|<img src=\"([^\"]+)\"")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.M)


def slug(heading):
    """The anchor GitHub gives a heading: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(path):
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    return {slug(heading) for heading in HEADING.findall(text)}


def documents():
    return [ROOT / "README.md", ROOT / "examples" / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]


@pytest.mark.parametrize("document", documents(), ids=lambda path: str(path.relative_to(ROOT)))
def test_every_link_and_anchor_resolves(document):
    text = re.sub(r"```.*?```", "", document.read_text(encoding="utf-8"), flags=re.S)
    broken = []
    for match in LINK.finditer(text):
        target = match.group(1) or match.group(2)
        if re.match(r"[a-z]+:", target):
            continue  # an external URL
        path, _, anchor = target.partition("#")
        resolved = (document.parent / path).resolve() if path else document
        if not resolved.exists():
            broken.append(target)
        elif anchor and resolved.suffix == ".md" and anchor not in anchors(resolved):
            broken.append(target)
    assert not broken, f"{document.name}: {broken}"


def test_every_tutorial_is_either_run_or_declared_as_needing_credentials():
    on_disk = {path.name for path in TUTORIALS.glob("[0-9]*.md")}
    needs_credentials = {"03-annotating-with-a-provider.md", "11-troubleshooting.md"}
    assert on_disk == set(RUNNABLE) | needs_credentials


@pytest.mark.parametrize("name", sorted(RUNNABLE))
def test_the_tutorial_runs_as_written(name, tmp_path, monkeypatch):
    if RUNNABLE[name]:
        pytest.importorskip("matplotlib")
        pytest.importorskip("seaborn")
    for folder in ("config", "examples"):
        shutil.copytree(ROOT / folder, tmp_path / folder)
    monkeypatch.chdir(tmp_path)
    # A tutorial may register providers of its own; none of them may outlive it.
    monkeypatch.setattr(providers, "_REGISTRY", dict(providers._REGISTRY))
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        [str(ROOT), *filter(None, [os.environ.get("PYTHONPATH")])])}

    namespace = {"__name__": "__tutorial__"}
    try:
        for language, body in blocks(TUTORIALS / name):
            if language == "python":
                exec(compile(body, str(TUTORIALS / name), "exec"), namespace)  # noqa: S102
            elif language == "bash":
                for line in command_lines(body):
                    run_command(line, tmp_path, env)
    finally:
        if "matplotlib.pyplot" in sys.modules:
            sys.modules["matplotlib.pyplot"].close("all")
