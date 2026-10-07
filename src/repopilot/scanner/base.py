"""Scanner base types: FileEntry, FileTree, and the secret-path guard.

Design constraints (security.md, tech.md):
- Paths stored in FileEntry.relative are always relative to the repo root.
- read_text never returns the contents of secret-like files.
- read_text never returns the contents of binary files.
- No code from the repository is executed, imported, or evaluated.
- All filesystem access is strictly read-only.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Secret-file patterns — read_text refuses to return content for these.
# Matching is done against the *relative* path (forward-slash normalised).
# ---------------------------------------------------------------------------

#: Exact filenames that are treated as secret carriers.
_SECRET_EXACT: Final[frozenset[str]] = frozenset(
    {
        ".env",
        "id_rsa",
        "id_dsa",
        "id_ed25519",
        "credentials",
        "credentials.json",
        "secrets.yml",
        "secrets.yaml",
    }
)

#: Glob patterns matched against the *basename* of the relative path.
_SECRET_GLOB_PATTERNS: Final[tuple[str, ...]] = (
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.env",       # *.env covers .env.local, .env.production, etc.
    ".env.*",
)

_BINARY_PROBE_BYTES: Final[int] = 8 * 1024  # 8 KB
_MAX_READ_BYTES: Final[int] = 1024 * 1024   # 1 MB


def _is_secret_path(relative: str) -> bool:
    """Return True if *relative* looks like a secret/credential file.

    Matching is case-insensitive and uses both exact-name and glob checks
    against the basename.  The full relative path is also checked for the
    exact names so that nested secret files (e.g. config/.env) are caught.

    Template/example files (.env.example, .env.sample) are explicitly
    excluded — they are not secrets, they are documentation artefacts
    (per REQ-005.5).
    """
    # Normalise to forward slashes for consistent matching.
    normalised = relative.replace("\\", "/")
    basename = normalised.split("/")[-1].lower()

    # Template files are never treated as secrets regardless of any other match.
    if basename.endswith(".example") or basename.endswith(".sample"):
        return False

    # Exact match against the basename.
    if basename in _SECRET_EXACT:
        return True

    # Glob match against the basename.
    for pattern in _SECRET_GLOB_PATTERNS:
        if fnmatch.fnmatch(basename, pattern):
            return True

    return False


def _is_binary(path: Path) -> bool:
    """Heuristic: return True if the file contains null bytes in its first 8 KB."""
    try:
        with path.open("rb") as fh:
            chunk = fh.read(_BINARY_PROBE_BYTES)
        return b"\x00" in chunk
    except OSError:
        return True  # unreadable → treat as binary / skip


# ---------------------------------------------------------------------------
# FileEntry
# ---------------------------------------------------------------------------


class FileEntry:
    """A single node (file or directory) recorded during a repository scan.

    Attributes:
        path:       Absolute path on the local filesystem.
        relative:   Path relative to the repository root, using forward
                    slashes on all platforms (``src/main.py``, not
                    ``src\\main.py``).
        size_bytes: File size in bytes; 0 for directories.
        is_dir:     True when this entry represents a directory.
    """

    __slots__ = ("path", "relative", "size_bytes", "is_dir")

    def __init__(
        self,
        *,
        path: Path,
        relative: str,
        size_bytes: int,
        is_dir: bool,
    ) -> None:
        self.path = path
        self.relative = relative
        self.size_bytes = size_bytes
        self.is_dir = is_dir

    def __repr__(self) -> str:
        kind = "dir" if self.is_dir else "file"
        return f"FileEntry({kind}, {self.relative!r}, {self.size_bytes} B)"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FileEntry):
            return NotImplemented
        return self.relative == other.relative and self.is_dir == other.is_dir

    def __hash__(self) -> int:
        return hash((self.relative, self.is_dir))


# ---------------------------------------------------------------------------
# FileTree
# ---------------------------------------------------------------------------


class FileTree:
    """An immutable snapshot of a repository's file structure.

    Produced by ``LocalScanner.scan()``.  All five convenience methods are
    designed to be used by rule implementations; they never perform I/O
    except for ``read_text``.

    ``entries`` is sorted by ``relative`` path for deterministic iteration.
    """

    def __init__(self, *, root: Path, entries: list[FileEntry]) -> None:
        self._root = root
        # Store a sorted, immutable view — rules must never mutate this.
        self._entries: tuple[FileEntry, ...] = tuple(
            sorted(entries, key=lambda e: e.relative)
        )

    @property
    def root(self) -> Path:
        """Absolute path to the repository root directory."""
        return self._root

    @property
    def entries(self) -> tuple[FileEntry, ...]:
        """All recorded entries, sorted by relative path."""
        return self._entries

    # ------------------------------------------------------------------
    # Convenience query methods
    # ------------------------------------------------------------------

    def has_file(self, name: str, *, case_insensitive: bool = True) -> bool:
        """Return True if any *file* entry has the given name as its basename.

        ``name`` is matched against the final component of each entry's
        relative path.  Directories are excluded.

        Args:
            name:             The filename to search for (e.g. ``"README.md"``).
            case_insensitive: When True (default), comparison is case-folded.
        """
        compare = name.lower() if case_insensitive else name
        for entry in self._entries:
            if entry.is_dir:
                continue
            basename = entry.relative.replace("\\", "/").split("/")[-1]
            candidate = basename.lower() if case_insensitive else basename
            if candidate == compare:
                return True
        return False

    def find_files(self, pattern: str) -> list[FileEntry]:
        """Return file entries whose relative path matches *pattern*.

        *pattern* is a Unix-style glob (``fnmatch`` semantics) matched
        against the full relative path.  Directories are excluded.

        Examples::

            tree.find_files("*.py")
            tree.find_files("tests/test_*.py")
            tree.find_files("**/*.yml")   # note: fnmatch doesn't support **
        """
        results: list[FileEntry] = []
        for entry in self._entries:
            if entry.is_dir:
                continue
            if fnmatch.fnmatch(entry.relative, pattern):
                results.append(entry)
        return results

    def find_dirs(self, name: str, *, case_insensitive: bool = True) -> list[FileEntry]:
        """Return directory entries whose basename matches *name*.

        Args:
            name:             The directory name to search for (e.g. ``"docs"``).
            case_insensitive: When True (default), comparison is case-folded.
        """
        compare = name.lower() if case_insensitive else name
        results: list[FileEntry] = []
        for entry in self._entries:
            if not entry.is_dir:
                continue
            basename = entry.relative.replace("\\", "/").split("/")[-1]
            candidate = basename.lower() if case_insensitive else basename
            if candidate == compare:
                results.append(entry)
        return results

    def root_files(self) -> list[FileEntry]:
        """Return entries at the repository root (depth 1, not nested).

        Both files and directories directly under the root are returned.
        Entries inside subdirectories are excluded.
        """
        results: list[FileEntry] = []
        for entry in self._entries:
            # A root-level entry has no slash in its relative path.
            rel = entry.relative.replace("\\", "/")
            if "/" not in rel:
                results.append(entry)
        return results

    def read_text(self, relative: str) -> str | None:
        """Safely read a text file from the repository.

        Returns ``None`` when:
        - The relative path matches a secret-file pattern.
        - The file does not exist in this FileTree.
        - The file appears to be binary (null bytes in first 8 KB).
        - The file cannot be read (permissions, I/O error).
        - The file is a directory.

        Content is capped at 1 MB; bytes beyond that limit are silently
        discarded.

        Args:
            relative: Path relative to the repository root.  Both forward
                      and back slashes are accepted.

        Returns:
            The file's text content, or ``None``.
        """
        # Normalise separators for consistent matching.
        normalised_rel = relative.replace("\\", "/")

        # Security: never return secret-file contents.
        if _is_secret_path(normalised_rel):
            return None

        # Locate the matching FileEntry.
        entry = self._entry_for(normalised_rel)
        if entry is None or entry.is_dir:
            return None

        # Validate the resolved absolute path stays inside the root.
        resolved = entry.path.resolve()
        try:
            resolved.relative_to(self._root.resolve())
        except ValueError:
            # Resolved path escapes the repository root (e.g. symlink attack).
            return None

        if _is_binary(entry.path):
            return None

        try:
            raw = entry.path.read_bytes()
            if len(raw) > _MAX_READ_BYTES:
                raw = raw[:_MAX_READ_BYTES]
            return raw.decode("utf-8", errors="replace")
        except OSError:
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entry_for(self, normalised_rel: str) -> FileEntry | None:
        """Return the FileEntry whose normalised relative path matches, or None."""
        for entry in self._entries:
            if entry.relative.replace("\\", "/") == normalised_rel:
                return entry
        return None

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"FileTree(root={self._root!r}, entries={len(self._entries)})"
