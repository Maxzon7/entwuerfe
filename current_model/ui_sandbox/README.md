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
│   ├── solar_sandbox_engine.py                 # 35,040-step PV yield, direct self-consumption, pure plant economics (LCOE) & Hockey-Stick Pareto curve
│   └── app.py                                  # Standalone 2-Tab app (Tab 1: Consumption Profile Ingestion, Tab 2: Sizing, Analytics & Pure Economics)
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
    ├── generator_sandbox_engine.py             # 35,040-step Willans fuel curve, "The Perfect Generator" unconstrained dimensioning, sweep & Plotly suite
    └── app.py                                  # Standalone 3-Tab app (Load Baseline, Sizing & Consolidated Visual Dispatch Suite, Ideal Peaker Optimizer)
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

---

## :material/wb_sunny: Scenario 3: Standalone Solar PV Sandbox (`ui_sandbox/Solar_sandbox/`)

The Solar PV Sandbox replicates the exact UI layout and proven calculation components of the main program ([`ui/tab3_solar/`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab3_solar/view.py)) into an isolated, standalone workbench:

* **Header Action Controls:** Quick `Load Example Case (Mendoza Benchmark)` and `Reset / Clear Solar` action buttons.
* **Tab 1: Facility Load & Consumption Profile (1:1 from Currentsituation_sandbox / Main App):**
  * Ingestion switch between real CSV meter data (with delimiter sniffer & timestamp mapper) and synthetic 24h/365d simulation.
  * Interactive 35,040-step 15-minute load profile chart, annual Load Duration Curve (LDC), and 4 Base KPIs.
* **Tab 2: Standalone Solar PV Generation & Financials (1:1 with Main Program):**
  * **1. Geographic Location & Solar Radiation Site:** Global city/place search (Open-Meteo Geocoding), Quick Site Presets (Mendoza, Santiago, Buenos Aires, Madrid, Berlin), interactive Folium map with click-to-pin coordinate detection, and manual GPS fine-tuning.
  * **Active Site Info Banner:** Renders active GPS coordinates, elevation, hemisphere, and optimal tilt & azimuth.
  * **2. Solar PV Technical Specifications & Generator Sizing:** TMY (Typical Meteorological Year) / historical weather mode, module quantity $\times$ rated wattage ($W_p$), active DC capacity banner, and estimated mounting area.
  * **Extended Options Expander:** Cell architecture (TOPCon, PERC, Backcontact), tilt, azimuth, inverter capacity, and system losses.
  * **Solar Financial & Turn-Key Investment Costs Expander:** Itemized CAPEX rates (Modules, Inverter, Substructure, Installation, Switchgear, Mobilization), annual O&M %, and discount rate.
  * **Primary Action:** `:material/calculate: Calculate Solar PV Generation` triggering the 35,040-step physical simulation.
  * **Sub-Tab A (Electricity Generation & Technical Yield):**
    * Weather data callout & 4 KPI cards (`Total Annual Yield`, `Specific Yield`, `Generator Sizing`, `Required Area`).
    * 15-Minute Solar Generation Timeseries Profile (POA Irradiance, DC Array Power, AC Grid Power with inverter limit line).
    * Monthly Energy Production Bar Chart, 24-hour seasonal diurnal curves, Physical Loss Waterfall, Itemized Monthly Table, and Multi-Technology Production Analysis.
  * **Sub-Tab B (Solar Financial & Turn-Key CAPEX Assessment):**
    * Quick Turn-Key Cost & Financial Parameter Tuner expander.
    * 4 Primary CAPEX & LCOE KPIs + 4 Secondary Return KPIs (Amortisation/Payback, 15Y Net Benefit, 15Y NPV, IRR %).
    * Itemized CAPEX breakdown donut chart, 15-Year Cash Flow & Cumulative Payback Waterfall, and financial ledger table.
* **Tab 3: Solar & Consumption Integration (Coupling & Hockey-Stick Auto-Sizing):**
  * **1. Coupled Dispatch Performance Metrics:** 8 KPI cards (Self-Consumption Rate %, Autarky %, Surplus Export kWh, Residual Grid Import kWh, Peak Demand Reduction kW / %, Net Energy Coverage %, Specific Yield, Direct Solar Consumption).
  * **2. Visual Dispatch Analysis (3 Sub-Tabs matching Screenshot 2):**
    * `:material/timeline: 15-Minute Dispatch Timeseries`: 35,040-step annual profile with interactive filter buttons (`7D`, `1M`, `3M`, `All`) and range slider for Facility Load, Solar AC Output, Direct Solar, PV Surplus, and Residual Grid Import.
    * `:material/bar_chart: Monthly Energy Balance`: 12-month coupled energy balance stacked bar chart.
    * `:material/schema: Energy Flow (Sankey)`: High-level energy flow diagram tracing Solar and Grid power to Direct Use, Facility Demand, and Grid Export.
  * **3. Sizing Optimization & Hockey-Stick Pareto Curve (Positioned at Bottom):**
    * Quick Auto-Sizing Presets Toolbar (40%, Sweet-Spot 55%, 60%, 80%, 100% Demand Net-Zero).
    * Interactive **Hockey-Stick Pareto Tradeoff Curve** mapping daylight coverage % vs. installed kWp and SCR %.
  * **4. Developer & Future Master Integration Data Contract:**
    * Stores 35,040-step $P_{\text{Residual}}(t) = \max(0, P_{\text{Load}}(t) - P_{\text{Direct}}(t))$ into `st.session_state["solar_standalone_result"]`.
    * One-click JSON download button for Phase 2 multi-scenario billing integration.

---

## :material/local_gas_station: Scenario 6: Standalone Generator & Grid Congestion Sandbox (`ui_sandbox/Generator_sandbox/`)

The Generator Sandbox replicates the exact UI layout and proven calculation components of the main program ([`ui/tab_generator/`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab_generator/view.py)) into an isolated, standalone workbench equipped with **"The Perfect Generator"** dimensioning diagnostic:

* **Header Action Controls:** Quick `Load Example Case (Liander 400 kW Grid Congestion Benchmark)` and `Reset / Clear Generator` action buttons.
* **Tab 1: Facility Load & Consumption Profile (1:1 from Currentsituation_sandbox / Main App):**
  * Ingestion switch between real CSV meter data (with delimiter sniffer & timestamp mapper) and synthetic 24h/365d simulation.
  * Interactive 35,040-step 15-minute load profile chart, annual Load Duration Curve (LDC), and 4 Base KPIs.
* **Tab 2: Standalone Generator Sizing & Fuel Economics (1:1 with Main Program UI):**
  * **1. Interactive Grid Limit Controller (outside form for instant live reactivity):** Numerical input with ±25 kW steppers and quick presets (`80% Peak`, `50% Peak`, `Default 400 kW`).
  * **2. Diagnostic Status Cards:** `Facility Peak Demand (kW)`, `Contracted Grid Limit (kW)`, `Overload Status (+kW Overload / Within Limit)`, and `Configured Capacity (kW)`.
  * **3. Generator Technical & Commercial Sizing Form (`st.form` template for Master Program):**
    * Model Presets (`100 kW Mobile Diesel Peaker`, `250 kW Heavy Industrial Diesel`, `500 kW Containerized Natural Gas CHP`, `Custom`).
    * Technical parameters: Continuous rated power (kW), operational dispatch strategy (`Peak Shaving Assist` vs. `Full Residual Backup`), dispatch trigger threshold (kW), fuel type (`Diesel`, `Natural Gas`, `HVO/Biofuel`), fuel price, maintenance cost/hour, and minimum loading ratio slider (0-50% to prevent wet-stacking).
    * Commercial parameters: Acquisition model (`Rental / Monthly Lease` vs. `Capital Purchase (CAPEX)`), turnkey CAPEX or monthly equipment lease fee.
  * **4. Executive KPI Results Cards:** `Shaved Peak Demand (kW)`, `Generator Runtime (hrs & starts)`, `Fuel Consumption (L or m³ & OPEX)`, and `Net Annual Impact (EUR/a)`.
  * **5. Consolidated Visual Dispatch & Financial Analysis Suite (4 Sub-Tabs):**
    * `:material/timeline: 15-Minute Dispatch Timeseries`: 35,040-step profile with interactive filter buttons (`7D`, `1M`, `3M`, `All`), range slider, generator active power area, residual grid import line, and red dashed grid limit line.
    * `:material/bar_chart: Monthly Generation & Fuel Breakdown`: 12-month dual-axis chart (Generator MWh on primary axis, fuel units on secondary axis).
    * `:material/schema: Energy Flow (Sankey)`: High-level energy flow diagram tracing Grid Import and Generator Output into Facility Demand.
    * `:material/payments: Commercial Zahlungsreihe & Amortization`: Cumulative payment trajectory comparing Status Quo vs. With Generator and detailed monthly ledger table.
* **Tab 3: Ideal Peaker Dimensioning & Sizing Optimizer ("The Perfect Generator"):**
  * **1. Active Generator Dispatch vs. Grid Congestion:** 8 coupled performance cards (`Shaved Peak Demand`, `Avoided Overload Hours %`, `Generator Generation MWh`, `Fuel Consumption`, `Operating Hours & Starts`, `Total Operating Cost`, `Avoided Overload Energy MWh`, `Residual Grid Purchase MWh`).
  * **2. "The Perfect Generator" Diagnostic Blueprint (Unconstrained Sizing Analysis):**
    * Inspired by the unconstrained BESS diagnostics, evaluates theoretical unconstrained generator dispatch to completely eliminate all grid breaches.
    * 4 Diagnostic KPI Cards: `Peak Grid Overload (kW)`, `Annual Overload Energy (MWh/a)`, `Longest Continuous Run (hrs)`, `Safe Tank Autonomy (L or m³: worst run + 48h emergency reserve)`.
    * Wet-Stacking Risk Warning: Identifies if engine loading drops below 25% nameplate capacity.
    * 3 Sizing Tiers with 1-Click Synchronization to Tab 2 Form:
      * **Tier 1: 100% Zero-Breach Champion:** Continuous rated capacity guaranteeing zero overload with 10% safety margin.
      * **Tier 2: 80% Economic Sweet Spot:** Capping 80% of peak breach with optimal CAPEX/fuel balance.
      * **Tier 3: 50% Peak-Assist Model:** Handles top 50% peaks, ideal for pairing with BESS or demand response.
  * **3. Parametric Capacity Sweep & Sizing Tradeoff Curve:**
    * Interactive sweep curve visualizing Avoided Overload % vs. Generator Rated kW vs. Fuel Consumption.
  * **4. Developer & Master Integration Data Contract:**
    * Stores 35,040-step $P_{\text{Residual}}(t) = \max(0, P_{\text{Load}}(t) - P_{\text{Gen}}(t))$ into `st.session_state["generator_standalone_result"]`.
    * One-click JSON download button for Phase 2 multi-scenario billing integration.
