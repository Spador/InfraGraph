"""
parsers/terraform.py — Thin wrapper around execution/parse_terraform.py.

Keeps Layer 3 (execution/parse_terraform.py) as the single source of truth
for all parsing logic. This module simply locates and imports it.
"""

import os
import sys

# Resolve the execution/ directory.
# Local:  backend/app/parsers/ → ../../.. → project root → execution/
# Docker: /app/app/parsers/   → ../..   → /app/         → execution/ (mounted volume)
_candidates = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "execution")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "execution")),
]
for _p in _candidates:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
        break

from parse_terraform import parse_terraform_files  # noqa: E402


class TerraformParser:
    """Parses one .tf file or a directory of .tf files."""

    def __init__(self, path: str) -> None:
        self.path = path

    def parse(self) -> dict:
        """
        Returns {"resources": [...], "edges": [...]}.
        Raises ValueError on parse error, FileNotFoundError if path missing.
        """
        return parse_terraform_files(self.path)
