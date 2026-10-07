"""Unit tests for Task 2.0: Rule base abstraction.

Uses a minimal concrete stub rule defined only in this file.  No real
analysis rules (documentation, structure, etc.) are imported.

Covers:
- RuleResult construction and defaults
- RuleResult immutability (frozen dataclass)
- Rule ABC cannot be instantiated directly
- Concrete rule: stable rule_id, category, default_severity, title, description
- evaluate() returns RuleResult
- evaluate() findings are sorted severity-descending then id-ascending
- evaluate() strength list is preserved in rule-supplied order
- evaluate() on empty FileTree returns valid RuleResult
- evaluate() called twice on same input returns identical output (determinism)
- _evaluate() exception is caught and converted to INFO finding
- Error finding id follows <rule_id>-error convention
- Error finding severity is always INFO
- Error finding category matches the rule's category
- No direct filesystem access inside _evaluate (rule uses only FileTree API)
- Severity propagation: finding severity comes from rule logic
- Category propagation: finding category matches rule category
- DEFAULT_RULES starts empty and is a list
- Module imports succeed
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repopilot.models import Category, Finding, Severity
from repopilot.rules import DEFAULT_RULES
from repopilot.rules.base import Rule, RuleResult
from repopilot.scanner.base import FileTree


# ---------------------------------------------------------------------------
# Helpers — synthetic FileTree (no real filesystem needed)
# ---------------------------------------------------------------------------


def _empty_tree(tmp_path: Path) -> FileTree:
    """Return a FileTree for an empty directory."""
    return FileTree(root=tmp_path, entries=[])


# ---------------------------------------------------------------------------
# Minimal concrete stub rules used only in these tests
# ---------------------------------------------------------------------------


class _AlwaysCleanRule(Rule):
    """A stub rule that always reports a single strength and no findings."""

    rule_id = "stub-always-clean"
    category = Category.DOCUMENTATION
    default_severity = Severity.LOW
    title = "Stub: always clean"
    description = "Stub rule that never produces findings."

    @property
    def rule_id(self) -> str:  # type: ignore[override]
        return "stub-always-clean"

    @property
    def category(self) -> Category:  # type: ignore[override]
        return Category.DOCUMENTATION

    @property
    def default_severity(self) -> Severity:  # type: ignore[override]
        return Severity.LOW

    @property
    def title(self) -> str:  # type: ignore[override]
        return "Stub: always clean"

    @property
    def description(self) -> str:  # type: ignore[override]
        return "Stub rule that never produces findings."

    def _evaluate(self, tree: FileTree) -> RuleResult:
        return RuleResult(strengths=["Everything looks fine (stub)"])


class _AlwaysFindingRule(Rule):
    """A stub rule that always produces one finding."""

    @property
    def rule_id(self) -> str:
        return "stub-always-finding"

    @property
    def category(self) -> Category:
        return Category.STRUCTURE

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def title(self) -> str:
        return "Stub: always a finding"

    @property
    def description(self) -> str:
        return "Stub rule that always produces one MEDIUM finding."

    def _evaluate(self, tree: FileTree) -> RuleResult:
        return RuleResult(
            findings=[
                Finding(
                    id=self.rule_id,
                    category=self.category,
                    severity=self.default_severity,
                    title=self.title,
                    detail="Stub finding detail.",
                )
            ]
        )


class _MultiFindingRule(Rule):
    """Stub rule that produces multiple findings in non-sorted order."""

    @property
    def rule_id(self) -> str:
        return "stub-multi"

    @property
    def category(self) -> Category:
        return Category.TESTING

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def title(self) -> str:
        return "Stub: multiple findings"

    @property
    def description(self) -> str:
        return "Stub rule that returns findings in an unsorted order."

    def _evaluate(self, tree: FileTree) -> RuleResult:
        # Deliberately return in low → critical order to verify sorting.
        findings = [
            Finding(
                id="stub-multi-low",
                category=self.category,
                severity=Severity.LOW,
                title="low finding",
                detail="d",
            ),
            Finding(
                id="stub-multi-critical",
                category=self.category,
                severity=Severity.CRITICAL,
                title="critical finding",
                detail="d",
            ),
            Finding(
                id="stub-multi-medium",
                category=self.category,
                severity=Severity.MEDIUM,
                title="medium finding",
                detail="d",
            ),
            Finding(
                id="stub-multi-high",
                category=self.category,
                severity=Severity.HIGH,
                title="high finding",
                detail="d",
            ),
            Finding(
                id="stub-multi-info",
                category=self.category,
                severity=Severity.INFO,
                title="info finding",
                detail="d",
            ),
        ]
        return RuleResult(findings=findings, strengths=["strength-z", "strength-a"])


class _RaisingRule(Rule):
    """Stub rule whose _evaluate always raises RuntimeError."""

    @property
    def rule_id(self) -> str:
        return "stub-raises"

    @property
    def category(self) -> Category:
        return Category.SECURITY_HYGIENE

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def title(self) -> str:
        return "Stub: raises"

    @property
    def description(self) -> str:
        return "Stub rule that always raises an exception."

    def _evaluate(self, tree: FileTree) -> RuleResult:
        raise RuntimeError("intentional test error")


class _FileTreeOnlyRule(Rule):
    """Stub rule that deliberately uses only the FileTree API (no direct I/O)."""

    @property
    def rule_id(self) -> str:
        return "stub-filetree-only"

    @property
    def category(self) -> Category:
        return Category.MAINTAINABILITY

    @property
    def default_severity(self) -> Severity:
        return Severity.INFO

    @property
    def title(self) -> str:
        return "Stub: FileTree-only access"

    @property
    def description(self) -> str:
        return "Stub that only uses FileTree methods, never os/pathlib directly."

    def _evaluate(self, tree: FileTree) -> RuleResult:
        # Use every FileTree method to confirm the API matches expectations.
        _ = tree.has_file("README.md")
        _ = tree.find_files("*.py")
        _ = tree.find_dirs("docs")
        _ = tree.root_files()
        _ = tree.read_text("README.md")
        return RuleResult(strengths=["FileTree API exercised"])


# ---------------------------------------------------------------------------
# RuleResult
# ---------------------------------------------------------------------------


class TestRuleResult:
    def test_default_construction(self) -> None:
        result = RuleResult()
        assert result.findings == []
        assert result.strengths == []

    def test_with_findings(self) -> None:
        f = Finding(
            id="x",
            category=Category.DOCUMENTATION,
            severity=Severity.HIGH,
            title="t",
            detail="d",
        )
        result = RuleResult(findings=[f])
        assert len(result.findings) == 1

    def test_frozen(self) -> None:
        result = RuleResult()
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.findings = []  # type: ignore[misc]

    def test_findings_and_strengths_independent(self) -> None:
        result = RuleResult(findings=[], strengths=["good"])
        assert result.strengths == ["good"]


import dataclasses  # noqa: E402  (needed for FrozenInstanceError reference above)


# ---------------------------------------------------------------------------
# Rule ABC
# ---------------------------------------------------------------------------


class TestRuleABC:
    def test_cannot_instantiate_abc_directly(self) -> None:
        with pytest.raises(TypeError):
            Rule()  # type: ignore[abstract]

    def test_repr_includes_rule_id(self) -> None:
        rule = _AlwaysCleanRule()
        assert "stub-always-clean" in repr(rule)


# ---------------------------------------------------------------------------
# Stable rule metadata
# ---------------------------------------------------------------------------


class TestRuleMetadata:
    def test_rule_id_is_string(self) -> None:
        rule = _AlwaysFindingRule()
        assert isinstance(rule.rule_id, str)
        assert rule.rule_id

    def test_rule_id_is_stable_across_instances(self) -> None:
        assert _AlwaysFindingRule().rule_id == _AlwaysFindingRule().rule_id

    def test_category_is_category_enum(self) -> None:
        rule = _AlwaysFindingRule()
        assert isinstance(rule.category, Category)

    def test_category_is_stable_across_instances(self) -> None:
        assert _AlwaysFindingRule().category == _AlwaysFindingRule().category

    def test_default_severity_is_severity_enum(self) -> None:
        rule = _AlwaysFindingRule()
        assert isinstance(rule.default_severity, Severity)

    def test_default_severity_is_stable(self) -> None:
        assert _AlwaysFindingRule().default_severity == _AlwaysFindingRule().default_severity

    def test_title_is_non_empty_string(self) -> None:
        rule = _AlwaysCleanRule()
        assert isinstance(rule.title, str)
        assert rule.title.strip()

    def test_description_is_non_empty_string(self) -> None:
        rule = _AlwaysCleanRule()
        assert isinstance(rule.description, str)
        assert rule.description.strip()

    def test_metadata_does_not_depend_on_filetree(self, tmp_path: Path) -> None:
        """Metadata must be identical before and after evaluate() is called."""
        rule = _AlwaysFindingRule()
        rule_id_before = rule.rule_id
        category_before = rule.category

        rule.evaluate(_empty_tree(tmp_path))

        assert rule.rule_id == rule_id_before
        assert rule.category == category_before


# ---------------------------------------------------------------------------
# evaluate() — basic contract
# ---------------------------------------------------------------------------


class TestEvaluateContract:
    def test_returns_rule_result(self, tmp_path: Path) -> None:
        result = _AlwaysCleanRule().evaluate(_empty_tree(tmp_path))
        assert isinstance(result, RuleResult)

    def test_clean_rule_has_no_findings(self, tmp_path: Path) -> None:
        result = _AlwaysCleanRule().evaluate(_empty_tree(tmp_path))
        assert result.findings == []

    def test_clean_rule_has_strength(self, tmp_path: Path) -> None:
        result = _AlwaysCleanRule().evaluate(_empty_tree(tmp_path))
        assert len(result.strengths) == 1

    def test_finding_rule_produces_finding(self, tmp_path: Path) -> None:
        result = _AlwaysFindingRule().evaluate(_empty_tree(tmp_path))
        assert len(result.findings) == 1

    def test_finding_rule_empty_strengths(self, tmp_path: Path) -> None:
        result = _AlwaysFindingRule().evaluate(_empty_tree(tmp_path))
        assert result.strengths == []

    def test_evaluate_on_empty_tree_succeeds(self, tmp_path: Path) -> None:
        """Every stub rule must handle an empty FileTree without error."""
        for rule in [_AlwaysCleanRule(), _AlwaysFindingRule(), _MultiFindingRule()]:
            result = rule.evaluate(_empty_tree(tmp_path))
            assert isinstance(result, RuleResult)


# ---------------------------------------------------------------------------
# Severity propagation
# ---------------------------------------------------------------------------


class TestSeverityPropagation:
    def test_finding_severity_matches_rule_default(self, tmp_path: Path) -> None:
        rule = _AlwaysFindingRule()
        result = rule.evaluate(_empty_tree(tmp_path))
        assert result.findings[0].severity == rule.default_severity

    def test_all_five_severities_are_valid(self, tmp_path: Path) -> None:
        """A rule may produce findings at any of the five allowed severities."""
        result = _MultiFindingRule().evaluate(_empty_tree(tmp_path))
        severities_found = {f.severity for f in result.findings}
        assert severities_found == set(Severity)


# ---------------------------------------------------------------------------
# Category propagation
# ---------------------------------------------------------------------------


class TestCategoryPropagation:
    def test_finding_category_matches_rule_category(self, tmp_path: Path) -> None:
        rule = _AlwaysFindingRule()
        result = rule.evaluate(_empty_tree(tmp_path))
        for finding in result.findings:
            assert finding.category == rule.category

    def test_multi_finding_rule_categories_consistent(self, tmp_path: Path) -> None:
        rule = _MultiFindingRule()
        result = rule.evaluate(_empty_tree(tmp_path))
        for finding in result.findings:
            assert finding.category == rule.category


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    def test_findings_sorted_critical_first(self, tmp_path: Path) -> None:
        result = _MultiFindingRule().evaluate(_empty_tree(tmp_path))
        severities = [f.severity for f in result.findings]
        assert severities[0] == Severity.CRITICAL
        assert severities[-1] == Severity.INFO

    def test_findings_sorted_full_order(self, tmp_path: Path) -> None:
        result = _MultiFindingRule().evaluate(_empty_tree(tmp_path))
        severities = [f.severity for f in result.findings]
        expected = [
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.INFO,
        ]
        assert severities == expected

    def test_same_severity_sorted_by_id(self, tmp_path: Path) -> None:
        """When two findings share a severity they must sort by id."""

        class _TwoSameSeverityRule(Rule):
            @property
            def rule_id(self) -> str:
                return "stub-two-same"

            @property
            def category(self) -> Category:
                return Category.DOCUMENTATION

            @property
            def default_severity(self) -> Severity:
                return Severity.MEDIUM

            @property
            def title(self) -> str:
                return "t"

            @property
            def description(self) -> str:
                return "d"

            def _evaluate(self, tree: FileTree) -> RuleResult:
                return RuleResult(findings=[
                    Finding(id="z-second", category=self.category, severity=Severity.MEDIUM, title="t", detail="d"),
                    Finding(id="a-first", category=self.category, severity=Severity.MEDIUM, title="t", detail="d"),
                ])

        result = _TwoSameSeverityRule().evaluate(_empty_tree(tmp_path))
        assert result.findings[0].id == "a-first"
        assert result.findings[1].id == "z-second"

    def test_repeated_evaluation_identical_output(self, tmp_path: Path) -> None:
        rule = _MultiFindingRule()
        tree = _empty_tree(tmp_path)
        result1 = rule.evaluate(tree)
        result2 = rule.evaluate(tree)
        assert [f.id for f in result1.findings] == [f.id for f in result2.findings]
        assert result1.strengths == result2.strengths


# ---------------------------------------------------------------------------
# Error isolation
# ---------------------------------------------------------------------------


class TestErrorIsolation:
    def test_exception_becomes_info_finding(self, tmp_path: Path) -> None:
        result = _RaisingRule().evaluate(_empty_tree(tmp_path))
        assert len(result.findings) == 1
        assert result.findings[0].severity == Severity.INFO

    def test_error_finding_id_has_error_suffix(self, tmp_path: Path) -> None:
        result = _RaisingRule().evaluate(_empty_tree(tmp_path))
        assert result.findings[0].id.endswith("-error")

    def test_error_finding_category_matches_rule(self, tmp_path: Path) -> None:
        result = _RaisingRule().evaluate(_empty_tree(tmp_path))
        assert result.findings[0].category == _RaisingRule().category

    def test_error_finding_detail_mentions_exception(self, tmp_path: Path) -> None:
        result = _RaisingRule().evaluate(_empty_tree(tmp_path))
        assert "intentional test error" in result.findings[0].detail

    def test_error_result_has_no_strengths(self, tmp_path: Path) -> None:
        result = _RaisingRule().evaluate(_empty_tree(tmp_path))
        assert result.strengths == []


# ---------------------------------------------------------------------------
# FileTree-only access
# ---------------------------------------------------------------------------


class TestFileTreeOnlyAccess:
    def test_rule_uses_only_filetree_api(self, tmp_path: Path) -> None:
        """The FileTree-only stub must succeed without any direct I/O."""
        result = _FileTreeOnlyRule().evaluate(_empty_tree(tmp_path))
        assert isinstance(result, RuleResult)
        assert result.strengths == ["FileTree API exercised"]

    def test_rule_works_on_populated_tree(self, tmp_path: Path) -> None:
        """Stub works on a tree with real entries, confirming API compatibility."""
        (tmp_path / "README.md").write_text("# hello")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x")

        from repopilot.scanner.local import LocalScanner
        tree = LocalScanner().scan(tmp_path)

        result = _FileTreeOnlyRule().evaluate(tree)
        assert isinstance(result, RuleResult)


# ---------------------------------------------------------------------------
# DEFAULT_RULES
# ---------------------------------------------------------------------------


class TestDefaultRules:
    def test_default_rules_is_a_list(self) -> None:
        assert isinstance(DEFAULT_RULES, list)

    def test_default_rules_starts_empty(self) -> None:
        """Task 2.0 leaves DEFAULT_RULES empty; rules are added in 2.1 – 2.6."""
        assert DEFAULT_RULES == []

    def test_default_rules_importable(self) -> None:
        from repopilot.rules import DEFAULT_RULES as dr  # noqa: PLC0415
        assert dr is not None


# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------


class TestModuleImports:
    def test_rule_base_importable(self) -> None:
        from repopilot.rules.base import Rule, RuleResult  # noqa: PLC0415
        assert Rule
        assert RuleResult

    def test_rules_package_importable(self) -> None:
        import repopilot.rules  # noqa: PLC0415
        assert repopilot.rules

    def test_no_circular_imports(self) -> None:
        """Re-importing the package should not raise."""
        import importlib  # noqa: PLC0415
        import repopilot.rules  # noqa: PLC0415
        importlib.reload(repopilot.rules)
