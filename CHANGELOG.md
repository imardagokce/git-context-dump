# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - Unreleased

### Fixed

- Nested code fences no longer break the output (fence length is chosen dynamically).
- Writing to stdout on Windows (cp125x consoles) no longer crashes.
- The output file is excluded from later dumps.
- The summary token count now matches the CLI threshold check.
- A UTF-8 BOM is stripped from file contents.
- UTF-16 files are decoded.
- Output is written with LF newlines on every platform.
- `.gitignore` semantics: `**`, `*` not crossing `/`, escaped `\#` / `\!`, trailing
  spaces, nested `.gitignore` files, `.git/info/exclude` and `core.excludesFile`;
  a file inside an excluded directory can no longer be re-included.
- Piping into a reader that stops early (`| head`) exits cleanly instead of failing.
- Binary, undecodable, oversized and unreadable files are reported instead of
  being dropped silently.

### Security

- Secret-like files (`.env*`, `*.pem`, `*.key`, `id_rsa*`, `*.p12`, `*.pfx`,
  `credentials*.json`, `.npmrc`, `.pypirc`, `.netrc`, ...) are excluded by default.
  Templates such as `.env.example` are still included.
- Symlinks and Windows junctions that resolve outside the target directory are
  skipped, and directory links are never followed.
- A warning is emitted for lines that look like secrets.
- The header shows the repository name instead of the absolute local path.

### Added

- Git-aware file listing via `git ls-files`, with a `--no-git` fallback.
- Branch and commit metadata in the header.
- `--diff`, `--staged` and `--since REF`.
- `--include` / `--exclude` glob filters.
- `.contextdumpignore` support.
- `--format markdown|xml|json`.
- `--copy` to copy the output to the clipboard.
- `--max-file-size`.
- `--fit-budget`.
- Per-file token table (largest files).
- Skipped-files report.
- `--verbose` and `--version`.
- Optional `--tokenizer tiktoken` (install the `tiktoken` extra).
- CI matrix (Linux, Windows, macOS; Python 3.10, 3.12, 3.13).
- ruff, mypy and coverage configuration.
- `py.typed` marker.

### Changed

- `parser.py` renamed to `walker.py`; `parser.py` is kept as a deprecated shim.
- The directory tree is traversed only once.
- Requires Python 3.10+.
- The version is single-sourced from `git_context_dump/__init__.py`.
- Expanded default binary, lockfile, minified-bundle and coverage-artefact exclusions
  (they can be re-included with `!pattern` in `.contextdumpignore`).
- The directory tree is rendered in a `text` code block and lists files only.
- Library API: `build_dump(DumpOptions(...))` returns a `DumpResult`;
  `generate_dump()` remains as a compatibility wrapper.

## [1.0.0] - 2026-11-09

- Initial release: CLI, root `.gitignore` support, ASCII tree, whitespace
  normalisation, token estimate, `--tree-only`, `-o -`.

[1.1.0]: https://github.com/imardagokce/git-context-dump/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/imardagokce/git-context-dump/releases/tag/v1.0.0
