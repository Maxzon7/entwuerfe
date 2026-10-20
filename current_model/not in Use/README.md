# :material/archive: Not In Use Archive (`not in Use`)

This directory serves as the dedicated repository archive for inactive, superseded, or experimental labs, scripts, runners, and backward-compatibility shims.

---

## :material/policy: Policy & Purpose

> [!NOTE]
> **Repository Archival Policy:**
> Everything that is **not currently needed** to run either the active production application (`app.py`) or the active **Current Situation Sandbox** (`ui_sandbox/Currentsituation_sandbox/app.py`) is moved into this `not in Use/` directory.
>
> This guarantees:
> 1. The active `ui_sandbox/` workspace remains clean, focused, and immediately understandable.
> 2. No deprecated labs or shims clutter the active prototyping workflow.
> 3. Historical experiments, prototypes, and older lab implementations remain preserved for reference without impacting production code or automated test suites.

---

## :material/folder_open: Archived Components

```text
current_model/not in Use/
├── README.md                                   # This archive documentation & policy guide
│
├── monthly_baseline_lab/                       # Superseded 12-Month Baseline & Commercial Tariff Lab
│   ├── standalone_monthly_baseline_lab.py      # Streamlit lab interface
│   ├── monthly_calc.py                         # Calculation models
│   ├── monthly_presets.py                      # Tariff presets
│   ├── monthly_charts.py                       # Visualizations
│   ├── monthly_editors.py                      # Interactive tables
│   ├── monthly_audit.py                        # Audit verification panel
│   └── monthly_financial_view.py               # Financial KPI cards & exports
│
├── three_party_contract_lab/                   # Prototype 3-Party Unbundled Contract Laboratory
│   ├── minimal_contract_system.py              # Minimal prototype lab runner
│   └── README.md                               # Lab documentation
│
├── status_quo_2025/                           # Standalone Status Quo 2025 Laboratory
│   ├── status_quo_lab.py                       # Streamlit UI lab page (superseded by Currentsituation_sandbox)
│   └── README.md                               # Standalone lab architecture & notes
│
├── sandbox_app.py                              # Legacy multi-lab switcher (superseded by direct app launches)
├── standalone_monthly_baseline_lab.py          # Backward-compatibility shim for monthly baseline lab
├── minimal_contract_system.py                  # Backward-compatibility shim for three-party contract lab
└── test_monthly_baseline_lab.py                # Unit tests associated with retired monthly baseline lab
```
