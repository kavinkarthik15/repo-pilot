# RepoPilot — Product Definition

## What RepoPilot Is

RepoPilot is a repository health analysis tool that inspects a Git repository and produces a structured, explainable health report. It evaluates documentation quality, repository structure, testing coverage, dependency hygiene, security hygiene, and long-term maintainability.

Reports are deterministic and evidence-based: every finding traces back to a specific rule applied to a specific artifact in the repository. RepoPilot never invents findings or generates speculative advice it cannot substantiate with observed data.

## Who It Is For

- Individual developers who want an objective baseline on a project's health before sharing or publishing it.
- Engineering teams running periodic health checks across a portfolio of repositories.
- Maintainers preparing open-source releases or onboarding contributors.
- Reviewers assessing third-party repositories before adopting a dependency.

## The Core User Problem

Developers often lack a consistent, machine-readable view of repository quality. Manual checklists are forgotten or skipped; CI pipelines surface narrow pass/fail signals; code review misses structural and documentation gaps. RepoPilot fills this gap with a single, repeatable command that surfaces actionable, prioritised findings without requiring any external service or paid API.

## Core Capabilities

| Dimension              | What is evaluated                                                                  |
|------------------------|------------------------------------------------------------------------------------|
| Documentation          | Presence and quality of README, CONTRIBUTING, CHANGELOG, LICENSE                  |
| Repository structure   | Expected directories, naming conventions, layout consistency                       |
| Testing                | Test directory presence, framework detection, basic coverage signals               |
| Dependency hygiene     | Manifest detection, lockfile detection, pinned vs. unpinned versions, committed dependency/build directories, suspicious dependency configuration |
| Security / hygiene     | Secret-like filenames, `.gitignore` coverage, sensitive path exposure              |
| Maintainability        | File complexity signals, dead code indicators, stale branch patterns               |

Each dimension produces a score and a set of findings. Findings carry one of five severity levels: `info`, `low`, `medium`, `high`, or `critical`.

> **Note on vulnerability lookup:** CVE/advisory database lookups are out of scope for the offline core. Dependency hygiene checks are limited to deterministic, locally-observable signals (manifest presence, lockfile presence, obviously unpinned version specifiers, committed build artefacts). Advisory integration may be added later as an optional, opt-in integration layer.

## Project Boundaries

RepoPilot analyses **what is already in the repository**. It does not:

- Execute any code from the repository under analysis.
- Push changes, create commits, or modify the repository in any way.
- Require network access for its core analysis (offline-first).
- Depend on any paid API, proprietary service, or external LLM.

Integration layers (FastAPI web service, future MCP adapter) are thin wrappers. The core analysis engine must remain usable as a standalone Python library, independent of any interface.

## Offline-First and Privacy Principles

The core analyser runs entirely on local data. When analysing a remote URL, RepoPilot clones the repository to a temporary directory, analyses local files, then deletes the clone. No repository content is transmitted to any external service by the core analyser. Environment variable values and secret file contents are never included in reports.

## Deterministic Analysis Philosophy

Given the same repository state, RepoPilot must produce the same report every time. Rules are applied mechanically from a well-defined rule set. Scoring formulas are documented and stable. Changes to rules or scoring weights are explicit, versioned, and recorded — not silently tuned.

## What RepoPilot Must Never Do

- Invent or hallucinate findings not grounded in observed repository artifacts.
- Expose the contents of secret files, `.env` files, or credential stores in any output.
- Execute, import, or evaluate code from the repository being analysed.
- Transmit repository contents to any remote service from the core analysis path.
- Modify the repository under analysis in any way.
- Apply non-deterministic logic where deterministic rules are feasible.
- Silently change scoring rules between versions without a documented reason.

## Expected User Experience

1. User points RepoPilot at a local path or Git URL.
2. RepoPilot scans the repository, applies rules across all dimensions, and computes scores.
3. A structured report is returned — JSON by default, human-readable summary on request.
4. Each finding states: the rule that fired, the file or path that triggered it, the severity, and a plain-language explanation.
5. The overall health score is a weighted aggregate, reproducible from the individual dimension scores.
6. The user can act on findings immediately; no account, API key, or internet connection is required for local analysis.
