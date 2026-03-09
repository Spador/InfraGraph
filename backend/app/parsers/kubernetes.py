"""
parsers/kubernetes.py — Thin wrapper around execution/parse_kubernetes.py.

Keeps Layer 3 (execution/parse_kubernetes.py) as the single source of truth
for all parsing logic. This module simply locates and imports it.
"""

import os
import sys

# Resolve the execution/ directory (same dual-path logic as terraform.py).
_candidates = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "execution")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "execution")),
]
for _p in _candidates:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
        break

from parse_kubernetes import parse_kubernetes_files  # noqa: E402


class KubernetesParser:
    """Parses one .yaml/.yml file or a directory of YAML files."""

    def __init__(self, path: str) -> None:
        self.path = path

    def parse(self) -> dict:
        """
        Returns {"resources": [...], "edges": [...]}.
        Raises ValueError on parse error, FileNotFoundError if path missing.
        """
        return parse_kubernetes_files(self.path)
