"""Rules layer — stateless analysis rules applied to a FileTree.

``DEFAULT_RULES`` is the canonical list of all built-in rules instantiated
in evaluation order.  It is populated incrementally as rule modules are
implemented (Tasks 2.1 – 2.6).  The service layer uses this list by default;
tests may pass a custom list for isolation.
"""

from __future__ import annotations

from repopilot.rules.base import Rule
from repopilot.rules.documentation import (
    ContributingRule,
    DocsDirectoryRule,
    ReadmePresenceRule,
    ReadmeSectionsRule,
    ReadmeSizeRule,
)

DEFAULT_RULES: list[Rule] = [
    # Task 2.1 — Documentation rules (evaluation order: presence → size → sections → contributing → docs)
    ReadmePresenceRule(),
    ReadmeSizeRule(),
    ReadmeSectionsRule(),
    ContributingRule(),
    DocsDirectoryRule(),
    # Task 2.2 – 2.6 rules appended here as they are implemented.
]
