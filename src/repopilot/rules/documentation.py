"""Documentation analysis rules for RepoPilot.

Implements Task 2.1 — all five rules from the approved design:

    ReadmePresenceRule   doc-no-readme           HIGH
    ReadmeSizeRule       doc-readme-minimal       HIGH   (< 200 bytes)
                         doc-readme-brief         MEDIUM (200–999 bytes)
    ReadmeSectionsRule   doc-readme-missing-*     LOW    (per section)
    ContributingRule     doc-no-contributing      LOW
    DocsDirectoryRule    doc-no-docs-dir          INFO

References: design.md § Documentation rules, REQ-002.1 – REQ-002.7
"""

from __future__ import annotations

import re
from typing import Final

from repopilot.models import Category, Finding, Severity
from repopilot.rules.base import Rule, RuleResult
from repopilot.scanner.base import FileTree

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: README filenames recognised by REQ-002.1 (matched case-insensitively).
_README_NAMES: Final[frozenset[str]] = frozenset(
    {"readme.md", "readme.rst", "readme.txt", "readme"}
)

#: CONTRIBUTING filenames recognised by REQ-002.5 (matched case-insensitively).
_CONTRIBUTING_NAMES: Final[frozenset[str]] = frozenset(
    {"contributing.md", "contributing.rst", "contributing"}
)

#: Byte thresholds from REQ-002.3 / REQ-002.4.
_MINIMAL_THRESHOLD: Final[int] = 200   # < 200 bytes → "minimal" (HIGH)
_BRIEF_THRESHOLD: Final[int] = 1_000   # 200–999 bytes → "brief"  (MEDIUM)

#: Required README sections from REQ-002.2.
#: Each entry is the keyword that must appear as a heading.
_REQUIRED_SECTIONS: Final[tuple[str, ...]] = (
    "installation",
    "usage",
    "features",
    "contributing",
    "testing",
    "license",
)

# Pre-compiled section-heading patterns (tasks.md specification):
#   Pattern A: Markdown ATX heading  ^#{1,4}\s*<keyword>
#   Pattern B: Setext underline      ^<keyword>\s*\n[=\-]+
# Both are MULTILINE + IGNORECASE.
_SECTION_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    section: re.compile(
        rf"(?:^#{{1,4}}\s*{re.escape(section)}"
        rf"|^{re.escape(section)}\s*\n[=\-]+)",
        re.MULTILINE | re.IGNORECASE,
    )
    for section in _REQUIRED_SECTIONS
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_readme_name(tree: FileTree) -> str | None:
    """Return the relative path of the first README variant found, or None.

    Only root-level files are considered (REQ-002.1: "at the repository root").
    """
    for entry in tree.root_files():
        if not entry.is_dir:
            basename = entry.relative.split("/")[-1].lower()
            if basename in _README_NAMES:
                return entry.relative
    return None


def _find_contributing_name(tree: FileTree) -> str | None:
    """Return the relative path of the first CONTRIBUTING variant, or None.

    Searched at the root and inside any ``docs/`` subdirectory (REQ-002.5).
    """
    # Root-level check.
    for entry in tree.root_files():
        if not entry.is_dir:
            basename = entry.relative.split("/")[-1].lower()
            if basename in _CONTRIBUTING_NAMES:
                return entry.relative

    # docs/ subdirectory check.
    for entry in tree.entries:
        if entry.is_dir:
            continue
        parts = entry.relative.replace("\\", "/").split("/")
        if len(parts) == 2 and parts[0].lower() == "docs":
            if parts[1].lower() in _CONTRIBUTING_NAMES:
                return entry.relative

    return None


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


class ReadmePresenceRule(Rule):
    """Check that a README file exists at the repository root.

    Finding: doc-no-readme (HIGH) when no README variant is found.
    Strength: "README present: <filename>" when found.
    """

    @property
    def rule_id(self) -> str:
        return "doc-no-readme"

    @property
    def category(self) -> Category:
        return Category.DOCUMENTATION

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def title(self) -> str:
        return "No README file found"

    @property
    def description(self) -> str:
        return (
            "Checks for a README file at the repository root. "
            "Accepted names: README.md, README.rst, README.txt, README "
            "(case-insensitive)."
        )

    def _evaluate(self, tree: FileTree) -> RuleResult:
        readme = _find_readme_name(tree)
        if readme is not None:
            return RuleResult(strengths=[f"README present: {readme}"])
        return RuleResult(
            findings=[
                Finding(
                    id=self.rule_id,
                    category=self.category,
                    severity=self.default_severity,
                    title=self.title,
                    detail=(
                        "No README file was found at the repository root. "
                        "Add a README.md (or README.rst / README.txt) describing "
                        "the project, how to install it, and how to use it."
                    ),
                    affected_paths=[],
                )
            ]
        )


class ReadmeSizeRule(Rule):
    """Check that the README meets minimum usefulness thresholds.

    Finding: doc-readme-minimal (HIGH) when content < 200 bytes.
    Finding: doc-readme-brief   (MEDIUM) when content is 200–999 bytes.
    No finding when content is ≥ 1 000 bytes.

    If no README exists, or if read_text returns None (binary / unreadable),
    this rule produces no findings — ReadmePresenceRule handles the absent case.
    """

    @property
    def rule_id(self) -> str:
        # Primary/representative ID; individual findings use specific IDs below.
        return "doc-readme-size"

    @property
    def category(self) -> Category:
        return Category.DOCUMENTATION

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def title(self) -> str:
        return "README is too short"

    @property
    def description(self) -> str:
        return (
            "Checks that the README is at least 1 000 bytes. "
            "Files under 200 bytes are flagged as minimal (HIGH); "
            "files under 1 000 bytes are flagged as brief (MEDIUM)."
        )

    def _evaluate(self, tree: FileTree) -> RuleResult:
        readme_path = _find_readme_name(tree)
        if readme_path is None:
            # No README — nothing to size-check here.
            return RuleResult()

        content = tree.read_text(readme_path)
        if content is None:
            # Unreadable / binary — cannot assess; no finding.
            return RuleResult()

        size = len(content.encode("utf-8"))

        if size < _MINIMAL_THRESHOLD:
            return RuleResult(
                findings=[
                    Finding(
                        id="doc-readme-minimal",
                        category=self.category,
                        severity=Severity.HIGH,
                        title="README is minimal (< 200 bytes)",
                        detail=(
                            f"The README at {readme_path!r} contains only "
                            f"{size} bytes. A minimal README provides almost "
                            "no useful information. Expand it to describe the "
                            "project purpose, installation steps, and usage."
                        ),
                        affected_paths=[readme_path],
                    )
                ]
            )

        if size < _BRIEF_THRESHOLD:
            return RuleResult(
                findings=[
                    Finding(
                        id="doc-readme-brief",
                        category=self.category,
                        severity=Severity.MEDIUM,
                        title="README is brief (< 1 000 bytes)",
                        detail=(
                            f"The README at {readme_path!r} contains only "
                            f"{size} bytes. Consider expanding it to include "
                            "installation instructions, usage examples, and "
                            "contribution guidelines."
                        ),
                        affected_paths=[readme_path],
                    )
                ]
            )

        # README is adequately sized — no finding.
        return RuleResult()


class ReadmeSectionsRule(Rule):
    """Check that the README contains the required conceptual sections.

    Produces one LOW finding per missing section from the set:
    {installation, usage, features, contributing, testing, license}.

    Section detection uses case-insensitive heading matching:
      - Markdown ATX: ``^#{1,4}\\s*<keyword>``
      - Setext underline: ``^<keyword>\\s*\\n[=-]+``

    If no README exists, or content is unavailable, no findings are produced.
    """

    @property
    def rule_id(self) -> str:
        return "doc-readme-sections"

    @property
    def category(self) -> Category:
        return Category.DOCUMENTATION

    @property
    def default_severity(self) -> Severity:
        return Severity.LOW

    @property
    def title(self) -> str:
        return "README is missing expected sections"

    @property
    def description(self) -> str:
        return (
            "Checks the README for the presence of standard section headings: "
            "Installation, Usage, Features, Contributing, Testing, License."
        )

    def _evaluate(self, tree: FileTree) -> RuleResult:
        readme_path = _find_readme_name(tree)
        if readme_path is None:
            return RuleResult()

        content = tree.read_text(readme_path)
        if content is None:
            return RuleResult()

        findings: list[Finding] = []
        strengths: list[str] = []

        for section in _REQUIRED_SECTIONS:
            pattern = _SECTION_PATTERNS[section]
            if pattern.search(content):
                strengths.append(f"README section present: {section}")
            else:
                findings.append(
                    Finding(
                        id=f"doc-readme-missing-{section}",
                        category=self.category,
                        severity=self.default_severity,
                        title=f"README missing '{section}' section",
                        detail=(
                            f"The README at {readme_path!r} does not contain "
                            f"a heading for '{section}'. "
                            f"Add a '## {section.capitalize()}' section to help "
                            "readers understand this aspect of the project."
                        ),
                        affected_paths=[readme_path],
                    )
                )

        return RuleResult(findings=findings, strengths=strengths)


class ContributingRule(Rule):
    """Check that a CONTRIBUTING file exists at the root or in docs/.

    Finding: doc-no-contributing (LOW) when absent.
    Strength: "CONTRIBUTING present: <path>" when found.
    """

    @property
    def rule_id(self) -> str:
        return "doc-no-contributing"

    @property
    def category(self) -> Category:
        return Category.DOCUMENTATION

    @property
    def default_severity(self) -> Severity:
        return Severity.LOW

    @property
    def title(self) -> str:
        return "No CONTRIBUTING file found"

    @property
    def description(self) -> str:
        return (
            "Checks for a CONTRIBUTING.md / CONTRIBUTING.rst / CONTRIBUTING "
            "file at the repository root or in a docs/ subdirectory."
        )

    def _evaluate(self, tree: FileTree) -> RuleResult:
        path = _find_contributing_name(tree)
        if path is not None:
            return RuleResult(strengths=[f"CONTRIBUTING present: {path}"])
        return RuleResult(
            findings=[
                Finding(
                    id=self.rule_id,
                    category=self.category,
                    severity=self.default_severity,
                    title=self.title,
                    detail=(
                        "No CONTRIBUTING file was found at the repository root "
                        "or in the docs/ directory. Add a CONTRIBUTING.md to "
                        "explain how to report issues, propose changes, and "
                        "set up a development environment."
                    ),
                    affected_paths=[],
                )
            ]
        )


class DocsDirectoryRule(Rule):
    """Check that a docs/ or doc/ directory exists.

    Finding: doc-no-docs-dir (INFO) when neither docs/ nor doc/ is found.
    Strength: "Docs directory present: <path>" when found.
    """

    @property
    def rule_id(self) -> str:
        return "doc-no-docs-dir"

    @property
    def category(self) -> Category:
        return Category.DOCUMENTATION

    @property
    def default_severity(self) -> Severity:
        return Severity.INFO

    @property
    def title(self) -> str:
        return "No docs/ directory found"

    @property
    def description(self) -> str:
        return (
            "Checks for a docs/ or doc/ directory, which indicates the "
            "project has dedicated documentation beyond the README."
        )

    def _evaluate(self, tree: FileTree) -> RuleResult:
        for name in ("docs", "doc"):
            dirs = tree.find_dirs(name)
            if dirs:
                return RuleResult(
                    strengths=[f"Docs directory present: {dirs[0].relative}"]
                )
        return RuleResult(
            findings=[
                Finding(
                    id=self.rule_id,
                    category=self.category,
                    severity=self.default_severity,
                    title=self.title,
                    detail=(
                        "No docs/ or doc/ directory was found. Consider adding "
                        "a docs/ directory with extended documentation, API "
                        "references, or architecture notes."
                    ),
                    affected_paths=[],
                )
            ]
        )
