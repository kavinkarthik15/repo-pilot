"""Unit tests for Task 1.1: FileTree and LocalScanner.

Covers:
- Normal repository traversal
- Deterministic (sorted) ordering
- Relative paths use forward slashes
- Missing repository path raises ScanError
- File path (not directory) raises ScanError
- Excluded / generated directories recorded but not traversed
- Empty repository (no files)
- has_file — case-insensitive and case-sensitive
- find_files — glob matching
- find_dirs — by name
- root_files — depth-1 only
- read_text — happy path
- read_text — secret-file patterns never return content
- read_text — binary file returns None
- read_text — capped at 1 MB
- read_text — missing file returns None
- Symlink escaping repository root is not descended into
- Path traversal via symlink does not expose external content
- _is_secret_path helper covers all documented patterns
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from repopilot.exceptions import ScanError
from repopilot.scanner.base import (
    FileEntry,
    FileTree,
    _is_secret_path,
)
from repopilot.scanner.local import EXCLUDED_DIRS, LocalScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _symlinks_supported() -> bool:
    """Check whether the current process can create symlinks."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "src.txt"
        src.write_text("x")
        dst = Path(td) / "link"
        try:
            dst.symlink_to(src)
            return True
        except (OSError, NotImplementedError):
            return False


def _make_tree(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    """Create a directory tree from a dict of relative-path → content.

    If a value is bytes it is written as binary; str values are written as
    UTF-8 text.  Directories are created automatically.
    """
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# _is_secret_path
# ---------------------------------------------------------------------------


class TestIsSecretPath:
    def test_dot_env(self) -> None:
        assert _is_secret_path(".env")

    def test_dot_env_nested(self) -> None:
        assert _is_secret_path("config/.env")

    def test_dot_env_variant(self) -> None:
        assert _is_secret_path(".env.production")

    def test_dot_env_variant_nested(self) -> None:
        assert _is_secret_path("deploy/.env.local")

    def test_pem_file(self) -> None:
        assert _is_secret_path("server.pem")

    def test_key_file(self) -> None:
        assert _is_secret_path("private.key")

    def test_id_rsa(self) -> None:
        assert _is_secret_path("id_rsa")

    def test_id_dsa(self) -> None:
        assert _is_secret_path("id_dsa")

    def test_id_ed25519(self) -> None:
        assert _is_secret_path("id_ed25519")

    def test_credentials_json(self) -> None:
        assert _is_secret_path("credentials.json")

    def test_secrets_yml(self) -> None:
        assert _is_secret_path("secrets.yml")

    def test_secrets_yaml(self) -> None:
        assert _is_secret_path("secrets.yaml")

    def test_credentials_plain(self) -> None:
        assert _is_secret_path("credentials")

    def test_case_insensitive(self) -> None:
        assert _is_secret_path("ID_RSA")
        assert _is_secret_path("Server.PEM")

    def test_normal_python_file(self) -> None:
        assert not _is_secret_path("src/main.py")

    def test_normal_readme(self) -> None:
        assert not _is_secret_path("README.md")

    def test_requirements_txt(self) -> None:
        assert not _is_secret_path("requirements.txt")

    def test_env_example_not_secret(self) -> None:
        # .env.example should NOT be secret (it's a template)
        # Our pattern *.env covers .env.example via fnmatch("env.example","*.env")=False
        # Let's verify the basename logic:
        assert not _is_secret_path(".env.example")

    def test_env_sample_not_secret(self) -> None:
        assert not _is_secret_path(".env.sample")


# ---------------------------------------------------------------------------
# FileTree — construction and queries
# ---------------------------------------------------------------------------


class TestFileTreeQueries:
    def test_entries_are_sorted(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"b.py": "", "a.py": "", "c.py": ""})
        tree = LocalScanner().scan(tmp_path)
        relatives = [e.relative for e in tree.entries]
        assert relatives == sorted(relatives)

    def test_relative_paths_use_forward_slashes(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"src/main.py": "", "tests/test_main.py": ""})
        tree = LocalScanner().scan(tmp_path)
        for entry in tree.entries:
            assert "\\" not in entry.relative, (
                f"Backslash in relative path: {entry.relative!r}"
            )

    def test_no_absolute_paths_in_relative(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"src/app.py": "x"})
        tree = LocalScanner().scan(tmp_path)
        for entry in tree.entries:
            assert not entry.relative.startswith("/")
            assert not (len(entry.relative) > 1 and entry.relative[1] == ":")

    def test_size_bytes_recorded(self, tmp_path: Path) -> None:
        content = "hello world"
        _make_tree(tmp_path, {"readme.txt": content})
        tree = LocalScanner().scan(tmp_path)
        file_entry = next(e for e in tree.entries if e.relative == "readme.txt")
        assert file_entry.size_bytes == len(content.encode())

    def test_directory_entry_has_size_zero(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"src/main.py": "x"})
        tree = LocalScanner().scan(tmp_path)
        dir_entry = next(e for e in tree.entries if e.is_dir and e.relative == "src")
        assert dir_entry.size_bytes == 0

    def test_has_file_present_case_insensitive(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"README.md": "# hi"})
        tree = LocalScanner().scan(tmp_path)
        assert tree.has_file("readme.md")
        assert tree.has_file("README.MD")
        assert tree.has_file("README.md")

    def test_has_file_absent(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"setup.py": ""})
        tree = LocalScanner().scan(tmp_path)
        assert not tree.has_file("README.md")

    def test_has_file_case_sensitive(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"README.md": "x"})
        tree = LocalScanner().scan(tmp_path)
        assert tree.has_file("README.md", case_insensitive=False)
        assert not tree.has_file("readme.md", case_insensitive=False)

    def test_has_file_does_not_match_directory(self, tmp_path: Path) -> None:
        # Create a *directory* called 'docs', not a file.
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "index.md").write_text("x")
        tree = LocalScanner().scan(tmp_path)
        assert not tree.has_file("docs")

    def test_find_files_glob(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {
            "tests/test_a.py": "",
            "tests/test_b.py": "",
            "src/main.py": "",
        })
        tree = LocalScanner().scan(tmp_path)
        found = tree.find_files("tests/test_*.py")
        relatives = {e.relative for e in found}
        assert "tests/test_a.py" in relatives
        assert "tests/test_b.py" in relatives
        assert "src/main.py" not in relatives

    def test_find_files_excludes_dirs(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"src/main.py": ""})
        tree = LocalScanner().scan(tmp_path)
        # "src" is a directory — find_files must not return it even if name matches.
        dirs_returned = [e for e in tree.find_files("src") if e.is_dir]
        assert dirs_returned == []

    def test_find_dirs_by_name(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"docs/index.md": "", "src/main.py": ""})
        tree = LocalScanner().scan(tmp_path)
        found = tree.find_dirs("docs")
        assert len(found) == 1
        assert found[0].is_dir

    def test_find_dirs_absent(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"src/main.py": ""})
        tree = LocalScanner().scan(tmp_path)
        assert tree.find_dirs("docs") == []

    def test_find_dirs_case_insensitive(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"Docs/index.md": ""})
        tree = LocalScanner().scan(tmp_path)
        assert tree.find_dirs("docs")

    def test_root_files_depth_one_only(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {
            "README.md": "x",
            "setup.py": "x",
            "src/main.py": "x",
            "tests/test_main.py": "x",
        })
        tree = LocalScanner().scan(tmp_path)
        root_items = tree.root_files()
        root_relatives = {e.relative for e in root_items}
        assert "README.md" in root_relatives
        assert "setup.py" in root_relatives
        assert "src" in root_relatives        # directory at root
        assert "tests" in root_relatives      # directory at root
        assert "src/main.py" not in root_relatives
        assert "tests/test_main.py" not in root_relatives


# ---------------------------------------------------------------------------
# LocalScanner — error handling
# ---------------------------------------------------------------------------


class TestLocalScannerErrors:
    def test_missing_path_raises_scan_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist"
        with pytest.raises(ScanError):
            LocalScanner().scan(missing)

    def test_file_path_raises_scan_error(self, tmp_path: Path) -> None:
        f = tmp_path / "somefile.txt"
        f.write_text("hello")
        with pytest.raises(ScanError):
            LocalScanner().scan(f)

    def test_scan_error_is_descriptive(self, tmp_path: Path) -> None:
        missing = tmp_path / "ghost"
        with pytest.raises(ScanError, match="does not exist"):
            LocalScanner().scan(missing)


# ---------------------------------------------------------------------------
# LocalScanner — normal traversal
# ---------------------------------------------------------------------------


class TestLocalScannerTraversal:
    def test_empty_repository(self, tmp_path: Path) -> None:
        tree = LocalScanner().scan(tmp_path)
        assert len(tree) == 0

    def test_flat_files_recorded(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"a.py": "x", "b.py": "x", ".gitignore": "x"})
        tree = LocalScanner().scan(tmp_path)
        relatives = {e.relative for e in tree.entries}
        assert "a.py" in relatives
        assert "b.py" in relatives
        assert ".gitignore" in relatives

    def test_nested_files_recorded(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {
            "src/repopilot/__init__.py": "",
            "src/repopilot/models.py": "",
        })
        tree = LocalScanner().scan(tmp_path)
        relatives = {e.relative for e in tree.entries}
        assert "src/repopilot/__init__.py" in relatives
        assert "src/repopilot/models.py" in relatives

    def test_both_file_and_dir_entries_recorded(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"src/main.py": "x"})
        tree = LocalScanner().scan(tmp_path)
        relatives = {e.relative for e in tree.entries}
        # Both the directory and the file must be present.
        assert "src" in relatives
        assert "src/main.py" in relatives

    def test_deterministic_on_repeated_scans(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"z.py": "", "a.py": "", "m.py": ""})
        scanner = LocalScanner()
        tree1 = scanner.scan(tmp_path)
        tree2 = scanner.scan(tmp_path)
        assert [e.relative for e in tree1.entries] == [e.relative for e in tree2.entries]


# ---------------------------------------------------------------------------
# LocalScanner — excluded directories
# ---------------------------------------------------------------------------


class TestExcludedDirectories:
    def test_excluded_dir_recorded_not_traversed(self, tmp_path: Path) -> None:
        # Create node_modules with a deeply nested file.
        (tmp_path / "node_modules" / "lodash").mkdir(parents=True)
        (tmp_path / "node_modules" / "lodash" / "index.js").write_text("x")
        (tmp_path / "README.md").write_text("# hi")

        tree = LocalScanner().scan(tmp_path)
        relatives = {e.relative for e in tree.entries}

        # The directory entry itself must be present.
        assert "node_modules" in relatives
        # But its contents must NOT be traversed.
        assert "node_modules/lodash" not in relatives
        assert "node_modules/lodash/index.js" not in relatives

    def test_git_dir_recorded_not_traversed(self, tmp_path: Path) -> None:
        (tmp_path / ".git" / "objects").mkdir(parents=True)
        (tmp_path / ".git" / "objects" / "pack").write_text("x")
        (tmp_path / "README.md").write_text("x")

        tree = LocalScanner().scan(tmp_path)
        relatives = {e.relative for e in tree.entries}

        assert ".git" in relatives
        assert ".git/objects" not in relatives

    def test_venv_recorded_not_traversed(self, tmp_path: Path) -> None:
        (tmp_path / ".venv" / "lib" / "python3.13").mkdir(parents=True)
        (tmp_path / ".venv" / "lib" / "python3.13" / "os.py").write_text("x")
        (tmp_path / "main.py").write_text("x")

        tree = LocalScanner().scan(tmp_path)
        relatives = {e.relative for e in tree.entries}

        assert ".venv" in relatives
        assert ".venv/lib" not in relatives

    def test_pycache_recorded_not_traversed(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__pycache__").mkdir()
        (tmp_path / "src" / "__pycache__" / "models.cpython-313.pyc").write_text("x")
        (tmp_path / "src" / "models.py").write_text("x")

        tree = LocalScanner().scan(tmp_path)
        relatives = {e.relative for e in tree.entries}

        assert "src/__pycache__" in relatives
        assert "src/__pycache__/models.cpython-313.pyc" not in relatives

    def test_all_excluded_dirs_in_constant(self) -> None:
        """Spot-check that the required dirs are in EXCLUDED_DIRS."""
        required = {
            ".git", "node_modules", "__pycache__", ".venv", "venv",
            "env", "dist", "build", ".tox",
        }
        assert required.issubset(EXCLUDED_DIRS)


# ---------------------------------------------------------------------------
# read_text — content guarding
# ---------------------------------------------------------------------------


class TestReadText:
    def test_reads_normal_text_file(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"README.md": "# Hello"})
        tree = LocalScanner().scan(tmp_path)
        content = tree.read_text("README.md")
        assert content == "# Hello"

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        tree = LocalScanner().scan(tmp_path)
        assert tree.read_text("nonexistent.md") is None

    def test_returns_none_for_directory(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"src/main.py": "x"})
        tree = LocalScanner().scan(tmp_path)
        assert tree.read_text("src") is None

    def test_returns_none_for_binary_file(self, tmp_path: Path) -> None:
        # Write a file with null bytes.
        binary_content = b"\x00\x01\x02\x03" * 100
        _make_tree(tmp_path, {"data.bin": binary_content})
        tree = LocalScanner().scan(tmp_path)
        assert tree.read_text("data.bin") is None

    def test_caps_at_1mb(self, tmp_path: Path) -> None:
        big_content = "x" * (1024 * 1024 + 500)
        _make_tree(tmp_path, {"big.txt": big_content})
        tree = LocalScanner().scan(tmp_path)
        result = tree.read_text("big.txt")
        assert result is not None
        assert len(result) == 1024 * 1024

    def test_secret_dot_env_returns_none(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {".env": "SECRET=password123"})
        tree = LocalScanner().scan(tmp_path)
        assert tree.read_text(".env") is None

    def test_secret_pem_returns_none(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"server.pem": "-----BEGIN CERTIFICATE-----"})
        tree = LocalScanner().scan(tmp_path)
        assert tree.read_text("server.pem") is None

    def test_secret_key_returns_none(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"private.key": "-----BEGIN RSA PRIVATE KEY-----"})
        tree = LocalScanner().scan(tmp_path)
        assert tree.read_text("private.key") is None

    def test_secret_id_rsa_returns_none(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"id_rsa": "ssh-rsa AAAA..."})
        tree = LocalScanner().scan(tmp_path)
        assert tree.read_text("id_rsa") is None

    def test_secret_credentials_json_returns_none(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"credentials.json": '{"token": "abc"}'})
        tree = LocalScanner().scan(tmp_path)
        assert tree.read_text("credentials.json") is None

    def test_nested_secret_returns_none(self, tmp_path: Path) -> None:
        _make_tree(tmp_path, {"config/.env": "DB_PASS=secret"})
        tree = LocalScanner().scan(tmp_path)
        assert tree.read_text("config/.env") is None

    def test_env_example_is_readable(self, tmp_path: Path) -> None:
        """Template env files (.env.example, .env.sample) may be read."""
        _make_tree(tmp_path, {".env.example": "SECRET=changeme"})
        tree = LocalScanner().scan(tmp_path)
        # .env.example is a template — it should be readable.
        result = tree.read_text(".env.example")
        assert result == "SECRET=changeme"

    def test_accepts_backslash_separator(self, tmp_path: Path) -> None:
        """read_text must work with Windows-style separators as input."""
        _make_tree(tmp_path, {"src/main.py": "# code"})
        tree = LocalScanner().scan(tmp_path)
        # Pass with backslash; should normalise internally.
        result = tree.read_text("src\\main.py")
        assert result == "# code"


# ---------------------------------------------------------------------------
# Symlink safety
# ---------------------------------------------------------------------------


class TestSymlinkSafety:
    @pytest.mark.skipif(
        sys.platform == "win32" and not _symlinks_supported(),
        reason="Symlinks require elevated privileges or Developer Mode on Windows",
    )
    def test_symlink_escaping_root_not_traversed(
        self, tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """A symlink pointing outside the repo root must not be descended."""
        outside = tmp_path_factory.mktemp("outside")
        (outside / "secret.txt").write_text("top secret")

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("# hi")

        # Create symlink inside repo pointing to outside directory.
        link = repo / "escape_link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symlinks in this environment")

        tree = LocalScanner().scan(repo)
        relatives = {e.relative for e in tree.entries}

        # The symlink entry itself may or may not be recorded
        # (it resolves outside root so it depends on OS behaviour),
        # but the *contents* must never appear.
        assert "escape_link/secret.txt" not in relatives

    @pytest.mark.skipif(
        sys.platform == "win32" and not _symlinks_supported(),
        reason="Symlinks require elevated privileges or Developer Mode on Windows",
    )
    def test_read_text_refuses_symlink_escaping_root(
        self, tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """read_text must return None for a file whose resolved path escapes root."""
        outside = tmp_path_factory.mktemp("outside2")
        secret_file = outside / "external.txt"
        secret_file.write_text("external content")

        repo = tmp_path / "repo2"
        repo.mkdir()

        link = repo / "external_link.txt"
        try:
            link.symlink_to(secret_file)
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symlinks in this environment")

        tree = LocalScanner().scan(repo)
        result = tree.read_text("external_link.txt")
        assert result is None
