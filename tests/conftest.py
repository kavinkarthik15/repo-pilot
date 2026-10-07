"""Shared pytest fixtures for RepoPilot tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from repopilot.models import (
    AnalysisReport,
    Category,
    CategoryResult,
    Finding,
    RepositoryMetadata,
    Severity,
)


@pytest.fixture()
def minimal_metadata() -> RepositoryMetadata:
    """A minimal RepositoryMetadata instance for use in tests."""
    return RepositoryMetadata(
        source="/tmp/test-repo",
        name="test-repo",
        analyzed_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        analyzer_version="0.1.0",
        is_url=False,
    )


@pytest.fixture()
def sample_finding() -> Finding:
    """A single low-severity finding for use in tests."""
    return Finding(
        id="doc-no-readme",
        category=Category.DOCUMENTATION,
        severity=Severity.HIGH,
        title="No README found",
        detail="The repository has no README file at the root.",
        affected_paths=[],
    )
