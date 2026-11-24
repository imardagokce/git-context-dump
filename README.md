<div align="center">

#  git-context-dump

**A zero-dependency Python CLI for turning repositories into clean, LLM-optimised Markdown, XML or JSON snapshots.**

[![CI](https://github.com/imardagokce/git-context-dump/actions/workflows/ci.yml/badge.svg)](https://github.com/imardagokce/git-context-dump/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/Dependencies-Zero-brightgreen?style=for-the-badge)](#-features)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](#-license)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey?style=for-the-badge)](#-quick-start)

[Overview](#-overview) • [Features](#-features) • [Quick Start](#-quick-start) • [CLI Options](#-cli-options) • [Ignore Rules](#-ignore-rules) • [Sample Output](#-sample-output) • [Development](#-development)

</div>

---

##  Overview

`git-context-dump` creates a single snapshot of a project, including its directory structure and readable file contents. It is designed for LLM workflows with tools such as LM Studio and Ollama, coding assistants such as Aider, and chat assistants such as Claude.

Inside a Git repository it asks Git for the file list, so every ignore rule Git knows about applies. Outside one it walks the directory itself with the same gitignore semantics. It leaves out generated files, binaries, lockfiles and secrets, normalises whitespace, and wraps each file in a code fence that cannot be broken by the file's own contents.

> [!WARNING]
> **Review before you share.** Secret-like files (`.env`, private keys, credential files, …) are excluded by default, and lines that look like credentials trigger a warning. Both are safety nets, not guarantees.

---

## ✨ Features

- **Zero third-party dependencies:** Runs on the Python standard library (an optional `tiktoken` extra gives exact token counts).
- **Git-aware:** Uses `git ls-files` when available, so nested `.gitignore` files, `.git/info/exclude` and your global excludes all apply. The header shows the branch and commit.
- **Change-focused dumps:** `--diff`, `--staged` and `--since REF` include only the files you changed.
- **Accurate ignore rules without Git:** `--no-git` (or a plain folder) uses a full gitignore implementation: `**`, `*` that stops at `/`, negation, escapes, and nested `.gitignore` files.
- **Safe by default:** Secrets, binaries, lockfiles, minified bundles, the dump's own output file, and links that point outside the target directory are all left out.
- **Unbreakable fences:** Code fences grow longer than any backtick run inside a file, so Markdown files with their own code blocks render correctly.
- **Three formats:** Markdown (default), XML with CDATA sections, or JSON.
- **Token budgeting:** Shows a per-file token table and warns above `--max-tokens`. `--fit-budget` drops the largest files until the dump fits.
- **Transparent:** Every skipped file is counted in the summary, with the reason (binary, too large, unreadable, budget…).
- **Cross-platform:** UTF-8 output on every console, LF line endings, UTF-8 BOM and UTF-16 input handled, and `--copy` to the clipboard.

---

## ⚡ Quick Start

### Install

```bash
pipx install git+https://github.com/imardagokce/git-context-dump
# or, from a clone, in editable mode:
pip install -e .
# optional exact token counts:
pip install -e ".[tiktoken]"
```

### Generate a snapshot

Run from the repository you want to capture. By default, the snapshot is written to `context.md` in the current directory.

```bash
git-context-dump
```

Choose a target repository and output file with `--dir` and `--out`:

```bash
git-context-dump --dir ./my-project --out ./my-project-context.md
```

Common recipes:

```bash
git-context-dump --tree-only --out tree.md          # structure only
git-context-dump --out - | less                      # write to standard output
git-context-dump --diff --copy                       # uncommitted work, copied to the clipboard
git-context-dump --since main --format xml           # everything changed on this branch, as XML
git-context-dump --include "src/**" --exclude "*.test.ts"
git-context-dump --max-tokens 100000 --fit-budget    # stay inside a context window
```

---

## ⚙️ CLI Options

| Option | Description | Default |
| --- | --- | --- |
| `-d`, `--dir DIR` | Target directory to scan. | Current directory |
| `-o`, `--out PATH` | Output file (parent folders are created); use `-` for standard output. | `context.md` / `.xml` / `.json` |
| `-f`, `--format FMT` | `markdown`, `xml` or `json`. | `markdown` |
| `--tree-only` | Include the directory tree without file contents. | Off |
| `--include GLOB` | Only include files matching this gitignore-style glob. Repeatable. | All files |
| `--exclude GLOB` | Exclude paths matching this gitignore-style glob. Repeatable. | — |
| `--max-file-size SIZE` | Skip larger files (`500`, `256k`, `1m`); `0` disables the limit. | `256k` |
| `--no-git` | Walk the file system instead of asking Git for the file list. | Auto |
| `--diff` | Only files changed since `HEAD`, plus untracked files. | — |
| `--staged` | Only files staged for the next commit (contents are read from the working tree). | — |
| `--since REF` | Only files changed since a commit, branch or tag, plus untracked files. | — |
| `--max-tokens N` | Warn when the estimated token count exceeds `N`. | `32000` |
| `--fit-budget` | Drop the largest files until the dump fits within `--max-tokens`. | Off |
| `--tokenizer NAME` | `heuristic` (~4 characters per token) or `tiktoken` (needs the extra). | `heuristic` |
| `--copy` | Also copy the dump to the clipboard (`clip`, `pbcopy`, `wl-copy`, `xclip` or `xsel`). | Off |
| `-v`, `--verbose` | List every skipped file and the file source on standard error. | Off |
| `--version` | Print the version and exit. | — |
| `-h`, `--help` | Show help and exit. | — |

Diagnostics (warnings, skipped files) go to standard error, so piping the dump is always safe. The exit code is `0` on success and `1` on errors.

---

##  Ignore Rules

Rules are applied from lowest to highest precedence. The last matching rule wins, and a file can never be re-included when one of its parent directories is excluded (the same rule Git uses).

1. **Built-in defaults:** VCS folders, virtual environments, caches and coverage files, build output, binaries (images, fonts, media, archives, compiled files, documents, databases), lockfiles, minified bundles, source maps, and secrets (`.env`, `.env.*`, `*.pem`, `*.key`, `id_rsa*`, `credentials*.json`, `.npmrc`, `.netrc`, `*.tfstate`, `.ssh/`, `.aws/`, …). `.env.example`, `.env.sample` and `.env.template` stay included.
2. **Git's own rules:** applied by `git ls-files` in a repository, or re-implemented in `--no-git` mode (`core.excludesFile`, `.git/info/exclude`, then every `.gitignore` from the root down).
3. **`.contextdumpignore`** in the target directory, using gitignore syntax. Use it to drop files only from dumps, or to re-include a default (for example `!yarn.lock`).
4. **`--exclude`** patterns.
5. **The output file itself**, so re-running never dumps the previous snapshot.

Symlinks and Windows junctions that resolve outside the target directory are always skipped, and directory links are never followed.

---

##  Sample Output

The generated Markdown starts with metadata and a directory tree. Each readable file then gets its own fenced block, and a summary closes the document.

`````markdown
# Git Context Dump

- Generated: 2026-11-24T12:00:00+00:00
- Repository: project
- Branch: main
- Commit: a105f45 (with uncommitted changes)

## Directory Structure

```text
├── README.md
├── pyproject.toml
└── src
    └── app.py
```

## File Contents

### File: README.md

````markdown
Run it with:

```bash
python -m app
```
````

### File: src/app.py

```python
def main():
    print("Hello, world!")
```

## Summary

- Files included: 3
- Files skipped: 1 (binary: 1)
- Total characters: 1234
- Estimated tokens: 309 (heuristic, ~4 characters per token)

### Largest Files

| File | Tokens |
| --- | ---: |
| `README.md` | 14 |
| `src/app.py` | 11 |

### Skipped Files

- `logo.bin`: binary
`````

`--format xml` produces `<context_dump>` with `<file path="…" language="…" tokens="…">` elements that wrap contents in CDATA. `--format json` produces an object with `files`, `skipped` and `summary` keys.

### Using it from Python

```python
from pathlib import Path
from git_context_dump.dumper import DumpOptions, build_dump

result = build_dump(DumpOptions(root=Path("."), output_format="markdown", exclude=["docs/"]))
print(result.tokens, len(result.files), result.skipped, result.secret_findings)
```

---

##  Development

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m unittest discover -s tests -t .
ruff check . && ruff format --check . && mypy
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for coverage, conventions and the release process, and [CHANGELOG.md](CHANGELOG.md) for the release history.

---

##  License

This project is licensed under the MIT License.
