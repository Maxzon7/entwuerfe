"""
========================================================================================
DRACBV Energy Simulator — Standalone Root Entrypoint
========================================================================================

Launch via:
    python -m streamlit run app.py
or double-click:
    Start_DRACBV_Energy_Simulator.bat
"""

from __future__ import annotations

import os
import sys

_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import _bootstrap

_bootstrap.bootstrap_standalone_root()

from ui_sandbox.Combined_sandbox.app import main  # noqa: E402


if __name__ == "__main__":
    main()
