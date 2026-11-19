# :material/science: UI Sandbox Suite (`ui_sandbox`) — 6 Standalone Scenario Sandboxes on a Shared Foundation

An isolated, enterprise-grade suite of **6 standalone scenario sandboxes** inside `ui_sandbox/`. Each sandbox can be launched and tested **100% independently** on its own Streamlit port while sharing the exact same **3 foundational building blocks** (`ui_sandbox/common/`) so they can later be combined into a single unified multi-scenario optimization program without refactoring.

---

## :material/foundation: The 3 Shared Architectural Building Blocks (`ui_sandbox/common/`)

1. **Building Block 1: Standardized 15-Minute Load & Residual Load (`LoadSeries2025` & `build_residual_load_series_2025`)**
   - Every scenario takes a validated 35,040-step (15-min) `LoadSeries2025` baseline as input and outputs a post-mitigation grid import profile $P_{\text{Grid}}(t)$ converted back into a canonical `LoadSeries2025` object.
   - **Data Gap Neutralization Architecture (`is_gap` boolean mask):** Automatically detects real-world measurement interruptions (> 1 hour delta in CSV records or intervals outside recorded date ranges). Strictly confines micro-interpolation to isolated 1–2 step missing points (`limit=2`), while neutralizing full multi-day/week gaps with `aligned_power[is_gap] = 0.0 kW`. Protects simulation integrity by freezing battery SoC across data gaps, zeroing dispatch power flows and eliminating phantom linear interpolation energy, false peak overloads, and artificial multi-peak cluster deficits. In Plotly visual charts, gaps are masked with `NaN` values and `connectgaps=False` to render clean, empty breaks matching the Current Situation workbench standard.
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
├── NewContract_sandbox/                        # [Scenario 2] Contract Switch & Twin-Contract Benchmark Sandbox
│   ├── __init__.py
│   ├── contract_comparison_engine.py           # 4-Pillar delta KPIs, side-by-side stacked bar, 12-month grouped bill series, audit table & 15Y TCO
│   └── app.py                                  # Standalone 3-Tab Twin-Contract Workbench (Contract 1, Contract 2 auto-cloned, Cost Comparison)
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
│   ├── solar_bess_sandbox_engine.py            # Coupled 35,040-step PV+BESS dispatch, 3-Tier BESS pre-dimensioning, dual-strategy comparison, synergy & 15Y plant LCOE
│   └── app.py                                  # Standalone 4-Tab app (Load Profile, Solar PV Site & Hockey-Stick, BESS Sizing & Coupled Dispatch, Combined Plant Economics & Contract)
│
└── Generator_sandbox/                          # [Scenario 6] Peaking Generator & Grid Congestion Sandbox
    ├── __init__.py
    ├── generator_sandbox_engine.py             # 35,040-step Willans fuel curve, "The Perfect Generator" unconstrained dimensioning, sweep & Plotly suite
    └── app.py                                  # Standalone 3-Tab app (Load Baseline, Sizing & Consolidated Visual Dispatch Suite, Ideal Peaker Optimizer)

└── Combined_sandbox/                           # [Scenario 7] Combined System Sandbox (Grid + Solar + Battery + Generator)
    ├── __init__.py                             # Package public API re-exports via combined_sandbox_engine facade
    ├── combined_sandbox_engine.py              # Backward-compatible facade re-exporting all symbols from engine/
    ├── engine/                                 # Core simulation, sizing, utilization, tariff & financial modules
    │   ├── __init__.py                         # Aggregates and exports all engine symbols
    │   ├── models_and_presets.py               # Utility DSO presets, config dataclasses, KPIs & Mix Strategy specs
    │   ├── formatting.py                       # Pure Python European number/currency formatter (`fmt_num`, `fmt_curr`) & 1-line `USE_EU_NUMBER_FORMAT` rollback switch
    │   ├── solar_and_sizing.py                 # PVGIS/hourly solar model, cluster deficit kernel & dual/BESS/gen sizing
    │   ├── dispatch_simulation.py              # 35,040-step 4-source coupled dispatch kernel & hourly dataframe builder
    │   ├── utilization_and_tables.py           # Coordinated Mix Workbench optimizer, utilization diagnostics & summary tables
    │   ├── tariff_presets.py                   # Official NL & EDEMSA Single-Utility presets, Currentsituation sync & summary builder
    │   ├── cashflow_lifecycle.py               # TOU/component monthly aggregator & 15-year escalated cashflow/NPV/IRR engine
    │   ├── financial_engine.py                 # 4-Pillar & Single-Utility bill calculator, congestion lock & component economics
    │   ├── scenario_comparison_engine.py       # Pure Python lightweight snapshot capture, 1..N leaderboard/matrix, A/B preset pair & restore sync
    │   └── scenario_tables_and_profiles.py     # Pure Python 5-domain tables, upgrade payback check & zero-rerun `snapshot_to_sim_view` adapter
    ├── combined_charts.py                      # Backward-compatible facade re-exporting all Plotly charts from charts/
    ├── charts/                                 # Plotly interactive chart builders
    │   ├── __init__.py                         # Aggregates and exports all chart builders
    │   ├── dispatch_and_mix_charts.py          # Synchronized 2-in-1 15-min dispatch & SoC figure, Supply Mix & Utilization charts
    │   ├── financial_overview_charts.py        # 15Y TCO curve, Cashflow waterfall & CAPEX/OPEX breakdown charts
    │   ├── financial_isolated_charts.py        # Isolated Pillar 1-4 & component cost/payback charts
    │   ├── scenario_comparison_charts.py       # 6 1..N-ready scenario comparison charts (15Y TCO, Year-1 Stack, CAPEX/OPEX Shift, Supply/Util, Monthly Peak/Import, Energy Flow)
    │   └── scenario_profile_charts.py          # 1..N-ready 15-min WebGL Load Profile Overlay & side-by-side `sync_side_by_side_yaxis` utility
    ├── combined_excel_exporter.py              # 4-Sheet (or 5-Sheet incl. Scenario Comparison) .xlsx verification workbook exporter via openpyxl
    ├── views/                                  # Modular Streamlit Level 1-3 UI views & @st.fragment components
    │   ├── __init__.py                         # Aggregates view renderers, styles, and state/tuple helpers
    │   ├── state_and_helpers.py                # CSS theme, hot-reload guards, session defaults & simulation tuple helpers
    │   ├── level1_overview_bar.py              # Level 1 compact KPI summary bar
    │   ├── subtab1_consumption.py              # Sub-tab 1: Load profile selector, auto tariff sync, upload & peak overview
    │   ├── subtab2_solar.py                    # Sub-tab 2: Solar capacity, array geometry & yield preview
    │   ├── subtab3_battery.py                  # Sub-tab 3: BESS kW/kWh, C-rate & dual-mode sizing
    │   ├── subtab4_generator.py                # Sub-tab 4: Backup generator capacity, fuel & winter cluster sizing
    │   ├── subtab5_mix_and_rules.py            # Sub-tab 5: Coordinated Mix Workbench & dispatch priority rules
    │   ├── subtab6_isolated_pillars.py         # Sub-tab 6 shared HTML/currency sub-ledger & Monthly/Pillar @st.fragment views
    │   ├── subtab6_financials_bill_and_hardware.py # Sub-tab 6.1: Bill structure (4-Part vs Single Utility), Presets, 2/3-Window Tariff editor
    │   ├── subtab6_hardware_costs.py           # Sub-tab 6.2: Technical profiles, unit rates, >0 lump-sum overrides & isolated asset charts
    │   ├── subtab6_financials_overview.py      # Sub-tab 6.3 & orchestrator: 15-Year Projection, Summary & Chart Gallery
    │   ├── subtab7_scenario_comparison.py      # Sub-tab 7: @st.fragment Scenario A vs. Scenario B vs. Current Situation comparison & Live Restore
    │   └── level3_master_output.py             # Level 3 permanent master summary, dispatch/mix charts & Excel export
    └── app.py                                  # Lean 3-Level Streamlit entrypoint wiring views/ & 15-min simulation cache
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

## :material/tune: Scenario 2: Standalone Contract Switch & Twin-Contract Benchmark Sandbox (`ui_sandbox/NewContract_sandbox/`)

The Contract Switch Sandbox provides a twin-contract workbench allowing rapid side-by-side benchmarking of your current commercial electricity contract against an alternative supply contract or right-sized capacity:

* **Top Header & Baseline Selector:** Active 35,040-step consumption profile with 1-click verified benchmarks (Rotterdam Stedin WKO, EDEMSA Bodegas Salentein, Enexis, Liander) or custom 15-minute CSV upload.
* **Tab 1: Contract 1 — Current Situation (Baseline Contract):**
  * Exact layout of the Current Situation contract workbench ([`ui_sandbox/Currentsituation_sandbox/contract/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/Currentsituation_sandbox/contract/view.py)).
  * General Market Structure & Currency Settings + Benchmark Presets Quick-Loader.
  * Live Master Bill Equation Bar + Simulation Assumptions Register Banner.
  * 5 Actor Sub-Tabs: Grid Network (DSO), Energy Supply (Retailer), Metering & Taxes, Executive Overview & 15Y TCO, and Classic Electricity Bill.
* **Tab 2: Contract 2 — Alternative Contract (Switch Setup):**
  * Identical layout and sub-tabs to Tab 1, operating with independent state.
  * **Auto-Cloned by Default:** Contract 2 initializes identically to Contract 1 so users can test changes (e.g. switch the Retailer in Sub-tab 2 from Fixed to EPEX Spot, or adjust contracted capacity in Sub-tab 1) without re-entering parameters.
  * Includes a 1-click `:material/content_copy: Reset / Sync from Contract 1` button.
* **Tab 3: Cost Comparison & Delta Analytics (Contract 1 vs. Contract 2):**
  * **Executive Delta Status Banner:** Instant notification of Net Annual Cost Savings / Surcharges.
  * **5 Executive Delta KPI Cards:** Annual Net Bill Delta, Annual Gross Bill Delta (incl. VAT), Pillar 1 (Supply) Delta, Pillar 2 (DSO) Delta, and Effective Blended Rate Delta (EUR/kWh).
  * **Interactive Plotly Suite:**
    * 4-Pillar Side-by-Side Cost Comparison (Stacked Bar Chart).
    * 12-Month Net Invoices Grouped Bar Chart (Month-by-month bill series & delta line).
    * 15-Year Life-Cycle Cumulative Cost & TCO NPV Trajectory.
  * **Detailed 4-Pillar Line-by-Line Comparative Audit Table:** Complete reconciliation of all 4 cost pillars, standing fees, capacity charges, and volumetric rates.
  * **Grid Capacity & Breach Diagnostics:** $P_{\text{contract}}$, Peak Overload, Breach Months, and Excess Penalties.
  * **Export & Master Integration:** CSV comparison table download, standardized `ScenarioEvaluationOutput` container, and JSON export.

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

## :material/battery_charging_full: Scenario 5: Hybrid Solar PV + BESS Sandbox (`ui_sandbox/SolarBESS_sandbox/`)

The Hybrid Solar PV + BESS Sandbox unites the physical Solar PV workbench from `Solar_sandbox`, the intelligent battery sizing diagnostics from `BESS_sandbox`, and the coupled 15-minute hybrid engine into a self-contained **4-Tab Workbench**:

* **Header & Global Action Bar:**
  * Active Load Baseline status banner (35,040 steps, Annual Energy kWh, Unmitigated Peak kW, Session Reset).
  * **Interactive Grid Connection Limit ($P_{\text{limit}}$ in kW) Controller (outside forms):** Live number input with ±25 kW steppers and quick Peak % buttons (`80% Peak`, `65% Peak`, `50% Peak`).
  * **1-Click Reference Hybrid Case Loaders:** `Mendoza Winery (270 kWp PV + 500 kWh / 250 kW BESS)` and `Rotterdam WKO (153 kWp PV + 300 kWh / 150 kW BESS)`.
* **Tab 1: Facility Load & Consumption Profile (1:1 from Currentsituation_sandbox):**
  * Seamless switch between real 15-minute CSV smart meter measurements and the synthetic 24h/365-day load simulator.
* **Tab 2: Solar PV Site, Sizing & Generation Baseline (Imported from Solar_sandbox):**
  * **1. Geographic Location & Solar Radiation Site:** City search, presets, interactive Folium map, and GPS coordinates.
  * **2. Technical PV Specification Form:** Module count $\times$ wattage ($W_p$), cell technology (`TOPCon`, `PERC`, `Backcontact`), tilt/azimuth, and inverter sizing.
  * **3. Solar Generation Baseline & Free BESS Charging Pool:** 4 KPI cards (`Annual Solar Yield`, `Specific Yield`, `Direct PV Self-Consumption (No BESS)`, and `Available PV Surplus for BESS` as the bridge to Tab 3).
  * **4. Solar Generation Profile Timeseries (15-Minute Resolution):** Interactive high-resolution generation profile chart with range slider, plus collapsible Monthly Energy Production & Physical Loss Waterfall expander.
  * **5. Hockey-Stick Auto-Sizing & Demand Coverage Curve:** 1-click demand presets (`40%`, `Sweet-Spot 55%`, `60%`, `80%`, `100% Net-Zero`) + interactive Hockey-Stick Pareto chart.
* **Tab 3: BESS Sizing & Coupled Hybrid Dispatch (Core Hybrid Engine):**
  * **1. Intelligent Battery Pre-Dimensioning:** Diagnoses post-solar net load ($P_{\text{Load}} - P_{\text{PV, Direct}}$) and daily solar surplus. Features a collapsible **One-Click BESS Dimensioning Recommendations Expander** with 3 sizing tiers:
    * *Tier 1: Peak-Shaving Focus (100% Zero-Breach)*
    * *Tier 2: Self-Consumption Focus (Solar Surplus Buffer)*
    * *Tier 3: Double-Lever Optimum (Peak Shaving + Solar Cycle Buffer)*
  * **2. BESS Hardware & Coupled Dispatch Strategy Form (`st.form`):** Capacity (kWh), Inverter Power (kW), Chemistry (LFP/NMC), RTE %, $\text{SoC}_{\min}$/$\text{SoC}_{\max}$, Peak Reserve SoC %, preventive grid recharging toggle, and EMS Strategy selector:
    * *Strategy 1 (`peak_shaving_priority`):* Reserves BESS strictly to cap $P_{\text{Grid}}(t) \le P_{\text{limit}}$.
    * *Strategy 2 (`hybrid_self_cons_and_peak`):* Double-lever cycling of midday solar surplus into evening/night demand while maintaining a protected peak-shaving reserve floor.
  * **3. Coupled Dispatch Performance & Strategy Comparison:** 8 Executive Hybrid KPI cards + side-by-side comparison table of Strategy 1 vs. Strategy 2 on identical hardware.
  * **4. Interactive Hybrid Dispatch & Synergy Visualizations (4 Sub-Tabs):**
    * `:material/timeline: 2-in-1 Synchronized Dispatch & SoC`: Shared X-axis 15-minute active power flow and battery SoC % with `7D`, `1M`, `3M`, `All` buttons and Peak Demand Week zoom toggle.
    * `:material/bar_chart: Monthly Energy Balance`: 12-month stacked bar of Direct PV, BESS Discharge, and Residual Grid Import.
    * `:material/schema: Hybrid Energy Flow (Sankey)`: Complete energy flow diagram including BESS round-trip losses and green charging share.
    * `:material/compare_arrows: Synergy Benchmark (PV vs. BESS vs. Hybrid)`: 4-stage comparison (Status Quo vs. Solar-Only vs. BESS-Only vs. Hybrid PV+BESS).
* **Tab 4: Combined Plant Economics (CAPEX/OPEX/LCOE) & Master Contract:**
  * Combined Turnkey Cost & Mid-Life Augmentation Form (Year 11 cell augmentation reserve).
  * 4 Primary Financial KPI Cards (`Combined Total CAPEX` with PV/BESS % split, `Combined Annual OPEX`, `Discounted Hybrid LCOE`, `Specific Cost per Shaved kW`).
  * Turnkey CAPEX Breakdown Donut Chart, 15-Year Plant Outflow & Cumulative Trajectory, and 15-Year Ledger Table.
  * Standardized Master Integration Data Contract stored in `st.session_state["solar_bess_standalone_result"]` with JSON export.

---

## :material/local_gas_station: Scenario 6: Standalone Generator & Grid Congestion Sandbox (`ui_sandbox/Generator_sandbox/`)

The Generator Sandbox replicates the exact UI layout and proven calculation components of the main program ([`ui/tab_generator/`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab_generator/view.py)) into an isolated, standalone workbench equipped with **"The Perfect Generator"** dimensioning diagnostic:

* **Header Action Controls:** Quick `Load Example Case (Liander 400 kW Grid Congestion Benchmark)` and `Reset / Clear Generator` action buttons.
* **Tab 1: Facility Load & Consumption Profile (1:1 from Currentsituation_sandbox / Main App):**
  * Ingestion switch between real CSV meter data (with delimiter sniffer & timestamp mapper) and synthetic 24h/365d simulation.
  * Interactive 35,040-step 15-minute load profile chart, annual Load Duration Curve (LDC), and 4 Base KPIs.
* **Tab 2: Standalone Generator Sizing, Ideal Peaker & Fuel Economics (1:1 with Main Program UI):**
  * **1. Interactive Grid Limit Controller (outside form for instant live reactivity):** Numerical input with ±25 kW steppers and quick presets (`80% Peak`, `50% Peak`, `Default 400 kW`).
  * **2. Diagnostic Status Cards:** `Facility Peak Demand (kW)`, `Contracted Grid Limit (kW)`, `Overload Status (+kW Overload / Within Limit)`, and `Configured Capacity (kW)`.
  * **3. "The Perfect Generator" Diagnostic Blueprint & Sizing Recommendations:**
    * Inspired by the unconstrained BESS diagnostics, evaluates unconstrained generator dispatch to completely eliminate all grid breaches.
    * 4 Diagnostic KPI Cards: `Peak Grid Overload (kW)`, `Annual Overload Energy (MWh/a)`, `Longest Continuous Run (hrs)`, and `Safe Tank Autonomy (L or m³: worst run + 48h emergency reserve)`.
    * Wet-Stacking Risk Warning: Identifies if engine loading drops below 25% nameplate capacity.
    * 3 Sizing Tiers with 1-Click Auto-Configure into the form below:
      * **Tier 1: 100% Zero-Breach Champion:** Continuous rated capacity guaranteeing zero overload with 10% safety margin.
      * **Tier 2: 80% Economic Sweet Spot:** Capping 80% of peak breach with optimal CAPEX/fuel balance.
      * **Tier 3: 50% Peak-Assist Model:** Handles top 50% peaks, ideal for pairing with BESS or demand response.
  * **4. Generator Technical & Commercial Sizing Form (`st.form` template for Master Program):**
    * Model Presets (`100 kW Mobile Diesel Peaker`, `250 kW Heavy Industrial Diesel`, `500 kW Containerized Natural Gas CHP`, `Custom`).
    * Technical parameters: Continuous rated power (kW), operational dispatch strategy (`Peak Shaving Assist` vs. `Full Residual Backup`), dispatch trigger threshold (kW), fuel type (`Diesel`, `Natural Gas`, `HVO/Biofuel`), fuel price, maintenance cost/hour, and minimum loading ratio slider (0-50% to prevent wet-stacking).
    * Commercial parameters: Acquisition model (`Rental / Monthly Lease` vs. `Capital Purchase (CAPEX)`), turnkey CAPEX or monthly equipment lease fee.
  * **5. Executive KPI Results Cards:** `Shaved Peak Demand (kW)`, `Generator Runtime (hrs & starts)`, `Fuel Consumption (L or m³ & OPEX)`, and `Net Annual Impact (EUR/a)`.
  * **6. Consolidated Visual Dispatch & Financial Analysis Suite (4 Sub-Tabs):**
    * `:material/timeline: 15-Minute Dispatch Timeseries`: 35,040-step profile with interactive filter buttons (`7D`, `1M`, `3M`, `All`), range slider, generator active power area, residual grid import line, and red dashed grid limit line.
    * `:material/bar_chart: Monthly Generation & Fuel Breakdown`: 12-month dual-axis chart (Generator MWh on primary axis, fuel units on secondary axis).
    * `:material/schema: Energy Flow (Sankey)`: High-level energy flow diagram tracing Grid Import and Generator Output into Facility Demand.
    * `:material/payments: Commercial Payment Schedule & Amortization`: Cumulative payment trajectory comparing Status Quo vs. With Generator and detailed monthly ledger table.
* **Tab 3: Parametric Capacity Sweep & Master Integration:**
  * **1. Active Generator Dispatch vs. Grid Congestion:** 8 coupled performance cards (`Shaved Peak Demand`, `Avoided Overload Hours %`, `Generator Generation MWh`, `Fuel Consumption`, `Operating Hours & Starts`, `Total Operating Cost`, `Avoided Overload Energy MWh`, `Residual Grid Purchase MWh`).
  * **2. Parametric Capacity Sweep & Sizing Tradeoff Curve:**
    * Interactive sweep curve visualizing Avoided Overload % vs. Generator Rated kW vs. Fuel Consumption, plus quick sweep target buttons.
  * **3. Developer & Master Integration Data Contract:**
    * Stores 35,040-step $P_{\text{Residual}}(t) = \max(0, P_{\text{Load}}(t) - P_{\text{Gen}}(t))$ into `st.session_state["generator_standalone_result"]`.
    * One-click JSON download button for Phase 2 multi-scenario billing integration.

---

## :material/grid_view: Scenario 7: Combined System Sandbox (`ui_sandbox/Combined_sandbox/`)

The Combined System Sandbox serves as the official UX reference standard under the **Clean Screen Policy**, uniting **Grid, Solar, Battery, Generator, and Lazy-Loaded Financials** in a **3-Level Modular Architecture**:

* **Level 1 (Top — System Overview Bar):**
  * **Grid Limit (kW) & Peak Demand:** Form-encapsulated numerical input for the contracted Grid Limit (`st.form("comb_grid_limit_form")` with `Apply Limit` button) displayed right next to the facility's measured Peak Demand (kW) and overload status.
  * **Global Module Activation Switches:** Toggles for `Solar`, `Battery`, `Generator`, and `Financials`. All add-on modules start **deactivated (OFF)** by default.
  * **Lazy-Loaded Financials Performance Rule:** While `Financials` is deactivated, only the fast 35,040-step physical 15-minute simulation runs. The 4-Pillar tariff billing and 15-year lifecycle cashflow engine only execute when `Financials` is activated.
* **Level 2 (Middle — 7 Modular Sub-Tabs with 1-Click Activation):**
  * If a sub-tab is inactive, its form controls are disabled/grayed out and a prominent primary button `Activate [Module]` inside the sub-tab enables immediate 1-click activation.
  * **Subtab 1: Consumption (Always Active, `@st.fragment` & Session-Cached):**
    * 1-Click Example Profiles (`Bakery 250 kW`, `Rotterdam WKO 110 kW`, `Heavy Logistics 550 kW`, `Salentein Mendoza 430 kW`) in `st.form("comb_ref_scenario_form")`, alongside `Upload CSV Data` (`1. Upload CSV or Demo Data`, `2. Select Columns & Units`, `3. Date Filter`, `4. Load Profile Chart`, `5. Full-Year Reference Profile`) and `Custom Profile Builder`.
    * **Session-Cached CSV & Synthetic Computation Pipelines:** Caches raw CSV parsing (`_get_parsed_raw_csv_cached`), gap detection (`detect_load_profile_gaps`), restored baseline metadata, and synthetic 24h/365d profile aggregations (`_compute_synthetic_baseline_cached` keyed by consumer & holiday fingerprint).
    * **Granular `@st.fragment` UI Isolation (`consumption/csv_inspector/view.py` & `consumption/synthetic/view.py`):** Isolates CSV header previews (`_render_csv_header_preview_fragment`), sub-meter selection & grid-limit preview charts (`_render_csv_submeter_and_preview_fragment`), lazy on-demand raw curve/table expanders (`_render_optional_raw_inspection_fragment`), restored CSV inspection controls (`_render_restored_inspection_controls_fragment`), synthetic `.drac` export widgets (`_render_synthetic_export_fragment`), and synthetic 24h/365d horizon + chart toggles (`_render_synthetic_inspection_and_charts_fragment`) so local interactions never rerun downstream modules (`scope="app"` only when explicitly confirming data or changing header skip count).
    * **2-Step "Inspect & Confirm" Sub-Meter Ingestion Workflow:** Upon CSV upload (or demo loading), displays detected sub-meters (`Select Meters & Total Load`) allowing the user to selectively include/exclude loads, recalculate the aggregated `Total_Demand_kW`, and click `:material/check_circle: Confirm Total Load`.
    * **Data Gap Detection & Neutralization Banner:** Explicit notification identifying detected measurement interruptions (> 1 hour) with exact dates and duration (e.g. 22.5 days in Feb, 10.3 days in Aug). Confines micro-interpolation to <= 2 steps, preserving true data gaps as empty with `NaN` breaks in the load profile preview chart rather than connecting them with artificial linear ramps.
    * **Clean Confirmed Profile Status Card:** Once confirmed, collapses the raw multi-trace chart and column selectors into a sleek 1-container summary banner with an `:material/edit: Edit / Change Sub-Meters` button and a lazy-loaded optional inspection expander. Downstream modules (and Level 3 Master Dispatch) simulate strictly the single confirmed Total Demand series, eliminating >250,000 SVG elements from the active DOM.
    * 4 Base KPIs (`Annual Consumption`, `Peak Demand`, `Average Load`, `Overload above Grid Limit`) computed strictly across valid non-gap measurements.
  * **Subtab 2: Solar:**
    * City search, location presets, and manual `Latitude (°N)` / `Longitude (°E)` inputs encapsulated in `st.form("comb_solar_location_form")` (`Apply Location`, Default: `Amsterdam`) + collapsible `@st.fragment` interactive Folium click-to-pin map (`Location Map & Pin Selection`) + data source line (`Data source: EU PVGIS (ERA5 15-min TMY) | Specific Yield: X kWh/kWp/year`).
    * Clean 3-Column Sizing Form (`st.form("comb_solar_form")`) focusing strictly on core simulation inputs: Column 1 (Sizing Mode `% of Annual Consumption` vs `Direct kWp`, Share of Consumption %), Column 2 (Direct Size kWp, `Disable Inverter AC Limit`, Inverter AC Limit kW `0 = Auto` with live auto-sized readout), Column 3 (Inverter Efficiency % slider default 98%, `Update Solar Settings & Run Simulation` submit button), keeping map clicks, preset dropdown, and Tab 5 System Mix synchronized via `comb_pending_solar_*` queues.
    * Dynamic live calculation box (`Calculation: (Annual kWh × Share %) / Specific Yield = Installed kWp`) paired with a plain-language `How Solar Sizing & Weather Data Work` explainer covering the `20% / 40% / 60% / 100%` annual share presets, why 100% annual PV generation does not equal 100% direct self-consumption, and the EU PVGIS ERA5 TMY weather basis, plus the standalone `Solar Production` expander with hover phase energies, legend-toggleable `Solar Phase Energy (kWh)` peak labels, and collapsible `Daily Solar Production Log (Energy per Day)`.
  * **Subtab 3: Battery (1:1 with BESS Sandbox Physics & Layout):**
    * **Block 1: `1. Recommended Battery Size`:**
      * Mode Switcher (`Mode A – Standalone (Battery only)` vs. `Mode B – Coupled (With active Solar / Generator & Rules)`) wrapped inside `@st.fragment` (`_render_battery_reference_fragment`) displaying an active assumptions banner (`Rule 1/2/3`, Solar & Generator coupling). Mode B uses `_calibrate_coupled_bess_capacity_kwh` (binary search over `_execute_coupled_dispatch_arrays`) to match the real 35,040-step coupled dispatch without 4x reserve-window inflation.
      * 4 Metric Cards: `Min. Required Gross Capacity (kWh)`, `Min. Required Usable Energy (kWh)`, `Min. Required Discharge Power (kW)`, and `Worst Multi-Peak Cluster Duration (hrs)`.
      * 1-Click Quick Apply Buttons: `Apply 100% Zero-Overload` (primary), `Apply 80% Quick-Size`, and `Apply 50% Quick-Size` (80%/50% scale energy capacity kWh while preserving 100% required peak discharge power kW; 1-click activation also seeds coupled defaults on first enable).
    * **Block 2: `2. Battery Size & Settings` (`st.form("comb_battery_form")`):**
      * `Lock to Standard 0.5 C (2-Hour Storage: Capacity kWh = 2 × Battery Power kW)` checkbox.
      * 3-Column Clean Form:
        * Column 1 — Modular Storage Units: Scale-Aware Modular Storage Units (`determine_smart_modular_units`) provisioning realistic hardware tiers (50 kWh racks for $\le 500\text{ kWh}$, 100/250 kWh cabinets up to $2,500\text{ kWh}$, 500 kWh blocks up to $10,000\text{ kWh}$, and 1,000/2,500 kWh containerized systems for mega scale), with crash-proof dynamic widget bounds and defensive value clamping preventing `StreamlitValueAboveMaxError`. Inputs: `Modular Unit Count`, `Capacity per Unit (kWh)`, live `Configured Gross Nameplate: X kWh`.
        * Column 2 — Inverter Power & Efficiency: Unified bidirectional `Battery Power (kW)` (for charge & discharge) and `Round-Trip Efficiency (RTE %)` slider (70%–98%).
        * Column 3 — State of Charge Boundaries: `SoC Minimum Buffer (%)` (0%–40%), `SoC Maximum Limit (%)` (60%–100%), and `Usable DoD Window: X%`.
      * Form Submit Button: `Update Battery Settings & Run Simulation`.
    * **Block 3: `3. System Limit Check`:**
      * Root-cause Feasibility & Utilization Banners distinguishing **Inverter Power Bottleneck (`kW`)**, **Energy Capacity Bottleneck (`kWh`)**, **Recharge Headroom Deficit**, and **Battery Oversized (`Min SoC > 50%`)**.
      * 4 Simultaneous Diagnostic Metric Cards: `Inverter Discharge Power`, `Storage Capacity (Multi-Peak Clusters)`, `Recharge Inverter Power`, and `Grid Recharge Headroom`.
      * Expandable `Sizing Comparison Table`.
  * **Subtab 4: Generator (With Dual-Sizing & Model Presets):**
    * **Block 1: `1. Recommended Generator Size`:** Mode A/B switcher inside `@st.fragment`, 4 Diagnostic Cards (`Min. Required Power kW`, `Annual Peaking Energy MWh`, `Longest Continuous Run hrs`, `Recommended Fuel Tank L`), and 100%/80%/50% quick buttons.
    * **Block 2: `2. Generator Models` (`st.form("comb_gen_preset_form")`):** 7 commercial models (`50 kW Small Diesel`, `100 kW CAT DE110`, `200 kW CAT DE220`, `500 kW Cummins QSK19`, `150 kW Volvo Penta HVO100`, `250 kW INNIO Jenbacher Natural Gas`, `Custom`).
    * **Block 3: `3. Generator Size & Settings` (`st.form("comb_generator_form")`):** 3 clean columns: `Generator Power (kW)`, `Fuel Type` (`Diesel`, `Natural Gas`, `HVO`), and `Minimum Load (%)` (15–50% wet-stacking protection).
  * **Subtab 5: `5. System Mix & Rules` (Supply Mix, Asset Utilization & Right-Sizing Cockpit):**
    * **Section 1 (`1. Where Your Electricity Comes From & How Much You Use It`, reusable `@st.fragment` `render_supply_mix_and_utilization_overview`):** Powered by `SystemUtilizationDiagnostics` / `compute_system_utilization_diagnostics` across `create_supply_mix_pie_figure` (Plotly Donut chart + 4-row `MWh/yr`, `%`, and peak contribution table across Grid Direct, Solar Direct, Battery Discharge, and Generator Output) and `create_component_utilization_bars_figure` (0–100% stacked horizontal bars comparing Actively Used % vs. Unused / Idle Reserve % across Solar Yield MWh, Battery Capacity kWh, and Generator Power kW, with plain-language right-sizing callouts and `bess_right_sized_kwh` target).
    * **Section 2 (`2. Adjust System Mix (Right-Sizing)`):** Provides 4 direct 1-click actions (`Trim Unused Battery Capacity`, `Compact 2h Battery + Generator Backup`, `100% Battery (No Generator)`, `100% Generator (No Battery)`) plus a 4-column `st.form("comb_system_mix_form")` (`Grid Limit`, `Solar Target`, `Battery Size`, `Generator Backup` + auto-size checkbox) with `Preview Mix` -> Current vs. Proposed Mix comparison table and `Apply Mix to System`.
    * **Section 3 (`3. Dispatch Interaction Rules` in `st.form("comb_rules_form")`):** Plain-language callout banner explaining automatic Solar direct priority + all 3 operating rules: **Rule 1 – Peak Priority**, **Rule 2 – Daily Battery Use** (`Peak Reserve SoC (%)` slider; reverts to Peak Shaving mode when Solar is inactive), and **Rule 3 – Charging Sources** (defaulting to `solar_and_grid` via `InteractionRulesConfig`, supporting Options A–D).
    * **Cache Synchronization (`ENGINE_VERSION` = "13.7") & High-Speed Architecture:** Automatic module reloading via `importlib.reload` and session state cache invalidation ensuring simulated dispatch and sizing results are always synchronized with the current engine version. Powered by `@_opt_njit` (`numba.njit(cache=True, fastmath=True)` with CPython fallback) for `_fast_combined_dispatch_kernel` (wrapped via `_execute_coupled_dispatch_arrays`) and `_cluster_deficit_kernel`, C-level NumPy run-length vectorization, and vectorized `np.bincount` / `np.maximum.at` 12-month aggregation.
  * **Subtab 6: Financials (3-Sub-Tab, 3-Zone Sub-Ledger Workbench, `@st.fragment` Isolated, Strictly English UI):**
    * **Persistent `Annual Cost & Savings` Bar (`_render_master_cost_equation_bar`):** Always displayed at the top of Subtab 6 (`Current Situation Bill` -> `New Grid Bill` + `Hardware OPEX & Fuel` - `Solar Export Income` -> `Net Annual Savings`, plus `Net CAPEX:`, `Payback Period:`, `15-Year NPV`, and a conditional `GRID CONGESTION LOCK ACTIVE` compliance/violation badge) alongside an Economic Bottleneck banner if battery OPEX exceeds >50% of gross bill savings.
    * **Structured Across 3 Dedicated Inner Sub-Tabs Matching `Currentsituation_sandbox` Depth:**
      - **Subtab 6.1 — `1. Electricity Bill`:** Top **Strict Grid Congestion Lock** toggle (`strict_grid_congestion_mode`) with instant Compliant/Violation banner and automatic zeroing of avoided grid upgrade credits; `Utility Presets` expander (`st.form("comb_utility_preset_form")` with English tier/package labels & `scope="fragment"` reloads); Zone 1 collapsible expanders inside `st.form("comb_tariff_inputs_form")` supporting **Dual TOU (`Peak HT` Mon–Fri 07:00–23:00 / `Off-Peak NT`) vs. Single Flat Rate**, **Green Certificate & Procurement Surcharge**, split **Fixed Connection Fee** & **Fixed Transport Fee**, **Breach Capacity Step-Up**, **Annual Tax Credit**, and **VAT %**; Zone 2 itemized `Annual Electricity Bill Breakdown (Net Excl. VAT)` + Gross Incl. VAT reconciliation caption; Zone 3 `@st.fragment` `_render_monthly_grid_bill_progression_fragment`; and Zone 4 collapsible `@st.fragment` `_render_isolated_pillar_deep_dive_fragment` allowing isolated inspection of **Grid Operator Contract Only (DSO)**, **Energy Supplier Contract Only (Retailer)**, or **Metering & Statutory Taxes Only** with 4 KPIs, a dedicated Plotly chart (`create_dso_isolated_breakdown_figure`, `create_supplier_isolated_breakdown_figure`, `create_tax_isolated_breakdown_figure`), and a 12-month verification DataFrame (`dso_monthly_df`, `supplier_monthly_df`, `tax_monthly_df`).
      - **Subtab 6.2 — `2. Hardware CAPEX & OPEX`:** Collapsible expanders (`Solar CAPEX & OPEX`, `Battery CAPEX & OPEX`, `Generator CAPEX & OPEX`, `Avoided Grid Upgrade Credit (CAPEX Offset)` automatically locked when Grid Congestion Lock is active) inside `st.form("comb_hardware_costs_form")` pairing unified `CAPEX`/`OPEX` inputs (`Turnkey Solar CAPEX`, `Annual OPEX (% of CAPEX/yr)`, `Generator CAPEX (Purchase Price)`, `Lump-Sum CAPEX Override`, `Lump-Sum Annual OPEX Override`) with HTML Sub-Ledgers, followed by `@st.fragment` `_render_isolated_component_economics_fragment` providing 3 collapsible expanders (Solar, Battery, Generator) with standalone KPIs, dedicated Plotly charts (`create_solar_isolated_financial_figure`, `create_battery_isolated_financial_figure`, `create_generator_isolated_financial_figure`), and 12-month verification tables (`solar_fin_monthly_df`, `battery_fin_monthly_df`, `generator_fin_monthly_df`).
      - **Subtab 6.3 — `3. 15-Year Overview`:** `Price Increases & Lifespan` form (`st.form("comb_fin_longterm_form")`), a clean single row of **4 Headline KPI Cards** (`Total CAPEX`, `Annual Savings (Year 1)`, `Payback Period`, `15-Year Net Profit`), `System Cost Summary` HTML Sub-Ledger, collapsible `Additional Financial & Contract Indicators` expander (`Discounted Payback Period`, NPV & IRR, 15Y BCR, LCOE vs. Grid, DSO/Supplier savings & Grid Congestion Compliance), collapsible `@st.fragment` `_render_subtab6_supply_mix_bridge_fragment` embedding `render_supply_mix_and_utilization_overview` + a **Physical Energy Share (%) vs. Annual Operating Cost Share (%)** table, `@st.fragment` `_render_financial_chart_gallery_fragment` (`Financial Charts` with 4 views), lazy `@st.fragment` `_render_cashflow_table_expander_fragment` wrapping `15-Year Cashflow Table`, and lazy `@st.fragment` `_render_pdf_export_fragment` generating the DRACBV-branded A4 Feasibility Study PDF (`pdf_report/`, `weasyprint` + `kaleido` light-mode chart snapshots).
  * **Subtab 7: `7. Scenario Comparison` (`@st.fragment` Scenario A vs. Scenario B vs. Current Situation — `1..N` Ready):**
    * **Zone 1 (Snapshot Management, Quick-Generator & Consistency Guard):** Captures compact `np.float32` dispatch vectors (`grid_import_kw_f32`, `bess_soc_pct_f32`, `unmet_overload_kw_f32`, `dispatch_f32_dict`) without `float64` duplication into `st.session_state["comb_saved_scenarios"]` via `st.form("comb_save_slot_A_form")` / `st.form("comb_save_slot_B_form")`. Includes **1-Click `Quick-Generate A/B Preset Pair`** (`100% Battery` vs. `Compact 2h Battery + Generator`), **Consistency Guard** for load/tariff drift, and **1-Click `Load into Live Editor`** restoring Level 1 + Sub-Tabs 2–6 safely via staged `comb_pending_*_widget_sync` keys + `st.rerun(scope="app")`.
    * **Zone 2 (Side-by-Side Single-Scenario Scorecards):** Displays Winner summary (`Lowest CAPEX`, `Fastest Payback Period`) + Scenario A (left) vs. Scenario B (right) KPI scorecards aligned with Sub-Tab 6.3 (`Total CAPEX`, `Annual Savings (Year 1)`, `Payback Period`, `15-Year Net Profit`) and Level 3 (`Grid Peak Demand`, `Remaining Overload`, `Electricity Supply Split`, `System Operation`).
    * **Zone 3 (Visual Scenario Comparison via Proven Single-Scenario Diagrams inside `st.tabs` + Lazy `@st.fragment`):** Reconstructs lightweight view objects via `snapshot_to_sim_view` with zero dispatch re-execution and renders 3 main `st.tabs` for 0 ms client-side switching: (1) **Supply Mix & System Usage** (side-by-side Sub-Tab 5 `create_supply_mix_pie_figure` Donut + mini table & `create_component_utilization_bars_figure`), (2) **Financial Charts** (2 instant inner `st.tabs` for Sub-Tab 6.3 `15-Year TCO & Payback` and `Annual Cost Bridge` with synchronized Y-axes via `sync_side_by_side_yaxis`), and (3) **Power Flow & Battery Level** (`@st.fragment` `_render_power_flow_lazy_fragment` with default-off lazy toggles `comb_ab_show_overlay_pf` and `comb_ab_show_side_by_side_pf` so heavy 35,040-step WebGL charts only load on demand).
    * **Zone 4 (Head-to-Head Upgrade Summary & Collapsible Comparison Tables inside `@st.fragment`):** Displays the explicit **"Head-to-Head Comparison: X vs. Y"** card (`compute_incremental_bwl_evaluation`: `CAPEX Difference`, `Annual Savings Difference`, `Incremental Payback Period` incl. `Never` when dominated, and `15-Year Profit Difference` — clearly scoped as a direct comparison between the two saved options rather than against the Current Situation) above 5 collapsible `st.expander` sub-ledgers (`1. System Size & Operating Rules`, `2. Grid Limit & Electricity Supply`, `3. System Usage & Unused Capacity`, `4. CAPEX & Yearly Electricity Bill`, `5. 15-Year Costs, Payback & Profit`, all defaulting to `expanded=False`), plus full tabular export and optional 5th Excel sheet `Scenario Comparison`.

### Rollback / Revert Instructions (European Number Formatting & Unified CAPEX/OPEX Labels)
1. **1-Line Number Formatting Rollback (`USE_EU_NUMBER_FORMAT`):** Open [`ui_sandbox/Combined_sandbox/engine/formatting.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/Combined_sandbox/engine/formatting.py) and set `USE_EU_NUMBER_FORMAT: bool = False`. This immediately switches `fmt_num()`, `fmt_curr()`, `format_currency_value()`, `_fmt_curr()`, and Plotly `separators` (`get_plotly_separators()`) back to Anglo-American grouping (`1,234.56`) across all KPI cards, HTML sub-ledgers, phase badges, comparison tables, Plotly charts, and the DRACBV PDF report without modifying any downstream view or engine file. `st.number_input` widgets and raw numeric floats in `.xlsx` exports were intentionally left untouched.
2. **Display-Label Unification Scope (No Schema/Calculation Changes):** No dataclass fields, session state keys, or widget keys were changed. Unified `CAPEX` / `OPEX` / `Current Situation` / `Payback Period` display strings reside strictly in `views/subtab6_isolated_pillars.py`, `views/subtab6_hardware_costs.py`, `views/subtab6_financials_overview.py`, `views/subtab7_scenario_comparison.py`, `engine/scenario_comparison_engine.py`, `engine/scenario_tables_and_profiles.py`, and `pdf_report/report_builder.py`.
* **Level 3 (Bottom — `Simulation Results`, Always Visible Below Sub-Tabs):**
  * **Central Physical Dispatch Caching:** `simulate_combined_system_dispatch` is cached via `comb_dispatch_fp` so switching the chart timeframe or editing financials does not re-trigger the 35,040-step simulation.
  * **Synchronized `Power Flow & Battery Level` Chart (Aligned 1:1 with BESS Sandbox Standard):** 2-panel Plotly subplot driven by GPU WebGL acceleration (`go.Scattergl`) with compact `np.float32` trace buffers eliminating WebGL gap-fill polygon artifacts (`_mask_gap_for_webgl_fill` zeros gap boundaries while keeping multi-step interiors `NaN`), halving WebSocket serialization payload size, and providing 60 FPS smooth rendering across all 35,040 intervals:
    * **Upper Subplot (`15-Minute Power Dispatch in kW`):** Crisp neutral Facility Load line (`#94A3B8`), Grid Import line (`#3B82F6`) capped at limit, Solar Direct (`#FACC15`, when active), legend-toggled `Solar Total Potential (kW)` dashed amber curve (`#F59E0B`, `visible="legendonly"`), BESS Discharge (`#22C55E`, `fill="tozeroy"`), negative BESS Recharge area (`#06B6D4`, `dash="dot"`, `y=-p_bess_chg`), Generator Output (`#F97316`, when active), red Remaining Deficit area (`#EF4444`), red dashed Grid Limit line with top-left annotation, **unified hover phase energy tooltips** (`Phase: X kWh (Y h, HH:MM-HH:MM)` via `engine/bess_phase_events.py` & `engine/solar_phase_events.py`), and client-side legend-toggleable peak label traces (`BESS Phase Energy (kWh)` & `Solar Direct Phase (kWh)` via `charts/phase_overlay_helpers.py`, defaulting `visible="legendonly"`).
    * **Lower Subplot (`Battery State of Charge (% and stored kWh)`):** Dual synchronized Y-axes (Left: `SoC (%)` range `[0, 105%]` with purple curve `#A78BFA` and translucent gradient fill; Right: `Stored (kWh)` range `[0, capacity * 1.05]` with dotted curve `#C4B5FD`), labeled dashed lines for `SoC Min` and `SoC Max`, Peak Reserve line (when active), and Generator active runtime shading. Battery SoC is held constant across data gaps and rendered with clean breaks (`connectgaps=False`).
    * **Native Client-Side Timeframe Selector & Range Slider:** Driven by Plotly's native 5-button rangeselector (`1 Day`, `1 Week`, `2 Weeks`, `1 Month`, `Full Year`) on the upper axis and a synchronized range-slider (`thickness=0.05`) on the lower axis with initial 7-day focus around the annual peak load (`compute_focus_range_for_timestamps`), enabling instant client-side zooming/panning with 0ms lag and zero server reruns.
    * **Collapsible Phase Event Logs & Date-Range Summaries (`_render_bess_phase_log_expander` & `_render_solar_phase_log_expander`):** Default-collapsed `st.expander` panels inside `_render_master_dispatch_chart_fragment` providing phase-type filtering (`All` / `Discharge` / `Charge`), optional `Merge pauses <= 30 min` (`merge_gap_steps=2` synchronized with chart hover & labels), date-range AC energy totals (`summarize_bess_window_energy`, `summarize_solar_window_energy`), sortable daily/event tables, and 1-click CSV export.
    * **Feasibility Banner & On-Demand Excel Export Fragment:** Prominent `Grid Limit Met (Zero Overload)` or diagnostic bottleneck/utilization banners (distinguishing inverter `kW` clipping vs capacity `kWh` depletion vs `Min SoC > 50%` oversizing), plus an isolated `@st.fragment` (`_render_excel_export_fragment`) providing on-demand `Prepare Excel (.xlsx)` -> `Download Excel (.xlsx)` generation so normal form submissions never block on 35,040-row `openpyxl` workbook construction.
  * **Compact `System Comparison` Table:** Side-by-side comparison of active components against `Current situation`.
