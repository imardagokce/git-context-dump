# git-context-dump

**Turn a working directory into a tidy Markdown snapshot.**

`git-context-dump` collects a readable directory tree and text files into one file that is easy to share with a colleague, attach to an issue, or provide as project context to a language model. It uses Python's standard library and honours root `.gitignore` rules alongside sensible defaults for generated and binary files.

## Key Features

- Produces a readable, sorted ASCII directory tree.
- Includes UTF-8 text files in language-labelled Markdown code blocks.
- Skips common generated, binary, and ignored paths.
- Offers a tree-only mode for a quick overview.
- Reports character and approximate token counts.
- Runs on Python 3.12 or newer with no runtime dependencies.

## Quick Start

Run directly from a checkout:

```console
python -m git_context_dump.cli --dir . --out context.md
```

Or install the project to use its console command:

```console
python -m pip install .
git-context-dump --dir . --out context.md
```

Print the dump to the terminal instead of writing a file:

```console
git-context-dump --dir . --out -
```

Generate only the directory overview:

```console
git-context-dump --tree-only --out structure.md
```

## CLI Options

| Option | Default | Description |
| --- | --- | --- |
| `-d`, `--dir` | Current directory | Repository or directory to inspect. |
| `-o`, `--out` | `context.md` | Markdown output path; use `-` for standard output. |
| `--tree-only` | Off | Include the directory structure without file contents. |
| `--max-tokens` | `32000` | Warn on standard error when the estimated token count exceeds this threshold. |
| `-h`, `--help` | — | Show the command help. |

## Sample Output

````markdown
# Git Context Dump

- Generated: 2026-01-01T12:00:00+00:00
- Target directory: /work/example

## Directory Structure

├── README.md
└── src
    └── main.py

## File Contents

### File: src/main.py

```python
print("Hello, world!")
```

## Summary

- Total characters: 248
- Estimated tokens: 62
````
