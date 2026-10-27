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
├── consumption/                                <- Ingestion and load profiling package
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
├── contract/                                   <- Unbundled electricity contract & billing package
│   ├── __init__.py                             <- Package exports for contract views
│   ├── view.py                                 <- Orchestrator module & Compact Total Strip
│   ├── tab_dso.py                              <- Sub-Tab 1: Regulated Grid Operator (DSO)
│   ├── tab_supplier.py                         <- Sub-Tab 2: Energy Retailer (Supplier)
│   ├── tab_metering.py                         <- Sub-Tab 3: Certified Metering & Statutory Taxes
│   ├── tab_overview.py                         <- Sub-Tab 4: Total Overview & Statement (at the end)
│   ├── charts.py                               <- Donut, 12-month payment series & peak charts
│   ├── form.py                                 <- Contract tariff parameter configuration form
│   ├── comparison_view.py                      <- Multi-contract scenario comparison view
│   └── comparison_charts.py                    <- Tariff comparison figures
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

### B. Status Quo 2025 Unbundled Contract & Statement (`contract/`)

#### 1. Compact Total Strip (Positioned Directly Above Tabs)
Directly above the tab container, a compact, border-encapsulated KPI strip displays the master billing totals with zero page lag:
- **Annual Net Total**: Consolidated annual electricity expenditure before taxes.
- **Annual Gross Total (incl. VAT)**: Complete net spend plus statutory 21% VAT.
- **Blended Net Rate**: All-inclusive effective electricity price (€/kWh).
- **Annual Peak Demand**: Highest recorded 15-minute demand across the profile (kW).

#### 2. Sub-Tab 1: Regulated Grid Operator (DSO) (`tab_dso.py`)
- **Official 2025 Dutch DSO Rate Catalogs**: Presets for **Enexis Netbeheer**, **Liander Netbeheer**, and **Stedin Netbeheer** across voltage tiers (`LS <= 50 kW`, `MS/LS 50-136 kW`, `MS-D 125-1,500 kW`, `MS 136-2,000 kW`, `MS-T > 1,500 kW`, `HS/MS`, `TS`, `HS`).
- **One-Click Catalog Synchronization**: `Reload Preset Defaults` button and `Always reload catalog defaults on tier switch` toggle.
- **Side-by-Side `st.form` Architecture**:
  - Technical inputs on the left (62% width): Standing charge, contracted capacity, capacity tariff, monthly peak demand rate, transformer limit, and interactive Time-of-Use matrix editor (`st.data_editor`).
  - Direct Cost Impact preview on the right (38% width): Aligned HTML table showing Component, Per Year (€/yr), and Per Month (€/mo). Itemizes fixed standing charge, contracted capacity fee, monthly peak fee, and volumetric transport fee with individual Daytime / HT and Off-Peak / NT sub-items.
  - Live capacity diagnostics showing facility peak vs. reserved capacity and overload status.
- **Isolated Pure DSO Analytics**:
  - 4 Executive KPI cards: Annual DSO Net Total, Contracted Capacity Fee, Monthly Peak Demand Fee, and Grid Breach Status.
  - Interactive Monthly Peak Demand vs. Reserved Grid Capacity chart highlighting breach months in red.
  - Itemized 12-Month DSO statement table with monthly peak (kW), billed kW, capacity fee, peak fee, volumetric transport, and total.

#### 3. Sub-Tab 2: Energy Retailer (Supplier) (`tab_supplier.py`)
- **Commercial Retailer Catalog**: Major suppliers (**Vattenfall Zakelijk**, **Eneco Zakelijk**, **Essent Zakelijk**, **Shell Energy**, **TotalEnergies**, **Greenchoice**, **Scholt Energy**, **Nieuwe Stroom**, **Tibber / Dynamic**, **Custom Retailer**).
- **3-Model Commercial Pricing Toolbar**:
  1. *Fixed Dual Rate (HT/NT)*: Daytime High Tariff vs. Night & Weekend Low Tariff.
  2. *Fixed Single Rate*: Uniform 24/7 flat rate.
  3. *Dynamic Day-Ahead (EPEX Spot NL + Markup)*: Synchronous wholesale index plus retailer margin.
- **Encapsulated `st.form` Configuration**:
  - Interactive Time-of-Use Matrix (`st.data_editor`) for Dual Rate with Start/End hours and weekend toggle.
  - Base fee, procurement fee, green certificates (GvO), and model-specific parameters.
- **Dual Evaluation Horizon Switch**:
  - *Actual Measured Period*: Day-exact billing for the recorded meter timeframe with pro-rata standing fees.
  - *Annualized Projection*: 365-day extrapolation with automated info badge for profiles shorter than 360 days.
- **Isolated Pure Supplier Analytics**:
  - 4 Executive KPI cards: Pure Supplier Net Total, Effective Commodity Rate (€/kWh & ct/kWh), HT/NT Volume & Cost Split (% & kWh), and Model Benchmark Delta.
  - Visual Benchmark bar chart (Fixed Dual vs. Fixed Single vs. Dynamic Spot).
  - Diurnal 24h schedule curve (Fixed rates) or synchronous dual-axis demand vs. EPEX Spot curve (Dynamic rate).
  - Pure Supplier 12-Month Settlement Statement table.

#### 4. Sub-Tab 3: Metering & Taxes (`tab_metering.py`)
- **Certified Metering Providers**: **Fudura B.V.**, **Joulz Meetbedrijf**, **Kenter B.V.**, and **Custom**.
- **Service Packages**: Standard Grootverbruik Telemetry (MS/RLM), Measurement Transformers (CT/VT), Submetering, and High Voltage Telemetry.
- **Statutory Levies & VAT Form**:
  - Regulated energy tax rate (€/kWh), annual statutory tax reduction credit (€/year), and 21% VAT.
  - Primary submit button (`Save Metering & Tax Rates`) preventing page rerun lag.
- **Isolated Metering & Tax Analytics**:
  - 4 Executive KPI cards: Metering Annual Fee, Statutory Energy Levies, Statutory Tax Reduction Credit, and Net Subtotal.
  - Itemized Annual vs. Monthly Tax and Telemetry schedule table.

#### 5. Sub-Tab 4: Total Overview & Statement (`tab_overview.py`)
- **Positioned at the End (Tab 4)**: Consolidates all four cost pillars (DSO, Supplier, Metering, Taxes) into an executive summary view.
- **Period Filter Inspector**:
  - Toggle between full-year overview (*"All Months (Full Year 2025 Overview)"*) and individual month drilldown (*"January"*, *"February"*, etc.).
  - Reactive KPI cards, Donut chart, and statement table dynamically update to reflect the selected period.
- **Executive KPI Cards**: Consolidated Net Invoice, Blended Net Rate, Annual Peak Demand & Breach status, and 15-Year TCO Net Present Value (NPV).
- **Consolidated Visualizations**:
  - Cost Share Donut chart across all 4 cost pillars.
  - 12-Month Stacked Payment Series chart tracking month-by-month cash outflows.
- **Itemized 12-Month Master Accounting Statement Table**:
  - Full breakdown per month: Measured Peak (kW), Energy (kWh), DSO Total (€), Supplier Total (€), Metering Total (€), Statutory Levies (€), VAT (€), Net Total (€), and Gross Total (€).
- **15-Year Long-Term Cost Structure & Lifecycle Projection (2025 - 2039)**:
  - WACC / Discount Rate ($r$ %) and annual electricity price escalation ($g$ %) input controls.
  - 4 Executive Lifecycle KPI cards: 15-Year Nominal Spend, 15-Year TCO (NPV), Average Annual Spend, and Projected Year 15 Cost.
  - Interactive Plotly 15-Year stacked bar chart showing annual cost escalation and discounted present value curve.
  - 15-Year annual financial schedule table.
- **4-Way Export Toolbar**:
  1. CSV 12-Month Master Statement (`status_quo_2025_statement.csv`)
  2. CSV 15-Year TCO Lifecycle Projection (`status_quo_15_year_lifecycle_projection.csv`)
  3. JSON Audit Report (`status_quo_2025_audit.json`)
  4. JSON Contract Configuration (`unbundled_contract_2025.json`)

---

## 4. How to Run

### Standalone Execution
```bash
streamlit run ui_sandbox/Currentsituation_sandbox/app.py
```

### Running Unit Tests
```bash
python -m unittest tests/test_ui_sandbox.py
```
