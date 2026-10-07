"""Unit tests for Task 1.2: GitCloneScanner.

All tests mock the git.Repo.clone_from boundary so no real network access
is required.  The temporary-directory lifecycle and URL-validation logic are
tested without touching GitHub.

Covers:
- _validate_url: valid HTTPS, malformed, unsupported schemes,
  file://, local paths (POSIX + Windows), empty string, domain-only
- GitCloneScanner.scan: orchestration (clone called, LocalScanner called)
- Shallow-clone option is passed through
- Temporary directory created before clone
- Cleanup after successful scan
- Cleanup after clone failure (GitCommandError)
- Cleanup after scanner failure (ScanError from LocalScanner)
- No tmpdir leak when clone is never attempted (validate fails)
- Context-manager protocol (__enter__ / __exit__)
- __del__ triggers cleanup
- Credentials in URL are stripped from error messages
- Returned FileTree originates from LocalScanner
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from repopilot.exceptions import InvalidSourceError, ScanError
from repopilot.scanner.git_clone import (
    GitCloneScanner,
    _sanitise_url,
    _validate_url,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_local_tree(tmp_path: Path) -> None:
    """Populate *tmp_path* with a minimal fake repository layout."""
    (tmp_path / "README.md").write_text("# fake")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("# fake")


# ---------------------------------------------------------------------------
# _sanitise_url
# ---------------------------------------------------------------------------


class TestSanitiseUrl:
    def test_removes_credentials(self) -> None:
        url = "https://user:secret@github.com/owner/repo.git"
        assert "secret" not in _sanitise_url(url)
        assert "user" not in _sanitise_url(url)

    def test_preserves_host_and_path(self) -> None:
        url = "https://github.com/owner/repo.git"
        sanitised = _sanitise_url(url)
        assert "github.com" in sanitised
        assert "owner/repo" in sanitised

    def test_plain_url_unchanged_in_structure(self) -> None:
        url = "https://github.com/owner/repo"
        sanitised = _sanitise_url(url)
        assert sanitised == url

    def test_does_not_raise_on_garbage(self) -> None:
        # Should return a placeholder rather than raise.
        result = _sanitise_url("")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _validate_url
# ---------------------------------------------------------------------------


class TestValidateUrl:
    # --- valid URLs ---

    def test_accepts_https_github_url(self) -> None:
        _validate_url("https://github.com/owner/repo.git")  # no exception

    def test_accepts_https_without_dot_git(self) -> None:
        _validate_url("https://github.com/owner/repo")

    def test_accepts_https_with_subdirectory(self) -> None:
        _validate_url("https://example.com/org/group/repo.git")

    # --- local paths ---

    def test_rejects_posix_absolute_path(self) -> None:
        with pytest.raises(InvalidSourceError, match="filesystem path"):
            _validate_url("/home/user/repo")

    def test_rejects_windows_absolute_path(self) -> None:
        with pytest.raises(InvalidSourceError, match="filesystem path"):
            _validate_url("C:\\Users\\user\\repo")

    def test_rejects_windows_absolute_path_forward_slash(self) -> None:
        with pytest.raises(InvalidSourceError, match="filesystem path"):
            _validate_url("C:/Users/user/repo")

    def test_rejects_relative_dot_slash(self) -> None:
        with pytest.raises(InvalidSourceError, match="filesystem path"):
            _validate_url("./my-repo")

    def test_rejects_relative_dotdot(self) -> None:
        with pytest.raises(InvalidSourceError, match="filesystem path"):
            _validate_url("../my-repo")

    # --- unsupported schemes ---

    def test_rejects_http(self) -> None:
        with pytest.raises(InvalidSourceError, match="[Uu]nsupported"):
            _validate_url("http://github.com/owner/repo")

    def test_rejects_file_scheme(self) -> None:
        with pytest.raises(InvalidSourceError, match="file"):
            _validate_url("file:///home/user/repo")

    def test_rejects_ssh_scheme(self) -> None:
        with pytest.raises(InvalidSourceError, match="[Uu]nsupported"):
            _validate_url("ssh://git@github.com/owner/repo.git")

    def test_rejects_git_scheme(self) -> None:
        with pytest.raises(InvalidSourceError, match="[Uu]nsupported"):
            _validate_url("git://github.com/owner/repo.git")

    def test_rejects_ftp_scheme(self) -> None:
        with pytest.raises(InvalidSourceError, match="[Uu]nsupported"):
            _validate_url("ftp://example.com/repo")

    def test_rejects_unknown_scheme(self) -> None:
        with pytest.raises(InvalidSourceError, match="[Uu]nsupported"):
            _validate_url("xyz://example.com/repo")

    # --- malformed ---

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(InvalidSourceError):
            _validate_url("")

    def test_rejects_domain_only(self) -> None:
        with pytest.raises(InvalidSourceError):
            _validate_url("https://github.com")

    def test_rejects_domain_only_trailing_slash(self) -> None:
        with pytest.raises(InvalidSourceError):
            _validate_url("https://github.com/")

    def test_rejects_no_host(self) -> None:
        with pytest.raises(InvalidSourceError):
            _validate_url("https:///repo/path")


# ---------------------------------------------------------------------------
# GitCloneScanner — orchestration with mocked git
# ---------------------------------------------------------------------------


class TestGitCloneScannerOrchestration:
    """Tests that mock git.Repo.clone_from to avoid network access."""

    @patch("repopilot.scanner.git_clone.LocalScanner")
    @patch("repopilot.scanner.git_clone.tempfile.mkdtemp")
    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_scan_calls_clone_with_url(
        self,
        mock_rmtree: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_local_scanner_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """scan() must invoke git.Repo.clone_from with the supplied URL."""
        mock_mkdtemp.return_value = str(tmp_path)
        _make_fake_local_tree(tmp_path)

        with patch("git.Repo.clone_from") as mock_clone:
            scanner = GitCloneScanner()
            scanner.scan("https://github.com/owner/repo.git")

        mock_clone.assert_called_once()
        args, kwargs = mock_clone.call_args
        assert args[0] == "https://github.com/owner/repo.git"

    @patch("repopilot.scanner.git_clone.LocalScanner")
    @patch("repopilot.scanner.git_clone.tempfile.mkdtemp")
    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_scan_uses_shallow_clone(
        self,
        mock_rmtree: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_local_scanner_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Shallow clone (depth=1) must always be requested."""
        mock_mkdtemp.return_value = str(tmp_path)
        _make_fake_local_tree(tmp_path)

        with patch("git.Repo.clone_from") as mock_clone:
            GitCloneScanner().scan("https://github.com/owner/repo.git")

        _, kwargs = mock_clone.call_args
        assert kwargs.get("depth") == 1

    @patch("repopilot.scanner.git_clone.LocalScanner")
    @patch("repopilot.scanner.git_clone.tempfile.mkdtemp")
    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_scan_delegates_to_local_scanner(
        self,
        mock_rmtree: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_local_scanner_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """scan() must call LocalScanner.scan() on the cloned directory."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_local_instance = mock_local_scanner_cls.return_value
        mock_local_instance.scan.return_value = MagicMock()

        with patch("git.Repo.clone_from"):
            GitCloneScanner().scan("https://github.com/owner/repo.git")

        mock_local_instance.scan.assert_called_once_with(Path(str(tmp_path)))

    @patch("repopilot.scanner.git_clone.LocalScanner")
    @patch("repopilot.scanner.git_clone.tempfile.mkdtemp")
    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_scan_returns_file_tree_from_local_scanner(
        self,
        mock_rmtree: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_local_scanner_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """The FileTree returned is the one produced by LocalScanner."""
        mock_mkdtemp.return_value = str(tmp_path)
        fake_tree = MagicMock(name="FileTree")
        mock_local_scanner_cls.return_value.scan.return_value = fake_tree

        with patch("git.Repo.clone_from"):
            result = GitCloneScanner().scan("https://github.com/owner/repo.git")

        assert result is fake_tree

    @patch("repopilot.scanner.git_clone.LocalScanner")
    @patch("repopilot.scanner.git_clone.tempfile.mkdtemp")
    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_scan_creates_tmpdir_before_clone(
        self,
        mock_rmtree: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_local_scanner_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A temporary directory must be allocated before any clone attempt."""
        call_order: list[str] = []
        mock_mkdtemp.side_effect = lambda **kw: (call_order.append("mkdtemp"), str(tmp_path))[1]
        mock_local_scanner_cls.return_value.scan.return_value = MagicMock()

        def _record_clone(*args: object, **kwargs: object) -> None:
            call_order.append("clone")

        with patch("git.Repo.clone_from", side_effect=_record_clone):
            GitCloneScanner().scan("https://github.com/owner/repo.git")

        assert call_order.index("mkdtemp") < call_order.index("clone")


# ---------------------------------------------------------------------------
# GitCloneScanner — cleanup behaviour
# ---------------------------------------------------------------------------


class TestGitCloneScannerCleanup:
    @patch("repopilot.scanner.git_clone.LocalScanner")
    @patch("repopilot.scanner.git_clone.tempfile.mkdtemp")
    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_cleanup_called_after_successful_scan_via_context_manager(
        self,
        mock_rmtree: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_local_scanner_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """__exit__ must call rmtree on the temp dir after a successful scan."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_local_scanner_cls.return_value.scan.return_value = MagicMock()

        with patch("git.Repo.clone_from"):
            with GitCloneScanner() as scanner:
                scanner.scan("https://github.com/owner/repo.git")

        mock_rmtree.assert_called()
        assert mock_rmtree.call_args[0][0] == str(tmp_path)

    @patch("repopilot.scanner.git_clone.LocalScanner")
    @patch("repopilot.scanner.git_clone.tempfile.mkdtemp")
    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_cleanup_called_after_clone_failure(
        self,
        mock_rmtree: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_local_scanner_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """rmtree must be called even when clone raises GitCommandError."""
        import git
        mock_mkdtemp.return_value = str(tmp_path)

        with patch(
            "git.Repo.clone_from",
            side_effect=git.exc.GitCommandError("git clone", 128),
        ):
            with pytest.raises(ScanError):
                GitCloneScanner().scan("https://github.com/owner/repo.git")

        mock_rmtree.assert_called()
        assert mock_rmtree.call_args[0][0] == str(tmp_path)

    @patch("repopilot.scanner.git_clone.LocalScanner")
    @patch("repopilot.scanner.git_clone.tempfile.mkdtemp")
    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_cleanup_called_after_scanner_failure(
        self,
        mock_rmtree: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_local_scanner_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """rmtree must be called even when LocalScanner.scan() raises."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_local_scanner_cls.return_value.scan.side_effect = ScanError("scan failed")

        with patch("git.Repo.clone_from"):
            with pytest.raises(ScanError, match="scan failed"):
                GitCloneScanner().scan("https://github.com/owner/repo.git")

        mock_rmtree.assert_called()

    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_no_cleanup_when_validate_fails(self, mock_rmtree: MagicMock) -> None:
        """No tmpdir is created (or deleted) when URL validation rejects the URL."""
        with pytest.raises(InvalidSourceError):
            GitCloneScanner().scan("file:///home/user/repo")

        mock_rmtree.assert_not_called()

    @patch("repopilot.scanner.git_clone.LocalScanner")
    @patch("repopilot.scanner.git_clone.tempfile.mkdtemp")
    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_double_cleanup_is_safe(
        self,
        mock_rmtree: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_local_scanner_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Calling _cleanup() twice must not attempt rmtree a second time."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_local_scanner_cls.return_value.scan.return_value = MagicMock()

        scanner = GitCloneScanner()
        with patch("git.Repo.clone_from"):
            with scanner:
                scanner.scan("https://github.com/owner/repo.git")

        first_call_count = mock_rmtree.call_count
        # Manually trigger a second cleanup (simulates __del__ after __exit__).
        scanner._cleanup()
        # rmtree must NOT have been called again.
        assert mock_rmtree.call_count == first_call_count


# ---------------------------------------------------------------------------
# GitCloneScanner — context manager protocol
# ---------------------------------------------------------------------------


class TestGitCloneScannerContextManager:
    def test_enter_returns_scanner_instance(self) -> None:
        scanner = GitCloneScanner()
        result = scanner.__enter__()
        assert result is scanner
        scanner._cleanup()  # no tmpdir to clean but exercises the path

    @patch("repopilot.scanner.git_clone.LocalScanner")
    @patch("repopilot.scanner.git_clone.tempfile.mkdtemp")
    @patch("repopilot.scanner.git_clone.shutil.rmtree")
    def test_exit_cleans_up_on_exception_inside_with_block(
        self,
        mock_rmtree: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_local_scanner_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """__exit__ must clean up even when the body of `with` raises."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_local_scanner_cls.return_value.scan.return_value = MagicMock()

        with pytest.raises(RuntimeError, match="downstream failure"):
            with patch("git.Repo.clone_from"):
                with GitCloneScanner() as scanner:
                    scanner.scan("https://github.com/owner/repo.git")
                    raise RuntimeError("downstream failure")

        mock_rmtree.assert_called()


# ---------------------------------------------------------------------------
# GitCloneScanner — error message safety
# ---------------------------------------------------------------------------


class TestGitCloneScannerErrorSafety:
    def test_credentials_not_in_scan_error_message(
        self, tmp_path: Path
    ) -> None:
        """Credentials embedded in a URL must not appear in ScanError.args."""
        import git

        url_with_creds = "https://user:supersecret@github.com/owner/repo.git"

        with (
            patch("repopilot.scanner.git_clone.tempfile.mkdtemp", return_value=str(tmp_path)),
            patch("repopilot.scanner.git_clone.shutil.rmtree"),
            patch(
                "git.Repo.clone_from",
                side_effect=git.exc.GitCommandError("git clone", 128, stderr=url_with_creds),
            ),
        ):
            with pytest.raises(ScanError) as exc_info:
                GitCloneScanner().scan(url_with_creds)

        error_text = str(exc_info.value)
        assert "supersecret" not in error_text

    def test_invalid_source_error_for_file_url(self) -> None:
        """file:// raises InvalidSourceError, not ScanError."""
        with pytest.raises(InvalidSourceError):
            GitCloneScanner().scan("file:///home/user/repo")

    def test_invalid_source_error_for_local_path(self) -> None:
        """A bare local path raises InvalidSourceError."""
        with pytest.raises(InvalidSourceError):
            GitCloneScanner().scan("/home/user/repo")
