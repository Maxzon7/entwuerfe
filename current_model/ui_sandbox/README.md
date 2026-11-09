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
    ├── __init__.py
    ├── combined_sandbox_engine.py              # 35,040-step 4-source coupled dispatch (Rules 1-3 incl. Option D), Dual-Sizing, 4-Bottleneck BESS Table & Lazy 4-Pillar Financials
    ├── combined_charts.py                      # Synchronized 2-in-1 15-min dispatch & SoC (% & kWh) figure + Consumption chart + Cost Comparison chart
    ├── combined_excel_exporter.py              # 4-Sheet .xlsx verification workbook exporter (Summary, 15-Min Dispatch, Monthly, Cost & Tariffs + 15Y Cashflow)
    └── app.py                                  # 3-Level Modular App (Level 1 Overview Bar, Level 2 6 Sub-Tabs with 1-Click Activation, Level 3 Permanent Master Output)
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
  * **Grid Limit (kW) & Peak Demand:** Direct numerical input for the contracted Grid Limit (kW) displayed right next to the facility's measured Peak Demand (kW) and overload status.
  * **Global Module Activation Switches:** Toggles for `Solar`, `Battery`, `Generator`, and `Financials`. All add-on modules start **deactivated (OFF)** by default.
  * **Lazy-Loaded Financials Performance Rule:** While `Financials` is deactivated, only the fast 35,040-step physical 15-minute simulation runs. The 4-Pillar tariff billing and 15-year lifecycle cashflow engine only execute when `Financials` is activated.
* **Level 2 (Middle — 6 Module Sub-Tabs with 1-Click Activation):**
  * If a sub-tab is inactive, its form controls are disabled/grayed out and a prominent primary button `Activate [Module]` inside the sub-tab enables immediate 1-click activation.
  * **Subtab 1: Consumption (Always Active):**
    * CSV upload (selected as default, with delimiter sniffer, date filter, and 15-min `kWh -> kW` conversion) plus benchmark switcher and 4 Base KPIs (`Annual Consumption`, `Peak Demand`, `Average Load`, `Overload above Grid Limit`).
  * **Subtab 2: Solar:**
    * City search & location presets (Default: `Amsterdam`) + data source line (`Data source: EU PVGIS (ERA5 15-min TMY) | Specific Yield: X kWh/kWp/year`).
    * Dual Quick-Sizing (`% of Annual Consumption`: `20% | 40% | 60% | 100%` vs. `Direct Size (kWp)`) outside the form for instant 1-click response; manual inputs (`Share of Consumption %`, `Direct Size kWp`, `Inverter AC Limit kW`, `Inverter Efficiency %`) encapsulated in `st.form("comb_solar_form")` (`Apply Solar Settings`), plus blue live calculation formula box.
  * **Subtab 3: Battery (With Fingerprint-Cached Dual-Sizing & `O(1)` 4-Criterion Bottleneck Diagnostic Table):**
    * **Dual Sizing System (`100% Zero-Overload`, `80%`, `50%`):**
      * *Mode A – Standalone (Battery only):* Required battery size (`kWh / kW`) to eliminate grid overloads 100% on its own.
      * *Mode B – Coupled (With active Solar / Generator & Rules):* Required battery size accounting for active Solar, active Generator, and the configured Interaction Rules.
      * Cached via parameter fingerprint (`comb_bess_sizing_fp`) so `compute_dual_battery_sizing` only runs once when upstream parameters change.
    * **4-Criterion Bottleneck Diagnostic Table:** Evaluates `1. Peak Discharge Power (kW)`, `2. Single Peak Event Energy (kWh)`, `3. Multi-Day Cluster Energy (kWh)`, and `4. Available Recharge Headroom` for Standalone vs. Coupled vs. Configured Battery, refreshing the `Configured Battery` & `Status` columns in `O(1)` via `refresh_bottleneck_table_configured_status`.
    * **Core Technical Parameters (`st.form("comb_battery_form")` / `Apply Battery Settings`):** `Battery Capacity (kWh)`, `Battery Power (kW)`, `Min SoC (%)` (`10%`), `Max SoC (%)` (`90%`), and `Round-Trip Efficiency (%)` (`88%`).
  * **Subtab 4: Generator (With Fingerprint-Cached Dual-Sizing):**
    * **Dual Sizing System (`100%`, `80%`, `50%`):** *Mode A – Standalone (Generator only)* vs. *Mode B – Coupled (Remaining peak after Solar & Battery)*, cached via `comb_gen_sizing_fp` / `comb_cached_dual_gen`.
    * **Minimalist Core Inputs (`st.form("comb_generator_form")` / `Apply Generator Settings`):** `Generator Power (kW)`, `Minimum Load (%)` (`25%` wet-stacking protection), and `Fuel Type` (`Diesel`, `Natural Gas`, `HVO`).
  * **Subtab 5: Interaction Rules:**
    * Explicit callout banner explaining that active **Solar** always feeds Consumption directly first, automatically lowering demand and daytime peaks before Battery or Generator step in.
    * **Rule 1 – Peak Shaving Priority (Above Grid Limit):** `Battery first, Generator as backup` vs. `Generator first, Battery for small/fast peaks`.
    * **Rule 2 – Normal Load Coverage (Below Grid Limit):** `Peak Shaving only` vs. `Self-Consumption + Peak Reserve` (with `Peak Reserve SoC %` slider).
    * **Rule 3 – Battery Charging Sources & Timing:** `Option A: Solar surplus only`, `Option B: Solar surplus + Grid headroom`, `Option C: Solar surplus + Generator excess (Cycle Charging)`, and `Option D: Solar + Grid + Generator excess`.
  * **Subtab 6: Financials (Lazy-Loaded, `st.form("comb_financials_form")` Encapsulated, 4-Pillar Tariff & Cost Comparison Chart):**
    * All cost blocks are wrapped inside `st.form("comb_financials_form")` with primary button `Calculate Financials`.
    * **Block A – Grid & Tariff Costs (Always in the 4-Pillar Tariff Module):** `1. Energy Supply (Supplier)`, `2. Grid Network (DSO & Overload Penalty)`, `3. Metering`, and `4. Taxes & Discount Rate`.
    * **Block B – Solar Turnkey CAPEX & O&M (if Solar active):** `Modules (€/Wp)`, `Inverter (€/W)`, `Mounting & Installation (€/Wp)`, and `Annual O&M (%/yr)`.
    * **Block C – Battery Turnkey CAPEX, O&M & Augmentation (if Battery active):** `Storage Racks (€/kWh)`, `Inverter (€/kW)`, `Installation & Cabling (€)`, `Annual O&M (%/yr)`, plus optional `Mid-Life Cell Replacement (Year 11)`.
    * **Block D – Generator Purchase vs. Rental & Fuel OPEX (if Generator active):** `Purchase (CAPEX €)` vs. `Monthly Rental (OPEX €/month)`, `Fuel Price`, and `Maintenance (€/operating hour)`.
    * **Consolidated Financial Evaluation:** 4 Financial KPIs (`Total Combined CAPEX`, `Annual Total OPEX`, `Annual Net Savings vs. Current situation`, `Payback Period & 15Y NPV`), interactive **Annual Cost Comparison Chart (`Current situation` vs. `Combined system`)**, and **15-Year Lifecycle Cashflow Table**.
* **Level 3 (Bottom — Permanent Master Output, Always Visible Below Sub-Tabs):**
  * **Central Physical Dispatch Caching:** `simulate_combined_system_dispatch` is cached via `comb_dispatch_fp` so switching the chart timeframe (`7D / 1M / 3M / All`) or editing financials does not re-trigger the 35,040-step simulation.
  * **4 Compact Master KPIs:** `Grid Peak Demand`, `Remaining Overload`, `Energy Supply Split`, and `System Operation / Financials`.
  * **Synchronized 15-Minute Master Chart:** Upper subplot (`Power Flow in kW`: Consumption, red Grid Limit line, and stacked areas of active sources) + Lower subplot (`Battery Level SoC % & kWh`, Reserve threshold, and Generator active runtime bands), timeframe filter (`7D | 1M | 3M | All`), Range-Slider, and cached `Download Excel (.xlsx)` button (`comb_cached_excel_bytes` with strict Lazy-Financials protection).
  * **Compact System Comparison Table:** Side-by-side comparison of active components against `Current situation`.
