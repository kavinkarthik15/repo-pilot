"""Rules layer — stateless analysis rules applied to a FileTree.

``DEFAULT_RULES`` is the canonical list of all built-in rules instantiated
in evaluation order.  It is populated incrementally as rule modules are
implemented (Tasks 2.1 – 2.6).  The service layer uses this list by default;
tests may pass a custom list for isolation.
"""

from __future__ import annotations

from repopilot.rules.base import Rule

# Populated in Tasks 2.1 – 2.6 as each rule module is implemented.
DEFAULT_RULES: list[Rule] = []
