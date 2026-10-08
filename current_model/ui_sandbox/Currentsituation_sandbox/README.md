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
└── contract/                                   <- Copied from current_model/ui/tab2_contract/
    ├── __init__.py
    ├── view.py                                 <- Contract & billing view with active dataset linkage
    ├── charts.py                               <- Donut chart and 12-month payment series
    ├── form.py                                 <- Contract tariff parameter configuration form
    ├── comparison_view.py                      <- Multi-contract scenario comparison view
    └── comparison_charts.py                    <- Tariff comparison figures
```

---

## 3. Key Capabilities

### A. Consumption Profile Inspector (`consumption/`)
- **CSV Ingestion**: Auto-detects delimiters, encodings, and headers for 15-minute interval files.
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
- **3 Dedicated Actor Sub-Tabs & Multi-Tier Catalogs**:
  * **Sub-Tab 1: Regulated Grid Operator (Netzbetreiber / DSO)**:
    - Official 2025 Dutch DSO rate catalogs for **Enexis Netbeheer**, **Liander Netbeheer**, and **Stedin Netbeheer** across all voltage tiers (`LS ≤ 50 kW`, `MS/LS 50–136 kW`, `MS-D 125–1,500 kW`, `MS 136–2,000 kW`, `MS-T > 1,500 kW`, `HS/MS`, `TS`, `HS`).
    - Structured into the proven 4-section numbered layout:
      * **`1. General & Active Capacity Parameters`**: Contract Name / Identifier, Currency, Base Monthly Fee (Cargo Comercialización / Vastrecht + Aansluitdienst), Contracted Active Capacity (kW), Contracted Capacity Tariff (€/kW/mo), Measured Demand Tariff (€/kW/mo), Max Physical Limit (kW), and Peak Penalty Rate (€/kW).
      * **`2. Reactive Power Parameters`**: Reactive Energy Tariff (€/kVARh), Min Power Factor ($\cos \varphi$), Reactive Allowance (% of kWh).
      * **`3. Time-of-Use (TOU) Energy Rates`**: High Tariff HT / Normaal (€/kWh), Off-Peak NT / Dal (€/kWh), Weekend Off-Peak toggle, and Dutch breach capacity adjustment rule.
      * **`Save Contract Configuration`** action button.
  * **Sub-Tab 2: Energy Retailer (Energielieferant / Supplier)**:
    - Commercial suppliers: **Vattenfall Zakelijk**, **Eneco Zakelijk**, **Essent Zakelijk**, **Shell Energy**, **TotalEnergies**, **Greenchoice**, **Tibber / Dynamisch**, **Custom**.
    - Multi-tier product selector: *Fixed 1-Year (Dubbeltarief HT/NT)*, *Fixed 1-Year (Enkeltarief)*, *Fixed 3-Year (Prijszekerheid)*, *Dynamic Spot (EPEX Spot NL 2025)*, *Variable Monthly (12-mo schedule)*, *100% Dutch Green Power (GvO)*.
    - Full support for **Dual Commodity TOU Rates**: Separate High Tariff ($E_{\text{HT}}$) and Low Tariff ($E_{\text{NT}}$) commodity prices, procurement fee (*Inkoopvergoeding*), and green power surcharge.
  * **Sub-Tab 3: Certified Metering Company (Meetbedrijf) & Statutory Taxes**:
    - Providers: **Fudura B.V.**, **Joulz Meetbedrijf**, **Kenter B.V.**, **Custom**.
    - Multi-tier service packages: *Standard Grootverbruik Telemetry (MS/RLM)*, *Grootverbruik + Measurement Transformers (CT/VT)*, *Submetering (Kleinverbruik / Tussenmeting)*, *High Voltage Telemetry (HS/TS > 2 MW)*.
    - Statutory levies: Indicative energy tax (€/kWh), tax reduction credit (*Vermindering energiebelasting / Heffingskorting* €/yr), and 21% VAT.
    - 15-Year TCO lifecycle parameters: WACC ($r$ %) and electricity price escalation ($g$ %).

- **Time-of-Use (TOU) Segment Visualizer**:
  * High-Tariff (HT / Normaal: Mo–Fr 07:00–23:00) vs Off-Peak (NT / Dal / Laag: Mo–Fr 23:00–07:00 and Sa–Su all day).
  * Energy split KPI cards ($E_{\text{HT}}$ kWh & %, $E_{\text{NT}}$ kWh & %, Peak kW HT vs NT).
  * 24-hour diurnal Plotly schedule comparing average weekday vs weekend demand curves with shaded TOU bands.

- **Period Filter Inspector & Financial Executive Cards**:
  * Filter dropdown: Inspect *"All Months (Full Year 2025 Overview)"* or drill down into any single month (*"January"*, *"February"*, etc.).
  * Single-month reactive mode: KPI cards, Donut chart, and statement table immediately isolate that month's Net, Gross, Peak kW, Overload breach, and DSO/Supplier/Meter/Levies cost split.
  * Full-year overview mode: Annual Net invoice (€), Blended Net Rate (€/kWh), Annual Peak Demand (kW) & Breach status, and 15-Year TCO Net Present Value (NPV).

- **14-Criteria / 4-Point Verification Battery (`perform_full_status_quo_audit`)**:
  * Point 1: Load series integrity (35,040 intervals, calendar alignment, HT/NT energy conservation).
  * Point 2: DSO accounting accuracy (12 monthly peaks, breach detection, no negative fees).
  * Point 3: Commercial contract consistency (energy volume match, dual TOU split, spot pricing alignment, metering & levy calculations).
  * Point 4: Master accounting arithmetic (Total = DSO + Supplier + Metering + Levies, blended price, 15-year TCO NPV).

- **Visual Cost Distribution & Export Toolbar**:
  * Cost Share Donut chart (adapts to selected month or full year) and 12-Month Stacked Payment Series (*Zahlungsreihe*).
  * Itemized statement table.
  * Triple export toolbar: CSV 12-Month Statement, JSON Audit Report, and JSON Contract Model Configuration.

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
