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
│   ├── charts.py                               <- Donut chart and 12-month payment series
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

### B. Status Quo 2025 Unbundled Contract & Audit (`contract/`)
- **3 Dedicated Actor Sub-Tabs & Multi-Tier Catalogs**:
  * **Sub-Tab 1: Regulated Grid Operator (Netzbetreiber / DSO)**:
    - Official 2025 Dutch DSO rate catalogs for **Enexis Netbeheer**, **Liander Netbeheer**, and **Stedin Netbeheer** across all voltage tiers (`LS ≤ 50 kW`, `MS/LS 50–136 kW`, `MS-D 125–1,500 kW`, `MS 136–2,000 kW`, `MS-T > 1,500 kW`, `HS/MS`, `TS`, `HS`).
      * **`Reload Preset Defaults`** & **`Always reload catalog defaults on tier switch`**: Instant one-click restoration of official catalog values or continuous synchronization when selecting different grid tiers.
      * **`1. Grid Capacity & Fixed Fees`**: Simplified & professional naming aligned with official tariff tables:
        - `Fixed Monthly Grid Fee (€/month)`: Fixed standing charge for grid access (Tabelle 2.1 Festgebühr Transport / Vastrecht, € 36.75/month for MS/LS; connection fee *Aansluitdienst* omitted in baseline stage).
        - `Reserved Grid Capacity (kW)`: Power reserved on the grid (*kW-Vertrag*), dynamically sized to the measured peak load.
        - `Reserved Capacity Rate (€/kW/month)`: Monthly fee per reserved kW (*kW-Vertrag Tarif*, € 3.6567/kW/mo for MS/LS).
        - `Monthly Peak Demand Rate (€/kW/month)`: Measured maximum 15-min peak rate (*kW max. pro Monat*, € 3.4600/kW/mo).
        - `Physical Transformer Limit (kW)` & `Capacity Exceedance Penalty (€/kW)`.
      * **`2. Reactive Power & Power Factor (Blindenergie)`**: `Reactive Power Rate (€/kVARh)` (€ 0.0000), `Target Power Factor (cos φ)` (0.90), `Free Reactive Energy Allowance (%)` (33%).
      * **`3. Time-of-Use Electricity Rates (Interactive Matrix Editor)`**: Dynamic `st.data_editor` table matching Tab 2 with intuitive rows (`Daytime / Working Hours (kWh hoch)` at € 0.2200/kWh, `Night & Weekend / Off-Peak (kWh niedrig)` at € 0.2200/kWh 1:1 matching printed PDF Table 2.1), Weekend Off-Peak toggle, and Dutch breach capacity adjustment rule.
      * **Side-by-Side `st.form` Architecture & Direct Cost Impact Card**:
        - Form inputs (62% width, left) are paired directly with an itemized **Direct Cost Impact** preview card (38% width, right) inside the same `st.form`.
        - Aligned Cost Table: strictly aligned tabular layout showing **Component | Per Year (€/yr) | Per Month (€/mo)** with zero row drift.
        - Detailed Volumetric Sub-items: displays total Volumetric Transport alongside its individual **Daytime / HT** and **Off-Peak / NT** cost and volume (kWh) subcomponents.
        - Live capacity & grid diagnostics indicate whether peak demand stays safely within reserved limits or triggers monthly capacity overloads.
        - Preserves clean `st.form` encapsulation with a primary **`Save Contract Configuration & Recalculate`** button, preventing unwanted full-page reruns while typing.
  * **Sub-Tab 2: Energy Retailer (Energielieferant / Supplier)**:
    - Commercial suppliers: **Vattenfall Zakelijk**, **Eneco Zakelijk**, **Essent Zakelijk**, **Shell Energy**, **TotalEnergies**, **Greenchoice**, **Scholt Energy** (B2B/Industry), **Nieuwe Stroom** (Pure Spot/Dynamic standard), **Tibber / Dynamisch**, **Custom Energy Retailer**.
    - **Streamlined Toolbar (outside form)**: Rapid pre-selection across the 3 core commercial pricing models (covering >90% of Dutch market):
      1. *Fixed Dual Rate (Dubbeltarief HT/NT)*: Workdays 07:00–23:00 High Tariff, Nights & Weekends Low Tariff.
      2. *Fixed Single Rate (Enkeltarief)*: Uniform 24/7 all-in commodity price.
      3. *Dynamic Day-Ahead (EPEX Spot NL + Opslag)*: Synchronous hourly wholesale index + supplier markup.
    - **Performance Encapsulation (`st.form`) & Time-of-Use Matrix Editor**:
      - Numerical inputs encapsulated within `st.form` with primary `Apply Provider Tariff & Calculate` button preventing unwanted full-page reruns on typing.
      - **Interactive Time-of-Use Matrix (`st.data_editor`) for Fixed Dual Rate (HT/NT)**: Exactly matching Sub-Tab 1 (DSO), users can directly inspect and edit the tariff names, commodity rates (€/kWh), and Start/End times (`HH:MM`) along with a dedicated `"Treat Weekends as Off-Peak"` checkbox.
      - Dynamic recalculation: The HT/NT volume split, costs, settlement statement, and the diurnal 24h schedule curve dynamically synchronize with the configured hours and weekend rule.
      - Contextual parameter rendering: only fields relevant to the active pricing model are visible (Dual: Interactive TOU matrix & weekend toggle; Single: Flat rate; Dynamic: Retail markup & procurement fee; Standing fee and Green certificates GvO always visible).
    - **Dual Evaluation Horizon Switch**:
      - *Modus A: Actual Measured Period (DEFAULT)*: Tagesgenaue Abrechnung für den realen Messzeitraum (z. B. 28 Tage) mit pro-rata Grundgebühr ($V_{\text{annual}} \times \frac{T_{\text{days}}}{365}$).
      - *Modus B: Annualized Projection (365-Tage-Hochrechnung)*: Lineare 365-Tage-Skalierung mit automatischer Info-Badge-Kennzeichnung bei Profilen $< 360$ Tagen.
    - **Isolated Pure Supplier Analytics (Reine Lieferantensicht)**:
      - *4 Executive KPI Cards*: Pure Supplier Total (Netto €), Effective Commodity Rate (€/kWh & ct/kWh), HT/NT Volume & Cost Split (% & kWh), Model Benchmark Delta (automatischer Schattenvergleich mit alternativen Tarifen).
      - *Visual Benchmark & Load Schedule (Left)*: Horizontaler 3-Modell-Kostenvergleich (Fixed Dual vs. Fixed Single vs. Dynamic Spot) und modellabhängige Detailgrafik (24h-Tagesschnitt bei Festpreis; **Synchronous Dual-Axis Chart** Lastgang kW vs. EPEX Spot €/MWh bei dynamischem Tarif).
      - *Itemized Settlement Statement (Right)*: Reine Lieferanten-Abrechnungstabelle mit Monats-/Periodenauflösung (kWh, HT, NT, Arbeitskosten, Grundgebühr, Effektivpreis).
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

- **15-Year Long-Term Cost Structure & Lifecycle Projection**:
  * **Complete 4-Pillar Consolidation**: Fully consolidates all 4 cost aspects: Regulated DSO Grid, Energy Supplier Commodity, Certified Metering, and Statutory Taxes into a 15-year lifecycle trajectory ($y \in [1, 15]$).
  * **Compounded Price Escalation & WACC Discounting**: Accounts for user-configured annual electricity price escalation ($g = 3.0\%$) and WACC discount rate ($r = 5.0\%$).
  * **4 Executive Lifecycle KPI Cards**:
    - `15-Year Spend (Nominal)`: Cumulative cash outlay across 15 years.
    - `15-Year TCO (NPV)`: Discounted Net Present Value of lifetime electricity spend.
    - `Average Annual Spend`: Mean annual consolidated budget over 15 years.
    - `Projected Year 15 Cost (2039)`: Final year compounded annual electricity expenditure.
  * **Interactive Plotly 15-Year Stacked Figure**:
    - Color-coded stacked bars showing the 3 core parties (DSO Grid, Energy Supplier, Metering & Taxes).
    - Violet dashed curve tracking annual Discounted Present Value ($PV$).
    - Secondary Y-axis tracking cumulative 15-year expenditure trajectory.
  * **15-Year Annual Financial Schedule Table**:
    - Detailed row-by-row table showing Year, Calendar Year (2025–2039), DSO Grid (€), Supplier (€), Metering & Taxes (€), Annual Net Spend (€), Cumulative Spend (€), Discount Factor, Present Value (€), and Blended Rate (€/kWh).

- **Visual Cost Distribution & 4-Way Export Toolbar**:
  * Cost Share Donut chart (adapts to selected month or full year) and 12-Month Stacked Payment Series (*Zahlungsreihe*).
  * 12-Month itemized statement table.
  * Quadruple export toolbar:
    1. CSV 12-Month Statement (`status_quo_2025_statement.csv`)
    2. CSV 15-Year TCO Lifecycle Projection (`status_quo_15_year_lifecycle_projection.csv`)
    3. JSON Audit Report (`status_quo_2025_audit.json`)
    4. JSON Contract Model Configuration (`unbundled_contract_2025.json`)

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
