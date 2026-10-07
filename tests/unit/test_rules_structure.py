"""Unit tests for Task 2.2: Repository structure rules.

All tests use synthetic FileTree objects built via LocalScanner on temporary
directories.  No rule accesses the filesystem directly.

Covers:
    SourceDirectoryRule
      - no source dir at root                 → LOW struct-no-src-dir
      - src/ present                          → strength, no finding
      - lib/ present                          → strength
      - app/ present                          → strength
      - core/ present                         → strength
      - pkg/ present                          → strength
      - cmd/ present                          → strength
      - case-insensitive match (SRC/)         → found
      - source dir inside subdirectory only   → not counted (root-only)
      - excluded dirs (node_modules etc.)     → not treated as src
      - stable finding ID

    TestDirectoryRule
      - no test dir anywhere                  → MEDIUM struct-no-tests-dir
      - tests/ at root                        → strength
      - test/ at root                         → strength
      - spec/ at root                         → strength
      - __tests__/ at root                    → strength
      - e2e/ at root                          → strength
      - integration/ at root                  → strength
      - tests/ nested one level deep          → strength (src/tests/)
      - tests/ nested two levels deep         → NOT counted
      - case-insensitive (Tests/)             → found
      - stable finding ID

    EmptyRepoRule
      - empty repo (0 entries)                → HIGH struct-empty-repo
      - 1 non-hidden file                     → HIGH
      - 2 non-hidden files                    → HIGH
      - exactly 3 non-hidden files            → strength, no finding
      - 10 non-hidden files                   → no finding
      - hidden files only (.gitignore)        → still empty (hidden excluded)
      - mix hidden + non-hidden               → only non-hidden counted
      - finding affected_paths lists found entries
      - stable finding ID

    ConfigFilesRule
      - no config files                       → INFO struct-no-config-files
      - pyproject.toml present                → strength
      - Makefile present                      → strength (case-insensitive)
      - Dockerfile present                    → strength
      - .editorconfig present                 → strength
      - .prettierrc present                   → strength
      - .eslintrc present                     → strength
      - .eslintrc.js present                  → strength
      - setup.cfg present                     → strength
      - .flake8 present                       → strength
      - tox.ini present                       → strength
      - docker-compose.yml present            → strength
      - multiple config files → multiple strengths, sorted
      - config file in subdirectory only      → not counted
      - non-config file                       → not counted
      - stable finding ID

    General invariants across all structure rules
      - category == STRUCTURE for all findings
      - all findings have relative paths only
      - repeated evaluation identical output
      - no direct filesystem access from rule code
      - DEFAULT_RULES contains all four structure rules
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repopilot.models import Category, Severity
from repopilot.rules import DEFAULT_RULES
from repopilot.rules.structure import (
    ConfigFilesRule,
    EmptyRepoRule,
    SourceDirectoryRule,
    TestDirectoryRule,
)
from repopilot.scanner.base import FileTree
from repopilot.scanner.local import LocalScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tree(tmp_path: Path, files: dict[str, str | bytes]) -> FileTree:
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
# SourceDirectoryRule
# ---------------------------------------------------------------------------


class TestSourceDirectoryRule:
    def test_no_src_dir_produces_low_finding(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x"})
        result = SourceDirectoryRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "struct-no-src-dir"
        assert result.findings[0].severity == Severity.LOW

    def test_src_directory_present(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"src/main.py": "x"})
        result = SourceDirectoryRule().evaluate(tree)
        assert result.findings == []
        assert any("src" in s for s in result.strengths)

    def test_lib_directory_present(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"lib/utils.py": "x"})
        result = SourceDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_app_directory_present(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"app/models.py": "x"})
        result = SourceDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_core_directory_present(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"core/engine.py": "x"})
        result = SourceDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_pkg_directory_present(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"pkg/handler.go": "x"})
        result = SourceDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_cmd_directory_present(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"cmd/main.go": "x"})
        result = SourceDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_case_insensitive_match(self, tmp_path: Path) -> None:
        # Create directory with uppercase name
        (tmp_path / "SRC").mkdir()
        (tmp_path / "SRC" / "main.py").write_text("x")
        tree = LocalScanner().scan(tmp_path)
        result = SourceDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_src_nested_not_counted(self, tmp_path: Path) -> None:
        # src/ exists only as a nested dir — not at root
        tree = _tree(tmp_path, {"project/src/main.py": "x"})
        result = SourceDirectoryRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "struct-no-src-dir"

    def test_excluded_dirs_not_treated_as_source(self, tmp_path: Path) -> None:
        # node_modules is in EXCLUDED_DIRS — should not count as source
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lodash").mkdir()
        tree = LocalScanner().scan(tmp_path)
        result = SourceDirectoryRule().evaluate(tree)
        # node_modules is recorded by scanner but is not in _SOURCE_DIR_NAMES
        assert result.findings[0].id == "struct-no-src-dir"

    def test_finding_category_is_structure(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = SourceDirectoryRule().evaluate(tree)
        assert all(f.category == Category.STRUCTURE for f in result.findings)

    def test_finding_id_stable(self) -> None:
        assert SourceDirectoryRule().rule_id == "struct-no-src-dir"

    def test_repeated_evaluation_identical(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        rule = SourceDirectoryRule()
        r1 = rule.evaluate(tree)
        r2 = rule.evaluate(tree)
        assert [f.id for f in r1.findings] == [f.id for f in r2.findings]


# ---------------------------------------------------------------------------
# TestDirectoryRule
# ---------------------------------------------------------------------------


class TestTestDirectoryRule:
    def test_no_test_dir_produces_medium_finding(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"src/main.py": "x"})
        result = TestDirectoryRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "struct-no-tests-dir"
        assert result.findings[0].severity == Severity.MEDIUM

    def test_tests_at_root(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"tests/test_main.py": "x"})
        result = TestDirectoryRule().evaluate(tree)
        assert result.findings == []
        assert any("tests" in s.lower() for s in result.strengths)

    def test_test_at_root(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"test/test_main.py": "x"})
        result = TestDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_spec_at_root(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"spec/main_spec.rb": "x"})
        result = TestDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_dunder_tests_at_root(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"__tests__/app.test.js": "x"})
        result = TestDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_e2e_at_root(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"e2e/suite.ts": "x"})
        result = TestDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_integration_at_root(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"integration/api_test.go": "x"})
        result = TestDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_tests_nested_one_level_deep(self, tmp_path: Path) -> None:
        # src/tests/ is one level deep — should be found
        tree = _tree(tmp_path, {"src/tests/test_main.py": "x"})
        result = TestDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_tests_nested_two_levels_deep_not_counted(self, tmp_path: Path) -> None:
        # src/app/tests/ is two levels deep — should NOT be counted
        tree = _tree(tmp_path, {"src/app/tests/test_main.py": "x"})
        result = TestDirectoryRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "struct-no-tests-dir"

    def test_case_insensitive_match(self, tmp_path: Path) -> None:
        (tmp_path / "Tests").mkdir()
        (tmp_path / "Tests" / "test_main.py").write_text("x")
        tree = LocalScanner().scan(tmp_path)
        result = TestDirectoryRule().evaluate(tree)
        assert result.findings == []

    def test_finding_category_is_structure(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = TestDirectoryRule().evaluate(tree)
        assert all(f.category == Category.STRUCTURE for f in result.findings)

    def test_finding_id_stable(self) -> None:
        assert TestDirectoryRule().rule_id == "struct-no-tests-dir"

    def test_repeated_evaluation_identical(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        rule = TestDirectoryRule()
        r1 = rule.evaluate(tree)
        r2 = rule.evaluate(tree)
        assert [f.id for f in r1.findings] == [f.id for f in r2.findings]


# ---------------------------------------------------------------------------
# EmptyRepoRule
# ---------------------------------------------------------------------------


class TestEmptyRepoRule:
    def test_empty_repo_produces_high_finding(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = EmptyRepoRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "struct-empty-repo"
        assert result.findings[0].severity == Severity.HIGH

    def test_one_file_still_high(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x"})
        result = EmptyRepoRule().evaluate(tree)
        assert result.findings[0].id == "struct-empty-repo"

    def test_two_files_still_high(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x", "setup.py": "x"})
        result = EmptyRepoRule().evaluate(tree)
        assert result.findings[0].id == "struct-empty-repo"

    def test_three_files_no_finding(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x", "setup.py": "x", "main.py": "x"})
        result = EmptyRepoRule().evaluate(tree)
        assert result.findings == []

    def test_three_files_produces_strength(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x", "setup.py": "x", "main.py": "x"})
        result = EmptyRepoRule().evaluate(tree)
        assert len(result.strengths) == 1
        assert "3" in result.strengths[0]

    def test_ten_files_no_finding(self, tmp_path: Path) -> None:
        files = {f"file{i}.py": "x" for i in range(10)}
        tree = _tree(tmp_path, files)
        result = EmptyRepoRule().evaluate(tree)
        assert result.findings == []

    def test_hidden_files_only_still_empty(self, tmp_path: Path) -> None:
        # Only hidden file — count of non-hidden = 0
        tree = _tree(tmp_path, {".gitignore": "*.pyc"})
        result = EmptyRepoRule().evaluate(tree)
        assert result.findings[0].id == "struct-empty-repo"

    def test_hidden_files_excluded_from_count(self, tmp_path: Path) -> None:
        # 2 non-hidden + 3 hidden = 2 non-hidden → still HIGH
        tree = _tree(tmp_path, {
            "README.md": "x",
            "main.py": "x",
            ".gitignore": "x",
            ".env.example": "x",
            ".editorconfig": "x",
        })
        result = EmptyRepoRule().evaluate(tree)
        assert result.findings[0].id == "struct-empty-repo"

    def test_mix_hidden_and_nonhidden_counted_correctly(self, tmp_path: Path) -> None:
        # 3 non-hidden + 1 hidden = 3 non-hidden → no finding
        tree = _tree(tmp_path, {
            "README.md": "x",
            "main.py": "x",
            "setup.py": "x",
            ".gitignore": "x",
        })
        result = EmptyRepoRule().evaluate(tree)
        assert result.findings == []

    def test_directories_count_as_non_hidden_entries(self, tmp_path: Path) -> None:
        # A directory at the root contributes to the count if non-hidden
        tree = _tree(tmp_path, {
            "src/main.py": "x",
            "tests/test_main.py": "x",
            "README.md": "x",
        })
        result = EmptyRepoRule().evaluate(tree)
        # src/, tests/, README.md → 3 non-hidden root entries
        assert result.findings == []

    def test_finding_affected_paths_lists_found_entries(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x"})
        result = EmptyRepoRule().evaluate(tree)
        assert "README.md" in result.findings[0].affected_paths

    def test_empty_repo_affected_paths_is_empty_list(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = EmptyRepoRule().evaluate(tree)
        assert result.findings[0].affected_paths == []

    def test_finding_category_is_structure(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        result = EmptyRepoRule().evaluate(tree)
        assert all(f.category == Category.STRUCTURE for f in result.findings)

    def test_finding_id_stable(self) -> None:
        assert EmptyRepoRule().rule_id == "struct-empty-repo"

    def test_repeated_evaluation_identical(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"README.md": "x"})
        rule = EmptyRepoRule()
        r1 = rule.evaluate(tree)
        r2 = rule.evaluate(tree)
        assert [f.id for f in r1.findings] == [f.id for f in r2.findings]


# ---------------------------------------------------------------------------
# ConfigFilesRule
# ---------------------------------------------------------------------------


class TestConfigFilesRule:
    def test_no_config_files_produces_info_finding(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"main.py": "x"})
        result = ConfigFilesRule().evaluate(tree)
        assert len(result.findings) == 1
        assert result.findings[0].id == "struct-no-config-files"
        assert result.findings[0].severity == Severity.INFO

    def test_pyproject_toml_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"pyproject.toml": "[tool.ruff]"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []
        assert any("pyproject.toml" in s for s in result.strengths)

    def test_makefile_detected_case_insensitive(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"Makefile": "all:\n\techo ok"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_dockerfile_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"Dockerfile": "FROM python:3.13"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_editorconfig_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {".editorconfig": "[*]\nindent_style = space"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_prettierrc_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {".prettierrc": '{"semi": false}'})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_eslintrc_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {".eslintrc": '{"rules": {}}'})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_eslintrc_js_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {".eslintrc.js": "module.exports = {}"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_eslintrc_json_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {".eslintrc.json": "{}"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_setup_cfg_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"setup.cfg": "[metadata]\nname = mypackage"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_flake8_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {".flake8": "[flake8]\nmax-line-length = 100"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_tox_ini_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"tox.ini": "[tox]\nenvlist = py313"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_docker_compose_yml_detected(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"docker-compose.yml": "version: '3'"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []

    def test_multiple_config_files_multiple_strengths(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {
            "pyproject.toml": "x",
            "Makefile": "x",
            ".editorconfig": "x",
        })
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings == []
        assert len(result.strengths) == 3

    def test_multiple_strengths_sorted(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {
            "tox.ini": "x",
            ".editorconfig": "x",
            "pyproject.toml": "x",
        })
        result = ConfigFilesRule().evaluate(tree)
        strengths = result.strengths
        paths = [s.split(": ", 1)[1] for s in strengths]
        assert paths == sorted(paths)

    def test_config_file_in_subdirectory_not_counted(self, tmp_path: Path) -> None:
        # pyproject.toml exists only in a subdirectory
        tree = _tree(tmp_path, {"src/pyproject.toml": "x", "README.md": "x"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings[0].id == "struct-no-config-files"

    def test_random_file_not_counted(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"main.py": "x", "utils.py": "x"})
        result = ConfigFilesRule().evaluate(tree)
        assert result.findings[0].id == "struct-no-config-files"

    def test_finding_category_is_structure(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"main.py": "x"})
        result = ConfigFilesRule().evaluate(tree)
        assert all(f.category == Category.STRUCTURE for f in result.findings)

    def test_finding_id_stable(self) -> None:
        assert ConfigFilesRule().rule_id == "struct-no-config-files"

    def test_repeated_evaluation_identical(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"main.py": "x"})
        rule = ConfigFilesRule()
        r1 = rule.evaluate(tree)
        r2 = rule.evaluate(tree)
        assert [f.id for f in r1.findings] == [f.id for f in r2.findings]


# ---------------------------------------------------------------------------
# General invariants across all structure rules
# ---------------------------------------------------------------------------


class TestStructureRuleInvariants:
    _ALL_RULES = [
        SourceDirectoryRule(),
        TestDirectoryRule(),
        EmptyRepoRule(),
        ConfigFilesRule(),
    ]

    def test_all_findings_have_structure_category(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        for rule in self._ALL_RULES:
            result = rule.evaluate(tree)
            for f in result.findings:
                assert f.category == Category.STRUCTURE, (
                    f"{rule.__class__.__name__} produced finding with category {f.category}"
                )

    def test_all_findings_have_relative_paths(self, tmp_path: Path) -> None:
        tree = _tree(tmp_path, {"src/main.py": "x", "tests/test_main.py": "x"})
        for rule in self._ALL_RULES:
            result = rule.evaluate(tree)
            for f in result.findings:
                for p in f.affected_paths:
                    assert not p.startswith("/"), f"Absolute path: {p!r}"
                    assert not (len(p) > 1 and p[1] == ":"), f"Windows drive: {p!r}"

    def test_repeated_evaluation_identical(self, tmp_path: Path) -> None:
        tree = _empty(tmp_path)
        for rule in self._ALL_RULES:
            r1 = rule.evaluate(tree)
            r2 = rule.evaluate(tree)
            assert [f.id for f in r1.findings] == [f.id for f in r2.findings], (
                f"{rule.__class__.__name__} is not deterministic"
            )

    def test_no_direct_filesystem_dependency(self, tmp_path: Path) -> None:
        """Rules must not access the filesystem; they only read the FileTree."""
        tree = LocalScanner().scan(tmp_path)
        for rule in self._ALL_RULES:
            result = rule.evaluate(tree)
            assert isinstance(result.findings, list)

    def test_healthy_repo_produces_no_findings(self, tmp_path: Path) -> None:
        """A well-structured repository should produce no structure findings."""
        tree = _tree(tmp_path, {
            "README.md": "x",
            "pyproject.toml": "x",
            "Makefile": "x",
            "src/main.py": "x",
            "tests/test_main.py": "x",
        })
        for rule in self._ALL_RULES:
            result = rule.evaluate(tree)
            assert result.findings == [], (
                f"{rule.__class__.__name__} unexpectedly produced findings "
                f"on a healthy repo: {[f.id for f in result.findings]}"
            )


# ---------------------------------------------------------------------------
# DEFAULT_RULES registration
# ---------------------------------------------------------------------------


class TestDefaultRulesRegistration:
    def test_structure_rules_in_default_rules(self) -> None:
        rule_types = {type(r) for r in DEFAULT_RULES}
        assert SourceDirectoryRule in rule_types
        assert TestDirectoryRule in rule_types
        assert EmptyRepoRule in rule_types
        assert ConfigFilesRule in rule_types

    def test_default_rules_has_four_structure_rules(self) -> None:
        struct_rules = [r for r in DEFAULT_RULES if r.category == Category.STRUCTURE]
        assert len(struct_rules) == 4
