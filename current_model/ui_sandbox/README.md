# :material/science: UI Sandbox & Minimal Contract Lab (`ui_sandbox`)

An isolated, minimal environment for uploading consumption CSV load profiles and configuring electricity supply contracts with live financial calculation **without having to run `app.py`**.

---

## :material/verified_user: Architectural Rules & Dependency Boundary

> [!IMPORTANT]
> **Strict One-Way Dependency Isolation:**
> 1. **Allowed (`ui_sandbox` $\rightarrow$ Project):** Code inside `ui_sandbox/` is permitted to import modules from `core/`, `models/`, and `ui/` to test live functionality against domain engines.
> 2. **Prohibited (Main Project $\rightarrow$ `ui_sandbox`):** The main application (`app.py`), core calculation engines, domain models, or production UI tabs must **NEVER** import or reference anything located in `ui_sandbox/`.
> 3. **Design Standards:** All UI prototypes must strictly adhere to the project's iconography standard (**Streamlit native Google Material Symbols `:material/<icon_name>:`**, zero cartoon emojis) and English UI text.

---

## :material/folder_open: Directory Structure

```text
current_model/ui_sandbox/
├── __init__.py                   # Module package initializer
├── minimal_contract_system.py    # Minimal CSV + Contract single-page app
├── sandbox_app.py                # Standalone Streamlit test runner
└── README.md                     # Sandbox architecture & usage guide
```

---

## :material/play_arrow: Quick Start & Execution

You can run the UI Sandbox directly with Streamlit:

### From the `current_model` directory:
```bash
python -m streamlit run ui_sandbox/sandbox_app.py
```

### From the repository workspace root:
```bash
python -m streamlit run current_model/ui_sandbox/sandbox_app.py
```
*(or run `minimal_contract_system.py` directly: `python -m streamlit run current_model/ui_sandbox/minimal_contract_system.py`)*

---

## :material/featured_play_list: Core Functionality

1. **:material/bolt: 1. Consumption (CSV Load Profile Ingestion)**:
   - Upload single/multi-channel CSV meter files or load the 15-minute demo dataset via `render_csv_inspector()`.
   - Automatic delimiter detection, column mapping, and 15-minute timeseries visualization.

2. **:material/description: 2. Electricity Contract & Live Financial Assessment**:
   - Configure contractual supply parameters with clear, accessible terminology.
   - **Monthly Contract Validity (`applicable_months`)**: Define validity periods per contract (defaulting to all 12 months). Multi-contract portfolio allows customizing different rates, capacity tariffs, and peak charges per month (e.g. Netherlands dynamic/seasonal contracts vs. standard single-tariff contracts).
   - **12-Month Coverage Overview Matrix**: Interactive visual cards display which contract governs each calendar month.
   - **Contract Duplication & Management**: Duplicate contracts with 1 click to create monthly variants (e.g., Q1 vs. Q2-Q4, Summer vs. Winter).
   - **Presets**: Includes European, Argentine, and Netherlands commercial multi-tariff presets (`Netherlands Commercial Multi-Tariff (EUR)`).
   - Computes real-time billing metrics, single-month focus breakdowns, 12-month stacked payment schedules (Zahlungsreihe), and itemized invoice tables.
