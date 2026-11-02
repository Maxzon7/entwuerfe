# :material/science: UI Sandbox Suite (`ui_sandbox`) — 6 Standalone Scenario Sandboxes on a Shared Foundation

An isolated, enterprise-grade suite of **6 standalone scenario sandboxes** inside `ui_sandbox/`. Each sandbox can be launched and tested **100% independently** on its own Streamlit port while sharing the exact same **3 foundational building blocks** (`ui_sandbox/common/`) so they can later be combined into a single unified multi-scenario optimization program without refactoring.

---

## :material/foundation: The 3 Shared Architectural Building Blocks (`ui_sandbox/common/`)

1. **Building Block 1: Standardized 15-Minute Load & Residual Load (`LoadSeries2025` & `build_residual_load_series_2025`)**
   - Every scenario takes a validated 35,040-step (15-min) `LoadSeries2025` baseline as input and outputs a post-mitigation grid import profile $P_{\text{Grid}}(t)$ converted back into a canonical `LoadSeries2025` object.
2. **Building Block 2: 4-Pillar Electricity Bill Engine (`StatusQuoConfig2025` & `evaluate_scenario_4pillar_bill_comparison`)**
   - Zero blended-rate approximations: every standalone sandbox evaluates both Baseline and Mitigated/Alternative scenarios through `calculate_status_quo_master_2025` and `build_invoice_positions`, rendering side-by-side itemized 4-Pillar invoice comparisons and A4 PDF reports.
3. **Building Block 3: Standardized Scenario Evaluation Result (`ScenarioEvaluationOutput`)**
   - Every sandbox emits and exports a uniform `ScenarioEvaluationOutput` container (technical peak/energy KPIs + 4-Pillar bill savings, CAPEX, OPEX, simple payback, and 15-year TCO NPV).

---

## :material/folder_open: Complete Directory Structure

```text
current_model/ui_sandbox/
├── __init__.py                                 # Package root
├── README.md                                   # Architecture, shared foundation & execution guide
│
├── common/                                     # [Shared Foundation] 3 Core Building Blocks
│   ├── __init__.py                             # Exports common models, evaluators & loaders
│   ├── evaluation_models.py                    # ScenarioEvaluationOutput, 4-Pillar comparison UI & 15Y TCO NPV
│   └── baseline_loader.py                      # Standalone preset selector, CSV uploader & JSON snapshot I/O
│
├── Currentsituation_sandbox/                   # [Scenario 1] Status Quo Baseline & 4-Pillar Contract Workbench
│   ├── __init__.py
│   ├── app.py                                  # Standalone Streamlit entrypoint
│   ├── consumption/                            # Tab 1: 15-minute CSV & synthetic load ingestion
│   ├── contract/                               # Tab 2: 4-Pillar Contract (DSO, Supplier, Metering/Taxes, Overview, Invoice PDF)
│   └── engine/                                 # 5-Layer 2025 Unbundled & Single-Utility Calculation Engine
│
├── NewContract_sandbox/                        # [Scenario 2] Pure Contract & Capacity Optimization Sandbox
│   ├── __init__.py
│   └── app.py                                  # Standalone 4-Tab app (P_contract optimization sweep, tariff switch, 4-Pillar diff)
│
├── Solar_sandbox/                              # [Scenario 3] Standalone Solar PV & Hockey-Stick Auto-Sizing Sandbox
│   ├── __init__.py
│   ├── solar_sandbox_engine.py                 # 35,040-step PV yield, direct self-consumption & Hockey-Stick Pareto curve
│   └── app.py                                  # Standalone 4-Tab app (Site/Tech, Hockey-Stick Sizing, 4-Pillar Bill, 15Y TCO)
│
├── BESS_sandbox/                               # [Scenario 4] Standalone BESS Peak-Shaving Sandbox
│   ├── __init__.py
│   ├── app.py                                  # Standalone 4-Tab app (Load/Overload, Pareto Sizing, 4-Pillar Bill, 15Y TCO)
│   ├── baseline_presets.py
│   ├── sandbox_bess_engine.py
│   ├── sandbox_charts.py
│   ├── view_problem.py
│   ├── view_technical.py
│   ├── view_bill_comparison.py
│   ├── view_financial.py
│   └── view_optimizer.py
│
├── SolarBESS_sandbox/                          # [Scenario 5] Hybrid Solar PV + BESS Sandbox (Double Lever)
│   ├── __init__.py
│   └── app.py                                  # Standalone 4-Tab app (Strategy A Peak vs Strategy B Self-Cons+Peak, 4-Pillar Bill)
│
└── Generator_sandbox/                          # [Scenario 6] Peaking Generator & Grid Congestion Sandbox
    ├── __init__.py
    └── app.py                                  # Standalone 4-Tab app (Willans fuel curve, 4-Pillar bill vs fuel, Purchase vs Rental)
```

---

## :material/play_arrow: Quick Start: Run Any of the 6 Sandboxes Independently

```bash
# Scenario 1: Status Quo Baseline & 4-Pillar Contract Workbench
python -m streamlit run "ui_sandbox/Currentsituation_sandbox/app.py"

# Scenario 2: Contract & Capacity Optimization (Zero-CAPEX Baseline)
python -m streamlit run "ui_sandbox/NewContract_sandbox/app.py"

# Scenario 3: Standalone Solar PV & Hockey-Stick Auto-Sizing
python -m streamlit run "ui_sandbox/Solar_sandbox/app.py"

# Scenario 4: Standalone BESS Peak-Shaving & 4-Pillar Bill Comparison
python -m streamlit run "ui_sandbox/BESS_sandbox/app.py"

# Scenario 5: Hybrid Solar PV + BESS (Double Lever: kWh + kW)
python -m streamlit run "ui_sandbox/SolarBESS_sandbox/app.py"

# Scenario 6: Peaking Generator & Grid Congestion (Purchase CAPEX vs. Rental OPEX)
python -m streamlit run "ui_sandbox/Generator_sandbox/app.py"
```
