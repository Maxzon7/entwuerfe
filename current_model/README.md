# Energy Simulator & Load Profile Analyzer — `current_model` Architecture

A modular, enterprise-grade simulation and analytics platform for electrical load profiling, real meter ingestion, electricity supply contract modeling, and Solar PV generation analysis.

---

## 🎨 UI Iconography & Visual Presentation Policy (Mandatory Guidelines)

> [!IMPORTANT]
> **1. Iconography Standard (Piktogramme & UI Icons):**
> To maintain a clean, professional, and subtle aesthetic, **exclusively Streamlit's native Google Material Symbols (`:material/<icon_name>:`)** must be used across all application tabs, sub-tabs, buttons, expanders, input controls, and headings.
> 
> * **Prohibited:** Colorful cartoon emojis (e.g. 🍇, 🏭, 🏢, 📁, 📥, 📤, 💾, ⚙️, ⚖️, 📌, 📋) must **never** be used in user-facing controls, tables, or presets.
> * **Native Streamlit Material Icons:** Use the `:material/<icon_name>:` syntax directly in widgets (e.g. `icon=":material/rocket_launch:"`, `icon=":material/restart_alt:"`, `icon=":material/download:"`, `st.tabs([":material/analytics: 1. Consumption", ...])`).
> * **Country Flags:** Use vector **Flag Icons** (`fi fi-<country_code>`) or text labels where country indicators are required.
> 
> **2. Charts & Diagrams Standard (Diagramme & Visualisierungen):**
> * **Interactive Application Charts:** Use **Plotly** (`plotly.graph_objects.Figure`) exclusively for all analytical plots, timeseries, heatmaps, stacked area charts, balance bars, waterfalls, and Sankey diagrams. Static raster images (matplotlib/seaborn PNGs) are strictly prohibited.
> * **System Architecture & Flows:** Use **Mermaid** diagrams (`flowchart TD`, `sequenceDiagram`) directly in Markdown documentation.

The stylesheets and helper icons are globally injected via [`ui/common/styles.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/common/styles.py).

---

## ⚡ Quick-Lookup Directory Map (1:1 Visual-to-Code Mapping)

Every top-level Tab in the Streamlit application corresponds directly to its dedicated directory under `ui/`:

| UI Area / Component | Description & Responsibility | File Path |
| :--- | :--- | :--- |
| **Main Application Entry** | Top-level orchestrator & Tab navigation | [`app.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/app.py) |
| **Global Theme & Styles** | Dark mode CSS, card classes, and icon CDNs | [`ui/common/styles.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/common/styles.py) |
| **Shared KPI Components** | Metric cards (`render_kpi_card`) with status badges | [`ui/common/cards.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/common/cards.py) |
| **Cross-Tab Session Utils** | Active load dataset & contract discovery helpers | [`ui/common/session_utils.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/common/session_utils.py) |
| **Tab 1: Consumption** | Top-level switcher: Synthetic Simulator vs. Real Meter CSV | [`ui/tab1_consumption/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/view.py) |
| **Tab 1: Synthetic View** | 24h & 365d simulation orchestrator, KPIs, and `.drac` toolbar | [`ui/tab1_consumption/synthetic/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/synthetic/view.py) |
| **Tab 1: Synthetic Forms** | Add/edit consumer asset forms, operating windows, weekly schedules | [`ui/tab1_consumption/synthetic/forms.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/synthetic/forms.py) |
| **Tab 1: Synthetic Charts** | Plotly 24h stacked area, 365d timeseries & 2D heatmap | [`ui/tab1_consumption/synthetic/charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/synthetic/charts.py) |
| **Tab 1: CSV Inspector** | Ingestion pipeline, multi-meter viewer, and overload analyzer | [`ui/tab1_consumption/csv_inspector/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/csv_inspector/view.py) |
| **Tab 1: CSV Forms** | File upload widget, delimiter sniffer, and column mapping | [`ui/tab1_consumption/csv_inspector/forms.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/csv_inspector/forms.py) |
| **Tab 1: CSV Charts** | High-performance interactive multi-channel timeseries chart | [`ui/tab1_consumption/csv_inspector/charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/csv_inspector/charts.py) |
| **Tab 2: Contract Data** | Subtabs: 2.1 Single Contract & 2.2 Multi-Contract Benchmark | [`ui/tab2_contract/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab2_contract/view.py) |
| **Tab 2: Contract Form** | Electricity tariff configuration form & `.drac` file transfer bar | [`ui/tab2_contract/form.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab2_contract/form.py) |
| **Tab 2: Financial Charts** | Cost distribution donut chart and monthly payment schedule series | [`ui/tab2_contract/charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab2_contract/charts.py) |
| **Tab 2: Comparison View** | Multi-tariff benchmark, savings leaderboard & ranking table | [`ui/tab2_contract/comparison_view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab2_contract/comparison_view.py) |
| **Tab 2: Comparison Charts**| Stacked component comparison, 12-month series & rate benchmark | [`ui/tab2_contract/comparison_charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab2_contract/comparison_charts.py) |
| **Tab 3: Solar PV** | Sub-tabs coordinator: 3.1 Standalone & 3.2 Integrated | [`ui/tab3_solar/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab3_solar/view.py) |
| **Tab 3.1: Standalone View**| Pure physical generation simulator, tech matrix & risk assessment | [`ui/tab3_solar/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab3_solar/view.py) |
| **Tab 3.1: Forms** | Site GPS, module sizing, tilt/azimuth & loss factors | [`ui/tab3_solar/forms.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab3_solar/forms.py) |
| **Tab 3.1: Charts** | 15-min generation curve, monthly yields, loss waterfall & matrix | [`ui/tab3_solar/charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab3_solar/charts.py) |
| **Tab 3.2: Integration View**| Solar-load coupling, auto-sizing (40-100%), SCR & Autarky KPIs | [`ui/tab3_solar/integration_view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab3_solar/integration_view.py) |
| **Tab 3.2: Charts** | 15-min dispatch timeseries, monthly balance, seasonal & Sankey | [`ui/tab3_solar/integration_charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab3_solar/integration_charts.py) |
| **Test Suite Runner** | Regression & health-check runner (56 automated tests) | [`run_tests.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/run_tests.py) |

---

## 🏗️ System Architecture & Inner Workings

```mermaid
flowchart TD
    subgraph UI ["User Interface Layer (Streamlit)"]
        Tab1["Tab 1: Consumption Profile (Synthetic & CSV)"]
        Tab2["Tab 2: Contract Data & Financial Assessment"]
        Tab3["Tab 3: Solar PV Physical Generation"]
    end

    subgraph FileTransfer ["File Transfer Layer (.drac Format)"]
        DracContract["Contract File (.drac)"]
        DracProfile["Profile File (.drac)"]
    end

    subgraph CoreEngines ["Core Calculation Engines"]
        SyntheticEngine["Synthetic Engine (96 / 35,040 steps)"]
        CSVEngine["CSV Parser & Time Processor"]
        FinancialEngine["Financial & Billing Engine"]
        SolarEngine["Solar Physics Engine"]
    end

    subgraph Models ["Data Models (Dataclasses)"]
        ConsumerModel["SimpleConsumer & TimeWindow"]
        ContractModel["Contract (TOU & Taxes)"]
        SolarModel["SolarPVConfig & SimulationResult"]
    end

    Tab1 <--> SyntheticEngine
    Tab1 <--> CSVEngine
    Tab2 <--> FinancialEngine
    Tab3 <--> SolarEngine

    DracProfile <--> Tab1
    DracContract <--> Tab2

    SyntheticEngine --> ConsumerModel
    FinancialEngine --> ContractModel
    SolarEngine --> SolarModel

    Tab1 -.->|Active Timeseries Data| Tab2
```

---

## 🧩 Detailed Module Breakdown

### 1. Tab 1: Consumption Modeling & Real Meter Ingestion
* **Bottom-Up Synthetic Simulation ([`core/synthetic_engine.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/synthetic_engine.py))**:
  * **24-Hour Profile**: Generates 96 fifteen-minute power intervals ($kW$) for typical daily operational profiles.
  * **Full Year (365 Days / 35,040 Steps)**: Vectorized calculation applying weekday masks (0=Monday..6=Sunday), startup inrush spikes, monthly seasonal scaling factors (e.g. summer/winter shifts), and system-wide custom holidays (treated automatically as Sundays).
* **CSV Real-Meter Parser ([`core/csv_parser.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/csv_parser.py))**:
  * Auto-detects delimiters (`,`, `;`, `\t`), European comma decimals (`1.234,56`), and Spanish/English timestamp column formats.
  * Scales energy intervals into active power demand ($15\text{-min-kWh} \times 4 \to \text{kW}$).
* **Grid Capacity Overload Analysis ([`models/grid_limit.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/grid_limit.py))**:
  * Analyzes power curves against contracted physical connection limits, reporting peak overload ($kW$), duration ($hours$), and excess energy ($kWh$).

---

### 2. Tab 2: Electricity Contract & Billing Engine
* **Contract Model ([`models/contract.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/contract.py))**:
  * **Capacity & Base Charges**: Fixed monthly base fee ($/month$), contracted active capacity charge ($/kW/month$), and measured peak demand charge ($/kW/month$).
  * **Dynamic Time-of-Use (TOU) Rates**: Configurable table of tariff windows (e.g. *Pico* 18:00–23:00, *Valle* 23:00–05:00, *Resto* 05:00–18:00) with overnight-shift support and optional weekend off-peak rules.
  * **Power Factor & Reactive Penalties**: Cos $\phi$ threshold evaluation and reactive energy tariffs ($/kVARh$).
  * **Dynamic Taxes & Surcharges**: Customizable taxes supporting percentage rates (e.g. VAT 27%, Provincial 9%), per-kWh levies, and fixed monthly charges.
* **Financial Engine ([`core/financial_engine.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/financial_engine.py))**:
  * Automatically binds to the active load profile from Tab 1.
  * Computes itemized line items, effective unit prices ($/kWh$), fixed vs. variable cost splits, and full-duration month-by-month payment schedules (*Zahlungsreihe*).
* **Presets Library**:
  * Includes ready-to-use industry contracts such as `Paula1 (Bodegas Salentein - EDEMSA T2 R MT)` (ARS), `Industrial Multi-Tariff` (EUR), `Commercial Standard Fixed` (EUR), and `Argentine T3 Grandes Demandas` (ARS).

---

### 3. Tab 3: Solar PV Simulation & Facility Load Integration
* **Sub-Tab 3.1: Standalone Solar PV Generation Simulator**:
  * **Solar Physics Engine ([`core/solar_engine.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/solar_engine.py))**:
    * Models solar geometry (tilt, azimuth, solar elevation, solar zenith).
    * Direct Normal (DNI), Diffuse Horizontal (DHI), and Global Horizontal (GHI) irradiance transposition onto tilted planes via Perez anisotropic sky model.
    * Dynamic cell temperature modeling: $T_{\text{cell}} = T_{\text{amb}} + G_{\text{POA}} \times \frac{\text{NMOT} - 20}{800}$.
    * Thermal derate factor: $\eta_{\text{temp}} = 1.0 - \max(0, T_{\text{cell}} - 25^\circ\text{C}) \times \frac{|\gamma|}{100}$.
    * Inverter AC conversion and clipping power threshold ($kW_{\text{AC}}$ limit).
    * Calculates Key Performance Indicators: Specific Yield ($kWh/kWp/year$), Performance Ratio ($PR$), Capacity Factor ($\%$) and Full Load Hours ($h/a$).
    * Multi-technology production matrix across 15 years (PERC vs. TOPCon vs. Backcontact).
    * Climatological 10-year multi-year risk evaluation (P50, P90 debt-financing limit, P95, volatility).
* **Sub-Tab 3.2: Solar & Consumption Integration**:
  * **Automated Load Coupling**: Discovers active consumption dataset from Tab 1 (CSV real meter or Synthetic 365d/24h) via `ui/common/session_utils.py`.
  * **Target Net Coverage Auto-Sizing**: Quick-sizes PV capacity ($kW_p$) for **40%**, **60%**, **80%**, and **100% Net Zero** annual energy coverage:
    $$\text{Target } kW_p = \frac{\text{Annual Consumption } (kWh) \times \text{Coverage } \%}{\text{Specific Yield } (kWh/kW_p)}$$
  * **Interval-by-Interval Electrical Dispatch ($dt = 0.25h$)**:
    * Direct Self-Consumption: $P_{\text{direct}}(t) = \min(P_{\text{load}}(t), P_{\text{solar}}(t))$
    * Surplus Export / Battery Potential: $P_{\text{surplus}}(t) = \max(0, P_{\text{solar}}(t) - P_{\text{load}}(t))$
    * Residual Grid Load: $P_{\text{residual}}(t) = \max(0, P_{\text{load}}(t) - P_{\text{solar}}(t))$
    * Self-Consumption Rate: $\text{SCR} = \frac{E_{\text{direct}}}{E_{\text{solar}}} \times 100\%$
    * Autarky / Solar Fraction: $\text{SF} = \frac{E_{\text{direct}}}{E_{\text{load}}} \times 100\%$
    * Peak Shaving: $\Delta P_{\text{peak}} = P_{\text{load, max}} - P_{\text{residual, max}}$
  * **Financial Avoided Cost Assessment**: Integrates with active Tab 2 electricity contract (evaluating baseline bill vs. residual bill), with optional deactivated-by-default manual flat-rate estimator.

---

## 💾 The `.drac` File Format Standard

Both Electricity Contracts and Synthetic Load Profiles can be exported with custom names and imported using the proprietary **`.drac`** JSON format:

### Contract Schema (`.drac`):
```json
{
  "format": "drac_contract",
  "version": "1.0",
  "name": "Paula1",
  "currency": "ARS",
  "base_monthly_fee": 514145.55,
  "contracted_capacity_kw": 430.0,
  "monthly_capacity_tariff": 40607.046,
  "demand_capacity_tariff": 8554.439,
  "max_physical_limit_kw": 1000.0,
  "peak_penalty_rate": 40607.046,
  "reactive_power_tariff": 0.0,
  "min_power_factor": 0.90,
  "reactive_power_allowance_pct": 33.0,
  "tou_rates": [
    {"name": "Valle (23:00 - 05:00)", "rate": 66.1017, "start_time": "00:00", "end_time": "05:00"},
    {"name": "Resto (05:00 - 18:00)", "rate": 66.7737, "start_time": "05:00", "end_time": "18:00"},
    {"name": "Pico (18:00 - 23:00)", "rate": 68.4335, "start_time": "18:00", "end_time": "23:00"},
    {"name": "Valle (23:00 - 05:00)", "rate": 66.1017, "start_time": "23:00", "end_time": "24:00"}
  ],
  "default_energy_rate": 66.7737,
  "weekend_is_off_peak": false,
  "taxes_and_fees": [
    {"name": "I.V.A. Resp. Inscripto", "type": "percentage", "value": 27.0, "description": "IVA Nacional"},
    {"name": "CCCE art 74 inc d) Ley 6497", "type": "percentage", "value": 9.0, "description": "Fondo Compensador Provincial"},
    {"name": "Cargo AP Municipal Ord. 3028", "type": "fixed_monthly", "value": 43091.0, "description": "Alumbrado Público"}
  ]
}
```

### Load Profile Schema (`.drac`):
```json
{
  "format": "drac_load_profile",
  "version": "1.0",
  "profile_name": "Winery Bottling Facility",
  "consumer_count": 4,
  "consumers": [
    {
      "name": "Bottling Line A",
      "power_kw": 120.0,
      "category": "Production",
      "count": 1,
      "active_days": [0, 1, 2, 3, 4],
      "time_windows": [
        {
          "start_time": "06:00",
          "end_time": "15:00",
          "has_peak": true,
          "peak_power_kw": 150.0,
          "peak_duration_min": 30
        }
      ]
    }
  ]
}
```

---

## 🧪 Automated Testing Suite

Execute the health check and regression suite from the project root:

```bash
python run_tests.py
```

The suite covers **56 automated unit tests** across:
* `.drac` serialization, deserialization, and round-trip fidelity.
* Backward compatibility and state migration.
* Vectorized 24h and 365-day annual load aggregation.
* Dynamic Time-of-Use rate matching and weekend off-peak logic.
* Financial billing calculations and multi-month invoice series.
* CSV delimiter heuristics and decimal normalization.
* Solar PV physical modeling, irradiance transposition, and temperature derates.
* Python syntax and compilation check across the entire workspace.
