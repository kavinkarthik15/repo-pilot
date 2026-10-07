"""Repository structure analysis rules for RepoPilot.

Implements Task 2.2 — all four rules from the approved design:

    SourceDirectoryRule   struct-no-src-dir       LOW
    TestDirectoryRule     struct-no-tests-dir     MEDIUM
    EmptyRepoRule         struct-empty-repo       HIGH
    ConfigFilesRule       struct-no-config-files  INFO

References: design.md § Structure rules, REQ-003.1 – REQ-003.6
"""

from __future__ import annotations

import fnmatch
from typing import Final

from repopilot.models import Category, Finding, Severity
from repopilot.rules.base import Rule, RuleResult
from repopilot.scanner.base import FileTree

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Source directory names (REQ-003.1). Matched case-insensitively at root.
_SOURCE_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {"src", "lib", "app", "core", "pkg", "cmd"}
)

#: Test directory names (REQ-003.2). Matched at root or one level deep.
_TEST_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {"tests", "test", "spec", "__tests__", "e2e", "integration"}
)

#: Config file patterns from REQ-003.3.
#: Exact names or glob patterns matched against root-level file basenames.
_CONFIG_FILE_PATTERNS: Final[tuple[str, ...]] = (
    ".editorconfig",
    ".prettierrc",
    ".eslintrc",       # exact; glob covers variants below
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.yaml",
    ".eslintrc.yml",
    ".eslintrc.json",
    "pyproject.toml",
    "setup.cfg",
    ".flake8",
    "tox.ini",
    "makefile",        # lower-cased for case-insensitive comparison
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
)

#: Glob patterns for config files (applied after exact match fails).
_CONFIG_GLOB_PATTERNS: Final[tuple[str, ...]] = (
    ".eslintrc*",
    "docker-compose*",
)


def _is_config_file(basename: str) -> bool:
    """Return True if *basename* (lower-cased) matches a known config file."""
    lower = basename.lower()
    if lower in _CONFIG_FILE_PATTERNS:
        return True
    for pattern in _CONFIG_GLOB_PATTERNS:
        if fnmatch.fnmatch(lower, pattern):
            return True
    return False


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


class SourceDirectoryRule(Rule):
    """Check for a recognised source directory at the repository root.

    Checks for any of: src, lib, app, core, pkg, cmd (case-insensitive).

    Finding: struct-no-src-dir (LOW) when none found.
    Strength: "Source directory present: <name>" when found.
    """

    @property
    def rule_id(self) -> str:
        return "struct-no-src-dir"

    @property
    def category(self) -> Category:
        return Category.STRUCTURE

    @property
    def default_severity(self) -> Severity:
        return Severity.LOW

    @property
    def title(self) -> str:
        return "No recognised source directory found"

    @property
    def description(self) -> str:
        return (
            "Checks for a recognised source directory at the repository root. "
            "Accepted names: src, lib, app, core, pkg, cmd (case-insensitive)."
        )

    def _evaluate(self, tree: FileTree) -> RuleResult:
        for entry in tree.root_files():
            if not entry.is_dir:
                continue
            basename = entry.relative.split("/")[-1].lower()
            if basename in _SOURCE_DIR_NAMES:
                return RuleResult(
                    strengths=[f"Source directory present: {entry.relative}"]
                )
        return RuleResult(
            findings=[
                Finding(
                    id=self.rule_id,
                    category=self.category,
                    severity=self.default_severity,
                    title=self.title,
                    detail=(
                        "No recognised source directory was found at the "
                        "repository root. Consider organising source code under "
                        "a directory such as src/, lib/, or app/."
                    ),
                    affected_paths=[],
                )
            ]
        )


class TestDirectoryRule(Rule):
    """Check for a recognised test directory at root or one level deep.

    Checks for any of: tests, test, spec, __tests__, e2e, integration
    at the root level or as an immediate child of any root-level directory.

    Finding: struct-no-tests-dir (MEDIUM) when none found.
    Strength: "Test directory present: <path>" when found.
    """

    @property
    def rule_id(self) -> str:
        return "struct-no-tests-dir"

    @property
    def category(self) -> Category:
        return Category.STRUCTURE

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def title(self) -> str:
        return "No recognised test directory found"

    @property
    def description(self) -> str:
        return (
            "Checks for a recognised test directory at the root or one level "
            "deep. Accepted names: tests, test, spec, __tests__, e2e, "
            "integration (case-insensitive)."
        )

    def _evaluate(self, tree: FileTree) -> RuleResult:
        for entry in tree.entries:
            if not entry.is_dir:
                continue
            rel = entry.relative.replace("\\", "/")
            parts = rel.split("/")
            # Depth 1: root-level directory.
            # Depth 2: one level deep (child of a root-level directory).
            if len(parts) not in (1, 2):
                continue
            basename = parts[-1].lower()
            if basename in _TEST_DIR_NAMES:
                return RuleResult(
                    strengths=[f"Test directory present: {entry.relative}"]
                )
        return RuleResult(
            findings=[
                Finding(
                    id=self.rule_id,
                    category=self.category,
                    severity=self.default_severity,
                    title=self.title,
                    detail=(
                        "No recognised test directory was found at the root or "
                        "one level deep. Consider adding a tests/ or test/ "
                        "directory to organise automated tests."
                    ),
                    affected_paths=[],
                )
            ]
        )


class EmptyRepoRule(Rule):
    """Check that the repository root contains enough non-hidden files.

    REQ-003.5: fewer than 3 non-hidden root files → flagged as suspiciously
    empty.  Hidden entries (name starts with '.') are excluded from the count.
    Directories are included so that a repo with only subdirectories and no
    files still counts those directories toward the minimum.

    Finding: struct-empty-repo (HIGH) when non-hidden root count < 3.
    Strength: "Repository root has <n> non-hidden entries" when count ≥ 3.
    """

    @property
    def rule_id(self) -> str:
        return "struct-empty-repo"

    @property
    def category(self) -> Category:
        return Category.STRUCTURE

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def title(self) -> str:
        return "Repository appears suspiciously empty"

    @property
    def description(self) -> str:
        return (
            "Checks that the repository root contains at least 3 non-hidden "
            "files or directories. Fewer than 3 suggests an uninitialised or "
            "skeleton repository."
        )

    def _evaluate(self, tree: FileTree) -> RuleResult:
        # Count non-hidden entries at the root (both files and directories).
        non_hidden = [
            e for e in tree.root_files()
            if not e.relative.split("/")[-1].startswith(".")
        ]
        count = len(non_hidden)

        if count < 3:
            # REQ-003.6: state which files/dirs triggered the finding.
            found_names = sorted(e.relative for e in non_hidden)
            affected = found_names  # relative paths, may be empty
            detail = (
                f"The repository root contains only {count} non-hidden "
                f"{'entry' if count == 1 else 'entries'}"
                + (f" ({', '.join(found_names)})" if found_names else "")
                + ". A minimum of 3 is expected. This may indicate an "
                "uninitialised or skeleton repository."
            )
            return RuleResult(
                findings=[
                    Finding(
                        id=self.rule_id,
                        category=self.category,
                        severity=self.default_severity,
                        title=self.title,
                        detail=detail,
                        affected_paths=affected,
                    )
                ]
            )

        return RuleResult(
            strengths=[f"Repository root has {count} non-hidden entries"]
        )


class ConfigFilesRule(Rule):
    """Check for the presence of common project configuration files.

    Checks root-level files against the list from REQ-003.3:
    .editorconfig, .prettierrc, .eslintrc*, pyproject.toml, setup.cfg,
    .flake8, tox.ini, Makefile, Dockerfile, docker-compose.yml.

    Finding: struct-no-config-files (INFO) when none found.
    Strength: "Config file present: <name>" for each match found.
    """

    @property
    def rule_id(self) -> str:
        return "struct-no-config-files"

    @property
    def category(self) -> Category:
        return Category.STRUCTURE

    @property
    def default_severity(self) -> Severity:
        return Severity.INFO

    @property
    def title(self) -> str:
        return "No project configuration files found"

    @property
    def description(self) -> str:
        return (
            "Checks for common project configuration files at the repository "
            "root: .editorconfig, .prettierrc, .eslintrc*, pyproject.toml, "
            "setup.cfg, .flake8, tox.ini, Makefile, Dockerfile, "
            "docker-compose.yml."
        )

    def _evaluate(self, tree: FileTree) -> RuleResult:
        found: list[str] = []
        for entry in tree.root_files():
            if entry.is_dir:
                continue
            basename = entry.relative.split("/")[-1]
            if _is_config_file(basename):
                found.append(entry.relative)

        if found:
            # Sort for deterministic strength ordering.
            strengths = [f"Config file present: {p}" for p in sorted(found)]
            return RuleResult(strengths=strengths)

        return RuleResult(
            findings=[
                Finding(
                    id=self.rule_id,
                    category=self.category,
                    severity=self.default_severity,
                    title=self.title,
                    detail=(
                        "No common project configuration files were found at "
                        "the repository root. Consider adding a pyproject.toml, "
                        "Makefile, .editorconfig, or similar tool-configuration "
                        "file."
                    ),
                    affected_paths=[],
                )
            ]
        )
