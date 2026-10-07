# RepoPilot

Deterministic, offline-first repository health analysis tool.

RepoPilot evaluates a Git repository across six dimensions — documentation, structure,
testing, dependency hygiene, security hygiene, and maintainability — and produces a
structured, explainable health report with scores and prioritised findings.

## Quick start

```bash
uv sync
repopilot analyze <path-or-url>
```

## Development

```bash
uv sync
pytest
```
