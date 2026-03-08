"""
conftest.py — pytest configuration for InfraGraph backend tests.
Adds the execution/ directory to sys.path so tests can import execution scripts directly.
"""

import os
import sys

# execution/ is at: <project_root>/execution/
# This conftest is at: <project_root>/backend/tests/conftest.py
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_execution_dir = os.path.join(_project_root, "execution")

if _execution_dir not in sys.path:
    sys.path.insert(0, _execution_dir)
