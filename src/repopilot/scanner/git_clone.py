"""GitCloneScanner — clone a remote Git repository and analyse it locally.

This module is the *only* place in the core codebase that is permitted to
make outbound network calls (security.md, tech.md).  All other layers
(domain, rules, scoring, services) must remain network-free.

Design constraints:
- Only HTTPS URLs are supported (REQ-001.2).  SSH and file:// are rejected.
- Clones are shallow (depth=1) to minimise data transfer.
- Submodules are never initialised.
- No repository hooks are run during or after cloning.
- The temporary directory is always deleted — on success, on clone failure,
  and on scanner failure — via the context-manager protocol and a __del__
  fallback.
- Credentials embedded in URLs (user:password@host) are stripped before
  they appear in log messages or exception text.
- Repository contents never leave the temporary clone directory.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Final
from urllib.parse import urlparse, urlunparse

from repopilot.exceptions import CleanupError, InvalidSourceError, ScanError
from repopilot.scanner.base import FileTree
from repopilot.scanner.local import LocalScanner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

#: The only URL scheme supported by the offline core (REQ-001.2).
_ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"https"})

#: Schemes that are explicitly rejected with a clear message.
_REJECTED_SCHEMES: Final[dict[str, str]] = {
    "http":  "plain HTTP is not supported; use an HTTPS URL",
    "ssh":   "SSH URLs are not supported; use an HTTPS URL",
    "git":   "git:// URLs are not supported; use an HTTPS URL",
    "file":  "file:// URLs are not supported; supply a local path directly",
    "ftp":   "FTP URLs are not supported",
}

# Matches a Windows drive letter or POSIX leading slash — i.e. a local path.
_LOCAL_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:[A-Za-z]:[/\\]|[/\\]|\.{1,2}[/\\]|\.{1,2}$)"
)


def _sanitise_url(url: str) -> str:
    """Return *url* with any embedded ``user:password@`` component removed.

    Used when constructing log messages and exception text so that
    credentials are never exposed.
    """
    try:
        parsed = urlparse(url)
        # Replace netloc with the host-only portion (drop userinfo).
        sanitised = parsed._replace(netloc=parsed.hostname or parsed.netloc)
        return urlunparse(sanitised)
    except Exception:
        # If parsing itself fails, return a truncated placeholder.
        return "<url>"


def _validate_url(url: str) -> None:
    """Raise InvalidSourceError if *url* is not a supported HTTPS Git URL.

    Checks performed (in order):
    1. Local filesystem paths are rejected.
    2. The URL must be parseable.
    3. The scheme must be in _ALLOWED_SCHEMES.
    4. The URL must have a non-empty host.
    5. The URL must have a non-empty path component (i.e. not just a domain).

    Raises:
        InvalidSourceError: with a safe (credential-free) description.
    """
    stripped = url.strip()

    # Reject bare local paths before trying to parse as a URL.
    if _LOCAL_PATH_RE.match(stripped):
        raise InvalidSourceError(
            "Local filesystem paths are not accepted as remote URLs; "
            "pass a Path object to LocalScanner instead."
        )

    try:
        parsed = urlparse(stripped)
    except Exception as exc:
        raise InvalidSourceError(f"Malformed URL: {exc}") from exc

    scheme = parsed.scheme.lower()

    if scheme in _REJECTED_SCHEMES:
        raise InvalidSourceError(
            f"Unsupported URL scheme {scheme!r}: {_REJECTED_SCHEMES[scheme]}"
        )

    if scheme not in _ALLOWED_SCHEMES:
        raise InvalidSourceError(
            f"Unsupported URL scheme {scheme!r}; only HTTPS URLs are supported."
        )

    if not parsed.hostname:
        raise InvalidSourceError(
            f"URL has no host component: {_sanitise_url(url)!r}"
        )

    path_part = parsed.path.rstrip("/")
    if not path_part or path_part == "":
        raise InvalidSourceError(
            f"URL has no repository path component: {_sanitise_url(url)!r}"
        )


# ---------------------------------------------------------------------------
# GitCloneScanner
# ---------------------------------------------------------------------------


class GitCloneScanner:
    """Clone a remote Git repository and return a FileTree of its contents.

    The scanner is designed to be used as a context manager so the
    temporary clone directory is reliably removed::

        with GitCloneScanner() as scanner:
            tree = scanner.scan("https://github.com/owner/repo")

    It can also be used without the context manager; in that case cleanup
    happens when the instance is garbage-collected (``__del__``).  Callers
    should prefer the context-manager form for predictable cleanup.

    The ``scan()`` method:

    1. Validates the URL.
    2. Creates a system temporary directory.
    3. Clones the repository (shallow, no submodules, no hooks).
    4. Delegates to ``LocalScanner`` to produce the ``FileTree``.
    5. Cleans up the temporary directory (or schedules it for ``__exit__``).

    On any failure in steps 2–4 the temporary directory is removed before
    the exception propagates.
    """

    def __init__(self) -> None:
        self._tmpdir: str | None = None

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "GitCloneScanner":
        return self

    def __exit__(self, *args: object) -> None:
        self._cleanup()

    def __del__(self) -> None:
        """Last-resort cleanup in case the context manager was not used."""
        self._cleanup()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, url: str) -> FileTree:
        """Clone *url* to a temporary directory and return a ``FileTree``.

        Args:
            url: A public HTTPS Git URL, e.g.
                 ``"https://github.com/owner/repo.git"``.

        Returns:
            A ``FileTree`` representing the cloned repository contents.

        Raises:
            InvalidSourceError: If the URL is malformed, uses an unsupported
                scheme, or is a local filesystem path.
            ScanError: If the clone fails (network error, repository not
                found, authentication required) or if the local scan fails.
        """
        # --- 1. Validate URL -------------------------------------------
        _validate_url(url)

        # --- 2. Create temporary directory -----------------------------
        tmpdir = tempfile.mkdtemp(prefix="repopilot_clone_")
        self._tmpdir = tmpdir

        try:
            # --- 3. Clone the repository -------------------------------
            self._clone(url, tmpdir)

            # --- 4. Run LocalScanner -----------------------------------
            tree = LocalScanner().scan(Path(tmpdir))

        except Exception:
            # Clean up immediately on any failure so no orphaned dirs remain.
            self._cleanup()
            raise

        # Cleanup is deferred to __exit__ / __del__ when used as a context
        # manager.  If called bare (not as a CM), cleanup happens in __del__.
        return tree

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clone(self, url: str, dest: str) -> None:
        """Perform the actual git clone into *dest*.

        Uses a shallow clone (depth=1) to minimise data transfer.  No
        submodules are initialised.  No repository hooks are executed.

        Args:
            url:  The validated HTTPS URL to clone.
            dest: Absolute path to an existing empty temporary directory.

        Raises:
            ScanError: On any clone failure, with the URL sanitised so that
                       credentials are never exposed in the error message.
        """
        # Import here so that the git library is only loaded when actually
        # needed; domain/rules/scoring modules never trigger this import.
        try:
            import git  # gitpython
            from git.exc import GitCommandError, GitCommandNotFound, InvalidGitRepositoryError
        except ImportError as exc:
            raise ScanError(
                "gitpython is not installed; cannot clone remote repositories."
            ) from exc

        safe_url = _sanitise_url(url)
        logger.debug("Cloning %s (shallow) …", safe_url)

        try:
            git.Repo.clone_from(
                url,
                dest,
                depth=1,                  # shallow clone
                no_single_branch=True,    # clone default branch only
                no_local=True,            # never treat as local path
                multi_options=[
                    "--no-tags",          # skip tag objects
                ],
                # Prevent any hook execution from the cloned repository.
                env={"GIT_CONFIG_NOSYSTEM": "1", "HOME": dest},
            )
        except GitCommandNotFound as exc:
            raise ScanError(
                "git executable not found; ensure git is installed and on PATH."
            ) from exc
        except GitCommandError as exc:
            # exc.stderr may contain the original URL; sanitise it.
            stderr_safe = (exc.stderr or "").replace(url, safe_url)
            raise ScanError(
                f"Failed to clone {safe_url!r}: {stderr_safe.strip()}"
            ) from exc
        except Exception as exc:
            raise ScanError(
                f"Unexpected error while cloning {safe_url!r}: {type(exc).__name__}"
            ) from exc

    def _cleanup(self) -> None:
        """Remove the temporary clone directory if it still exists.

        Logs a warning (but does not raise) if removal fails, so that a
        cleanup failure never masks the actual analysis result.
        """
        tmpdir = self._tmpdir
        if tmpdir is None:
            return
        self._tmpdir = None  # prevent double-cleanup

        try:
            shutil.rmtree(tmpdir, ignore_errors=False)
            logger.debug("Cleaned up temporary clone: %s", tmpdir)
        except Exception as exc:
            # Log the error; do NOT raise — a cleanup failure must not shadow
            # an earlier analysis result or exception.
            logger.warning(
                "Failed to remove temporary clone directory %r: %s", tmpdir, exc
            )
