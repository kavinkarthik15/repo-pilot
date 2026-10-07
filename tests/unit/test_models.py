"""Unit tests for repopilot.models.

Covers:
- Severity enum — exact five values, string values, ordering helper
- Category enum — all six values
- Finding — construction, path validation, immutability
- RecommendedAction — construction and validation
- CategoryResult — score range enforcement
- RepositoryMetadata — construction
- AnalysisReport — construction, score range, JSON round-trip
- severity_sort_key — deterministic ordering
- exceptions module — importable, hierarchy correct
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from repopilot.exceptions import (
    CleanupError,
    InvalidRepositoryError,
    InvalidSourceError,
    RepoPilotError,
    RepositoryNotFoundError,
    RuleError,
    ScanError,
)
from repopilot.models import (
    AnalysisReport,
    Category,
    CategoryResult,
    Finding,
    RecommendedAction,
    RepositoryMetadata,
    Severity,
    SEVERITY_ORDER,
    severity_sort_key,
)


# ---------------------------------------------------------------------------
# Severity enum
# ---------------------------------------------------------------------------


class TestSeverityEnum:
    def test_exactly_five_values(self) -> None:
        """The Severity enum must have exactly five members — no more, no less."""
        assert set(Severity) == {
            Severity.INFO,
            Severity.LOW,
            Severity.MEDIUM,
            Severity.HIGH,
            Severity.CRITICAL,
        }

    def test_no_warning_value(self) -> None:
        """'warning' must not exist as a Severity value."""
        names = {m.name for m in Severity}
        values = {m.value for m in Severity}
        assert "WARNING" not in names
        assert "warning" not in values

    def test_string_values(self) -> None:
        """Each Severity member must have the exact lowercase string value."""
        assert Severity.INFO == "info"
        assert Severity.LOW == "low"
        assert Severity.MEDIUM == "medium"
        assert Severity.HIGH == "high"
        assert Severity.CRITICAL == "critical"

    def test_is_str_enum(self) -> None:
        """Severity members should behave as strings (StrEnum)."""
        assert isinstance(Severity.HIGH, str)
        assert Severity.HIGH == "high"

    def test_severity_order_covers_all_values(self) -> None:
        """SEVERITY_ORDER must map every Severity member to a unique integer."""
        assert set(SEVERITY_ORDER.keys()) == set(Severity)
        ranks = list(SEVERITY_ORDER.values())
        assert len(ranks) == len(set(ranks)), "ranks must be unique"

    def test_severity_order_critical_is_lowest_rank(self) -> None:
        """CRITICAL must sort first (rank 0), INFO must sort last."""
        assert SEVERITY_ORDER[Severity.CRITICAL] < SEVERITY_ORDER[Severity.HIGH]
        assert SEVERITY_ORDER[Severity.HIGH] < SEVERITY_ORDER[Severity.MEDIUM]
        assert SEVERITY_ORDER[Severity.MEDIUM] < SEVERITY_ORDER[Severity.LOW]
        assert SEVERITY_ORDER[Severity.LOW] < SEVERITY_ORDER[Severity.INFO]


# ---------------------------------------------------------------------------
# Category enum
# ---------------------------------------------------------------------------


class TestCategoryEnum:
    def test_exactly_six_values(self) -> None:
        assert len(Category) == 6

    def test_expected_values(self) -> None:
        assert Category.DOCUMENTATION == "documentation"
        assert Category.STRUCTURE == "structure"
        assert Category.TESTING == "testing"
        assert Category.DEPENDENCY_HYGIENE == "dependency_hygiene"
        assert Category.SECURITY_HYGIENE == "security_hygiene"
        assert Category.MAINTAINABILITY == "maintainability"


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


class TestFinding:
    def test_basic_construction(self) -> None:
        f = Finding(
            id="doc-no-readme",
            category=Category.DOCUMENTATION,
            severity=Severity.HIGH,
            title="No README",
            detail="Missing README file.",
        )
        assert f.id == "doc-no-readme"
        assert f.severity == Severity.HIGH
        assert f.affected_paths == []

    def test_with_relative_paths(self) -> None:
        f = Finding(
            id="sec-env-file",
            category=Category.SECURITY_HYGIENE,
            severity=Severity.CRITICAL,
            title="Committed .env",
            detail="A .env file was found.",
            affected_paths=[".env", "config/.env.local"],
        )
        assert len(f.affected_paths) == 2

    def test_absolute_path_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Finding(
                id="test",
                category=Category.DOCUMENTATION,
                severity=Severity.INFO,
                title="t",
                detail="d",
                affected_paths=["/absolute/path/file.py"],
            )
        assert "relative paths only" in str(exc_info.value)

    def test_path_traversal_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Finding(
                id="test",
                category=Category.DOCUMENTATION,
                severity=Severity.INFO,
                title="t",
                detail="d",
                affected_paths=["../../etc/passwd"],
            )
        assert "escape the repository root" in str(exc_info.value)

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Finding(
                id="   ",
                category=Category.DOCUMENTATION,
                severity=Severity.INFO,
                title="t",
                detail="d",
            )

    def test_immutable(self) -> None:
        f = Finding(
            id="doc-no-readme",
            category=Category.DOCUMENTATION,
            severity=Severity.HIGH,
            title="No README",
            detail="Missing.",
        )
        with pytest.raises(ValidationError):
            f.id = "other"  # type: ignore[misc]

    def test_severity_accepts_all_five_values(self) -> None:
        for sev in Severity:
            f = Finding(
                id=f"test-{sev}",
                category=Category.DOCUMENTATION,
                severity=sev,
                title="t",
                detail="d",
            )
            assert f.severity == sev


# ---------------------------------------------------------------------------
# RecommendedAction
# ---------------------------------------------------------------------------


class TestRecommendedAction:
    def test_basic_construction(self) -> None:
        action = RecommendedAction(
            finding_ids=["doc-no-readme"],
            priority=Severity.HIGH,
            action="Add a README.md file to the repository root.",
        )
        assert action.priority == Severity.HIGH
        assert len(action.finding_ids) == 1

    def test_empty_finding_ids_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            RecommendedAction(
                finding_ids=[],
                priority=Severity.LOW,
                action="Do something.",
            )
        assert "at least one finding" in str(exc_info.value)

    def test_immutable(self) -> None:
        action = RecommendedAction(
            finding_ids=["x"],
            priority=Severity.INFO,
            action="Do something.",
        )
        with pytest.raises(ValidationError):
            action.action = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CategoryResult
# ---------------------------------------------------------------------------


class TestCategoryResult:
    def test_basic_construction(self) -> None:
        result = CategoryResult(
            category=Category.TESTING,
            score=75,
        )
        assert result.score == 75
        assert result.findings == []
        assert result.strengths == []

    def test_score_zero(self) -> None:
        result = CategoryResult(category=Category.TESTING, score=0)
        assert result.score == 0

    def test_score_100(self) -> None:
        result = CategoryResult(category=Category.TESTING, score=100)
        assert result.score == 100

    def test_score_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CategoryResult(category=Category.TESTING, score=-1)

    def test_score_above_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CategoryResult(category=Category.TESTING, score=101)

    def test_with_findings_and_strengths(self, sample_finding: Finding) -> None:
        result = CategoryResult(
            category=Category.DOCUMENTATION,
            score=50,
            findings=[sample_finding],
            strengths=["CONTRIBUTING.md present"],
        )
        assert len(result.findings) == 1
        assert result.strengths[0] == "CONTRIBUTING.md present"


# ---------------------------------------------------------------------------
# RepositoryMetadata
# ---------------------------------------------------------------------------


class TestRepositoryMetadata:
    def test_local_path(self) -> None:
        meta = RepositoryMetadata(
            source="/home/user/my-repo",
            name="my-repo",
            analyzed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            analyzer_version="0.1.0",
            is_url=False,
        )
        assert meta.is_url is False
        assert meta.name == "my-repo"

    def test_url_source(self) -> None:
        meta = RepositoryMetadata(
            source="https://github.com/owner/repo",
            name="repo",
            analyzed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            analyzer_version="0.1.0",
            is_url=True,
        )
        assert meta.is_url is True

    def test_immutable(self) -> None:
        meta = RepositoryMetadata(
            source="/tmp/r",
            name="r",
            analyzed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            analyzer_version="0.1.0",
            is_url=False,
        )
        with pytest.raises(ValidationError):
            meta.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AnalysisReport
# ---------------------------------------------------------------------------


def _make_report(
    overall_score: int = 80,
    findings: list[Finding] | None = None,
) -> AnalysisReport:
    meta = RepositoryMetadata(
        source="/tmp/repo",
        name="repo",
        analyzed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        analyzer_version="0.1.0",
        is_url=False,
    )
    category_results = [
        CategoryResult(category=cat, score=overall_score) for cat in Category
    ]
    return AnalysisReport(
        metadata=meta,
        overall_score=overall_score,
        category_results=category_results,
        strengths=["README present"],
        findings=findings or [],
        recommended_actions=[],
    )


class TestAnalysisReport:
    def test_basic_construction(self) -> None:
        report = _make_report(overall_score=74)
        assert report.overall_score == 74

    def test_score_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_report(overall_score=-1)

    def test_score_above_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_report(overall_score=101)

    def test_to_json_returns_valid_json(self) -> None:
        report = _make_report(overall_score=90)
        raw = report.to_json()
        parsed = json.loads(raw)
        assert parsed["overall_score"] == 90
        assert "metadata" in parsed

    def test_to_json_contains_severity_strings(self, sample_finding: Finding) -> None:
        """Severity values must serialise as strings, not as enum repr."""
        report = _make_report(findings=[sample_finding])
        raw = report.to_json()
        parsed = json.loads(raw)
        finding = parsed["findings"][0]
        assert finding["severity"] == "high"

    def test_from_json_round_trip(self) -> None:
        report = _make_report(overall_score=55)
        raw = report.to_json()
        restored = AnalysisReport.from_json(raw)
        assert restored.overall_score == report.overall_score
        assert restored.metadata.name == report.metadata.name
        assert restored.metadata.analyzer_version == report.metadata.analyzer_version

    def test_from_json_round_trip_with_finding(self, sample_finding: Finding) -> None:
        report = _make_report(findings=[sample_finding])
        raw = report.to_json()
        restored = AnalysisReport.from_json(raw)
        assert len(restored.findings) == 1
        assert restored.findings[0].id == "doc-no-readme"
        assert restored.findings[0].severity == Severity.HIGH

    def test_datetime_serialises_as_iso_string(self) -> None:
        report = _make_report()
        raw = report.to_json()
        parsed = json.loads(raw)
        # datetime must appear as an ISO-8601 string, not a raw object
        assert isinstance(parsed["metadata"]["analyzed_at"], str)

    def test_immutable(self) -> None:
        report = _make_report()
        with pytest.raises(ValidationError):
            report.overall_score = 0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# severity_sort_key
# ---------------------------------------------------------------------------


class TestSeveritySortKey:
    def test_critical_sorts_before_high(self) -> None:
        critical = Finding(
            id="a",
            category=Category.SECURITY_HYGIENE,
            severity=Severity.CRITICAL,
            title="t",
            detail="d",
        )
        high = Finding(
            id="b",
            category=Category.SECURITY_HYGIENE,
            severity=Severity.HIGH,
            title="t",
            detail="d",
        )
        assert severity_sort_key(critical) < severity_sort_key(high)

    def test_same_severity_ordered_by_id(self) -> None:
        f_a = Finding(
            id="aaa",
            category=Category.DOCUMENTATION,
            severity=Severity.LOW,
            title="t",
            detail="d",
        )
        f_b = Finding(
            id="bbb",
            category=Category.DOCUMENTATION,
            severity=Severity.LOW,
            title="t",
            detail="d",
        )
        assert severity_sort_key(f_a) < severity_sort_key(f_b)

    def test_sorted_list_is_deterministic(self) -> None:
        findings = [
            Finding(id="z-info", category=Category.TESTING, severity=Severity.INFO, title="t", detail="d"),
            Finding(id="a-critical", category=Category.SECURITY_HYGIENE, severity=Severity.CRITICAL, title="t", detail="d"),
            Finding(id="m-medium", category=Category.DOCUMENTATION, severity=Severity.MEDIUM, title="t", detail="d"),
            Finding(id="b-high", category=Category.STRUCTURE, severity=Severity.HIGH, title="t", detail="d"),
            Finding(id="c-low", category=Category.MAINTAINABILITY, severity=Severity.LOW, title="t", detail="d"),
        ]
        sorted_once = sorted(findings, key=severity_sort_key)
        sorted_twice = sorted(findings, key=severity_sort_key)
        assert [f.id for f in sorted_once] == [f.id for f in sorted_twice]
        assert sorted_once[0].severity == Severity.CRITICAL
        assert sorted_once[-1].severity == Severity.INFO


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_all_exceptions_importable(self) -> None:
        assert RepoPilotError
        assert InvalidSourceError
        assert RepositoryNotFoundError
        assert InvalidRepositoryError
        assert ScanError
        assert RuleError
        assert CleanupError

    def test_all_inherit_from_base(self) -> None:
        for exc_cls in (
            InvalidSourceError,
            RepositoryNotFoundError,
            InvalidRepositoryError,
            ScanError,
            RuleError,
            CleanupError,
        ):
            assert issubclass(exc_cls, RepoPilotError)

    def test_base_inherits_from_exception(self) -> None:
        assert issubclass(RepoPilotError, Exception)

    def test_can_be_raised_and_caught_as_base(self) -> None:
        with pytest.raises(RepoPilotError):
            raise ScanError("scanner failed")

    def test_distinct_types_are_distinguishable(self) -> None:
        with pytest.raises(ScanError):
            raise ScanError("scan error")
        with pytest.raises(InvalidSourceError):
            raise InvalidSourceError("bad source")
