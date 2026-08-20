# Energy Simulator & Load Profile Analyzer — `current_model` Architecture

Welcome to the **`current_model`** module repository. This package is an enterprise-ready, modular platform for bottom-up synthetic load profile generation, real-world CSV smart-meter data ingestion, grid capacity limit monitoring, and electricity contract/tariff modeling.

---

## 1. Directory Structure

```
current_model/
├── README.md                      # 📖 Architecture, module guide & update instructions
├── app.py                         # 🚀 Central Streamlit Application Orchestrator with Tabs (~55 lines)
│
├── models/                        # 📦 Pure Data Models & Serializable Classes
│   ├── __init__.py                # Package exports
│   ├── load_component.py          # TimeWindow, LoadComponent, SimpleConsumer (96-slot 24h arrays)
│   ├── contract.py                # Contract dataclass (TOU tariffs, reactive power, taxes)
│   ├── grid_limit.py              # GridLimitConfig, OverloadAnalysisResult
│   └── presets.py                 # Factory presets (Manufacturing, Office, Mobility Hub)
│
├── core/                          # ⚙️ Computation & Data Processing Engines
│   ├── __init__.py                # Package exports
│   ├── csv_parser.py              # Encodings (UTF-8, Latin-1), delimiter sniffing, heuristics
│   ├── load_processor.py          # Data cleansing, datetime parsing, unit scaling (kWh -> kW)
│   ├── metrics_engine.py          # KPI metrics (P_max, MWh, avg kW, data point intervals)
│   └── synthetic_engine.py        # 24h 96-step aggregation of active machines & sum curve
│
└── ui/                            # 🎨 Streamlit Presentation Layer & UI Components
    ├── __init__.py                # Package exports
    ├── common/                    # Shared visual assets
    │   ├── __init__.py
    │   ├── styles.py              # Dark theme CSS, glassmorphism, card typography
    │   └── cards.py               # KPI and alert card renderers (Standard, OK-Green, Alert-Red)
    │
    ├── synthetic/                 # UI Module: 24-Hour Synthetic Simulation
    │   ├── __init__.py
    │   ├── charts.py              # Plotly stacked area chart with grid capacity threshold line
    │   ├── forms.py               # st.form for adding (up to 4 windows/peaks) and editing consumers
    │   └── view.py                # render_synthetic_simulator() orchestrator
    │
    ├── csv_inspector/             # UI Module: Real CSV Smart-Meter Inspector
    │   ├── __init__.py
    │   ├── charts.py              # Multi-channel line chart with rangeslider and peak markers
    │   ├── forms.py               # File uploader and column mapping widgets
    │   └── view.py                # render_csv_inspector() orchestrator
    │
    └── contract/                  # UI Module: Contract & Tariff Configuration
        ├── __init__.py
        └── form.py                # render_contract_view() & render_contract_form()
```

---

## 2. Navigation & Tab Layout

The application is structured into two main tabs:
* **Tab 1: `⚡ Consumption`**
  * Switch between bottom-up 24-hour synthetic load simulation and multi-channel real CSV meter data inspection.
  * Includes compact grid capacity limit monitoring and real-time overload analysis cards.
* **Tab 2: `📄 Contract Data`**
  * Dedicated electricity supply contract and tariff configuration form.
  * Includes a helpful guidance warning: *"Should you wish to not use a contract, leave the fields empty."*
  * Configures capacity charges, Time-of-Use rates (peak/off-peak), reactive energy penalties, and dynamic tax tables.

---

## 3. How to Run

From the project root directory, launch the Streamlit application:

```bash
python -m streamlit run current_model/app.py
```

Alternatively, the prototype orchestrator remains fully functional:
```bash
python -m streamlit run prototypes/presentation.py
```
