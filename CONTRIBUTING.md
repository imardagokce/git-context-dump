# Contributing to git-context-dump

Thanks for helping out. The tool has no runtime dependencies; please keep it that way
(optional features go behind an extra, like `tiktoken`).

## Development setup

Python 3.10 or newer is required.

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -e .[dev]
```

Add the `tiktoken` extra (`pip install -e .[dev,tiktoken]`) if you are working on the
`--tokenizer tiktoken` path.

## Running tests

Tests use the standard library `unittest` runner:

```bash
python -m unittest discover -s tests -t .
```

With coverage (the build fails below 85%):

```bash
coverage run -m unittest discover -s tests -t .
coverage report
```

## Linting, formatting and type checking

```bash
ruff check .        # lint (add --fix to apply safe fixes)
ruff format .       # format
mypy                # strict type check of git_context_dump/
```

CI runs `ruff check .`, `ruff format --check .`, `mypy` and the test suite on Linux,
Windows and macOS, so please run them locally before opening a PR.

## Branches and pull requests

- Branch off `main` with a descriptive name, e.g. `feat/xml-format` or `fix/windows-stdout`.
- Use conventional commit prefixes, matching the existing history:
  - `feat:` new functionality
  - `fix:` bug fixes
  - `docs:` documentation only
  - `chore:` tooling, CI, packaging and other housekeeping
- Keep PRs focused, include tests for behaviour changes, and describe what changed and why.

## Updating the changelog

Every user-visible change gets an entry in [`CHANGELOG.md`](CHANGELOG.md) under the
`Unreleased` version, in the matching section (`Added`, `Changed`, `Fixed`, `Security`,
...), following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Releasing

1. Bump `__version__` in `git_context_dump/__init__.py` (the only place the version
   lives; `pyproject.toml` reads it dynamically).
2. In `CHANGELOG.md`, replace `Unreleased` with today's date (`YYYY-MM-DD`) and update
   the comparison links at the bottom.
3. Commit (`chore: release vX.Y.Z`), then tag and push:

   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```

4. The `Release` workflow (`.github/workflows/release.yml`) checks that the tag matches
   `__version__`, builds the sdist and wheel, and publishes them to PyPI through
   trusted publishing. Before the first release, add a trusted publisher on pypi.org
   for this repository (workflow `release.yml`, environment `pypi`), and create a
   `pypi` environment in the GitHub repository settings.
