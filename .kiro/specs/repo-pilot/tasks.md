# RepoPilot — Implementation Tasks

## How to read this file

Tasks are ordered so each builds on what came before. Within a phase, tasks at the same level can be parallelised. Every task references the requirement IDs it satisfies and the design sections it implements. The "Done when" criterion is the acceptance check.

---

## Phase 0 — Project Scaffolding

### Task 0.1 — Repository & project layout
**Refs:** NFR-005, NFR-007, NFR-009  
**Design:** Directory Layout

Create the full directory skeleton:

```
repo-pilot/
├── pyproject.toml
├── .gitignore
├── README.md
├── src/
│   └── repopilot/
│       ├── __init__.py
│       ├── scanner/
│       ├── rules/
│       ├── api/
│       └── frontend/
└── tests/
    ├── unit/
    ├── property/
    └── integration/
        └── fixtures/
```

`pyproject.toml` must declare:
- `name = "repopilot"`, `version = "0.1.0"`, `requires-python = ">=3.13"`
- All runtime dependencies listed in the design dependency table with pinned minimum versions.
- Dev dependencies in `[dependency-groups]` or `[project.optional-dependencies]`.
- Entry point: `[project.scripts] repopilot = "repopilot.cli:app"`.
- Ruff configuration in `[tool.ruff]`.
- Pytest configuration in `[tool.pytest.ini_options]`.

**Done when:** `uv sync` succeeds and `pytest --collect-only` exits 0 (no tests yet is fine).

---

### Task 0.2 — Domain models
**Refs:** REQ-008, REQ-009  
**Design:** Domain Models section

Implement `src/repopilot/models.py` with all Pydantic models:
- `Severity` (StrEnum or Enum)
- `Category` (StrEnum or Enum)
- `Finding` (with validator: `affected_paths` must contain relative paths only — no absolute paths, no file contents)
- `RecommendedAction`
- `CategoryResult`
- `RepositoryMetadata`
- `AnalysisReport` (including `to_json()` method)

**Done when:** `from repopilot.models import AnalysisReport` succeeds; `pytest tests/unit/test_models.py` passes.

---

## Phase 1 — Scanner

### Task 1.1 — FileTree and LocalScanner
**Refs:** REQ-001.1, REQ-001.5, REQ-001.6, NFR-010  
**Design:** Scanner Layer

Implement:
- `src/repopilot/scanner/base.py` — `FileEntry`, `FileTree`, `ScanError`
- `src/repopilot/scanner/local.py` — `LocalScanner`

`FileTree` must implement all five convenience methods (`has_file`, `find_files`, `find_dirs`, `root_files`, `read_text`).

`read_text` must:
- Return `None` for binary files (detect via heuristic: null bytes in first 8 KB).
- Return `None` for files whose relative path matches secret-file patterns (`.env`, `*.key`, `*.pem`, `id_rsa`, `id_dsa`, `id_ed25519`, `credentials`, `credentials.json`, `secrets.yml`, `secrets.yaml`).
- Cap returned content at 1 MB.

`LocalScanner` must:
- Skip all directories in `EXCLUDED_DIRS` during the walk (do not descend into them, but record their top-level `FileEntry` as a directory so rules can detect committed `node_modules` etc.).
- Record `size_bytes` for every file.
- Raise `ScanError` if path doesn't exist or isn't a directory.

**Done when:** `pytest tests/unit/test_scanner.py` passes; scanner correctly excludes recursing into excluded dirs but records their presence.

---

### Task 1.2 — GitCloneScanner
**Refs:** REQ-001.2, REQ-001.3, REQ-001.4  
**Design:** Scanner Layer — GitCloneScanner

Implement `src/repopilot/scanner/git_clone.py` — `GitCloneScanner`.

- Uses `gitpython` (`git.Repo.clone_from`).
- Clones to a `tempfile.mkdtemp()` directory.
- Delegates to `LocalScanner`.
- Implements `__enter__`/`__exit__` as a context manager.
- Implements `__del__` as a cleanup fallback.
- Raises `ScanError` with a meaningful message on clone failure (network error, invalid URL, non-existent repo).
- Must not store any repo content outside the temp directory.

**Done when:** `pytest tests/unit/test_scanner.py` (including `GitCloneScanner` tests using a mock for the git clone) passes.

---

## Phase 2 — Rules

All rule files live in `src/repopilot/rules/`. Each rule:
- Subclasses `Rule` from `base.py`.
- Is a pure function of `FileTree`.
- Never raises unhandled exceptions — catches internal errors and converts to an INFO finding.
- Returns `(findings, strengths)`.

### Task 2.0 — Rule base class
**Design:** Rules Layer — Rule ABC

Implement `src/repopilot/rules/base.py`:
- `Rule` ABC with abstract `category` property and abstract `evaluate` method.
- `RuleResult` named tuple (or dataclass): `findings: list[Finding]`, `strengths: list[str]`.

Also implement `src/repopilot/rules/__init__.py` with `DEFAULT_RULES: list[Rule]` that instantiates one of each concrete rule class (to be populated as rules are added).

**Done when:** imports succeed.

---

### Task 2.1 — Documentation rules
**Refs:** REQ-002  
**Design:** Documentation rules table

Implement `src/repopilot/rules/documentation.py`:

| Class | Logic |
|-------|-------|
| `ReadmePresenceRule` | `has_file` for README variants; HIGH finding if absent, strength if present |
| `ReadmeSizeRule` | `read_text` README; HIGH if < 200 bytes, MEDIUM if 200–999 bytes |
| `ReadmeSectionsRule` | Scan README text for section keywords (case-insensitive heading match via regex `^#{1,4}\s*keyword` OR `^keyword\s*\n[=-]+`); LOW finding per missing section from the set {installation, usage, features, contributing, testing, license} |
| `ContributingRule` | `has_file` for CONTRIBUTING variants at root or in `docs/`; LOW if absent |
| `DocsDirectoryRule` | `find_dirs("docs")` or `find_dirs("doc")`; INFO if absent |

**Done when:** `pytest tests/unit/test_rules_documentation.py` passes with tests covering present/absent README, size thresholds, section detection, and CONTRIBUTING.

---

### Task 2.2 — Structure rules
**Refs:** REQ-003  
**Design:** Structure rules table

Implement `src/repopilot/rules/structure.py`:

| Class | Logic |
|-------|-------|
| `SourceDirectoryRule` | Check for any of `src`, `lib`, `app`, `core`, `pkg`, `cmd` at root; LOW if none found |
| `TestDirectoryRule` | Check for any of `tests`, `test`, `spec`, `__tests__`, `e2e`, `integration` at root or one level deep; MEDIUM if none |
| `EmptyRepoRule` | Count non-hidden root files; HIGH if < 3 |
| `ConfigFilesRule` | Check for any config file from the list in REQ-003.3; INFO if none |

**Done when:** `pytest tests/unit/test_rules_structure.py` passes.

---

### Task 2.3 — Testing rules
**Refs:** REQ-004  
**Design:** Testing rules table

Implement `src/repopilot/rules/testing.py`:

| Class | Logic |
|-------|-------|
| `TestFilesRule` | Glob for all test file patterns (REQ-004.1) excluding excluded dirs; HIGH if count == 0, strength with count if > 0 |
| `TestFrameworkConfigRule` | Check for config files in REQ-004.2; for `setup.cfg`, read and check for `[tool:pytest]` / `[pytest]` section; LOW if none found |

**Done when:** `pytest tests/unit/test_rules_testing.py` passes.

---

### Task 2.4 — Dependency rules
**Refs:** REQ-005  
**Design:** Dependency rules table

Implement `src/repopilot/rules/dependency.py`:

| Class | Logic |
|-------|-------|
| `LockfileRule` | For each manifest found (REQ-005.1), check for its lockfile (REQ-005.2); MEDIUM per missing lockfile |
| `CommittedEnvFileRule` | Find all `.env` files (exact name); CRITICAL per file. Strength if none found. |
| `EnvVariantRule` | Find `*.env` and `.env.*` except `*.example` / `*.sample`; MEDIUM per file |
| `CommittedSecretFileRule` | Find files matching REQ-005.7 patterns; CRITICAL per file. Never read contents. |

**Done when:** `pytest tests/unit/test_rules_dependency.py` passes.

---

### Task 2.5 — Security rules
**Refs:** REQ-006  
**Design:** Security rules table

Implement `src/repopilot/rules/security.py`:

| Class | Logic |
|-------|-------|
| `GitignorePresenceRule` | `has_file(".gitignore")`; MEDIUM if absent |
| `GitignoreContentRule` | Read `.gitignore`; check for `node_modules` (if `package.json` present), `.venv`/`venv` (if Python manifest present), `.env`; LOW per missing entry |
| `CommittedGeneratedDirRule` | Check top-level entries for names in the generated-dir list (REQ-006.3); HIGH per found dir |
| `LargeFilesRule` | Find files > 10 MB; MEDIUM per file |

**Done when:** `pytest tests/unit/test_rules_security.py` passes.

---

### Task 2.6 — Maintainability rules
**Refs:** REQ-007  
**Design:** Maintainability rules table

Implement `src/repopilot/rules/maintainability.py`:

| Class | Logic |
|-------|-------|
| `LicenseRule` | `has_file` for LICENSE variants; MEDIUM if absent |
| `CIConfigRule` | Check for CI config patterns (REQ-007.3); LOW if none |
| `LintConfigRule` | Check for lint config patterns (REQ-007.5); read `pyproject.toml` / `setup.cfg` for tool sections; LOW if none |
| `ProjectMetadataRule` | Read `package.json`, `pyproject.toml`, `Cargo.toml` for name/version (REQ-007.7); LOW if none found. Record detected metadata as strength. |
| `EntryPointRule` | Check for entry point filenames (REQ-007.8); INFO if none |

**Done when:** `pytest tests/unit/test_rules_maintainability.py` passes.

---

## Phase 3 — Scoring

### Task 3.1 — ScoreCalculator
**Refs:** REQ-008  
**Design:** Scoring Layer

Implement `src/repopilot/scoring.py`:
- `DEDUCTIONS` and `WEIGHTS` constants.
- `ScoreCalculator` with `calculate_category_score` and `calculate_overall_score`.
- `build_recommended_actions(findings: list[Finding]) -> list[RecommendedAction]` — groups HIGH and MEDIUM findings into action items, one action per finding (or merged for closely related findings).

**Done when:** `pytest tests/unit/test_scoring.py` passes and all properties in `pytest tests/property/test_scoring_properties.py` pass (Hypothesis).

---

## Phase 4 — Application Service

### Task 4.1 — AnalysisService
**Refs:** REQ-001, REQ-009, REQ-010  
**Design:** Application Service Layer

Implement `src/repopilot/service.py`:
- `InvalidSourceError(RepoPilotError)`.
- `AnalysisService.__init__` with injected rules and scorer.
- `AnalysisService.analyze(source: str) -> AnalysisReport`.
- Helper `is_url(source: str) -> bool` (checks `http://` / `https://` prefix).
- Helper `infer_name(source: str) -> str` (last path segment, strip `.git`).

Populate `DEFAULT_RULES` in `repopilot/rules/__init__.py`.

**Done when:** `pytest tests/integration/test_service.py` passes against all three fixture repos.

---

## Phase 5 — API

### Task 5.1 — FastAPI app
**Refs:** REQ-010  
**Design:** API Layer

Implement:
- `src/repopilot/api/schemas.py` — `AnalyzeRequest`, `AnalyzeResponse` (wraps `AnalysisReport`), `ErrorResponse`, `HealthResponse`.
- `src/repopilot/api/routes.py` — `POST /analyze`, `GET /health`.
- `src/repopilot/api/app.py` — app factory, mounts `/static`, serves `index.html` at `/`.
- `src/repopilot/api/__init__.py`.

Error handling:
- `InvalidSourceError` → 400
- `ScanError` → 500 with sanitized message (no file contents, no secret values)
- Unhandled → 500

**Done when:** `pytest tests/integration/test_api.py` passes including health check, valid analyze, invalid source, and bad URL tests.

---

## Phase 6 — CLI

### Task 6.1 — CLI
**Refs:** REQ-011  
**Design:** CLI Layer

Implement `src/repopilot/cli.py` using Typer:
- `repopilot analyze <source> [--output FILE] [--format text|json]`
- `repopilot version`
- `repopilot serve [--host HOST] [--port PORT]` — starts uvicorn

Summary renderer must use Rich (bundled with Typer) for the table layout. Exit codes per REQ-011.5.

**Done when:** `repopilot analyze tests/integration/fixtures/good_python_repo` prints a valid summary and exits 0; `repopilot analyze /nonexistent` exits 2.

---

## Phase 7 — Frontend

### Task 7.1 — Frontend HTML/CSS/JS
**Refs:** REQ-012  
**Design:** Frontend section

Implement in `src/repopilot/frontend/`:

**`index.html`**
- Single-page layout as described in the design wireframe.
- Form with text input and Analyze button.
- Loading spinner (CSS-only).
- Results section (hidden until report received).

**`styles.css`**
- Colour palette: overall score bar (green ≥ 80, amber 50–79, red < 50).
- Severity badge colours: dark red (CRITICAL), red (HIGH), orange (MEDIUM), yellow (LOW), blue (INFO).
- Category bars with percentage fill.
- Responsive layout (works at 320 px–1 920 px).
- Accessible: sufficient colour contrast (WCAG AA), `aria-live` region for results.

**`main.js`**
- Submit handler: `POST /analyze`, show spinner, hide on response.
- `renderReport(report)` — populates all result sections from the JSON response.
- Error display: show API error message in the UI (never log raw file contents or secrets).
- No external dependencies (no CDN calls from the browser).

**Done when:** Manually verify in browser: submit a local repo path, see score and findings rendered correctly; error message shown for invalid input.

---

## Phase 8 — Property Tests

### Task 8.1 — Hypothesis property tests
**Refs:** NFR-007  
**Design:** Testing Strategy — Property-based tests

Implement `tests/property/test_scoring_properties.py`:

| Property | Description |
|----------|-------------|
| `score_always_in_range` | For any list of findings, category score is in [0, 100] |
| `more_findings_never_increase_score` | Adding a finding to a list never increases the score |
| `no_findings_gives_100` | Empty findings list yields score == 100 |
| `overall_score_in_range` | For any category score dict, overall is in [0, 100] |
| `score_deterministic` | Same findings list always yields same score |

Implement `tests/property/test_models_properties.py`:

| Property | Description |
|----------|-------------|
| `report_json_roundtrip` | `AnalysisReport` serializes and deserializes without data loss |
| `finding_paths_always_relative` | Generated `Finding` objects never contain absolute paths |

**Done when:** `pytest tests/property/ --hypothesis-seed=0` passes with no flaky failures.

---

## Phase 9 — Integration Fixtures and Final Verification

### Task 9.1 — Integration fixture repos
**Refs:** Design — Testing Strategy

Create the three fixture repos under `tests/integration/fixtures/`:

**`empty_repo/`**
- Only a `.gitkeep` file.
- Expected: `struct-empty-repo` (HIGH), `doc-no-readme` (HIGH), `test-no-test-files` (HIGH), `sec-no-gitignore` (MEDIUM), `maint-no-license` (MEDIUM).

**`good_python_repo/`**
- `README.md` (>1 000 bytes, all six sections present)
- `src/myapp/__init__.py`, `src/myapp/main.py`
- `tests/test_main.py`
- `pyproject.toml` (with `[project]` metadata and `[tool.pytest.ini_options]`)
- `uv.lock` (empty placeholder)
- `LICENSE` (MIT text, at least 100 bytes)
- `.gitignore` (mentions `.venv`, `.env`, `__pycache__`)
- `.github/workflows/ci.yml`
- `CONTRIBUTING.md`
- Expected: overall score ≥ 85, no HIGH findings.

**`bad_hygiene_repo/`**
- `README.md` (50 bytes — minimal)
- `.env` (contains the literal text `SECRET=placeholder` — not a real secret)
- `node_modules/.gitkeep`
- `package.json` (no lockfile)
- Expected: `sec-committed-generated-dir` (HIGH), `dep-committed-env-file` (CRITICAL), `test-no-test-files` (HIGH), `dep-missing-lockfile-npm` (MEDIUM).

**Done when:** `pytest tests/integration/` passes.

---

### Task 9.2 — End-to-end smoke test
**Refs:** All

Run the full stack:
1. `repopilot analyze tests/integration/fixtures/good_python_repo` — exits 0, score ≥ 85.
2. `repopilot analyze tests/integration/fixtures/bad_hygiene_repo` — exits 0, at least 3 HIGH findings in output.
3. Start API (`repopilot serve`), verify `GET /health` returns 200.
4. Open browser, submit `tests/integration/fixtures/good_python_repo`, confirm report renders.

**Done when:** all four checks pass manually.

---

## Task Dependency Graph

```
0.1 → 0.2 → 1.1 → 1.2
                 ↓
            2.0 → 2.1 → 3.1 → 4.1 → 5.1 → 6.1 → 7.1
                  2.2 ↗
                  2.3 ↗
                  2.4 ↗
                  2.5 ↗
                  2.6 ↗
            8.1 (after 3.1)
            9.1 (after 4.1)
            9.2 (after 5.1, 6.1, 7.1, 9.1)
```

Tasks 2.1–2.6 are independent of each other (all depend only on 2.0 and 1.1) and can be developed in parallel.
