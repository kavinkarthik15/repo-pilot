# RepoPilot — Architecture & Design

## Overview

RepoPilot is structured as a layered Python application with a clear separation between repository access, rule evaluation, scoring, domain models, the FastAPI API, the CLI, and the web frontend. Each layer depends only on the layers below it; the API and CLI are peers that both consume the application service layer.

```
┌─────────────────────────────────────────────────────────────┐
│                     Presentation Layer                       │
│        Web Frontend (HTML/CSS/JS, served by FastAPI)        │
│                  CLI  (repopilot.cli)                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                     API Layer                                │
│                FastAPI  (repopilot.api)                      │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                  Application Service Layer                   │
│              AnalysisService  (repopilot.service)            │
└──────┬─────────────────┬─────────────────────┬──────────────┘
       │                 │                     │
┌──────▼──────┐  ┌───────▼──────┐   ┌──────────▼───────────┐
│  Scanner    │  │   Evaluator  │   │      Scorer          │
│ (repopilot  │  │ (repopilot   │   │  (repopilot.scoring) │
│ .scanner)   │  │ .rules)      │   └──────────────────────┘
└──────┬──────┘  └──────────────┘
       │
┌──────▼─────────────────────────────────────────────────────┐
│                  Models Layer                               │
│              (repopilot.models)                             │
└────────────────────────────────────────────────────────────┘
```

---

## Directory Layout

```
repo-pilot/
├── pyproject.toml               # project metadata, deps, entry points
├── uv.lock                      # uv lockfile
├── README.md
├── .gitignore
├── src/
│   └── repopilot/
│       ├── __init__.py
│       ├── models.py            # Pydantic domain models
│       ├── scanner/
│       │   ├── __init__.py
│       │   ├── base.py          # FileTree / ScanResult
│       │   ├── local.py         # LocalScanner
│       │   └── git_clone.py     # GitCloneScanner (wraps LocalScanner)
│       ├── rules/
│       │   ├── __init__.py
│       │   ├── base.py          # Rule ABC
│       │   ├── documentation.py
│       │   ├── structure.py
│       │   ├── testing.py
│       │   ├── dependency.py
│       │   ├── security.py
│       │   └── maintainability.py
│       ├── scoring.py           # ScoreCalculator
│       ├── service.py           # AnalysisService (orchestrator)
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py           # FastAPI app factory
│       │   ├── routes.py        # /analyze, /health
│       │   └── schemas.py       # Pydantic request/response schemas
│       ├── cli.py               # Typer CLI
│       └── frontend/
│           ├── index.html
│           ├── main.js
│           └── styles.css
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    │   ├── test_models.py
    │   ├── test_scanner.py
    │   ├── test_rules_documentation.py
    │   ├── test_rules_structure.py
    │   ├── test_rules_testing.py
    │   ├── test_rules_dependency.py
    │   ├── test_rules_security.py
    │   ├── test_rules_maintainability.py
    │   └── test_scoring.py
    ├── property/
    │   ├── test_scoring_properties.py   # Hypothesis
    │   └── test_models_properties.py
    └── integration/
        ├── test_service.py
        ├── test_api.py
        └── fixtures/            # minimal fake repo trees for tests
            ├── empty_repo/
            ├── good_python_repo/
            └── bad_hygiene_repo/
```

---

## Domain Models (`repopilot.models`)

All models are Pydantic `BaseModel` instances with full type annotations.

### `Severity` (enum)
```
INFO | LOW | MEDIUM | HIGH | CRITICAL
```

`CRITICAL` is reserved for findings where clearly committed credential or secret-related files are detected (e.g. `id_rsa`, `.env` with live credentials, `credentials.json`). It must never expose file contents.

### `Category` (enum)
```
DOCUMENTATION | STRUCTURE | TESTING | DEPENDENCY_HYGIENE |
SECURITY_HYGIENE | MAINTAINABILITY
```

### `Finding`
```python
id: str                     # deterministic, e.g. "doc-no-readme"
category: Category
severity: Severity
title: str
detail: str
affected_paths: list[str]   # relative paths, never absolute; never contents
```

### `RecommendedAction`
```python
finding_ids: list[str]
priority: Severity          # derived from highest-severity linked finding
action: str
```

### `CategoryResult`
```python
category: Category
score: int                  # 0-100
findings: list[Finding]
strengths: list[str]
```

### `RepositoryMetadata`
```python
source: str                 # original input (path or URL)
name: str                   # inferred repo name
analyzed_at: datetime
analyzer_version: str
is_url: bool
```

### `AnalysisReport`
```python
metadata: RepositoryMetadata
overall_score: int
category_results: list[CategoryResult]
strengths: list[str]        # aggregated from all categories
findings: list[Finding]     # aggregated, sorted severity desc
recommended_actions: list[RecommendedAction]

def to_json(self) -> str    # serialize
```

---

## Scanner Layer (`repopilot.scanner`)

### `FileEntry`
```python
path: Path           # absolute path on the local filesystem
relative: str        # path relative to repo root (for reports)
size_bytes: int
is_dir: bool
```

### `FileTree`
An immutable snapshot of the repository structure produced by walking the filesystem.

```python
root: Path
entries: list[FileEntry]

# Convenience methods:
def has_file(self, name: str, *, case_insensitive: bool = True) -> bool
def find_files(self, pattern: str) -> list[FileEntry]   # glob
def find_dirs(self, name: str) -> list[FileEntry]
def root_files(self) -> list[FileEntry]                 # depth == 1
def read_text(self, relative: str) -> str | None        # safe read, max 1 MB
```

### `LocalScanner`
Walks a local directory and produces a `FileTree`.

```python
EXCLUDED_DIRS: frozenset = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "env", ".eggs", "dist", "build", ".gradle", ".next",
    ".nuxt", "target", ".tox",
}

def scan(self, path: Path) -> FileTree
```

`scan` raises `ScanError` if the path does not exist or is not a directory.

### `GitCloneScanner`
Clones a URL to a `tempfile.mkdtemp()` directory, delegates to `LocalScanner`, and guarantees cleanup via context-manager / `__del__`.

```python
def scan(self, url: str) -> FileTree   # may raise ScanError
```

---

## Rules Layer (`repopilot.rules`)

### `Rule` (ABC)
```python
@property
def category(self) -> Category: ...

def evaluate(self, tree: FileTree) -> tuple[list[Finding], list[str]]:
    """Return (findings, strengths)."""
    ...
```

Each concrete rule class encapsulates one conceptual check (e.g. `ReadmeRule`, `LicenseRule`, `TestFilesRule`). Rules are pure functions of a `FileTree`; they hold no mutable state and are safe to call multiple times.

### Finding ID convention
`<category-prefix>-<short-slug>`, e.g.:
- `doc-no-readme`
- `doc-readme-minimal`
- `doc-no-contributing`
- `struct-no-tests-dir`
- `test-no-test-files`
- `dep-missing-lockfile-npm`
- `sec-committed-env-file`
- `sec-no-gitignore`
- `maint-no-license`
- `maint-no-ci`

### Rule inventory

#### Documentation rules (`documentation.py`)
| Rule class | Finding IDs | Severity |
|-----------|-------------|----------|
| `ReadmePresenceRule` | `doc-no-readme` | HIGH |
| `ReadmeSizeRule` | `doc-readme-minimal`, `doc-readme-brief` | HIGH, MEDIUM |
| `ReadmeSectionsRule` | `doc-readme-missing-<section>` | LOW (per section) |
| `ContributingRule` | `doc-no-contributing` | LOW |
| `DocsDirectoryRule` | `doc-no-docs-dir` | INFO |

#### Structure rules (`structure.py`)
| Rule class | Finding IDs | Severity |
|-----------|-------------|----------|
| `SourceDirectoryRule` | `struct-no-src-dir` | LOW |
| `TestDirectoryRule` | `struct-no-tests-dir` | MEDIUM |
| `EmptyRepoRule` | `struct-empty-repo` | HIGH |
| `ConfigFilesRule` | `struct-no-config-files` | INFO |

#### Testing rules (`testing.py`)
| Rule class | Finding IDs | Severity |
|-----------|-------------|----------|
| `TestFilesRule` | `test-no-test-files` | HIGH |
| `TestFrameworkConfigRule` | `test-no-framework-config` | LOW |

#### Dependency rules (`dependency.py`)
| Rule class | Finding IDs | Severity |
|-----------|-------------|----------|
| `LockfileRule` | `dep-missing-lockfile-<ecosystem>` | MEDIUM |
| `CommittedEnvFileRule` | `dep-committed-env-file` | CRITICAL |
| `CommittedSecretFileRule` | `dep-committed-secret-file` | CRITICAL |
| `EnvVariantRule` | `dep-committed-env-variant` | MEDIUM |

#### Security rules (`security.py`)
| Rule class | Finding IDs | Severity |
|-----------|-------------|----------|
| `GitignorePresenceRule` | `sec-no-gitignore` | MEDIUM |
| `GitignoreContentRule` | `sec-gitignore-missing-<entry>` | LOW |
| `CommittedGeneratedDirRule` | `sec-committed-generated-dir` | HIGH |
| `LargeFilesRule` | `sec-large-binary-file` | MEDIUM |

#### Maintainability rules (`maintainability.py`)
| Rule class | Finding IDs | Severity |
|-----------|-------------|----------|
| `LicenseRule` | `maint-no-license` | MEDIUM |
| `CIConfigRule` | `maint-no-ci` | LOW |
| `LintConfigRule` | `maint-no-lint-config` | LOW |
| `ProjectMetadataRule` | `maint-no-project-metadata` | LOW |
| `EntryPointRule` | `maint-no-entry-point` | INFO |

---

## Scoring Layer (`repopilot.scoring`)

### Deduction table (default, overridable via config)
```python
DEDUCTIONS: dict[Severity, int] = {
    Severity.INFO:     0,
    Severity.LOW:      3,
    Severity.MEDIUM:   7,
    Severity.HIGH:     15,
    Severity.CRITICAL: 25,
}
```

### Category weights (default)
```python
WEIGHTS: dict[Category, float] = {
    Category.DOCUMENTATION:      0.20,
    Category.STRUCTURE:          0.15,
    Category.TESTING:            0.20,
    Category.DEPENDENCY_HYGIENE: 0.15,
    Category.SECURITY_HYGIENE:   0.15,
    Category.MAINTAINABILITY:    0.15,
}
```

### `ScoreCalculator`
```python
def calculate_category_score(
    self,
    findings: list[Finding],
    max_deduction: int = 100,
) -> int:
    """Start at 100, subtract per-finding deduction, floor at 0."""

def calculate_overall_score(
    self,
    category_scores: dict[Category, int],
) -> int:
    """Weighted average, rounded to nearest integer."""
```

Scoring is a pure function of findings: deterministic, no I/O.

---

## Application Service Layer (`repopilot.service`)

### `AnalysisService`
```python
def __init__(
    self,
    rules: list[Rule] | None = None,      # injection point for tests / extensions
    scorer: ScoreCalculator | None = None,
) -> None: ...

def analyze(self, source: str) -> AnalysisReport:
    """
    1. Determine whether source is a URL or local path.
    2. Use GitCloneScanner or LocalScanner to produce FileTree.
    3. Run each Rule against the FileTree.
    4. Aggregate findings and strengths per category.
    5. Calculate scores.
    6. Build and return AnalysisReport.
    7. Clean up temp clone if applicable.
    """
```

The service raises `InvalidSourceError` (bad input) or `ScanError` (unreadable repo).

---

## API Layer (`repopilot.api`)

### Routes
```
POST /analyze
  Request body:  { "source": str }
  Response:      AnalysisReport JSON (200)
  Errors:        400 InvalidSourceError, 500 ScanError/unexpected

GET /health
  Response: { "status": "ok", "version": str }

GET /
  Response: serves frontend index.html

GET /static/{path}
  Response: serves frontend assets
```

### Error schema
```json
{ "error": "human-readable message", "code": "INVALID_SOURCE | SCAN_ERROR | INTERNAL_ERROR" }
```

### FastAPI app factory (`app.py`)
Returns a configured `FastAPI` instance. The frontend static files are mounted at `/static`. The root route serves `index.html`.

---

## CLI Layer (`repopilot.cli`)

Built with [Typer](https://typer.tiangolo.com/).

```
repopilot analyze <source> [--output FILE] [--format text|json]
repopilot version
```

Summary output (default) example:
```
RepoPilot Analysis — my-project
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall Score:  74 / 100

Category Scores:
  Documentation     85
  Structure         90
  Testing           60  ← no test files found
  Dependency Hygiene 70
  Security & Hygiene 85
  Maintainability   70

Findings (4):
  [HIGH]   test-no-test-files          No test files found
  [MEDIUM] dep-missing-lockfile-npm    package.json has no lockfile
  [MEDIUM] maint-no-license            No LICENSE file found
  [LOW]    sec-gitignore-missing-venv  .gitignore doesn't mention .venv

Recommended Actions:
  1. Add automated tests for the codebase.
  2. Commit a lockfile alongside package.json.
  3. Add a LICENSE file to clarify usage terms.
```

---

## Frontend (`repopilot.frontend`)

A lightweight single-page application — no build step required in v1.

### Technology choices
- Vanilla HTML5, CSS3, JavaScript (ES2022 modules).
- No external frontend framework dependencies (avoids build tooling in v1).
- Fetch API for the `/analyze` call.

### UI layout
```
┌────────────────────────────────────────────┐
│  RepoPilot               [header]          │
├────────────────────────────────────────────┤
│  [ Repository path or URL         ] [Analyze] │
├────────────────────────────────────────────┤
│  ┌─────────────────────────────────────┐  │
│  │  Overall Score: 74/100   ████████░░ │  │
│  └─────────────────────────────────────┘  │
│                                            │
│  Category Scores  (horizontal bar chart)  │
│  Documentation     ████████████░░  85     │
│  Testing           ██████░░░░░░░░  60     │
│  …                                        │
│                                            │
│  Strengths         ✓ README present       │
│                    ✓ CI configured        │
│                                            │
│  Findings          [HIGH] No test files   │
│                    [MEDIUM] …             │
│                                            │
│  Recommended Actions                      │
│  1. Add automated tests …                 │
└────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. FileTree abstraction
All rules operate on `FileTree`, not raw `pathlib.Path`. This decouples rules from the filesystem and makes them fully testable by constructing synthetic `FileTree` objects.

### 2. Rule injection
`AnalysisService` accepts a `list[Rule]` via constructor. The default list registers all built-in rules. This pattern allows:
- Unit-testing individual rules in isolation.
- Future plug-in rules (e.g. a GitHub API rule) without modifying core code.

### 3. No secret content ever leaves the scanner
`FileTree.read_text` refuses to return content of files whose names match the secret-file patterns. Security rules only record the file path, never the content. This is enforced at the model layer by design, not by convention.

### 4. Deterministic finding IDs
Finding IDs are hard-coded slugs in each rule class. This enables stable references across runs, regression detection, and future suppression/allow-list support.

### 5. Scoring is purely functional
`ScoreCalculator` takes findings, returns scores. No I/O, no side effects. This makes it trivial to property-test with Hypothesis.

### 6. Temp clone lifecycle
`GitCloneScanner` is a context manager. If analysis raises an exception, the `__exit__` path still removes the temp directory. A `__del__` guard is included as a fallback for cases where the context manager is used incorrectly.

### 7. Frontend served inline
The FastAPI backend mounts the frontend static files. In v1, no separate frontend server is needed. The single `repopilot serve` command starts everything.

### 8. Extensibility seam for GitHub/MCP
A `GitHubScanner` (future) would implement the same `scan(source) -> FileTree` interface and be injected into `AnalysisService` just like `GitCloneScanner`. No changes to rules, scoring, or API would be needed.

---

## Dependency Inventory

### Runtime
| Package | Purpose |
|---------|---------|
| `fastapi` | HTTP API framework |
| `uvicorn[standard]` | ASGI server |
| `pydantic` | Domain models and validation |
| `typer[all]` | CLI framework |
| `gitpython` | Git clone for URL analysis |
| `toml` / stdlib `tomllib` | Parse `pyproject.toml`, `Cargo.toml` |

### Development / Test
| Package | Purpose |
|---------|---------|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support |
| `httpx` | AsyncClient for API tests |
| `hypothesis` | Property-based testing |
| `ruff` | Linting and formatting |
| `mypy` | Static type checking |

### Python stdlib only (no additional dep)
`pathlib`, `fnmatch`, `tomllib` (3.11+), `tempfile`, `shutil`, `json`, `datetime`, `re`, `os`

---

## Error Handling Strategy

| Layer | Exception | HTTP / Exit |
|-------|-----------|-------------|
| Scanner | `ScanError` (subclass of `RepoPilotError`) | 500 / exit 1 |
| Input validation | `InvalidSourceError` | 400 / exit 2 |
| Rule evaluation | Rules MUST NOT raise; errors are caught and converted to an INFO finding | — |
| Unexpected | Unhandled exception | 500 / exit 1 |

---

## Testing Strategy

### Unit tests
- Each rule module has a corresponding test file.
- Tests construct `FileTree` objects from fixture directories (not real repos) using a helper `make_tree(files: dict[str, str]) -> FileTree`.
- Scorer tests use lists of synthetic `Finding` objects.

### Property-based tests (Hypothesis)
- `test_scoring_properties.py`: verify that scores are always in [0, 100], that adding more findings never increases a score, that an empty finding list always yields 100.
- `test_models_properties.py`: round-trip JSON serialization of `AnalysisReport`.

### Integration tests
- `test_service.py`: exercise `AnalysisService` against fixture repo directories.
- `test_api.py`: use `httpx.AsyncClient` against the FastAPI app with fixture repos.

### Fixtures
Three fixture repos live under `tests/integration/fixtures/`:
1. `empty_repo/` — just a `.git/` placeholder; triggers empty-repo and missing-everything findings.
2. `good_python_repo/` — has README, tests, pyproject.toml, lockfile, LICENSE, .gitignore, CI config.
3. `bad_hygiene_repo/` — has .env file, node_modules dir, no README, no tests.
