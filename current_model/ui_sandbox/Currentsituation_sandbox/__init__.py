"""
========================================================================================
Current Situation Sandbox Package (ui_sandbox/Currentsituation_sandbox)
========================================================================================

Encapsulates the Status Quo / Current Situation workflow copied directly from the main application:
  - Consumption Module: Full CSV Inspector, 15-minute load curves, monthly breakdown, KPIs, synthetic simulator.
  - Contract Module: Electricity contract configuration, unbundled billing calculation, monthly payment series, donut charts.
"""

from typing import Optional

import os
import sys

# Ensure current_model and its parent directory (entwuerfe) are in sys.path
_this_dir = os.path.dirname(os.path.abspath(__file__))
_ui_sandbox_dir = os.path.abspath(os.path.join(_this_dir, ".."))
_current_model_dir = os.path.abspath(os.path.join(_this_dir, "..", ".."))
_parent_dir = os.path.abspath(os.path.join(_current_model_dir, ".."))
for _p in [_this_dir, _ui_sandbox_dir, _current_model_dir, _parent_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from current_model.ui_sandbox.Currentsituation_sandbox.consumption.view import render_tab1_consumption
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.view import render_tab2_base_contract, render_tab2_contract
except ImportError:
    try:
        from ui_sandbox.Currentsituation_sandbox.consumption.view import render_tab1_consumption
        from ui_sandbox.Currentsituation_sandbox.contract.view import render_tab2_base_contract, render_tab2_contract
    except ImportError:
        from consumption.view import render_tab1_consumption
        from contract.view import render_tab2_base_contract, render_tab2_contract

__all__ = [
    "render_tab1_consumption",
    "render_tab2_base_contract",
    "render_tab2_contract",
]
