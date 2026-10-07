# RepoPilot — Requirements

## Introduction

RepoPilot is a repository health analysis tool for software developers. Given a local path or a public repository URL, it performs deterministic, offline-capable analysis across six health categories and produces a structured report with scores, findings, strengths, and recommended actions.

This document defines the functional and non-functional requirements for the first version. Deterministic local checks are the foundation; LLM-assisted or third-party-API-dependent analysis is intentionally deferred to later versions.

---

## Functional Requirements

### REQ-001 — Repository Input

| ID | Requirement |
|----|-------------|
| REQ-001.1 | The system MUST accept a local filesystem path as the repository source. |
| REQ-001.2 | The system MUST accept a public HTTPS Git URL (e.g. `https://github.com/owner/repo`) as the repository source. |
| REQ-001.3 | When a URL is provided, the system MUST clone the repository to a temporary directory, perform the analysis, and delete the temporary directory after the report is produced. |
| REQ-001.4 | The system MUST NOT require authentication for public repositories. |
| REQ-001.5 | The system MUST validate the input before analysis begins and return a descriptive error if the path does not exist or the URL is not reachable/clonable. |
| REQ-001.6 | The system MUST NOT make any modifications to the repository being analyzed. |

---

### REQ-002 — Documentation Analysis

| ID | Requirement |
|----|-------------|
| REQ-002.1 | The analyzer MUST detect the presence of a README file at the repository root. Accepted filenames: `README.md`, `README.rst`, `README.txt`, `README` (case-insensitive). |
| REQ-002.2 | When a README is found, the analyzer MUST inspect its content for the presence of the following conceptual sections: **Installation**, **Usage**, **Features**, **Contributing**, **Testing**, **License**. Detection is keyword-based (case-insensitive heading match). |
| REQ-002.3 | A README smaller than 200 bytes MUST be flagged as "minimal". |
| REQ-002.4 | A README smaller than 1 000 bytes MUST be flagged as "brief". |
| REQ-002.5 | The analyzer MUST detect `CONTRIBUTING.md` / `CONTRIBUTING.rst` / `CONTRIBUTING` (case-insensitive) at the root or in a `docs/` subdirectory. |
| REQ-002.6 | The analyzer MUST detect a `docs/` directory or a `doc/` directory. |
| REQ-002.7 | Each missing documentation element MUST generate a finding with the appropriate severity (see Scoring section). |

---

### REQ-003 — Repository Structure Analysis

| ID | Requirement |
|----|-------------|
| REQ-003.1 | The analyzer MUST detect source directories. Recognized names: `src`, `lib`, `app`, `core`, `pkg`, `cmd`. |
| REQ-003.2 | The analyzer MUST detect test directories. Recognized names: `tests`, `test`, `spec`, `__tests__`, `e2e`, `integration`. |
| REQ-003.3 | The analyzer MUST detect common configuration files: `.editorconfig`, `.prettierrc`, `.eslintrc*`, `pyproject.toml`, `setup.cfg`, `.flake8`, `tox.ini`, `Makefile`, `Dockerfile`, `docker-compose.yml`. |
| REQ-003.4 | The analyzer MUST detect package/dependency manifests: `package.json`, `requirements.txt`, `Pipfile`, `pyproject.toml`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `Cargo.toml`, `go.mod`, `Gemfile`, `composer.json`. |
| REQ-003.5 | A repository with fewer than 3 non-hidden files at the root MUST be flagged as "suspiciously empty". |
| REQ-003.6 | Structure findings MUST state which files or directories triggered the finding. |

---

### REQ-004 — Testing Analysis

| ID | Requirement |
|----|-------------|
| REQ-004.1 | The analyzer MUST search for test files using the following patterns (recursively, excluding committed dependency directories): `test_*.py`, `*_test.py`, `*.test.js`, `*.spec.js`, `*.test.ts`, `*.spec.ts`, `*Test.java`, `*_test.go`. |
| REQ-004.2 | The analyzer MUST detect test framework configuration files: `pytest.ini`, `jest.config.*`, `karma.conf.*`, `phpunit.xml`, `.mocharc.*`, `vitest.config.*`, `setup.cfg` (when it contains a `[tool:pytest]` or `[pytest]` section). |
| REQ-004.3 | When test files are found, the analyzer MUST report the count and the frameworks inferred from the patterns/config. |
| REQ-004.4 | When no test files are found and no test framework configuration is found, the analyzer MUST produce a **high** severity finding. |
| REQ-004.5 | Detection MUST exclude `node_modules`, `.venv`, `venv`, `.env`, `vendor`, `dist`, `build` directories. |

---

### REQ-005 — Dependency Hygiene Analysis

| ID | Requirement |
|----|-------------|
| REQ-005.1 | The analyzer MUST detect the dependency manifests listed in REQ-003.4. |
| REQ-005.2 | For each detected manifest, the analyzer MUST check for its expected lockfile. Manifest-to-lockfile mapping: `package.json` → `package-lock.json` or `yarn.lock` or `pnpm-lock.yaml`; `Pipfile` → `Pipfile.lock`; `Cargo.toml` → `Cargo.lock`; `Gemfile` → `Gemfile.lock`; `composer.json` → `composer.lock`; `go.mod` → `go.sum`. |
| REQ-005.3 | When a manifest exists but no lockfile is found, the analyzer MUST produce a **medium** severity finding. |
| REQ-005.4 | The analyzer MUST detect `.env` files anywhere in the repository tree (excluding excluded directories). Each found `.env` file MUST produce a **critical** severity finding. |
| REQ-005.5 | The analyzer MUST detect files matching `*.env`, `.env.*` (e.g. `.env.local`, `.env.production`) and produce a **medium** severity finding unless the filename ends with `.example` or `.sample`. |
| REQ-005.6 | The analyzer MUST NOT read the contents of detected secret-like files. The finding MUST only reference the file path. |
| REQ-005.7 | The analyzer MUST detect any of the following credential-related filenames anywhere in the tree: `credentials`, `credentials.json`, `secrets.yml`, `secrets.yaml`, `*.pem`, `*.key`, `id_rsa`, `id_dsa`, `id_ed25519`. Each match MUST produce a **critical** severity finding. |

---

### REQ-006 — Security and Repository Hygiene Analysis

| ID | Requirement |
|----|-------------|
| REQ-006.1 | The analyzer MUST check for a `.gitignore` file at the repository root. |
| REQ-006.2 | When `.gitignore` is missing, the analyzer MUST produce a **medium** severity finding. |
| REQ-006.3 | The analyzer MUST detect committed directories that should normally not be in version control: `node_modules`, `__pycache__`, `.venv`, `venv`, `env`, `dist`, `build`, `.gradle`, `.next`, `.nuxt`, `target` (Java/Maven), `.eggs`, `*.egg-info`. Each found directory MUST produce a **high** severity finding. |
| REQ-006.4 | The analyzer MUST detect binary files larger than 10 MB committed to the repository. Each such file MUST produce a **medium** severity finding. |
| REQ-006.5 | The analyzer MUST check whether the detected `.gitignore` mentions `node_modules` (when `package.json` is present), `.venv`/`venv` (when `requirements.txt` or `Pipfile` is present), and `*.env` or `.env`. Missing entries MUST produce a **low** severity finding each. |

---

### REQ-007 — Maintainability Analysis

| ID | Requirement |
|----|-------------|
| REQ-007.1 | The analyzer MUST detect a LICENSE file at the root. Accepted names: `LICENSE`, `LICENSE.md`, `LICENSE.txt`, `LICENCE`, `LICENCE.md`, `LICENCE.txt` (case-insensitive). |
| REQ-007.2 | When no LICENSE file is found, the analyzer MUST produce a **medium** severity finding. |
| REQ-007.3 | The analyzer MUST detect CI configuration: `.github/workflows/*.yml`, `.github/workflows/*.yaml`, `.circleci/config.yml`, `.travis.yml`, `Jenkinsfile`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `bitbucket-pipelines.yml`, `codeship-steps.yml`. |
| REQ-007.4 | When no CI configuration is found, the analyzer MUST produce a **low** severity finding. |
| REQ-007.5 | The analyzer MUST detect linting/formatting configuration: `.eslintrc*`, `.prettierrc*`, `.flake8`, `pyproject.toml` (when it contains `[tool.black]`, `[tool.ruff]`, or `[tool.pylint]`), `setup.cfg` (when it contains `[flake8]`), `.rubocop.yml`, `golangci.yml`, `.golangci.*`. |
| REQ-007.6 | When no linting configuration is found, the analyzer MUST produce a **low** severity finding. |
| REQ-007.7 | The analyzer MUST detect project metadata by reading (not executing) `package.json` for `name`, `version`, `description`; `pyproject.toml` for `[project]` name/version; `Cargo.toml` for `[package]` name/version. |
| REQ-007.8 | The analyzer MUST attempt to detect common entry points: `main.py`, `app.py`, `index.js`, `main.js`, `main.ts`, `index.ts`, `Main.java`, `main.go`, `main.rs`, `Program.cs`. |

---

### REQ-008 — Scoring

| ID | Requirement |
|----|-------------|
| REQ-008.1 | The system MUST produce a per-category score in the range [0, 100]. |
| REQ-008.2 | The system MUST produce an overall score in the range [0, 100] as a weighted average of category scores. Default weights: Documentation 20 %, Structure 15 %, Testing 20 %, Dependency Hygiene 15 %, Security & Hygiene 15 %, Maintainability 15 %. |
| REQ-008.3 | Every point deduction MUST be traceable to one or more specific findings. |
| REQ-008.4 | Every finding MUST carry a severity: `info`, `low`, `medium`, `high`, or `critical`. |
| REQ-008.5 | Default deduction per severity: `info` = 0, `low` = 3, `medium` = 7, `high` = 15, `critical` = 25. Deductions apply within the relevant category score and are capped so no category score falls below 0. `critical` is reserved for findings where clearly committed credential or secret-related files are detected; it must never expose file contents. |
| REQ-008.6 | The system MUST also produce a non-empty list of **strengths** (things detected that are positive indicators). |
| REQ-008.7 | The system MUST produce a non-empty list of **recommended actions** derived from high- and medium-severity findings, each with a plain-English description. |
| REQ-008.8 | Scoring MUST be deterministic: the same repository state MUST always produce the same score. |

---

### REQ-009 — Report Output

| ID | Requirement |
|----|-------------|
| REQ-009.1 | The report MUST be serializable to JSON. |
| REQ-009.2 | The report MUST contain: repository metadata (path/URL, name inferred from path/URL, analysis timestamp, analyzer version); overall score; per-category scores; list of strengths; list of findings (each: id, category, severity, title, detail, affected_paths); list of recommended actions (each: finding_id refs, priority, action text). |
| REQ-009.3 | The API MUST return the report as a JSON response. |
| REQ-009.4 | The web frontend MUST render the report in a clear, human-readable layout. |
| REQ-009.5 | The CLI MUST print a summary to stdout and optionally write the full JSON report to a file (`--output`). |

---

### REQ-010 — API

| ID | Requirement |
|----|-------------|
| REQ-010.1 | The system MUST expose a FastAPI HTTP API. |
| REQ-010.2 | `POST /analyze` MUST accept `{ "source": "<path or URL>" }` and return the full report JSON. |
| REQ-010.3 | `GET /health` MUST return `{ "status": "ok" }`. |
| REQ-010.4 | The API MUST return appropriate HTTP status codes: `200` on success, `400` on invalid input, `422` on validation error, `500` on unexpected analysis failure. |
| REQ-010.5 | The API MUST not expose repository file contents or secret values in responses. |

---

### REQ-011 — CLI

| ID | Requirement |
|----|-------------|
| REQ-011.1 | The system MUST provide a CLI entry point `repopilot analyze <source>`. |
| REQ-011.2 | The CLI MUST print a human-readable summary table to stdout. |
| REQ-011.3 | The CLI MUST support `--output <file.json>` to write the full JSON report. |
| REQ-011.4 | The CLI MUST support `--format json` to print the full JSON to stdout instead of the summary. |
| REQ-011.5 | The CLI MUST exit with code `0` on success, `1` on analysis error, `2` on invalid input. |

---

### REQ-012 — Frontend

| ID | Requirement |
|----|-------------|
| REQ-012.1 | The frontend MUST be a single-page web application served by the FastAPI backend. |
| REQ-012.2 | The frontend MUST provide an input field for the repository path or URL and a submit button. |
| REQ-012.3 | The frontend MUST display a loading/progress indicator while analysis is running. |
| REQ-012.4 | The frontend MUST render: overall score (prominently), category scores, strengths, findings grouped by severity, and recommended actions. |
| REQ-012.5 | The frontend MUST render findings colour-coded by severity (critical = dark red, high = red, medium = orange, low = yellow, info = blue). |
| REQ-012.6 | The frontend MUST NOT send repository file contents to any external service. |

---

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-001 | Core analysis MUST work fully offline (no network requests during analysis of a local path). |
| NFR-002 | Analysis of a typical medium-sized repository (<5 000 files) MUST complete in under 30 seconds on a modern developer machine. |
| NFR-003 | The tool MUST NOT require any paid API keys. |
| NFR-004 | The tool MUST NOT read or transmit the contents of files that appear to contain secrets (env files, key files). |
| NFR-005 | Python 3.13 is the required runtime. |
| NFR-006 | All public Python modules MUST have type annotations. |
| NFR-007 | The codebase MUST be testable with `pytest`. Property-based tests using Hypothesis MUST cover the scoring logic. |
| NFR-008 | The architecture MUST be modular enough that a GitHub/MCP integration layer can be added without modifying core analysis or scoring logic. |
| NFR-009 | Dependencies MUST be declared in `pyproject.toml` with a `uv` lockfile (`uv.lock`). |
| NFR-010 | The tool MUST NOT perform any write, delete, or execute operation on the repository being analyzed. |

---

## Constraints and Out-of-Scope

- No LLM calls in v1. Architecture must not preclude adding them later.
- No authentication against private repositories in v1.
- No database persistence in v1 (reports are ephemeral).
- No user accounts or multi-tenancy in v1.
- No diff/history analysis (git log, blame) in v1.
- GitHub/MCP integration is explicitly out of scope for v1 but the architecture must not block it.
