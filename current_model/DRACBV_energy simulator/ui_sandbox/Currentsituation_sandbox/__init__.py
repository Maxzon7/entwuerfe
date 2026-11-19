"""
Standalone Current Situation Subset (`ui_sandbox/Currentsituation_sandbox`)
============================================================================

Provides only the Consumption UI (CSV Inspector & Synthetic Load Simulator) and
the 4-Pillar Status Quo engine (`engine/`) used by `Combined_sandbox`.
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import _bootstrap

_bootstrap.bootstrap_standalone_root()

from .consumption.view import render_tab1_consumption  # noqa: E402

__all__ = [
    "render_tab1_consumption",
]
