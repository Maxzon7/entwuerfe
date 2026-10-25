# :material/science: UI Sandbox (`ui_sandbox`)

An isolated, enterprise-grade sandbox environment for testing 15-minute interval CSV consumption profiles, configuring unbundled European **3-Party Electricity Contracts**, and evaluating 12-month commercial tariff baselines **without having to run `app.py`**.

---

## :material/archive: Deprecated Modules & 'not in Use' Directory Policy

> [!NOTE]
> **Repository Policy for Inactive & Deprecated Code:**
> Any prototype, lab runner, backward-compatibility shim, or experimental script that is **not currently needed** to operate the active production application or the **Current Situation Sandbox** is placed in the root **`not in Use/`** directory.
>
> Relocated to `not in Use/`:
> - `monthly_baseline_lab/` (superseded 12-month baseline lab)
> - `three_party_contract_lab/` (minimal prototype contract system)
> - `status_quo_2025/` (standalone laboratory UI)
> - `sandbox_app.py` (legacy multi-lab switcher)
> - `minimal_contract_system.py` & `standalone_monthly_baseline_lab.py` (legacy shims)
> - Associated test modules for retired labs

---

## :material/verified_user: Architectural Rules & Isolation Boundary

> [!IMPORTANT]
> **Strict One-Way Dependency Isolation:**
> 1. **Allowed (`ui_sandbox` -> Project):** Code inside `ui_sandbox/` is permitted to import domain engines, styles, and models from `core/`, `models/`, and `ui/` to test live functionality.
> 2. **Strictly Prohibited (Main Project -> `ui_sandbox`):** The production application (`app.py`), core calculation engines, domain models, or production UI tabs must **NEVER** import or reference anything located in `ui_sandbox/`.
> 3. **Design Standards:** All UI prototypes must strictly adhere to the project's iconography standard (**Streamlit native Google Material Symbols `:material/<icon_name>:`**, zero cartoon emojis) and English UI text.

---

## :material/folder_open: Directory Structure

```text
current_model/ui_sandbox/
├── __init__.py                                 # Package root exporting sandboxes
├── README.md                                   # Sandbox architecture, policies & user guide
│
├── Currentsituation_sandbox/                  # [Active Sandbox 1] Baseline Workbench
│   ├── __init__.py                             # Subpackage exports
│   ├── app.py                                  # Standalone Streamlit application entrypoint
│   ├── README.md                               # Detailed Currentsituation_sandbox documentation
│   │
│   ├── consumption/                            # Tab 1: Interval Consumption Ingestion & Visualizer
│   │   ├── __init__.py
│   │   ├── view.py
│   │   ├── csv_inspector/                      # Full 15-minute interactive Plotly inspector & metrics
│   │   └── synthetic/                          # 24-hour diurnal curve & 365-day generator
│   │
│   ├── contract/                               # Tab 2: Commercial Electricity Supply Contract & Billing
│   │   ├── __init__.py
│   │   ├── view.py
│   │   ├── form.py
│   │   ├── charts.py
│   │   └── comparison_charts.py
│   │
│   └── engine/                                 # 2025 5-Layer Unbundled Commercial Calculation Engine
│       ├── __init__.py
│       ├── config_and_models.py
│       ├── tariff_defaults_2025.py
│       ├── consumption_pipeline.py
│       ├── dso_accounting.py
│       ├── commercial_accounting.py
│       ├── status_quo_master.py
│       └── audit.py
│
└── BESS_sandbox/                               # [Active Sandbox 2] BESS Peak Shaving & Sizing Laboratory
    ├── __init__.py                             # Subpackage exports (render_bess_sandbox, main, engines, charts)
    ├── app.py                                  # Standalone Streamlit application entrypoint (2 physics tabs)
    ├── baseline_presets.py                     # Dutch industrial & commercial benchmark profiles
    ├── sandbox_bess_engine.py                  # Multi-peak clusters, simultaneous bottlenecks & Pareto tradeoff
    ├── sandbox_charts.py                       # Plotly synchronized 2-in-1 dispatch/SoC & Pareto hockey stick
    ├── view_problem.py                         # Tab 1: Current situation & 1:1 CSV load ingestion & validation pipeline
    ├── view_technical.py                       # Tab 2: 100% zero-deficit reference, manual 0.5C form, Pareto curve, 4 bottlenecks & synced chart
    ├── view_financial.py                       # Preserved for Step 2: Avoided grid upgrade CAPEX vs. BESS 15Y TCO
    ├── view_optimizer.py                       # Optional / Parametric capacity sweep & sensitivity
    └── README.md                               # Detailed BESS physics-first laboratory documentation

```

---

## :material/play_arrow: Quick Start & Execution

### 1. Run the Current Situation Sandbox
```bash
streamlit run ui_sandbox/Currentsituation_sandbox/app.py
```

### 2. Run the BESS Peak Shaving & 15Y TCO Sandbox
```bash
streamlit run ui_sandbox/BESS_sandbox/app.py
```

