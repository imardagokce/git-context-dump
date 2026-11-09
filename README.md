<div align="center">

#  git-context-dump

**A zero-dependency Python CLI for turning repositories into clean, LLM-optimised Markdown snapshots.**

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/Dependencies-Zero-brightgreen?style=for-the-badge)](#-features)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](#-license)
[![Platform](https://img.shields.io/badge/Platform-Cross--Platform-lightgrey?style=for-the-badge)](#-quick-start)

[Overview](#-overview) • [Features](#-features) • [Quick Start](#-quick-start) • [CLI Options](#-cli-options) • [Sample Output](#-sample-output)

</div>

---

##  Overview

`git-context-dump` creates a single Markdown snapshot of a project, including its directory structure and readable file contents. It is designed for local LLM workflows with tools such as LM Studio and Ollama, and coding assistants such as Aider.

The utility walks a target directory, honours its root `.gitignore` rules alongside built-in exclusions for common generated and binary files, normalises whitespace, and adds language-aware code fences. The result is ready to paste into a prompt or pipe to another command.

> [!NOTE]
> **Keep context focused:** Ignored files, binary content, and redundant whitespace are filtered before output. A rough token estimate helps you spot snapshots that may exceed your model's context budget.

---

## ✨ Features

- **Zero third-party dependencies:** Runs on the Python standard library.
- **`.gitignore` support:** Applies root `.gitignore` rules and sensible built-in exclusions for virtual environments, build output, and common binary files.
- **ASCII tree visualisation:** Shows the repository structure with `├──` and `└──` branches.
- **Whitespace normalisation:** Trims trailing whitespace and collapses repeated blank lines.
- **Token estimation:** Reports character and estimated token counts using a roughly four-characters-per-token heuristic; `--max-tokens` sets the warning threshold.
- **Flexible output:** Use `--tree-only` to inspect structure without file contents, or `-o -` to write the snapshot to standard output.
- **Language-aware fences:** Recognises common file extensions and formats their contents as Markdown code blocks.

---

## ⚡ Quick Start

### Install

From the repository root, install the command in editable mode:

```bash
pip install -e .
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

Print only the directory tree, or pipe the full snapshot to another command:

```bash
git-context-dump --tree-only --out tree.md
git-context-dump --out - | less
```

---

## ⚙️ CLI Options

| Option | Description | Default |
| --- | --- | --- |
| `-d`, `--dir DIR` | Target directory to scan. | Current working directory |
| `-o`, `--out PATH` | Output Markdown file; use `-` for standard output. | `context.md` |
| `--tree-only` | Include the directory tree without file contents. | Off |
| `--max-tokens N` | Warn when estimated token count exceeds `N`. | `32000` |
| `-h`, `--help` | Show help and exit. | — |

---

##  Sample Output

The generated Markdown starts with metadata and a directory tree, then lists each readable file in its own fenced block, followed by a size summary.

```text
project/
├── README.md
├── pyproject.toml
└── src/
    └── app.py
```

````markdown
# Git Context Dump

- Generated: 2026-11-09T12:00:00+00:00
- Target directory: /path/to/project

## Directory Structure

├── README.md
├── pyproject.toml
└── src
    └── app.py

## File Contents

### File: src/app.py

```python
def main():
    print("Hello, world!")
```

## Summary

- Total characters: 1234
- Estimated tokens: 309
````

---

##  License

This project is licensed under the MIT License.
