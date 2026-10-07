# RepoPilot — Development Workflow

## Specification First

All non-trivial features begin with a Kiro spec. The spec defines requirements, a design, and an ordered task list before any implementation code is written. Implementation must not deviate from the approved spec without updating the spec first.

If a task reveals that the design needs to change, stop, update the spec, and get alignment before continuing. Silent design drift is not acceptable.

## Incremental Implementation

Implement tasks in the order defined in the spec. Each task should leave the codebase in a working state — no half-built features that break the test suite or the service layer. Prefer small, reviewable commits over large, tangled changesets.

## Tests Accompany Implementation

Every new scanner, rule, or scoring function ships with unit tests in the same pull request / commit. A rule is not complete until it has tests.

Integration tests for new service-layer behaviour are written alongside the implementation, using fixture repositories in `tests/fixtures/`.

Do not mark a spec task complete if the relevant tests are failing or missing.

## Property-Based Tests for Suitable Invariants

Use Hypothesis for any logic that has mathematical invariants or must hold across a wide input space:

- Scoring functions: result always in `[0.0, 100.0]`; more severe findings never raise the score.
- Rule functions: valid domain inputs never raise an unhandled exception.
- Domain models: Pydantic serialisation round-trips are lossless.

Property tests live in `tests/property/` and are run as part of the standard test suite.

## Determinism Is Preferred

When there is a choice between a deterministic and a non-deterministic approach, choose deterministic. Sort outputs by stable keys. Avoid relying on dict insertion order for result ordering. Timestamp-based branching in rules is prohibited.

If non-determinism is unavoidable (e.g., parallel scanning), document it explicitly and ensure the final report output is still sorted deterministically before it reaches the caller.

## Run Tests Before Marking Tasks Complete

Before declaring any implementation task done:

1. Run the full test suite (`pytest`).
2. Confirm all tests pass, including property tests.
3. If the task touches the API layer, start the server and verify the relevant endpoint responds correctly.

A task is not complete if tests are red or skipped for related functionality.

## Do Not Silently Change Scoring Rules

Scoring weights and formulas are documented in `repopilot/scoring/`. Any change to a score calculation must:

1. Be intentional and justified (not a side effect of refactoring).
2. Update the relevant docstrings and any spec documentation.
3. Include a test that asserts the new behaviour.

Score changes that appear in a diff without a corresponding spec or comment are a red flag — they should be reverted and re-applied with justification.

## Findings Must Be Traceable to Rules

Every `Finding` in a `HealthReport` must identify the rule that produced it. The rule name must be a stable string constant, not a dynamically generated label. This traceability is what makes reports explainable and reproducible.

When a rule is renamed or removed, existing reports referencing the old rule name remain valid historical records. The new rule name is applied to future reports only.

## Avoid Unnecessary Dependencies

Before adding a new package:

1. Check whether the standard library or an already-approved dependency covers the need.
2. If a new package is genuinely needed, add it to `pyproject.toml` with a bounded version constraint.
3. Do not add packages that provide only minor convenience over a few lines of standard library code.

## Keep the Core Independent

The `domain/`, `scanners/`, `rules/`, `scoring/`, and `services/` layers must remain free of FastAPI, HTTP, and presentation concerns. This keeps the core usable as a standalone library and as a future MCP tool without modification.

Do not add FastAPI imports or response-shaping logic to these layers, even as a shortcut.

## Update Specs When Designs Change

Kiro specs in `.kiro/specs/` are living documents. When an implementation reveals that the approved design must change:

1. Update the spec's design and task sections to reflect the new approach.
2. Note the reason for the change.
3. Then continue implementation against the updated spec.

Out-of-date specs confuse future contributors and break the traceability the spec workflow is meant to provide.
