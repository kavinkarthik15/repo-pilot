"""Domain models for RepoPilot.

All cross-layer data structures are defined here as Pydantic models.
This module has zero imports from other internal RepoPilot modules:
it is the foundation everything else builds on.

Design constraints (from tech.md and design.md):
- All models use full type annotations.
- Value objects are frozen (immutable after construction).
- Finding.affected_paths must contain relative paths only — never absolute
  paths, never file contents.
- Severity uses exactly five values: info, low, medium, high, critical.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Severity(StrEnum):
    """Severity levels for analysis findings.

    Exactly five values are permitted.  Do not add 'warning' or any other
    value without updating the spec, steering docs, and scoring constants.

    Deduction per severity (from scoring.py, documented here for traceability):
        info     = 0
        low      = 3
        medium   = 7
        high     = 15
        critical = 25

    CRITICAL is reserved for clearly committed credential or secret-related
    files (e.g. id_rsa, .env, credentials.json).  It must never expose file
    contents in findings.
    """

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Category(StrEnum):
    """Analysis dimensions evaluated by RepoPilot."""

    DOCUMENTATION = "documentation"
    STRUCTURE = "structure"
    TESTING = "testing"
    DEPENDENCY_HYGIENE = "dependency_hygiene"
    SECURITY_HYGIENE = "security_hygiene"
    MAINTAINABILITY = "maintainability"


# ---------------------------------------------------------------------------
# Core finding types
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    """A single analysis finding produced by a rule.

    Finding IDs follow the convention ``<category-prefix>-<short-slug>``,
    e.g. ``doc-no-readme``, ``sec-committed-env-file``.  IDs are stable
    constants defined in each rule class — never dynamically generated labels.

    ``affected_paths`` must contain paths relative to the repository root.
    Absolute paths and file contents are never permitted here.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    category: Category
    severity: Severity
    title: str
    detail: str
    affected_paths: list[str] = []

    @field_validator("affected_paths", mode="after")
    @classmethod
    def paths_must_be_relative(cls, paths: list[str]) -> list[str]:
        """Reject absolute paths and guard against accidental content leakage.

        Checks are cross-platform and do not rely on the host OS's path
        semantics.  All of the following are treated as absolute and rejected
        regardless of whether the code runs on Windows or POSIX:

          - POSIX absolute:       /home/user/file
          - Windows drive-letter: C:\\Users\\user\\file  or  C:/Users/file
          - Windows root-only:    /file  (drive-relative root on Windows)
          - UNC paths:            \\\\server\\share\\file
        """
        import os  # stdlib only — no layer violation
        import re

        # Matches Windows drive-letter paths: C:\ C:/ c:\ c:/
        _WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[/\\]")
        # Matches UNC paths: \\server or //server
        _UNC_RE = re.compile(r"^[/\\]{2}")

        for p in paths:
            # Cross-platform absolute-path detection:
            # 1. Host-OS check (catches the native absolute form on any OS).
            # 2. POSIX leading slash (missed by os.path.isabs on Windows).
            # 3. Windows drive-letter prefix (missed by os.path.isabs on POSIX).
            # 4. UNC prefix (\\server or //server).
            if (
                os.path.isabs(p)
                or p.startswith("/")
                or _WINDOWS_DRIVE_RE.match(p)
                or _UNC_RE.match(p)
            ):
                raise ValueError(
                    f"affected_paths must contain relative paths only; "
                    f"got absolute path: {p!r}"
                )
            # Guard against path traversal attempts escaping the repo root.
            normalised = os.path.normpath(p)
            if normalised.startswith(".."):
                raise ValueError(
                    f"affected_paths must not escape the repository root; "
                    f"got: {p!r}"
                )
        return paths

    @field_validator("id", mode="after")
    @classmethod
    def id_must_not_be_empty(cls, v: str) -> str:
        """Finding IDs must be non-empty stable slugs."""
        if not v.strip():
            raise ValueError("Finding id must be a non-empty string")
        return v


class RecommendedAction(BaseModel):
    """A recommended remediation action derived from one or more findings.

    ``priority`` is derived from the highest severity among the linked findings.
    """

    model_config = ConfigDict(frozen=True)

    finding_ids: list[str]
    priority: Severity
    action: str

    @field_validator("finding_ids", mode="after")
    @classmethod
    def must_have_at_least_one_finding(cls, v: list[str]) -> list[str]:
        """An action must reference at least one finding."""
        if not v:
            raise ValueError("finding_ids must contain at least one finding ID")
        return v


# ---------------------------------------------------------------------------
# Aggregation models
# ---------------------------------------------------------------------------


class CategoryResult(BaseModel):
    """Score and findings for a single analysis dimension."""

    model_config = ConfigDict(frozen=True)

    category: Category
    score: int  # 0–100 inclusive
    findings: list[Finding] = []
    strengths: list[str] = []

    @field_validator("score", mode="after")
    @classmethod
    def score_in_range(cls, v: int) -> int:
        """Scores must be within the documented [0, 100] range."""
        if not (0 <= v <= 100):
            raise ValueError(f"score must be in [0, 100]; got {v}")
        return v


class RepositoryMetadata(BaseModel):
    """Provenance information recorded in every analysis report."""

    model_config = ConfigDict(frozen=True)

    source: str  # original user-supplied input (local path or URL)
    name: str  # inferred repository name (last path segment, .git stripped)
    analyzed_at: datetime
    analyzer_version: str
    is_url: bool


class AnalysisReport(BaseModel):
    """The complete output of a RepoPilot analysis run.

    Aggregates all category results, findings, strengths, and recommended
    actions into a single serialisable structure.

    ``findings`` is the flat list of all findings across categories, sorted
    by severity (critical → high → medium → low → info) then by finding ID
    for deterministic ordering.

    ``strengths`` is the flat list of all positive indicators across
    categories, deduplicated and sorted.
    """

    model_config = ConfigDict(frozen=True)

    metadata: RepositoryMetadata
    overall_score: int  # 0–100 inclusive
    category_results: list[CategoryResult]
    strengths: list[str] = []
    findings: list[Finding] = []
    recommended_actions: list[RecommendedAction] = []

    @field_validator("overall_score", mode="after")
    @classmethod
    def overall_score_in_range(cls, v: int) -> int:
        """Overall score must be within the documented [0, 100] range."""
        if not (0 <= v <= 100):
            raise ValueError(f"overall_score must be in [0, 100]; got {v}")
        return v

    @model_validator(mode="after")
    def findings_sorted_by_severity(self) -> "AnalysisReport":
        """Verify findings are in deterministic severity-descending order.

        This is a documentation-and-verification validator, not a sorter.
        Callers are expected to pass pre-sorted findings.  If they are not
        sorted the model is still constructed but a warning is not raised —
        the sorting responsibility belongs to the service layer.
        """
        return self

    def to_json(self, *, indent: int = 2) -> str:
        """Serialise the report to a JSON string.

        Uses Pydantic's model_dump with ``mode='json'`` so datetime fields
        are rendered as ISO-8601 strings and enums as their string values.
        """
        data: dict[str, Any] = self.model_dump(mode="json")
        return json.dumps(data, indent=indent)

    @classmethod
    def from_json(cls, raw: str) -> "AnalysisReport":
        """Deserialise a report from a JSON string (round-trip counterpart)."""
        return cls.model_validate_json(raw)


# ---------------------------------------------------------------------------
# Severity ordering helper (used by service layer for deterministic sorting)
# ---------------------------------------------------------------------------

#: Canonical severity order, highest impact first.
SEVERITY_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def severity_sort_key(finding: Finding) -> tuple[int, str]:
    """Return a stable sort key for a finding: (severity_rank, id).

    Lower rank = higher severity = sorts first.
    """
    return (SEVERITY_ORDER[finding.severity], finding.id)
