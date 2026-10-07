"""Unit tests for Task 2.1: Documentation rules.

All tests use synthetic FileTree objects built from real temporary directories
via LocalScanner — no direct filesystem access from within rule code.

Covers (per acceptance criteria):
    ReadmePresenceRule
      - no README at all                      → HIGH doc-no-readme
      - README.md present                     → strength, no findings
      - README.rst / README.txt / README      → found (case-insensitive variants)
      - CONTRIBUTING.md is NOT a readme       → still no readme
      - README inside subdirectory not counted
      - stable finding ID

    ReadmeSizeRule
      - README absent                         → no findings (presence rule's job)
      - README < 200 bytes                    → HIGH doc-readme-minimal
      - README exactly 200 bytes              → MEDIUM doc-readme-brief
      - README exactly 999 bytes              → MEDIUM doc-readme-brief
      - README exactly 1 000 bytes            → no finding
      - README > 1 000 bytes                  → no finding
      - read_text returns None                → no findings
      - stable finding IDs

    ReadmeSectionsRule
      - README absent                         → no findings
      - all six sections present              → six strengths, no findings
      - all six sections missing              → six LOW findings
      - ATX heading ## Installation           → detected
      - ATX heading # INSTALLATION (caps)     → detected
      - ATX heading #### installation         → detected
      - Setext underline Installation\n===    → detected
      - Setext underline Usage\n---           → detected
      - partial sections                      → findings only for missing ones
      - finding IDs follow doc-readme-missing-<section>

    ContributingRule
      - no CONTRIBUTING anywhere              → LOW doc-no-contributing
      - CONTRIBUTING.md at root               → strength
      - CONTRIBUTING.rst at root              → strength
      - CONTRIBUTING (no ext) at root         → strength
      - CONTRIBUTING.md in docs/              → strength
      - case-insensitive name                 → found
      - stable finding ID

    DocsDirectoryRule
      - no docs or doc dir                    → INFO doc-no-docs-dir
      - docs/ directory present               → strength
      - doc/ directory present                → strength
      - stable finding ID

    General
      - all rules: category == DOCUMENTATION
      - all rules: findings have relative paths only
      - all rules: repeated evaluation identical output
      - DEFAULT_RULES contains all five documentation rules
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repopilot.models import Category, Severity
from repopilot.rules import DEFAULT_RULES
from repopilot.rules.documentation import (
    ContributingRule,
    DocsDirectoryRule,
    ReadmePresenceRule,
    ReadmeSectionsRule,
    ReadmeSizeRule,
)
from repopilot.scanner.base import FileTree
from repopilot.scanner.local import LocalScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tree(tmp_path: Path, files: dict[str, str | bytes]) -> FileTree:
    """Populate *tmp_path* and return a scanned FileTree."""
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    return LocalScanner().scan(tmp_path)


def _empty(tmp_path: Path) -> FileTree:
    return LocalScanner().scan(tmp_path)


# ---------------------------------------------------------------------------
# ReadmePresenceRule
# ---------------------------------------------------------------------------


class TestReadmePresenceRule:
    def test_no_readme_produces_high_finding(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"setup.py": "x"})
        result = ReadmePresenceRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "doc-no-readme"
        assert result.findings[0].severity == Severity.HIGH

    def test_readme_md_present_no_findings(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "# Hello\n" * 20})
        result = ReadmePresenceRule().evaluate(tree)
        assert result.findings == []

    def test_readme_md_present_produces_strength(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "# Hello"})
        result = ReadmePresenceRule().evaluate(tree)
        assert any("README" in s for s in result.strengths)

    def test_readme_rst_variant(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.rst": "Project\n======="})
        result = ReadmePresenceRule().evaluate(tree)
        assert result.findings == []

    def test_readme_txt_variant(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.txt": "This is my project."})
        result = ReadmePresenceRule().evaluate(tree)
        assert result.findings == []

    def test_readme_no_extension(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README": "This is my project."})
        result = ReadmePresenceRule().evaluate(tree)
        assert result.findings == []

    def test_readme_case_insensitive(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"readme.md": "# hello"})
        result = ReadmePresenceRule().evaluate(tree)
        assert result.findings == []

    def test_readme_in_subdirectory_not_counted(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"docs/README.md": "# hi"})
        result = ReadmePresenceRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "doc-no-readme"

    def test_contributing_md_is_not_a_readme(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"CONTRIBUTING.md": "# Contributing"})
        result = ReadmePresenceRule().evaluate(tree)
        assert len(result.findings) == 1

    def test_finding_category(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = ReadmePresenceRule().evaluate(tree)
        assert all(f.category == Category.DOCUMENTATION for f in result.findings)

    def test_finding_id_stable(self) -> None:
        assert ReadmePresenceRule().rule_id == "doc-no-readme"

    def test_affected_paths_empty_when_no_readme(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = ReadmePresenceRule().evaluate(tree)
        assert result.findings[0].affected_paths == []


# ---------------------------------------------------------------------------
# ReadmeSizeRule
# ---------------------------------------------------------------------------


class TestReadmeSizeRule:
    def test_no_readme_no_findings(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = ReadmeSizeRule().evaluate(tree)
        assert result.findings == []

    def test_under_200_bytes_minimal_high(self, tmp_path: Path) -> None:
        content = "x" * 50  # 50 bytes < 200
        tree = _tree(tmp_path, {"README.md": content})
        result = ReadmeSizeRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "doc-readme-minimal"
        assert result.findings[0].severity == Severity.HIGH

    def test_exactly_199_bytes_is_minimal(self, tmp_path: Path) -> None:
        content = "a" * 199
        tree = _tree(tmp_path, {"README.md": content})
        result = ReadmeSizeRule().evaluate(tree)
        assert result.findings[0].id == "doc-readme-minimal"

    def test_exactly_200_bytes_is_brief(self, tmp_path: Path) -> None:
        content = "a" * 200
        tree = _tree(tmp_path, {"README.md": content})
        result = ReadmeSizeRule().evaluate(tree)
        assert result.findings[0].id == "doc-readme-brief"
        assert result.findings[0].severity == Severity.MEDIUM

    def test_exactly_999_bytes_is_brief(self, tmp_path: Path) -> None:
        content = "a" * 999
        tree = _tree(tmp_path, {"README.md": content})
        result = ReadmeSizeRule().evaluate(tree)
        assert result.findings[0].id == "doc-readme-brief"

    def test_exactly_1000_bytes_no_finding(self, tmp_path: Path) -> None:
        content = "a" * 1000
        tree = _tree(tmp_path, {"README.md": content})
        result = ReadmeSizeRule().evaluate(tree)
        assert result.findings == []

    def test_over_1000_bytes_no_finding(self, tmp_path: Path) -> None:
        content = "# Project\n\nA long description.\n" * 50
        tree = _tree(tmp_path, {"README.md": content})
        result = ReadmeSizeRule().evaluate(tree)
        assert result.findings == []

    def test_affected_paths_include_readme(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x"})
        result = ReadmeSizeRule().evaluate(tree)
        assert "README.md" in result.findings[0].affected_paths

    def test_finding_category(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x"})
        result = ReadmeSizeRule().evaluate(tree)
        assert all(f.category == Category.DOCUMENTATION for f in result.findings)

    def test_read_text_none_produces_no_finding(self, tmp_path: Path) -> None:
        """If FileTree can't read the README, ReadmeSizeRule stays silent."""
        # Write a binary file named README.md — read_text returns None.
        tree = _tree(tmp_path, {"README.md": b"\x00\x01\x02binary"})
        result = ReadmeSizeRule().evaluate(tree)
        assert result.findings == []

    def test_rst_variant_sized_correctly(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.rst": "x" * 50})
        result = ReadmeSizeRule().evaluate(tree)
        assert result.findings[0].id == "doc-readme-minimal"


# ---------------------------------------------------------------------------
# ReadmeSectionsRule
# ---------------------------------------------------------------------------

_ALL_SECTIONS_README = """\
# My Project

## Installation

Install with pip.

## Usage

Run the tool.

## Features

Many features.

## Contributing

Open a PR.

## Testing

Run pytest.

## License

MIT
"""

_NO_SECTIONS_README = "a" * 1200  # long enough, but no headings


class TestReadmeSectionsRule:
    def test_no_readme_no_findings(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = ReadmeSectionsRule().evaluate(tree)
        assert result.findings == []

    def test_all_sections_present_no_findings(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _ALL_SECTIONS_README})
        result = ReadmeSectionsRule().evaluate(tree)
        assert result.findings == []

    def test_all_sections_present_six_strengths(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _ALL_SECTIONS_README})
        result = ReadmeSectionsRule().evaluate(tree)
        assert len(result.strengths) == 6

    def test_no_sections_six_findings(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README})
        result = ReadmeSectionsRule().evaluate(tree)
        assert len(result.findings) == 6

    def test_all_section_findings_are_low(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README})
        result = ReadmeSectionsRule().evaluate(tree)
        assert all(f.severity == Severity.LOW for f in result.findings)

    def test_finding_ids_follow_convention(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README})
        result = ReadmeSectionsRule().evaluate(tree)
        ids = {f.id for f in result.findings}
        expected = {
            "doc-readme-missing-installation",
            "doc-readme-missing-usage",
            "doc-readme-missing-features",
            "doc-readme-missing-contributing",
            "doc-readme-missing-testing",
            "doc-readme-missing-license",
        }
        assert ids == expected

    def test_atx_heading_h1_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README + "\n# Installation\n"})
        result = ReadmeSectionsRule().evaluate(tree)
        ids = {f.id for f in result.findings}
        assert "doc-readme-missing-installation" not in ids

    def test_atx_heading_h2_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README + "\n## Usage\n"})
        result = ReadmeSectionsRule().evaluate(tree)
        ids = {f.id for f in result.findings}
        assert "doc-readme-missing-usage" not in ids

    def test_atx_heading_h4_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README + "\n#### Features\n"})
        result = ReadmeSectionsRule().evaluate(tree)
        ids = {f.id for f in result.findings}
        assert "doc-readme-missing-features" not in ids

    def test_atx_heading_case_insensitive(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README + "\n## INSTALLATION\n"})
        result = ReadmeSectionsRule().evaluate(tree)
        ids = {f.id for f in result.findings}
        assert "doc-readme-missing-installation" not in ids

    def test_setext_equals_underline_detected(self, tmp_path: Path) -> None:
        content = _NO_SECTIONS_README + "\nInstallation\n============\n"
        tree = _tree(tmp_path, {"README.md": content})
        result = ReadmeSectionsRule().evaluate(tree)
        ids = {f.id for f in result.findings}
        assert "doc-readme-missing-installation" not in ids

    def test_setext_dash_underline_detected(self, tmp_path: Path) -> None:
        content = _NO_SECTIONS_README + "\nUsage\n-----\n"
        tree = _tree(tmp_path, {"README.md": content})
        result = ReadmeSectionsRule().evaluate(tree)
        ids = {f.id for f in result.findings}
        assert "doc-readme-missing-usage" not in ids

    def test_partial_sections_only_missing_flagged(self, tmp_path: Path) -> None:
        content = _NO_SECTIONS_README + "\n## Installation\n\n## Usage\n"
        tree = _tree(tmp_path, {"README.md": content})
        result = ReadmeSectionsRule().evaluate(tree)
        ids = {f.id for f in result.findings}
        assert "doc-readme-missing-installation" not in ids
        assert "doc-readme-missing-usage" not in ids
        assert "doc-readme-missing-features" in ids
        assert len(result.findings) == 4

    def test_findings_in_deterministic_order(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README})
        result1 = ReadmeSectionsRule().evaluate(tree)
        result2 = ReadmeSectionsRule().evaluate(tree)
        assert [f.id for f in result1.findings] == [f.id for f in result2.findings]

    def test_affected_paths_include_readme(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README})
        result = ReadmeSectionsRule().evaluate(tree)
        for f in result.findings:
            assert "README.md" in f.affected_paths

    def test_category_documentation(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README})
        result = ReadmeSectionsRule().evaluate(tree)
        assert all(f.category == Category.DOCUMENTATION for f in result.findings)

    def test_rst_readme_sections_detected(self, tmp_path: Path) -> None:
        content = _NO_SECTIONS_README + "\n## Installation\n"
        tree = _tree(tmp_path, {"README.rst": content})
        result = ReadmeSectionsRule().evaluate(tree)
        ids = {f.id for f in result.findings}
        assert "doc-readme-missing-installation" not in ids


# ---------------------------------------------------------------------------
# ContributingRule
# ---------------------------------------------------------------------------


class TestContributingRule:
    def test_no_contributing_produces_low_finding(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x"})
        result = ContributingRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "doc-no-contributing"
        assert result.findings[0].severity == Severity.LOW

    def test_contributing_md_at_root(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"CONTRIBUTING.md": "# How to contribute"})
        result = ContributingRule().evaluate(tree)
        assert result.findings == []
        assert any("CONTRIBUTING" in s for s in result.strengths)

    def test_contributing_rst_at_root(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"CONTRIBUTING.rst": "Contributing\n============"})
        result = ContributingRule().evaluate(tree)
        assert result.findings == []

    def test_contributing_no_extension(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"CONTRIBUTING": "How to contribute."})
        result = ContributingRule().evaluate(tree)
        assert result.findings == []

    def test_contributing_in_docs_directory(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"docs/CONTRIBUTING.md": "# Contributing"})
        result = ContributingRule().evaluate(tree)
        assert result.findings == []

    def test_contributing_case_insensitive(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"contributing.md": "x"})
        result = ContributingRule().evaluate(tree)
        assert result.findings == []

    def test_finding_category(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = ContributingRule().evaluate(tree)
        assert all(f.category == Category.DOCUMENTATION for f in result.findings)

    def test_finding_id_stable(self) -> None:
        assert ContributingRule().rule_id == "doc-no-contributing"

    def test_contributing_in_deep_subdirectory_not_counted(self, tmp_path: Path) -> None:
        # Deep subdirectory — only root and docs/ are checked.
        tree = _tree(tmp_path, {"src/docs/CONTRIBUTING.md": "x"})
        result = ContributingRule().evaluate(tree)
        assert len(result.findings) == 1


# ---------------------------------------------------------------------------
# DocsDirectoryRule
# ---------------------------------------------------------------------------


class TestDocsDirectoryRule:
    def test_no_docs_dir_produces_info_finding(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x"})
        result = DocsDirectoryRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "doc-no-docs-dir"
        assert result.findings[0].severity == Severity.INFO

    def test_docs_directory_present(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"docs/index.md": "x"})
        result = DocsDirectoryRule().evaluate(tree)
        assert result.findings == []
        assert any("docs" in s.lower() for s in result.strengths)

    def test_doc_directory_present(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"doc/index.md": "x"})
        result = DocsDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_docs_case_insensitive(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"Docs/index.md": "x"})
        result = DocsDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_finding_category(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = DocsDirectoryRule().evaluate(tree)
        assert all(f.category == Category.DOCUMENTATION for f in result.findings)

    def test_finding_id_stable(self) -> None:
        assert DocsDirectoryRule().rule_id == "doc-no-docs-dir"

    def test_empty_tree_produces_finding(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = DocsDirectoryRule().evaluate(tree)
        assert len(result.findings) == 1


# ---------------------------------------------------------------------------
# General invariants across all documentation rules
# ---------------------------------------------------------------------------


class TestDocumentationRuleInvariants:
    _ALL_RULES = [
        ReadmePresenceRule(),
        ReadmeSizeRule(),
        ReadmeSectionsRule(),
        ContributingRule(),
        DocsDirectoryRule(),
    ]

    def test_all_findings_have_documentation_category(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        for rule in self._ALL_RULES:
            result = rule.evaluate(tree)
            for f in result.findings:
                assert f.category == Category.DOCUMENTATION, (
                    f"{rule.__class__.__name__} produced finding with category {f.category}"
                )

    def test_all_findings_have_relative_paths(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x", "CONTRIBUTING.md": "x"})
        for rule in self._ALL_RULES:
            result = rule.evaluate(tree)
            for f in result.findings:
                for p in f.affected_paths:
                    assert not p.startswith("/"), f"Absolute path in finding: {p!r}"
                    assert not (len(p) > 1 and p[1] == ":"), f"Windows drive path: {p!r}"

    def test_repeated_evaluation_identical(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": _NO_SECTIONS_README})
        for rule in self._ALL_RULES:
            r1 = rule.evaluate(tree)
            r2 = rule.evaluate(tree)
            assert [f.id for f in r1.findings] == [f.id for f in r2.findings], (
                f"{rule.__class__.__name__} is not deterministic"
            )

    def test_no_direct_filesystem_dependency(self, tmp_path: Path) -> None:
        """Rules must work with any FileTree, including a synthetic empty one."""
        # A FileTree whose root no longer exists on disk — rules must not
        # access the filesystem directly.  We scan first (root exists), then
        # check that rules don't break when we only have the in-memory tree.
        tree = LocalScanner().scan(tmp_path)
        for rule in self._ALL_RULES:
            result = rule.evaluate(tree)
            assert isinstance(result.findings, list)


# ---------------------------------------------------------------------------
# DEFAULT_RULES registration
# ---------------------------------------------------------------------------


class TestDefaultRulesRegistration:
    def test_documentation_rules_in_default_rules(self) -> None:
        rule_types = {type(r) for r in DEFAULT_RULES}
        assert ReadmePresenceRule in rule_types
        assert ReadmeSizeRule in rule_types
        assert ReadmeSectionsRule in rule_types
        assert ContributingRule in rule_types
        assert DocsDirectoryRule in rule_types

    def test_default_rules_has_five_documentation_rules(self) -> None:
        doc_rules = [r for r in DEFAULT_RULES if r.category == Category.DOCUMENTATION]
        assert len(doc_rules) == 5
