# RepoPilot — Repository Structure

## Top-Level Layout

```
repo-pilot/
├── repopilot/                  # Installable Python package — all application code
│   ├── domain/                 # Pure data models
│   ├── scanners/               # Read-only repository inspection
│   ├── rules/                  # Stateless analysis rules
│   ├── scoring/                # Score aggregation
│   ├── services/               # Orchestration / public API of the core library
│   ├── api/                    # FastAPI application
│   ├── presentation/           # CLI and report formatting
│   ├── remote/                 # Remote repo fetching (clone + cleanup only)
│   ├── exceptions.py           # Project-wide exception hierarchy
│   └── __init__.py
├── tests/
│   ├── unit/                   # Fast, isolated unit tests
│   ├── integration/            # Full-pipeline tests against fixture repos
│   ├── property/               # Hypothesis property-based tests
│   └── fixtures/               # Small synthetic repository trees for testing
├── frontend/                   # Static frontend assets (if applicable)
├── .kiro/
│   ├── steering/               # Persistent project guidance for Kiro
│   ├── specs/                  # Kiro feature specifications
│   └── hooks/                  # Kiro automation hooks
├── pyproject.toml              # Project metadata, dependencies, tool config
├── README.md
└── CONTRIBUTING.md
```

## Module Responsibilities

### `repopilot/domain/`

Contains all Pydantic models that represent the core concepts of the problem domain. No I/O, no business logic, no imports from other internal modules.

Key types: `Finding`, `Severity`, `DimensionScore`, `HealthReport`, `AnalysisRequest`, `RuleResult`, `RepositoryMetadata`.

### `repopilot/scanners/`

Read-only inspectors that walk the filesystem or query Git metadata and produce raw, uninterpreted observations. Scanners return plain domain objects or primitive data — they do not apply judgement.

Sub-modules correspond to scan targets: `filesystem.py`, `git_meta.py`, `dependency.py`, `secrets_paths.py`.

Scanners may be composed and are independently testable with any directory path.

### `repopilot/rules/`

Stateless pure functions: `(observation) → list[Finding]`. Each rule lives in its own module grouped by analysis dimension (documentation, structure, testing, dependencies, security, maintainability). Rules must not perform I/O.

Every rule function is named descriptively (`check_readme_presence`, `check_pinned_dependencies`, etc.) and is registered in a dimension-specific rule set so the service layer can enumerate and invoke them uniformly.

### `repopilot/scoring/`

Aggregates `Finding` lists into `DimensionScore` objects and combines dimension scores into an overall `HealthReport` score. Scoring formulas are documented in docstrings and must be deterministic and monotonic (more/higher-severity findings → lower score).

Weights per dimension are declared as named constants; they are never magic numbers.

### `repopilot/services/`

The single public interface for consuming applications. The primary entry point is `AnalysisService`, which:

1. Accepts an `AnalysisRequest` (local path or remote URL).
2. Invokes the appropriate scanners.
3. Runs all relevant rules against the scan results.
4. Computes scores.
5. Returns a `HealthReport`.

The service layer owns orchestration only — no raw I/O, no HTTP, no presentation logic.

### `repopilot/api/`

FastAPI application. Contains routers, request/response schemas (separate from domain models where the shapes differ), dependency injection setup, and exception handlers.

Routers must be thin: validate the incoming request, call `services/`, and serialise the response. No analysis logic belongs here.

Sub-modules: `app.py` (application factory), `routers/` (one file per logical resource group), `schemas.py` (API-layer Pydantic models).

### `repopilot/presentation/`

CLI command definitions and report formatters. Consumes `HealthReport` from the service layer and renders it as plain text, Markdown, or JSON for terminal output.

### `repopilot/remote/`

Handles cloning a remote Git URL to a temporary local directory and deleting it after analysis. This is the only module permitted to make outbound network calls. It must guarantee cleanup even on error (use `contextlib.ExitStack` or a context manager).

### `repopilot/exceptions.py`

Defines the exception hierarchy: `RepoPilotError` (base), `RepositoryNotFoundError`, `InvalidRepositoryError`, `ScanError`, `RuleError`, `CleanupError`. All domain-level exceptions inherit from `RepoPilotError`.

## Test Directory Responsibilities

### `tests/unit/`

One test module per source module. Tests are fast and isolated — no filesystem access beyond `tmp_path`, no network.

### `tests/integration/`

Tests that exercise the full `AnalysisService` pipeline against fixture repositories in `tests/fixtures/`. Each fixture is a minimal directory tree that demonstrates a specific condition (e.g., a repo with no README, a repo with unpinned dependencies).

### `tests/property/`

Hypothesis-driven tests covering scoring invariants, rule-function contracts, and domain model round-trips. Grouped by the layer they target.

### `tests/fixtures/`

Small, static directory trees committed to the repository. Each fixture is self-contained and named for the scenario it represents (`no_readme/`, `pinned_deps/`, `secret_files/`, etc.). Fixtures must not contain real secrets.

## Kiro Configuration

### `.kiro/steering/`

Persistent guidance documents read by Kiro at the start of every session. Cover product intent, technical standards, structure, security rules, and development workflow. Updated when intentional design decisions change.

### `.kiro/specs/`

Feature specifications created during Kiro Spec sessions. Each spec tracks requirements, design, and implementation tasks for a discrete feature.

### `.kiro/hooks/`

Automation hooks that fire on IDE events (file save, task completion, etc.) to run linters, tests, or inject context.
