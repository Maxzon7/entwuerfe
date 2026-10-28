# Current Situation (Status Quo) Sandbox

## 1. Overview & Purpose
The `Currentsituation_sandbox` folder provides a dedicated, self-contained baseline environment by copying and adapting the proven Consumption Ingestion and Electricity Contract Billing modules directly from the main program (`current_model/ui/tab1_consumption` and `current_model/ui/tab2_contract`).

This allows users to inspect real meter CSV files (such as 15-minute interval records), visually verify full-year load curves, monthly energy, peak demand, and overload hours, and immediately compute status quo contract costs without having to navigate other sub-scenarios (PV, BESS, generators).

---

## 2. Directory Structure

```text
current_model/ui_sandbox/Currentsituation_sandbox/
├── __init__.py                                 <- Package initializer exporting main render functions
├── README.md                                   <- Comprehensive documentation of module & architecture
├── app.py                                      <- Standalone Streamlit application entrypoint
├── consumption/                                <- Copied from current_model/ui/tab1_consumption/
│   ├── __init__.py
│   ├── view.py                                 <- Consumption mode switcher (CSV vs Synthetic)
│   ├── csv_inspector/
│   │   ├── __init__.py
│   │   ├── view.py                             <- CSV Inspector with full Plotly graphs & KPIs
│   │   ├── charts.py                           <- Interactive time series & monthly breakdown figures
│   │   └── forms.py                            <- File uploader, skiprows, and column mapping form
│   └── synthetic/
│       ├── __init__.py
│       ├── view.py                             <- 24h & 365-day synthetic simulator
│       ├── charts.py                           <- Daily load profile curves & heatmaps
│       └── forms.py                            <- Consumer appliance parametrization form
├── contract/                                   <- Copied from current_model/ui/tab2_contract/
│   ├── __init__.py
│   ├── view.py                                 <- Contract & billing view with active dataset linkage
│   ├── charts.py                               <- Donut chart, monthly payment series, and DSO peak figures
│   ├── form.py                                 <- Contract tariff parameter configuration form
│   ├── comparison_view.py                      <- Multi-contract scenario comparison view
│   ├── comparison_charts.py                    <- Tariff comparison figures
│   └── tab_invoice_experimental.py             <- Sub-Tab 5: Classic commercial invoice view & audit ledger
└── engine/                                     <- Layer 2 to 5 Computational Accounting Engine
    ├── __init__.py
    ├── config_and_models.py                    <- Dataclasses for tariffs, statements, and load series
    ├── tariff_defaults_2025.py                 <- Official 2025 Dutch rate catalogs (Enexis, Liander, Stedin)
    ├── consumption_pipeline.py                 <- 35,040 interval normalization & Liander TOU tagger
    ├── dso_accounting.py                       <- Regulated grid operator billing (standing, capacity, peak)
    ├── commercial_accounting.py                <- Retailer TOU commodity, metering, energy taxes, VAT
    ├── status_quo_master.py                    <- Master 12-month statement and 15-year NPV aggregator
    └── audit.py                                <- 14-point mathematical integrity and tax compliance audit
```

---

## 3. Key Capabilities

### A. Consumption Profile Inspector (`consumption/`)
- **CSV Ingestion & Full Year 2025 Demo**:
  * Auto-detects delimiters, encodings, and headers for 15-minute interval files.
  * One-click **"Load 15-Min Demo CSV (Full Year 2025)"** button instantly generates all 365 days of 2025 (`2025-01-01 00:00` to `2025-12-31 23:45`, 35,040 intervals) featuring realistic seasonal modulation across multiple meters (HVAC, Production, EV Chargers, Baseload).
- **Interactive Plotly Load Curve**:
  * Full 35,040-interval time series with range slider, zoom, and unified hover tooltips.
  * Visual peak power marker with annotation badges.
  * Configurable grid limit line to observe exceedances.
- **Annual Baseline & Monthly Breakdown**:
  * 365-day standardized baseline figure.
  * Monthly energy (MWh) bar chart with monthly peak demand (kW) secondary line.
- **Overload & Grid Violation Analysis**:
  * Quantifies peak exceedances above contracted capacity, total violation hours, and exceedance energy (kWh).
- **KPI Metric Cards**: Total consumption (kWh), Peak Demand (kW), Average Load (kW), and Load Factor (%).
- **Synthetic Simulator**: Optional alternative to generate 24h profiles and 365-day synthetic industrial/commercial load profiles.

### B. Status Quo 2025 Unbundled Contract & Audit (`contract/`)

#### Multi-Party Real-Time Total Strip (Above Sub-Tabs)
Immediately displays the high-level net totals across all market actors for real-time visibility:
- **Regulated Grid Operator (DSO)** Net Subtotal (€)
- **Energy Retailer (Supplier)** Net Subtotal (€)
- **Metering & Taxes** Net Subtotal (€)
- **Total Consolidated Net Spend** (€)

#### 5 Dedicated Sub-Tabs & Integrated Views
- **Sub-Tab 1: Regulated Grid Operator (DSO)**:
  * Official 2025 Dutch DSO rate catalogs for **Enexis Netbeheer**, **Liander Netbeheer**, and **Stedin Netbeheer** across all voltage tiers (`LS ≤ 50 kW`, `MS/LS 50–136 kW`, `MS-D 125–1,500 kW`, `MS 136–2,000 kW`, `MS-T > 1,500 kW`, `HS/MS`, `TS`, `HS`).
  * **`Reload Preset Defaults`** & **`Always reload catalog defaults on tier switch`**: Instant one-click restoration of official catalog values or continuous synchronization when selecting different grid tiers.
  * **`1. Grid Capacity & Fixed Fees`**: Simplified & professional naming aligned with official tariff tables:
    - `Fixed Monthly Grid Fee (€/month)`: Fixed standing charge for grid access (Table 2.1 Fixed Standing Fee / Vastrecht, € 36.75/month for MS/LS; connection fee omitted in baseline stage).
    - `Reserved Grid Capacity (kW)`: Power reserved on the grid (*Contracted Capacity*), dynamically sized to the measured peak load.
    - `Reserved Capacity Rate (€/kW/month)`: Monthly fee per reserved kW (€ 3.6567/kW/mo for MS/LS).
    - `Monthly Peak Demand Rate (€/kW/month)`: Measured maximum 15-min peak rate (€ 3.4600/kW/mo).
    - `Physical Transformer Limit (kW)` & `Capacity Exceedance Penalty (€/kW)`.
  * **`2. Reactive Power & Power Factor (cos φ)`**: `Reactive Power Rate (€/kVARh)` (€ 0.0000), `Target Power Factor (cos φ)` (0.90), `Free Reactive Energy Allowance (%)` (33%).
  * **`3. Time-of-Use Electricity Rates (Interactive Matrix Editor)`**: Dynamic `st.data_editor` table matching Tab 2 with intuitive rows (`Daytime / Working Hours` at € 0.2200/kWh, `Night & Weekend / Off-Peak` at € 0.2200/kWh), Weekend Off-Peak toggle, and Dutch breach capacity adjustment rule.
  * Encapsulated in a performant **`st.form`** with primary **`Save Contract Configuration`** submit button.

- **Sub-Tab 2: Energy Retailer (Supplier)**:
  * Commercial suppliers: **Vattenfall Zakelijk**, **Eneco Zakelijk**, **Essent Zakelijk**, **Shell Energy**, **TotalEnergies**, **Greenchoice**, **Scholt Energy** (B2B/Industry), **Nieuwe Stroom** (Pure Spot/Dynamic standard), **Tibber / Dynamic**, **Custom Energy Retailer**.
  * **Streamlined Toolbar (outside form)**: Rapid pre-selection across the 3 core commercial pricing models:
    1. *Fixed Dual Rate (High/Off-Peak)*: Workdays 07:00–23:00 High Tariff, Nights & Weekends Low Tariff.
    2. *Fixed Single Rate*: Uniform 24/7 all-in commodity price.
    3. *Dynamic Day-Ahead (EPEX Spot NL + Markup)*: Synchronous hourly wholesale index + supplier markup.
  * **Performance Encapsulation (`st.form`) & Time-of-Use Matrix Editor**:
    - Numerical inputs encapsulated within `st.form` with primary `Apply Provider Tariff & Calculate` button preventing unwanted full-page reruns on typing.
    - **Interactive Time-of-Use Matrix (`st.data_editor`) for Fixed Dual Rate**: Direct inspection and editing of tariff names, commodity rates (€/kWh), and Start/End times (`HH:MM`) along with a dedicated `"Treat Weekends as Off-Peak"` checkbox.
    - Dynamic recalculation: The High/Off-Peak volume split, costs, settlement statement, and the diurnal 24h schedule curve dynamically synchronize with the configured hours and weekend rule.
    - Contextual parameter rendering: only fields relevant to the active pricing model are visible.
  * **Dual Evaluation Horizon Switch**:
    - *Mode A: Actual Measured Period (DEFAULT)*: Day-exact billing for the real measured period (e.g., 28 days) with pro-rata standing fee ($V_{\text{annual}} \times \frac{T_{\text{days}}}{365}$).
    - *Mode B: Annualized Projection (365-Day Projection)*: Linear 365-day scaling with automatic info-badge indicator for profiles $< 360$ days.
  * **Isolated Pure Supplier Analytics**:
    - *4 Executive KPI Cards*: Pure Supplier Total (Net €), Effective Commodity Rate (€/kWh & ct/kWh), High/Off-Peak Volume & Cost Split (% & kWh), Model Benchmark Delta (automatic shadow comparison with alternative tariffs).
    - *Visual Benchmark & Load Schedule (Left)*: Horizontal 3-model cost comparison (Fixed Dual vs. Fixed Single vs. Dynamic Spot) and model-dependent detail plot (24h diurnal average for fixed; **Synchronous Dual-Axis Chart** load profile kW vs. EPEX Spot €/MWh for dynamic).
    - *Itemized Settlement Statement (Right)*: Clean supplier settlement table with monthly/period resolution (kWh, High Tariff, Off-Peak, Commodity Cost, Standing Fee, Effective Price).

- **Sub-Tab 3: Certified Metering Company & Statutory Taxes**:
  * Providers: **Fudura B.V.**, **Joulz Meetbedrijf**, **Kenter B.V.**, **Custom**.
  * Multi-tier service packages: *Standard Telemetry (MS/RLM)*, *Telemetry + Measurement Transformers (CT/VT)*, *Submetering*, *High Voltage Telemetry (> 2 MW)*.
  * Statutory levies: Indicative energy tax (€/kWh), statutory tax reduction credit (*Vermindering energiebelasting / Heffingskorting* €/yr), and 21% VAT.
  * 15-Year TCO lifecycle parameters: WACC ($r$ %) and electricity price escalation ($g$ %).

- **Sub-Tab 4: Total Overview & Statement**:
  * **Consolidated Statement**: Full unified statement reconciling DSO grid, supplier commodity, metering, and statutory levies.
  * **Period Filter Inspector & Financial Executive Cards**:
    - Filter dropdown: Inspect *"All Months (Full Year 2025 Overview)"* or drill down into any single month (*"January"*, *"February"*, etc.).
    - Reactive KPI cards, Donut chart, and statement table immediately isolate that month's Net, Gross, Peak kW, Overload breach, and actor cost split.
  * **Time-of-Use (TOU) Segment Visualizer**:
    - High-Tariff vs Off-Peak energy split KPI cards ($E_{\text{HT}}$ kWh & %, $E_{\text{NT}}$ kWh & %, Peak kW HT vs NT).
    - 24-hour diurnal Plotly schedule comparing average weekday vs weekend demand curves with shaded TOU bands.
  * **15-Year Long-Term Cost Structure & Lifecycle Projection**:
    - Complete 4-pillar consolidation into a 15-year lifecycle trajectory ($y \in [1, 15]$).
    - Compounded price escalation ($g$) and WACC discounting ($r$).
    - 4 Executive Lifecycle KPI Cards (15-Year Nominal Spend, 15-Year TCO NPV, Average Annual Spend, Projected Year 15 Cost).
    - Interactive Plotly 15-year stacked figure with Present Value curve and cumulative spend trajectory.
    - 15-Year annual financial schedule table.
  * **Visual Cost Distribution & 4-Way Export Toolbar**:
    - Cost Share Donut chart and 12-Month Stacked Payment Series (*Zahlungsreihe*).
    - 12-Month itemized statement table.
    - Quadruple export toolbar (Statement CSV, 15-Year Lifecycle CSV, Audit JSON, Model Config JSON).

- **Sub-Tab 5: Classic Invoice View (Experimental)**:
  * **Authentic Commercial Utility Bill Ledger**: Reproduces the layout and accounting rigor of commercial utility invoices with cent-exact mathematical reconciliation ($\Delta \le 0.00$).
  * **Zero Recalculation Architecture**: Reads pre-computed calculation objects (`result`, `active_config`, `load_series`) directly from Tab 4 state, guaranteeing complete numerical parity.
  * **5 Structured Sections**:
    1. *Section 1: Billing Period Selector & Horizon Status Banner*: Seamless toggle between Full Year 2025 and individual monthly billing cycles.
    2. *Section 2: Commercial Utility Cover Page*: Formal Briefkopf/letterhead, supplier and customer metadata, key metering parameters (annual MWh, peak demand kW, contracted capacity kW), and gross amount due banner.
    3. *Section 3: Itemized Position Ledger*: 4 distinct blocks of line items:
       - **Block A: Energy Retailer (Supplier)** (High Tariff commodity, Off-Peak commodity, retailer standing charge, GvO green certificates).
       - **Block B: Regulated Grid Operator (DSO)** (Fixed transport charge, reserved capacity fee, monthly maximum peak demand, reactive power & breach charges).
       - **Block C: Certified Metering Services** (Telemetry & base metering, measurement transformers).
       - **Block D: Statutory Levies & Tax Credits** (Indicative energy tax, statutory tax reduction credit, cent balancing adjustment, 21% VAT).
    4. *Section 4: Graphical Audit & Verification Enclosure*: Cost Share Donut chart, 12-Month Stacked Payment Schedule (with visual focus on the active billing month), and DSO Monthly Peak vs. Contracted Capacity audit chart.
    5. *Section 5: 12-Month Cross-Comparison Accounting Matrix & Download Toolbar*: Comprehensive 12-month cross-tabulation matrix and dual-format download toolbar (Itemized Positions CSV + Full Invoice Ledger JSON).

---

## 4. How to Run

### Standalone Execution
```bash
python -m streamlit run current_model/ui_sandbox/Currentsituation_sandbox/app.py
```

### Via Sandbox Suite
Launch the main sandbox hub:
```bash
python -m streamlit run current_model/ui_sandbox/sandbox_app.py
```
And select **Current Situation (Status Quo) Sandbox** from the sidebar suite selector.

### Running Unit Tests
```bash
python -m unittest tests/test_ui_sandbox.py
python -m unittest tests/test_status_quo_2025.py
```
