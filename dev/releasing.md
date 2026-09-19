# Releasing

For maintainers. `dev/` is not part of the package: it is not in the sdist or the wheel.

**Before anything else.** Some rubrics are not cleared for publication yet. Publishing puts
them on a public index permanently, and even a deleted release cannot be reused or recalled.
Until that clearance arrives, do not push tags and do not run the release workflow.

## What a release is

1. Everything is committed, and the tests pass (CI does this on every push).
2. `CHANGELOG.md` has an entry for the version, at the top.
3. `propensity/__init__.py` has the matching `__version__`, in its own "Release X.Y.Z" commit.
4. A tag `vX.Y.Z` points at that commit.

Pushing the tag is what starts a release. Nothing else publishes.

## What the workflows do

`.github/workflows/release.yml`, on a pushed tag `v*`:

| Job | Does |
|---|---|
| `build` | refuses unless the tag matches `__version__`, then builds the sdist and wheel and runs `twine check --strict` |
| `check` | installs the built wheel in a fresh environment on Linux, Windows and macOS (Python 3.10 and 3.13), runs the sdist's tests against it, and smoke-tests both commands |
| `testpypi` | publishes to TestPyPI through trusted publishing |
| `pypi` | never runs on a tag push. Start the workflow by hand, on the tag, with index `pypi` |

`.github/workflows/ci.yml` runs on every push and pull request: the suite on three systems and
four Python versions, a core-only run, two runs at the dependency floors
(`.github/constraints/`), and a packaging check that installs the built wheel.

## One-time setup

Trusted publishing means no tokens: each index trusts this repository's workflow.

1. **TestPyPI** → your project → Publishing → add a GitHub publisher:
   owner `Daniframe`, repository `propel`, workflow `release.yml`, environment `testpypi`.
2. **PyPI**, when the time comes: the same, as a *pending* publisher if the project does not
   exist yet, with environment `pypi`.
3. **GitHub** → Settings → Environments: create `testpypi` and `pypi`. Give `pypi` a required
   reviewer, so a real PyPI release always takes a second pair of eyes.

## Cutting a release

```bash
# 1. the version and the changelog, in their own commit
git commit -am "Release 0.1.4"
# 2. the tag, matching exactly
git tag v0.1.4
git push origin main
git push origin v0.1.4        # this publishes to TestPyPI
```

Then install from TestPyPI to see it as a user does. Dependencies come from PyPI; taking them
from TestPyPI would risk packages that merely share a name:

```bash
pip install --no-deps -i https://test.pypi.org/simple/ propensity==0.1.4
pip install "propensity[all]==0.1.4"
```

For PyPI: Actions → release → Run workflow → pick the tag → index `pypi`.

## If something goes wrong

- **A version is published once.** Fix forward with a new version; never reuse a number.
- **The tag does not match the version:** the `build` job stops before anything is published.
  Delete the tag, fix the version commit, tag again.
- **Publishing by hand** (only if the workflow cannot run):
  ```bash
  python -m build && python -m twine check --strict dist/*
  python -m twine upload --repository testpypi dist/*
  ```

## Version numbers

The policy is in [docs/stability.md](../docs/stability.md). In short, while PROPEL is `0.x`:
a change to the prompts or to anything that makes existing annotations incomparable bumps the
minor number; new dimensions and features bump it too; fixes bump the patch number. PROPEL
stays below `1.0` until every provider has been exercised against its real API.
