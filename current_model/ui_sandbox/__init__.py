"""
========================================================================================
UI Sandbox & Prototyping Laboratory (ui_sandbox)
========================================================================================
Dedicated isolated testing environment for experimenting with Streamlit UI components,
custom widgets, charts, and layout prototypes without launching the main application.

Active Sandbox Package:
- Currentsituation_sandbox: Tab 1 & Tab 2 replicas with upgraded 3-party financial architecture,
  complete interval load curve visualizer, and commercial electricity billing engine.

Note:
All retired, inactive, or experimental lab modules and shims (such as status_quo_2025 lab,
monthly_baseline_lab, and three_party_contract_lab) are stored in the root 'not in Use' directory.

IMPORTANT ARCHITECTURAL RULE:
- ui_sandbox may import from core, models, and ui.
- The main application (app.py, core/, models/, ui/) MUST NEVER import from ui_sandbox.
========================================================================================
"""

try:
    from ui_sandbox.Currentsituation_sandbox.app import (
        render_current_situation_sandbox,
        main as run_current_situation_sandbox,
    )
except ImportError:
    try:
        from current_model.ui_sandbox.Currentsituation_sandbox.app import (
            render_current_situation_sandbox,
            main as run_current_situation_sandbox,
        )
    except ImportError:
        render_current_situation_sandbox = None
        run_current_situation_sandbox = None

try:
    from ui_sandbox.BESS_sandbox.app import (
        render_bess_sandbox,
        main as run_bess_sandbox,
    )
except ImportError:
    try:
        from current_model.ui_sandbox.BESS_sandbox.app import (
            render_bess_sandbox,
            main as run_bess_sandbox,
        )
    except ImportError:
        render_bess_sandbox = None
        run_bess_sandbox = None

__all__ = [
    "render_current_situation_sandbox",
    "run_current_situation_sandbox",
    "render_bess_sandbox",
    "run_bess_sandbox",
]

