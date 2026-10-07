"""LocalScanner — walk a local repository directory and produce a FileTree.

Design constraints (security.md, tech.md):
- Scanning is strictly read-only; no files are written or executed.
- Symlinks are resolved to detect escapes outside the repository root.
  A symlink that resolves outside the root is recorded as a FileEntry
  (so rules can detect it) but is *not* descended into and its content
  is never read.
- Excluded directories (EXCLUDED_DIRS) are recorded as top-level
  FileEntry objects so rules can detect committed node_modules etc.,
  but their contents are NOT traversed.
- All relative paths use forward slashes on all platforms.
- Results are deterministic: entries are sorted by relative path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from repopilot.exceptions import ScanError
from repopilot.scanner.base import FileEntry, FileTree

# ---------------------------------------------------------------------------
# Directories that are recorded but never recursed into.
# ---------------------------------------------------------------------------

EXCLUDED_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",        # sometimes used as a directory name by accident
        ".eggs",
        "dist",
        "build",
        ".gradle",
        ".next",
        ".nuxt",
        "target",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".hypothesis",
        ".cache",
        "coverage",
        "htmlcov",
        ".coverage",
    }
)


class LocalScanner:
    """Walk a local directory and produce a FileTree.

    The scanner is intentionally stateless; a new scan is started each
    time ``scan()`` is called.

    Usage::

        scanner = LocalScanner()
        tree = scanner.scan(Path("/path/to/repo"))
    """

    def scan(self, path: Path) -> FileTree:
        """Walk *path* and return a FileTree snapshot.

        Args:
            path: Absolute or relative path to the repository root directory.

        Returns:
            A ``FileTree`` containing all discovered entries.

        Raises:
            ScanError: If *path* does not exist, is not a directory, or
                       cannot be accessed.
        """
        # Resolve to an absolute, canonical path before doing anything.
        try:
            root = path.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise ScanError(
                f"Repository path does not exist or cannot be accessed: {path!r}"
            ) from exc

        if not root.is_dir():
            raise ScanError(
                f"Repository path is not a directory: {path!r}"
            )

        entries: list[FileEntry] = []
        self._walk(root, root, entries)

        return FileTree(root=root, entries=entries)

    # ------------------------------------------------------------------
    # Internal walk
    # ------------------------------------------------------------------

    def _walk(
        self,
        root: Path,
        current: Path,
        entries: list[FileEntry],
    ) -> None:
        """Recursively walk *current*, appending FileEntry objects to *entries*.

        Args:
            root:    The repository root (used for relative-path calculation
                     and symlink-escape detection).
            current: The directory currently being walked.
            entries: The accumulator list.
        """
        try:
            # scandir is used for efficiency (stat bundled with the dir entry).
            dir_entries = list(os.scandir(current))
        except PermissionError:
            # Unreadable directory — skip silently.
            return
        except OSError:
            return

        # Sort for deterministic order within each directory.
        dir_entries.sort(key=lambda e: e.name)

        for os_entry in dir_entries:
            entry_path = Path(os_entry.path)

            # ----------------------------------------------------------
            # Symlink safety: resolve and confirm it stays inside root.
            # ----------------------------------------------------------
            try:
                resolved = entry_path.resolve(strict=True)
            except (OSError, RuntimeError):
                # Dangling symlink or resolution failure — skip.
                continue

            inside_root = self._is_inside_root(resolved, root)

            # Build the relative path (forward-slash normalised).
            try:
                relative = entry_path.relative_to(root).as_posix()
            except ValueError:
                # Should not happen, but skip defensively.
                continue

            # ----------------------------------------------------------
            # Determine entry type.
            # ----------------------------------------------------------
            try:
                stat = os_entry.stat(follow_symlinks=True)
            except OSError:
                continue

            is_dir = resolved.is_dir()

            if is_dir:
                size_bytes = 0
            else:
                size_bytes = stat.st_size

            entries.append(
                FileEntry(
                    path=entry_path,
                    relative=relative,
                    size_bytes=size_bytes,
                    is_dir=is_dir,
                )
            )

            # ----------------------------------------------------------
            # Decide whether to recurse.
            # ----------------------------------------------------------
            if not is_dir:
                continue

            name_lower = os_entry.name.lower()

            # Never descend into excluded directories (but we've already
            # recorded the directory entry itself above).
            if os_entry.name in EXCLUDED_DIRS or name_lower in EXCLUDED_DIRS:
                continue

            # Never follow a symlink that escapes the repository root.
            if not inside_root:
                continue

            self._walk(root, resolved, entries)

    @staticmethod
    def _is_inside_root(resolved: Path, root: Path) -> bool:
        """Return True if *resolved* is the root or a descendant of it."""
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            return False
