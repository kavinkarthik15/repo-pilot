"""Rule base abstraction for RepoPilot analysis rules.

All analysis rules must subclass ``Rule`` and implement its abstract
interface.  The contract enforced here ensures:

- Rules are pure functions of a ``FileTree``; they never touch the
  filesystem directly, make network calls, or execute repository code.
- Every rule exposes stable, deterministic metadata (rule_id, category,
  default_severity, title, description) that is defined at class definition
  time — never generated from runtime state.
- Finding lists returned by ``evaluate()`` are always sorted by a stable
  key so repeated calls on the same input produce identical output.
- Rules never raise unhandled exceptions from ``evaluate()``.  Any internal
  error is caught and converted to an INFO-severity finding so the service
  layer always receives a usable result.

Design reference: design.md § Rules Layer
"""

from __future__ import annotations

import dataclasses
import traceback
from abc import ABC, abstractmethod

from repopilot.models import Category, Finding, Severity, severity_sort_key
from repopilot.scanner.base import FileTree


# ---------------------------------------------------------------------------
# RuleResult
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RuleResult:
    """The output of a single rule evaluation.

    Attributes:
        findings: Zero or more ``Finding`` objects produced by the rule,
                  sorted in deterministic order (severity desc, then id asc).
        strengths: Zero or more plain-text strings describing positive signals
                   found by the rule (e.g. "README.md present").
    """

    findings: list[Finding] = dataclasses.field(default_factory=list)
    strengths: list[str] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Rule ABC
# ---------------------------------------------------------------------------


class Rule(ABC):
    """Abstract base class for all RepoPilot analysis rules.

    Concrete rules must implement the four abstract properties and the
    ``_evaluate`` method.  The public ``evaluate()`` method wraps
    ``_evaluate()`` with deterministic sorting and error isolation.

    Stable metadata contract
    ~~~~~~~~~~~~~~~~~~~~~~~~
    All four properties below must be defined as class-level constants or
    computed purely from class-level constants.  They must never depend on
    runtime state, object identity, timestamps, or filesystem ordering.

    Subclass example::

        class ReadmePresenceRule(Rule):
            rule_id = "doc-no-readme"
            category = Category.DOCUMENTATION
            default_severity = Severity.HIGH
            title = "No README file found"
            description = "Checks for a README file at the repository root."

            def _evaluate(self, tree: FileTree) -> RuleResult:
                if tree.has_file("README.md"):
                    return RuleResult(strengths=["README.md present"])
                return RuleResult(findings=[
                    Finding(
                        id=self.rule_id,
                        category=self.category,
                        severity=self.default_severity,
                        title=self.title,
                        detail="Add a README.md to the repository root.",
                    )
                ])
    """

    # ------------------------------------------------------------------
    # Stable metadata — defined as class attributes on concrete subclasses.
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Stable, unique slug for this rule, e.g. ``"doc-no-readme"``.

        Convention: ``<category-prefix>-<short-slug>``.
        Must be a non-empty string constant — never generated at runtime.
        """

    @property
    @abstractmethod
    def category(self) -> Category:
        """The analysis dimension this rule belongs to."""

    @property
    @abstractmethod
    def default_severity(self) -> Severity:
        """The severity assigned to findings from this rule by default."""

    @property
    @abstractmethod
    def title(self) -> str:
        """Short human-readable label for findings produced by this rule."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-sentence description of what this rule checks."""

    # ------------------------------------------------------------------
    # Evaluation contract
    # ------------------------------------------------------------------

    @abstractmethod
    def _evaluate(self, tree: FileTree) -> RuleResult:
        """Perform the actual rule check against *tree*.

        Implementations must:
        - Use only the ``FileTree`` API to inspect the repository.
        - Never access ``pathlib.Path``, ``os``, ``subprocess``, or the
          network directly.
        - Never execute, import, or evaluate repository code.
        - Return a ``RuleResult`` with findings and/or strengths.
        - Never raise; convert unexpected errors to ``RuleResult`` with
          an INFO finding describing the internal error.

        Finding ordering within the returned list does not need to be
        pre-sorted — ``evaluate()`` handles that.
        """

    def evaluate(self, tree: FileTree) -> RuleResult:
        """Evaluate this rule against *tree* and return a ``RuleResult``.

        This public method wraps ``_evaluate()`` with two guarantees:

        1. **Error isolation**: any exception from ``_evaluate()`` is caught
           and converted to an INFO-severity finding so the service layer
           always receives a usable result.

        2. **Deterministic ordering**: findings are sorted by
           ``(severity_rank, finding_id)`` before being returned, so
           repeated calls on the same input always produce the same output
           regardless of insertion order inside ``_evaluate()``.

        Args:
            tree: The ``FileTree`` snapshot of the repository to analyse.

        Returns:
            A ``RuleResult`` with findings sorted severity-descending then
            id-ascending, and strengths in the order the rule provided them.
        """
        try:
            result = self._evaluate(tree)
        except Exception as exc:  # noqa: BLE001
            # Convert any unhandled exception to a visible INFO finding so
            # the service layer is never silently broken by a buggy rule.
            error_finding = Finding(
                id=f"{self.rule_id}-error",
                category=self.category,
                severity=Severity.INFO,
                title=f"Rule evaluation error: {self.title}",
                detail=(
                    f"Rule {self.rule_id!r} raised an unexpected exception "
                    f"and could not complete its check. "
                    f"Error: {type(exc).__name__}: {exc}\n"
                    f"{traceback.format_exc()}"
                ),
                affected_paths=[],
            )
            return RuleResult(findings=[error_finding], strengths=[])

        # Sort findings for deterministic output.
        sorted_findings = sorted(result.findings, key=severity_sort_key)

        return RuleResult(findings=sorted_findings, strengths=list(result.strengths))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(rule_id={self.rule_id!r})"
