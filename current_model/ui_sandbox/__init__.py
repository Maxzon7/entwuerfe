"""
========================================================================================
UI Sandbox & Prototyping Laboratory (ui_sandbox)
========================================================================================
Dedicated isolated testing environment for experimenting with Streamlit UI components,
custom widgets, charts, and layout prototypes without launching the main application.

IMPORTANT ARCHITECTURAL RULE:
- ui_sandbox may import from core, models, and ui.
- The main application (app.py, core/, models/, ui/) MUST NEVER import from ui_sandbox.
========================================================================================
"""
