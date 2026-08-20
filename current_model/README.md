# Energy Simulator & Load Profile Analyzer — `current_model` Architecture

Welcome to the **`current_model`** architecture documentation. This platform is organized with a **1-to-1 visual-to-code mapping**: every Tab in the Streamlit application corresponds directly to its own dedicated folder under `ui/` (`tab1_consumption`, `tab2_contract`, etc.), allowing developers to instantly locate and modify any UI component or calculation.

---

## ⚡ Quick-Lookup Directory Map (What You See ➔ Where It Lives)

| UI Element / Screen Area | Screen Description | File Path |
| :--- | :--- | :--- |
| 🚀 **Main Entry Point** | Top-level orchestrator & Tab navigation | [`app.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/app.py) |
| 🎨 **Global Styling** | Dark theme CSS, `.sandbox-card`, `.sandbox-card-alert` | [`ui/common/styles.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/common/styles.py) |
| 🗂️ **Shared KPI Cards** | `render_kpi_card()` renderer for metrics and alerts | [`ui/common/cards.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/common/cards.py) |
| **⚡ TAB 1 — Top Level** | Switcher: Synthetic vs. CSV Meter Data | [`ui/tab1_consumption/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/view.py) |
| 📈 **Tab 1: 24h Stacked Chart** | Plotly 24h stacked area profile & grid limit line | [`ui/tab1_consumption/synthetic/charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/synthetic/charts.py) |
| ➕ **Tab 1: Add/Edit Consumer** | `st.form` for machine power, multi-windows, peaks | [`ui/tab1_consumption/synthetic/forms.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/synthetic/forms.py) |
| 🧪 **Tab 1: Synthetic View** | 24h Simulation orchestrator (KPIs, limit, alerts) | [`ui/tab1_consumption/synthetic/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/synthetic/view.py) |
| 📁 **Tab 1: CSV Uploader** | Upload widget, encoding sniffer & column mapping | [`ui/tab1_consumption/csv_inspector/forms.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/csv_inspector/forms.py) |
| 📊 **Tab 1: CSV Chart** | Multi-meter interactive line chart with rangeslider | [`ui/tab1_consumption/csv_inspector/charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/csv_inspector/charts.py) |
| 🔍 **Tab 1: CSV Inspector** | CSV inspector orchestrator (KPIs, overload check) | [`ui/tab1_consumption/csv_inspector/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/csv_inspector/view.py) |
| **📄 TAB 2 — Contract Data** | Warning banner & Contract configuration tab view | [`ui/tab2_contract/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab2_contract/view.py) |
| 📝 **Tab 2: Contract Form** | Capacity tariff, TOU peak/off-peak, taxes table | [`ui/tab2_contract/form.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab2_contract/form.py) |
| ⚙️ **Core: CSV Engine** | Encoding detection, heuristics, demo CSV creator | [`core/csv_parser.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/csv_parser.py) |
| ⚙️ **Core: Timeseries Processor**| Resampling, unit scaling ($15\text{-min-kWh} \to \text{kW}$) | [`core/load_processor.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/load_processor.py) |
| ⚙️ **Core: Metrics Engine** | Peak demand, total MWh, duration calculations | [`core/metrics_engine.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/metrics_engine.py) |
| ⚙️ **Core: Synthetic Engine** | 96-slot 24h consumer array summation & math | [`core/synthetic_engine.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/synthetic_engine.py) |
| 📦 **Model: Consumers** | `SimpleConsumer`, `LoadComponent`, `TimeWindow` | [`models/load_component.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/load_component.py) |
| 📦 **Model: Contract** | `Contract` dataclass, tariff evaluation methods | [`models/contract.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/contract.py) |
| 📦 **Model: Grid Limits** | `GridLimitConfig`, `OverloadAnalysisResult` | [`models/grid_limit.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/grid_limit.py) |
| 📦 **Model: Presets** | Industry, Office, and EV Hub preset generators | [`models/presets.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/presets.py) |

---

## 1. Full Directory Layout

```
current_model/
├── README.md                              # 📖 Quick-lookup index & architecture guide
├── app.py                                 # 🚀 Streamlit Entry Point (~30 lines)
│
├── models/                                # 📦 Pure Data Models (Framework agnostic)
│   ├── __init__.py
│   ├── load_component.py                  # TimeWindow, LoadComponent, SimpleConsumer
│   ├── contract.py                        # Contract dataclass (capacity, TOU, taxes)
│   ├── grid_limit.py                      # GridLimitConfig, OverloadAnalysisResult
│   └── presets.py                         # Predefined load factories (Manufacturing, Office, EV)
│
├── core/                                  # ⚙️ Computation & Data Processing Engines
│   ├── __init__.py
│   ├── csv_parser.py                      # Multi-encoding sniffer, column heuristics, sample CSV
│   ├── load_processor.py                  # Data cleansing, datetime parsing, unit scaling
│   ├── metrics_engine.py                  # KPI calculations (P_max, MWh, avg kW, intervals)
│   └── synthetic_engine.py                # 24h 96-slot summation engine
│
└── ui/                                    # 🎨 Presentation Layer (Mapped 1:1 to App Tabs)
    ├── __init__.py                        # Top-level UI package exports
    │
    ├── common/                            # 🗂️ Shared Styles & Reusable Visual Widgets
    │   ├── __init__.py
    │   ├── styles.py                      # Custom CSS (Dark theme, glassmorphism, card borders)
    │   └── cards.py                       # render_kpi_card() helper (default, ok, alert styles)
    │
    ├── tab1_consumption/                  # ⚡ TAB 1: CONSUMPTION (Synthetic & CSV Ingestion)
    │   ├── __init__.py
    │   ├── view.py                        # Tab 1 top-level dispatcher (render_tab1_consumption)
    │   │
    │   ├── synthetic/                     # Sub-Feature: 24h Bottom-Up Synthetic Simulation
    │   │   ├── __init__.py
    │   │   ├── charts.py                  # Plotly stacked area curve + grid limit line
    │   │   ├── forms.py                   # Add machine form & edit/delete expanders
    │   │   └── view.py                    # Synthetic simulator orchestrator
    │   │
    │   └── csv_inspector/                 # Sub-Feature: Real-World CSV Meter Data Inspector
    │       ├── __init__.py
    │       ├── charts.py                  # Plotly multi-meter timeseries + rangeslider
    │       ├── forms.py                   # CSV upload & column mapping form
    │       └── view.py                    # CSV inspector orchestrator
    │
    ├── tab2_contract/                     # 📄 TAB 2: CONTRACT DATA (Supply Contract & Tariffs)
    │   ├── __init__.py
    │   ├── form.py                        # Electricity supply contract & dynamic taxes editor
    │   └── view.py                        # Tab 2 view with warning banner (render_tab2_contract)
    │
    └── tab3_battery/                      # 🔋 TAB 3: (Future ready for Storage & Peak Shaving)
        └── ...
```

---

## 2. Tab Architecture Details

### Tab 1: `⚡ Consumption` (`ui/tab1_consumption/`)
* **Purpose**: Allows users to either build a synthetic bottom-up load profile machine-by-machine or upload real meter data CSVs.
* **Sub-modules**:
  * `synthetic/`: Bottom-up machine modeling across 96 quarter-hour slots with startup peaks.
  * `csv_inspector/`: High-performance ingestion of international/European CSV meter logs with automated unit scaling.
* **Grid Capacity Limit**: Compact inline toggle & input directly above the chart, accompanied by real-time overload warning cards below.

### Tab 2: `📄 Contract Data` (`ui/tab2_contract/`)
* **Purpose**: Configures the commercial electricity supply contract.
* **Guidance Warning**: Displays `⚠️ Should you wish to not use a contract, leave the fields empty.`
* **Configuration Parameters**:
  * Base monthly fee and currency.
  * Contracted active capacity ($kW$) & monthly capacity tariff ($€/kW/\text{month}$).
  * Excess peak demand penalty rate ($€/kW$).
  * Reactive power tariff ($€/kVARh$), minimum $\cos \varphi$, and free allowance percentage.
  * Time-of-Use (Peak vs. Off-Peak) pricing and peak hour window definitions.
  * Dynamic interactive tax table (VAT, grid fees, renewable surcharges).

---

## 3. How to Run the Application

Launch the primary application directly:

```bash
python -m streamlit run current_model/app.py
```

Or via the prototype orchestrator:

```bash
python -m streamlit run prototypes/presentation.py
```

---

## 4. Developer Guidelines: How to Add or Modify Tabs

1. **Adding a New Tab (e.g. Tab 3 — Battery Simulation)**:
   - Create folder `current_model/ui/tab3_battery/`.
   - Implement `view.py` with function `render_tab3_battery(key_prefix)`.
   - In `app.py`, add `"🔋 3. Battery Storage"` to `st.tabs(...)` and call `render_tab3_battery()`.
   - Update the **Quick-Lookup Directory Map** table in this README.
2. **Separation of Concerns**:
   - Keep data structures in `models/` (pure Python / dataclasses, zero UI dependencies).
   - Keep algorithms and calculations in `core/`.
   - Keep Streamlit widgets, layout, and plots in `ui/tab<N>_<name>/`.
