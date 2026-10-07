# RepoPilot — Technical Standards

## Language and Runtime

- **Python 3.13** is the minimum required version. Use modern language features (structural pattern matching, typed generics, `tomllib`, etc.) where they improve clarity.
- All public functions, methods, and module-level variables must carry **type hints**. Use `from __future__ import annotations` where needed for forward references.

## Core Frameworks and Libraries

| Purpose                     | Library / Tool                            |
|-----------------------------|-------------------------------------------|
| Web API                     | FastAPI                                   |
| Data validation / models    | Pydantic v2                               |
| Unit and integration tests  | pytest                                    |
| Property-based tests        | Hypothesis                                |
| ASGI server (dev/prod)      | Uvicorn                                   |
| Dependency management       | `pyproject.toml` with `uv` or `pip`       |

No paid APIs are permitted anywhere in the project. The offline core must operate without any network dependency.

## Architectural Layers

The codebase is divided into strict layers. Higher layers may depend on lower ones; lower layers must never import from higher ones.

```
repopilot/
  domain/        ← Pure data models (Pydantic). No I/O, no business logic.
  scanners/      ← Read-only filesystem/Git inspection. Produce raw observations.
  rules/         ← Stateless functions: observation → Finding. No I/O.
  scoring/       ← Aggregate findings → dimension scores → overall score.
  services/      ← Orchestrate scanner + rules + scoring. Entry point for callers.
  api/           ← FastAPI routers. Thin: validate input, call services, return responses.
  presentation/  ← CLI output formatting and report serialisation.
```

The `services/` layer is the only public interface for analysis. The `api/` layer must not contain business logic. The `domain/` layer must not import from any other internal module.

## Domain Models

- All data structures that cross layer boundaries must be **Pydantic models**.
- Use `model_config = ConfigDict(frozen=True)` for value objects that should be immutable after construction.
- Finding, DimensionScore, HealthReport, AnalysisRequest, and RuleResult are first-class domain types; do not pass raw dicts across layer boundaries.

## Dependency Management

- Declare all dependencies in `pyproject.toml` with **pinned or tightly bounded versions** (`>=x.y,<x+1`).
- Separate `[project.optional-dependencies]` groups for `dev`, `test`, and `lint`.
- Do not add a dependency that can be replaced by the standard library or a simpler approach.

## Error Handling

- Raise typed, descriptive exceptions defined in `repopilot/exceptions.py`.
- Never swallow exceptions silently; log at the appropriate level and re-raise or convert to a domain error.
- FastAPI exception handlers in `api/` convert domain exceptions to appropriate HTTP status codes. Business logic must not reference HTTP concepts.

## Testing Expectations

- Every scanner, rule, and scoring function must have unit tests.
- Service-layer integration tests exercise the full analysis pipeline against fixture repositories (small directory trees checked in under `tests/fixtures/`).
- **Property-based tests with Hypothesis** are required for:
  - Scoring formulas (score always in `[0, 100]`, monotonicity where applicable).
  - Rule functions (valid input never raises; severity mapping is exhaustive).
  - Domain model construction (round-trip serialisation).
- Test coverage is not a vanity metric; untested rules are incomplete rules.

## Determinism

- Analysis results must be deterministic for the same repository state. Avoid `set` iteration, unordered dict traversal, or timestamp-dependent branching in rule and scoring logic.
- Where ordering matters (finding lists, dimension scores), sort by a stable key before returning.

## Security Practices

- See `security.md` for mandatory constraints.
- Never `eval`, `exec`, or dynamically import code from the repository under analysis.
- Use `pathlib.Path` for all filesystem operations; validate that resolved paths stay within the expected root.
- Strip sensitive content before including any path or filename in a finding message.

## No External Service Dependency in Core

The `domain/`, `scanners/`, `rules/`, `scoring/`, and `services/` layers must not make network calls. HTTP calls are permitted only in `api/` (for serving) and in a dedicated `remote/` module responsible solely for cloning remote repositories before analysis begins.

## Code Style

- Follow PEP 8. Use `ruff` for linting and formatting.
- Maximum line length: 100 characters.
- Docstrings on all public symbols; single-line where sufficient, multi-line for complex behaviour.
- Prefer explicit over implicit; avoid magic strings — use `Enum` or named constants.
