"""Project-wide exception hierarchy for RepoPilot.

All domain exceptions inherit from RepoPilotError so callers can catch
the base class when they don't need to distinguish sub-types.
"""

from __future__ import annotations


class RepoPilotError(Exception):
    """Base class for all RepoPilot domain exceptions."""


class InvalidSourceError(RepoPilotError):
    """Raised when the user-supplied repository source is invalid.

    Examples: non-existent local path, malformed URL, unsupported scheme.
    """


class RepositoryNotFoundError(RepoPilotError):
    """Raised when a repository path or URL cannot be located or cloned."""


class InvalidRepositoryError(RepoPilotError):
    """Raised when a path exists but is not a valid Git repository or directory."""


class ScanError(RepoPilotError):
    """Raised when the scanner encounters an unrecoverable error during inspection."""


class RuleError(RepoPilotError):
    """Raised when a rule encounters an unexpected error during evaluation.

    Rules should generally catch their own errors and convert them to INFO
    findings; this exception is reserved for unrecoverable rule failures.
    """


class CleanupError(RepoPilotError):
    """Raised when a temporary clone directory cannot be deleted after analysis."""
