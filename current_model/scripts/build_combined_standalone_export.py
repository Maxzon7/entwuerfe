"""
Standalone Export Builder for Combined Sandbox -> DRACBV_energy simulator
==========================================================================

Builds a self-contained, export-ready copy of the Combined System Sandbox inside:
    <repo_root>/DRACBV_energy simulator/

Design Guarantees:
  1. Non-destructive: Never modifies any file inside the parent `current_model`
     codebase (`ui_sandbox/`, `core/`, `models/`, `ui/`, `tests/`).
  2. Strict standalone isolation: Copies only the required modules and assets,
     generates pruned package `__init__.py` markers, injects `_bootstrap.py`
     so `current_model.*` imports resolve strictly inside the exported folder
     regardless of folder location or name, and removes `_WORKSPACE_DIR` from
     copied `app.py` and `views/state_and_helpers.py`.
  3. Reproducible verification: Emits a standalone `run_tests.py` with path
     isolation checks and a developer-friendly `README.md`.
"""

from __future__ import annotations

import os
import shutil
import stat
import time
from typing import Dict, Iterable, List, Tuple


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TARGET_FOLDER_NAME = "DRACBV_energy simulator"
TARGET_DIR = os.path.join(REPO_ROOT, TARGET_FOLDER_NAME)

IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store")

# Directories copied verbatim from REPO_ROOT -> TARGET_DIR
COPIED_DIRECTORIES: Tuple[str, ...] = (
    os.path.join("ui_sandbox", "Combined_sandbox"),
    os.path.join("ui_sandbox", "Currentsituation_sandbox", "consumption"),
    os.path.join("ui_sandbox", "Currentsituation_sandbox", "engine"),
    os.path.join("sample_data", "market_prices"),
)

# Individual files copied verbatim from REPO_ROOT -> TARGET_DIR
COPIED_FILES: Tuple[str, ...] = (
    # Core engines required by Combined_sandbox and Currentsituation_sandbox
    os.path.join("core", "bess_engine.py"),
    os.path.join("core", "csv_parser.py"),
    os.path.join("core", "demo_scenario.py"),
    os.path.join("core", "load_processor.py"),
    os.path.join("core", "market_price_engine.py"),
    os.path.join("core", "metrics_engine.py"),
    os.path.join("core", "solar_engine.py"),
    os.path.join("core", "synthetic_engine.py"),
    # Data models required by Combined_sandbox and Currentsituation_sandbox
    os.path.join("models", "bess.py"),
    os.path.join("models", "calendar_config.py"),
    os.path.join("models", "contract.py"),
    os.path.join("models", "financial.py"),
    os.path.join("models", "load_component.py"),
    os.path.join("models", "presets.py"),
    os.path.join("models", "solar.py"),
    # Shared UI primitives
    os.path.join("ui", "common", "cards.py"),
    os.path.join("ui", "common", "session_utils.py"),
    os.path.join("ui", "common", "styles.py"),
    # Regression & physics test suite for Combined_sandbox
    os.path.join("tests", "test_combined_sandbox.py"),
)


def _write_text_file(rel_path: str, content: str) -> None:
    """Writes UTF-8 text to a path inside TARGET_DIR, creating parent directories."""
    abs_path = os.path.join(TARGET_DIR, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _copy_selected_assets() -> Tuple[int, int]:
    """Copies required directories and files from REPO_ROOT into TARGET_DIR."""
    dir_count = 0
    file_count = 0

    for rel_dir in COPIED_DIRECTORIES:
        src = os.path.join(REPO_ROOT, rel_dir)
        dst = os.path.join(TARGET_DIR, rel_dir)
        if not os.path.isdir(src):
            raise FileNotFoundError(f"Required source directory not found: {src}")
        shutil.copytree(src, dst, ignore=IGNORE_PATTERNS, dirs_exist_ok=True)
        dir_count += 1

    for rel_file in COPIED_FILES:
        src = os.path.join(REPO_ROOT, rel_file)
        dst = os.path.join(TARGET_DIR, rel_file)
        if not os.path.isfile(src):
            raise FileNotFoundError(f"Required source file not found: {src}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        file_count += 1

    return dir_count, file_count


def _build_bootstrap_source() -> str:
    return '''"""
Standalone Import Bootstrap (DRACBV Energy Simulator)
====================================================

Ensures all package imports (`core.*`, `models.*`, `ui.*`, `ui_sandbox.*`, and
`current_model.*`) resolve strictly from this standalone folder, regardless of
what directory name it has or whether it lives inside a parent checkout.
"""

from __future__ import annotations

import os
import sys
import types


def get_standalone_root() -> str:
    """Returns the normalized absolute directory containing this standalone app."""
    return os.path.abspath(os.path.dirname(__file__))


def bootstrap_standalone_root() -> str:
    """
    Pins `sys.path` and `sys.modules["current_model"]` exclusively to this standalone folder.
    Strips any parent or grandparent paths so a surrounding checkout cannot shadow files.
    """
    root = get_standalone_root()
    ui_sandbox_dir = os.path.join(root, "ui_sandbox")
    parent_dir = os.path.abspath(os.path.join(root, ".."))
    grandparent_dir = os.path.abspath(os.path.join(parent_dir, ".."))

    excluded = {
        os.path.normcase(parent_dir),
        os.path.normcase(grandparent_dir),
    }

    cleaned_path = []
    seen = set()
    for raw_entry in sys.path:
        if not raw_entry:
            continue
        abs_entry = os.path.normcase(os.path.abspath(raw_entry))
        if abs_entry in excluded or abs_entry in seen:
            continue
        seen.add(abs_entry)
        cleaned_path.append(raw_entry)

    # Ensure root precedes ui_sandbox_dir and everything else
    for entry in (ui_sandbox_dir, root):
        norm_entry = os.path.normcase(entry)
        cleaned_path = [
            p for p in cleaned_path if os.path.normcase(os.path.abspath(p)) != norm_entry
        ]
        cleaned_path.insert(0, entry)

    sys.path[:] = cleaned_path

    expected_init = os.path.join(root, "__init__.py")
    existing = sys.modules.get("current_model")
    needs_alias = True
    if existing is not None:
        existing_file = getattr(existing, "__file__", "") or ""
        if existing_file and os.path.normcase(os.path.abspath(existing_file)) == os.path.normcase(expected_init):
            needs_alias = False

    if needs_alias:
        for mod_name in list(sys.modules.keys()):
            if mod_name == "current_model" or mod_name.startswith("current_model."):
                del sys.modules[mod_name]

        pkg = types.ModuleType("current_model")
        pkg.__file__ = expected_init
        pkg.__path__ = [root]
        pkg.__package__ = "current_model"
        sys.modules["current_model"] = pkg

    return root
'''


def _build_root_app_source() -> str:
    return '''"""
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
'''


def _build_bat_launcher_source() -> str:
    return """@echo off
title DRACBV Energy Simulator
cd /d "%~dp0"

set "PYTHON_EXE="
if exist ".venv\\Scripts\\python.exe" (
    set "PYTHON_EXE=.venv\\Scripts\\python.exe"
) else if exist "..\\.venv\\Scripts\\python.exe" (
    set "PYTHON_EXE=..\\.venv\\Scripts\\python.exe"
)

echo ====================================================================
echo   DRACBV Energy Simulator (Standalone Combined System Workbench)
echo ====================================================================
echo.

if defined PYTHON_EXE (
    echo Using virtual environment: %PYTHON_EXE%
    "%PYTHON_EXE%" -m streamlit run app.py
    goto :done
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Using system Python from PATH...
    python -m streamlit run app.py
    goto :done
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Using Python Launcher py -3...
    py -3 -m streamlit run app.py
    goto :done
)

echo ERROR: Python 3.10+ was not found on this machine.
echo Please install Python or create a .venv and install requirements.txt.

:done
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%.
    pause
)
"""


def _build_requirements_source() -> str:
    return """# Core UI & Numerical Stack
streamlit==1.39.0
pandas>=2.0.0
numpy>=1.26.0
plotly>=5.20.0

# Geographic Solar Location Search & Interactive Maps
requests>=2.31.0
folium>=0.15.0
streamlit-folium>=0.18.0

# Excel & DRACBV A4 PDF Feasibility Report Exports
openpyxl>=3.1.0
Pillow>=10.0.0
weasyprint>=60.0
kaleido>=0.2.1
pypdf>=4.0.0

# Optional JIT acceleration for 35,040-step dispatch (falls back cleanly if omitted)
numba>=0.59.0

# Automated Regression Tests
pytest>=8.0.0
"""


def _build_run_tests_source() -> str:
    return '''"""
Standalone Test & Isolation Verification Runner
===============================================

Verifies:
  1. Strict Path Isolation: Every imported module (`current_model`, `core`,
     `models`, `ui`, `ui_sandbox`) resolves strictly inside this export folder.
  2. Combined Sandbox Physics, Sizing, Financials, Excel & PDF Regression Suite.
"""

from __future__ import annotations

import os
import sys
import unittest

_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import _bootstrap

STANDALONE_ROOT = _bootstrap.bootstrap_standalone_root()


def verify_strict_standalone_isolation() -> None:
    """Asserts that no imported package resolves outside STANDALONE_ROOT."""
    import current_model
    import current_model.core.csv_parser as csv_mod
    import current_model.models.solar as solar_mod
    import current_model.ui.common.cards as cards_mod
    import current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline as pipe_mod
    import current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine as comb_mod

    checked_modules = {
        "current_model": getattr(current_model, "__file__", ""),
        "core.csv_parser": getattr(csv_mod, "__file__", ""),
        "models.solar": getattr(solar_mod, "__file__", ""),
        "ui.common.cards": getattr(cards_mod, "__file__", ""),
        "Currentsituation_sandbox.engine.consumption_pipeline": getattr(pipe_mod, "__file__", ""),
        "Combined_sandbox.combined_sandbox_engine": getattr(comb_mod, "__file__", ""),
    }

    norm_root = os.path.normcase(os.path.abspath(STANDALONE_ROOT))
    for label, mod_file in checked_modules.items():
        if not mod_file:
            raise AssertionError(f"Module `{label}` has no __file__ attribute.")
        norm_mod = os.path.normcase(os.path.abspath(mod_file))
        common = os.path.commonpath([norm_root, norm_mod])
        if common != norm_root:
            raise AssertionError(
                f"ISOLATION BREACH: `{label}` loaded from `{norm_mod}` instead of `{norm_root}`!"
            )
    print(f"[ISOLATION OK] Verified {len(checked_modules)} package roots inside: {STANDALONE_ROOT}")


def main() -> int:
    print("=" * 72)
    print("DRACBV Energy Simulator - Standalone Verification Suite")
    print("=" * 72)
    verify_strict_standalone_isolation()

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("tests.test_combined_sandbox")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 72)
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    print(f"Summary: Ran={total}, Failures={failures}, Errors={errors}")
    print("=" * 72)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _get_pruned_package_inits() -> Dict[str, str]:
    """Returns minimal standalone `__init__.py` contents for pruned packages."""
    return {
        "__init__.py": '''"""DRACBV Energy Simulator standalone package root."""
''',
        os.path.join("core", "__init__.py"): '''"""
Standalone Core Engines Subset (`core`)
=======================================
Exports only the modules required by the DRACBV Energy Simulator.
"""

from .csv_parser import (
    read_raw_content,
    parse_csv_content,
    detect_suggested_columns,
    generate_sample_demo_csv,
)
from .load_processor import process_load_profile_data
from .metrics_engine import compute_load_profile_kpis, LoadProfileKPIs
from .synthetic_engine import (
    aggregate_synthetic_24h,
    aggregate_synthetic_year,
    generate_time_labels_24h,
)
from .market_price_engine import (
    load_market_price_series,
    list_available_market_profiles,
)

__all__ = [
    "read_raw_content",
    "parse_csv_content",
    "detect_suggested_columns",
    "generate_sample_demo_csv",
    "process_load_profile_data",
    "compute_load_profile_kpis",
    "LoadProfileKPIs",
    "aggregate_synthetic_24h",
    "aggregate_synthetic_year",
    "generate_time_labels_24h",
    "load_market_price_series",
    "list_available_market_profiles",
]
''',
        os.path.join("models", "__init__.py"): '''"""
Standalone Data Models Subset (`models`)
========================================
Exports only the dataclasses and presets required by the DRACBV Energy Simulator.
"""

from .load_component import TimeWindow, SimpleConsumer, LoadComponent, Consumer
from .contract import Contract
from .financial import CostLineItem, MonthlyPaymentRecord, FinancialCostBreakdown
from .calendar_config import CalendarConfig
from .presets import (
    PRESET_FACTORIES,
    PRESET_TEMPLATES,
    get_preset_factory,
    get_industry_preset_consumers,
    get_office_preset_consumers,
    get_ev_hub_preset_consumers,
)
from .solar import (
    SolarLocation,
    SolarPVConfig,
    SolarMonthlyYield,
    SolarKPIs,
    SolarSimulationResult,
    SolarFinancialConfig,
    SolarFinancialMetrics,
)
from .bess import BESSConfig, BESSKPIs, get_bess_presets

__all__ = [
    "TimeWindow",
    "SimpleConsumer",
    "LoadComponent",
    "Consumer",
    "Contract",
    "CostLineItem",
    "MonthlyPaymentRecord",
    "FinancialCostBreakdown",
    "CalendarConfig",
    "PRESET_FACTORIES",
    "PRESET_TEMPLATES",
    "get_preset_factory",
    "get_industry_preset_consumers",
    "get_office_preset_consumers",
    "get_ev_hub_preset_consumers",
    "SolarLocation",
    "SolarPVConfig",
    "SolarMonthlyYield",
    "SolarKPIs",
    "SolarSimulationResult",
    "SolarFinancialConfig",
    "SolarFinancialMetrics",
    "BESSConfig",
    "BESSKPIs",
    "get_bess_presets",
]
''',
        os.path.join("ui", "__init__.py"): '''"""
Standalone Common UI Subset (`ui`)
==================================
Exposes shared card and stylesheet primitives from `ui.common`.
"""

from .common.styles import apply_custom_styles
from .common.cards import render_kpi_card

__all__ = [
    "apply_custom_styles",
    "render_kpi_card",
]
''',
        os.path.join("ui", "common", "__init__.py"): '''"""Common UI helpers (`ui/common`)."""

from .styles import apply_custom_styles
from .cards import render_kpi_card

__all__ = [
    "apply_custom_styles",
    "render_kpi_card",
]
''',
        os.path.join("ui_sandbox", "__init__.py"): '''"""Standalone UI Sandbox package for DRACBV Energy Simulator."""

from .Currentsituation_sandbox.consumption.view import render_tab1_consumption

__all__ = [
    "render_tab1_consumption",
]
''',
        os.path.join("ui_sandbox", "Currentsituation_sandbox", "__init__.py"): '''"""
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
''',
        os.path.join("tests", "__init__.py"): '''"""Standalone test package for DRACBV Energy Simulator."""
''',
    }


def _patch_copied_bootstraps() -> None:
    """
    Patches ONLY the copied files inside TARGET_DIR so `_WORKSPACE_DIR` (the parent
    checkout) is never added to `sys.path`, and `_bootstrap` binds `current_model`.
    """
    # 1. Patch ui_sandbox/Combined_sandbox/app.py
    app_path = os.path.join(TARGET_DIR, "ui_sandbox", "Combined_sandbox", "app.py")
    with open(app_path, "r", encoding="utf-8") as handle:
        app_text = handle.read()

    old_app_block = """_CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
_WORKSPACE_DIR = os.path.abspath(os.path.join(_PROJECT_ROOT, ".."))
for _p in (_WORKSPACE_DIR, _PROJECT_ROOT, _UI_SANDBOX_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)"""

    new_app_block = """_CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
import _bootstrap
_bootstrap.bootstrap_standalone_root()
if _UI_SANDBOX_DIR not in sys.path:
    sys.path.insert(0, _UI_SANDBOX_DIR)"""

    if old_app_block not in app_text:
        raise ValueError(f"Expected sys.path block not found in copied {app_path}")
    app_text = app_text.replace(old_app_block, new_app_block, 1)

    with open(app_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(app_text)

    # 2. Patch ui_sandbox/Combined_sandbox/views/state_and_helpers.py
    helpers_path = os.path.join(
        TARGET_DIR, "ui_sandbox", "Combined_sandbox", "views", "state_and_helpers.py"
    )
    with open(helpers_path, "r", encoding="utf-8") as handle:
        helpers_text = handle.read()

    old_helpers_block = """_VIEWS_DIR = os.path.abspath(os.path.dirname(__file__))
_CURRENT_DIR = os.path.abspath(os.path.join(_VIEWS_DIR, ".."))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
_WORKSPACE_DIR = os.path.abspath(os.path.join(_PROJECT_ROOT, ".."))
for _p in (_WORKSPACE_DIR, _PROJECT_ROOT, _UI_SANDBOX_DIR, _CURRENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)"""

    new_helpers_block = """_VIEWS_DIR = os.path.abspath(os.path.dirname(__file__))
_CURRENT_DIR = os.path.abspath(os.path.join(_VIEWS_DIR, ".."))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
import _bootstrap
_bootstrap.bootstrap_standalone_root()
for _p in (_UI_SANDBOX_DIR, _CURRENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)"""

    if old_helpers_block not in helpers_text:
        raise ValueError(f"Expected sys.path block not found in copied {helpers_path}")
    helpers_text = helpers_text.replace(old_helpers_block, new_helpers_block, 1)

    with open(helpers_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(helpers_text)


def _patch_copied_standalone_tests() -> None:
    """
    Guards sibling-sandbox checks inside the copied `tests/test_combined_sandbox.py`
    so intentionally pruned modules (such as `BESS_sandbox`) do not fail standalone runs.
    """
    test_path = os.path.join(TARGET_DIR, "tests", "test_combined_sandbox.py")
    with open(test_path, "r", encoding="utf-8") as handle:
        test_text = handle.read().replace("\r\n", "\n")

    old_bess_check = """        # 7. Verify that hardcoded max_value=100 is gone from BESS_sandbox/view_technical.py
        bess_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "BESS_sandbox", "view_technical.py")
        )
        with open(bess_path, "r", encoding="utf-8") as f:
            bess_code = f.read()

        self.assertNotIn(
            'max_value=100,',
            bess_code,
            "Hardcoded max_value=100 must be replaced by dynamic max_sb_units",
        )
        self.assertIn("max_sb_units = max(100000, init_unit_count * 2)", bess_code)"""

    new_bess_check = """        # 7. Verify BESS_sandbox/view_technical.py only if present (pruned in standalone exports)
        bess_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "BESS_sandbox", "view_technical.py")
        )
        if os.path.isfile(bess_path):
            with open(bess_path, "r", encoding="utf-8") as f:
                bess_code = f.read()

            self.assertNotIn(
                'max_value=100,',
                bess_code,
                "Hardcoded max_value=100 must be replaced by dynamic max_sb_units",
            )
            self.assertIn("max_sb_units = max(100000, init_unit_count * 2)", bess_code)"""

    if old_bess_check not in test_text:
        raise ValueError(f"Expected BESS_sandbox check not found in copied {test_path}")
    test_text = test_text.replace(old_bess_check, new_bess_check, 1)

    with open(test_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(test_text)


def _build_standalone_readme() -> str:
    """Builds the developer-handover README for DRACBV_energy simulator."""
    return """# :material/bolt: DRACBV Energy Simulator (Standalone Combined System Workbench)

A clean, self-contained, export-ready Streamlit application modeling coupled commercial **Grid + Solar PV + Battery Storage (BESS) + Peaking Generator** microgrids at **15-minute (35,040-interval/year)** resolution, including automated **4-Pillar Electricity Billing (DSO, Supplier, Metering, Statutory Levies)**, **15-Year Financial Evaluation**, **Side-by-Side Scenario Comparison**, **Excel (.xlsx)** verification export, and **DRACBV-Branded A4 PDF Feasibility Studies**.

This folder is completely isolated and portable: it can be moved, renamed, or zipped as-is without depending on any external parent repository.

---

## :material/rocket_launch: Quick Start & Local Execution

### 1. Prerequisites
* **Python 3.10+** (tested on Python 3.11 / 3.12 on Windows)
* *(Windows PDF Note)* The optional A4 PDF generator (`weasyprint`) relies on GTK/Pango runtime DLLs on Windows; all Streamlit views, physics simulations, charts, and Excel exports run out-of-the-box without GTK.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Launch the Application
* **Option A (Windows 1-Click):** Double-click `Start_DRACBV_Energy_Simulator.bat`
* **Option B (Terminal from this folder):**
  ```bash
  python -m streamlit run app.py
  ```

### 4. Run Standalone Verification Tests
```bash
python run_tests.py
```
`run_tests.py` verifies strict standalone path isolation (guaranteeing zero accidental imports from any surrounding folder) and runs all unit tests in `tests/test_combined_sandbox.py`.

---

## :material/folder_open: Complete Folder & Module Structure

```text
DRACBV_energy simulator/
├── app.py                                      # Standalone root Streamlit entrypoint
├── _bootstrap.py                               # Path & `current_model` package alias isolation
├── __init__.py                                 # Package marker
├── Start_DRACBV_Energy_Simulator.bat           # Windows 1-click launcher
├── requirements.txt                            # Exact Python dependencies
├── run_tests.py                                # Isolation check + automated test runner
├── README.md                                   # Complete system & developer handover guide
│
├── ui_sandbox/
│   ├── __init__.py                             # Minimal sandbox package initializer
│   ├── Combined_sandbox/                       # Main application workbench
│   │   ├── app.py                              # 3-Level Clean Screen orchestrator
│   │   ├── __init__.py                         # Package exports
│   │   ├── combined_sandbox_engine.py          # Public facade re-exporting `engine/*`
│   │   ├── combined_charts.py                  # Public facade re-exporting `charts/*`
│   │   ├── combined_excel_exporter.py          # On-demand 4/5-sheet .xlsx workbook exporter
│   │   ├── assets/                             # App icon (`combined_system.ico`) & DRACBV PDF images
│   │   │
│   │   ├── engine/                             # Physics, sizing, utilization, financials & formatting
│   │   │   ├── __init__.py                     # Engine exports
│   │   │   ├── models_and_presets.py           # `ENGINE_VERSION` ("13.7"), presets & dataclasses
│   │   │   ├── formatting.py                   # EU/Anglo formatting (`USE_EU_NUMBER_FORMAT` toggle)
│   │   │   ├── solar_and_sizing.py             # PVGIS yield, cluster kernel, Dual BESS & Gen sizing
│   │   │   ├── dispatch_simulation.py          # `@_opt_njit` 35,040-step coupled dispatch & SoC kernel
│   │   │   ├── utilization_and_tables.py       # Coordinated Mix optimizer, asset usage & tables
│   │   │   ├── tariff_presets.py               # Utility presets, Currentsituation sync & summaries
│   │   │   ├── cashflow_lifecycle.py           # Monthly TOU aggregation & 15Y NPV / IRR / LCOE
│   │   │   ├── financial_engine.py             # 4-Pillar & Single-Utility bills & congestion lock
│   │   │   ├── scenario_comparison_engine.py   # Compact `float32` A/B snapshots & restore sync
│   │   │   ├── scenario_tables_and_profiles.py # 5 scenario comparison ledger tables & adapters
│   │   │   ├── bess_phase_events.py            # Battery charge/discharge contiguous event extractor
│   │   │   └── solar_phase_events.py           # Solar direct/export contiguous event extractor
│   │   │
│   │   ├── charts/                             # Plotly WebGL & SVG chart builders
│   │   │   ├── __init__.py
│   │   │   ├── dispatch_and_mix_charts.py      # GPU WebGL (`Scattergl`) Dispatch+SoC & Mix charts
│   │   │   ├── phase_overlay_helpers.py        # Hover tooltips & phase event callout layers
│   │   │   ├── financial_overview_charts.py    # 15Y TCO, waterfall bridge & monthly cashflow
│   │   │   ├── financial_isolated_charts.py    # DSO, Supplier, Tax, Solar, BESS & Gen sub-charts
│   │   │   ├── scenario_comparison_charts.py   # Multi-scenario bar/trajectory comparison figures
│   │   │   └── scenario_profile_charts.py      # WebGL profile overlay & `sync_side_by_side_yaxis`
│   │   │
│   │   ├── views/                              # 3-Level Streamlit UI panels & `@st.fragment` blocks
│   │   │   ├── __init__.py
│   │   │   ├── state_and_helpers.py            # Session state schema, cache keys & widget sync
│   │   │   ├── level1_overview_bar.py          # Top bar: Grid Limit (kW), Peak Load & switches
│   │   │   ├── subtab1_consumption.py          # 1-Click scenarios + CSV/Synthetic load ingestion
│   │   │   ├── subtab2_solar.py                # GPS search, Folium map & PV sizing form
│   │   │   ├── subtab3_battery.py              # Mode A/B BESS sizing & 4-bottleneck diagnostics
│   │   │   ├── subtab4_generator.py            # Commercial generator models, fuel & min-load
│   │   │   ├── subtab5_mix_and_rules.py        # Supply mix donut, right-sizing presets & Rules 1-3
│   │   │   ├── subtab6_isolated_pillars.py     # Shared bill HTML ledgers & isolated pillar views
│   │   │   ├── subtab6_financials_bill_and_hardware.py # Sub-tab 6.1: Tariff form & Utility presets
│   │   │   ├── subtab6_hardware_costs.py       # Sub-tab 6.2: CAPEX/OPEX inputs & asset economics
│   │   │   ├── subtab6_financials_overview.py  # Sub-tab 6 orchestrator & 6.3 15Y TCO + PDF button
│   │   │   ├── subtab7_scenario_comparison.py  # Sub-tab 7: Side-by-side A/B/Baseline workbench
│   │   │   └── level3_master_output.py         # Always-visible dispatch chart, KPIs, phase logs & Excel
│   │   │
│   │   └── pdf_report/                         # Modular DRACBV A4 PDF Feasibility Study engine
│   │       ├── __init__.py
│   │       ├── templates_and_css.py            # Letterhead, watermark & print CSS pagination
│   │       ├── chart_snapshots.py              # Light-mode Kaleido PNG rasterizer for PDF charts
│   │       └── report_builder.py               # Structured multi-page A4 PDF report assembler
│   │
│   └── Currentsituation_sandbox/               # Reused Status Quo load & billing modules (pruned)
│       ├── __init__.py
│       ├── consumption/                        # CSV Inspector & Synthetic Load Simulator UI
│       └── engine/                             # 4-Pillar DSO, Supplier, Metering & Levy accounting
│
├── core/                                       # Pruned shared numerical & parsing engines
│   ├── bess_engine.py                          # Overload & violation cluster helpers
│   ├── csv_parser.py                           # Robust multi-encoding CSV load parser
│   ├── demo_scenario.py                        # Built-in reference consumer builders
│   ├── load_processor.py                       # 15-minute timestamp alignment & gap detection
│   ├── market_price_engine.py                  # EPEX Spot NL 2025 wholesale price loader
│   ├── metrics_engine.py                       # Load KPIs & duration metrics
│   ├── solar_engine.py                         # Open-Meteo geocoding & PVGIS TMY simulator
│   └── synthetic_engine.py                     # 24h & 365-day synthetic load aggregation
│
├── models/                                     # Pruned core domain dataclasses
│   ├── bess.py
│   ├── calendar_config.py
│   ├── contract.py
│   ├── financial.py
│   ├── load_component.py
│   ├── presets.py
│   └── solar.py
│
├── ui/common/                                  # Pruned Streamlit KPI cards, gap helpers & CSS
│   ├── cards.py
│   ├── session_utils.py
│   └── styles.py
│
├── sample_data/market_prices/                  # EPEX Spot NL 2025 dataset (for Dynamic Spot mode)
└── tests/test_combined_sandbox.py              # Automated verification tests (dispatch, finance, export)
```

---

## :material/account_tree: How the Program Works

### Architecture Diagram
```mermaid
flowchart TD
    Entry["app.py & _bootstrap.py (Path Isolation)"] --> L1["Level 1: Overview Bar (Grid Limit & Feature Toggles)"]
    L1 --> L2["Level 2: 7 Modular Configuration Sub-Tabs"]
    L2 --> ST1["1. Consumption (CSV / Synthetic 35,040-step Profile)"]
    L2 --> ST2["2. Solar (PVGIS TMY & Folium GPS Map)"]
    L2 --> ST3["3. Battery (Dual Sizing & 4-Bottleneck Analysis)"]
    L2 --> ST4["4. Generator (Fuel Curve & Wet-Stacking Min Load)"]
    L2 --> ST5["5. System Mix & Rules (Supply Mix Donut & Rules 1-3)"]
    L2 --> ST6["6. Financials (4-Pillar Bill, CAPEX/OPEX, 15Y TCO & PDF)"]
    L2 --> ST7["7. Scenario Comparison (Compact float32 A vs. B Workbench)"]

    ST1 --> Kernel["Dispatch Simulator (`simulate_combined_system_dispatch`)"]
    ST2 --> Kernel
    ST3 --> Kernel
    ST4 --> Kernel
    ST5 --> Kernel

    Kernel --> L3["Level 3: Simulation Results (WebGL 2-Panel Dispatch & SoC, KPIs, Excel)"]
    Kernel --> ST6
    ST6 --> PDF["DRACBV A4 PDF Feasibility Study"]
    Kernel --> ST7
```

### Data & Simulation Lifecycle
1. **Isolated Bootstrap (`_bootstrap.py`):** Before importing application modules, `bootstrap_standalone_root()` cleans parent directories off `sys.path` and maps `current_model` directly to this folder so imports work consistently anywhere.
2. **Baseline Load Profile (`Sub-Tab 1`):** Users pick a benchmark load profile, build a synthetic facility profile, or upload custom CSV/XLSX interval data. `LoadSeries2025` holds canonical 35,040 15-minute intervals plus an `is_gap` mask that prevents artificial zero-interpolation artifacts during data outages.
3. **Coupled 15-Minute Dispatch (`engine/dispatch_simulation.py`):** Given the active Grid Limit (kW) and component switches (Solar, Battery, Generator), `_execute_coupled_dispatch_arrays` (accelerated via Numba `@_opt_njit` when available) evaluates all 35,040 timesteps under **Rules 1-3**:
   * **Rule 1:** Grid Limit peak shaving priority (protect physical fuse / contracted capacity).
   * **Rule 2:** Daily battery optimization (`Peak Reserve SoC (%)` reservation for overload safety).
   * **Rule 3:** Battery charging sources (`Solar Only`, `Solar + Grid Recharge`, etc.).
4. **4-Pillar Financials & 15-Year TCO (`engine/financial_engine.py`, `engine/cashflow_lifecycle.py`):** Evaluates baseline (`Current Situation`) vs. upgraded grid imports across DSO (regulated transport + peak demand + breach step-up), Energy Supplier (Flat / HT-NT Dual TOU / Spot), Certified Metering, and Statutory Levies, combining hardware CAPEX, OPEX, fuel costs, avoided grid upgrade credit, escalation, and discounting (NPV, IRR, Payback Period).
5. **High-Speed Visuals & Exports (`charts/dispatch_and_mix_charts.py`, `combined_excel_exporter.py`, `pdf_report/`):** Renders GPU WebGL (`go.Scattergl`) 2-panel time-series in `np.float32` buffers, generates multi-sheet `.xlsx` audit workbooks on demand, and renders multi-page DRACBV A4 PDF feasibility studies.

---

## :material/code: Developer Handover & Configuration Notes

### 1. Number Formatting Toggle (`USE_EU_NUMBER_FORMAT`)
All rendered tables, KPI cards, HTML ledgers, Plotly charts, and PDF exports default to European number grouping (`1.234,56`) via [`ui_sandbox/Combined_sandbox/engine/formatting.py`](ui_sandbox/Combined_sandbox/engine/formatting.py).
* **1-Line Switch Back to US/Anglo Formatting (`1,234.56`):** Set `USE_EU_NUMBER_FORMAT: bool = False` in `ui_sandbox/Combined_sandbox/engine/formatting.py`.
* Raw floats inside `openpyxl` `.xlsx` cells and Streamlit `st.number_input` widgets intentionally stay numeric so spreadsheets calculate reliably.

### 2. Extending the Application
* **Add or edit physical/financial formulas:** Modify the corresponding module under `ui_sandbox/Combined_sandbox/engine/` and keep public symbols re-exported via `engine/__init__.py` and `combined_sandbox_engine.py`. When dispatch outputs or cached tuple schemas change, bump `ENGINE_VERSION` in `engine/models_and_presets.py` so Streamlit session caches auto-invalidate cleanly.
* **Modify UI tabs without slowing dispatch:** Heavy charts, tariff forms, and exporters sit inside `@st.fragment` blocks in `ui_sandbox/Combined_sandbox/views/` so user edits do not trigger unnecessary full-page reruns.
* **Validate changes:** Always run `python run_tests.py` after editing engine or UI code.
"""


def _clean_target_dir(target_dir: str) -> None:
    """
    Removes existing target contents safely, tolerating transient Windows/OneDrive
    directory locks on `__pycache__` folders while deleting all `.pyc`/`.py` files.
    """
    if not os.path.isdir(target_dir):
        return

    def _on_rm_error(func, path, _exc_info) -> None:
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except PermissionError:
            pass

    for attempt in range(3):
        shutil.rmtree(target_dir, onerror=_on_rm_error)
        if not os.path.exists(target_dir):
            return
        time.sleep(0.25)

    # Fallback: sweep every remaining file if OneDrive still holds an empty dir lock
    for root, _dirs, files in os.walk(target_dir, topdown=False):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                os.chmod(fpath, stat.S_IWRITE)
                os.remove(fpath)
            except OSError:
                pass
        try:
            os.rmdir(root)
        except OSError:
            pass


def build_export() -> None:
    """Rebuilds the clean standalone `DRACBV_energy simulator` folder."""
    _clean_target_dir(TARGET_DIR)
    os.makedirs(TARGET_DIR, exist_ok=True)

    dir_count, file_count = _copy_selected_assets()

    _write_text_file("_bootstrap.py", _build_bootstrap_source())
    _write_text_file("app.py", _build_root_app_source())
    _write_text_file("Start_DRACBV_Energy_Simulator.bat", _build_bat_launcher_source())
    _write_text_file("requirements.txt", _build_requirements_source())
    _write_text_file("run_tests.py", _build_run_tests_source())
    _write_text_file("README.md", _build_standalone_readme())

    for rel_init, content in _get_pruned_package_inits().items():
        _write_text_file(rel_init, content)

    _patch_copied_bootstraps()
    _patch_copied_standalone_tests()

    print(
        f"Successfully built standalone export at: {TARGET_DIR}\n"
        f"Copied directories: {dir_count}, Copied files: {file_count}"
    )


if __name__ == "__main__":
    build_export()
