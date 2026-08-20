# Energy Simulator & Load Profile Analyzer — `current_model` Architecture

Welcome to the **`current_model`** architecture documentation. This platform is organized with a **1-to-1 visual-to-code mapping**: every Tab in the Streamlit application corresponds directly to its own dedicated folder under `ui/` (`tab1_consumption`, `tab2_contract`, etc.), allowing developers to instantly locate and modify any UI component or calculation.

---

## ⚡ Quick-Lookup Directory Map (What You See ➔ Where It Lives)

| UI Element / Screen Area | Screen Description | File Path |
| :--- | :--- | :--- |
| 🚀 **Main Entry Point** | Top-level orchestrator & Tab navigation | [`app.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/app.py) |
| 🧪 **Test Suite Runner** | Zero-dependency health check & regression suite | [`run_tests.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/run_tests.py) |
| 🎨 **Global Styling** | Dark theme CSS, `.sandbox-card`, `.sandbox-card-alert` | [`ui/common/styles.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/common/styles.py) |
| 🗂️ **Shared KPI Cards** | `render_kpi_card()` renderer for metrics and alerts | [`ui/common/cards.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/common/cards.py) |
| **⚡ TAB 1 — Top Level** | Switcher: Synthetic (24h/365d) vs. CSV Meter Data | [`ui/tab1_consumption/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/view.py) |
| 📈 **Tab 1: 24h & 365d Charts** | Plotly 24h stacked, 365d timeseries & 2D heatmap | [`ui/tab1_consumption/synthetic/charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/synthetic/charts.py) |
| ➕ **Tab 1: Add/Edit Consumer** | `st.form` for power, schedule (Mo-Fr), seasonality | [`ui/tab1_consumption/synthetic/forms.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/synthetic/forms.py) |
| 🧪 **Tab 1: Synthetic View** | 24h & 365d simulation, holiday calendar, KPIs | [`ui/tab1_consumption/synthetic/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/synthetic/view.py) |
| 📁 **Tab 1: CSV Uploader** | Upload widget, encoding sniffer & column mapping | [`ui/tab1_consumption/csv_inspector/forms.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/csv_inspector/forms.py) |
| 📊 **Tab 1: CSV Chart** | Multi-meter interactive line chart with rangeslider | [`ui/tab1_consumption/csv_inspector/charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/csv_inspector/charts.py) |
| 🔍 **Tab 1: CSV Inspector** | CSV inspector orchestrator (KPIs, overload check) | [`ui/tab1_consumption/csv_inspector/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab1_consumption/csv_inspector/view.py) |
| **📄 TAB 2 — Contract & Costs** | Contract form, monthly payment series & financial bill | [`ui/tab2_contract/view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab2_contract/view.py) |
| 📝 **Tab 2: Contract Form** | Dynamic TOU rates editor, capacity charge, taxes | [`ui/tab2_contract/form.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab2_contract/form.py) |
| 📊 **Tab 2: Financial Charts** | Cost Donut chart & monthly payment series stacked bar | [`ui/tab2_contract/charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui/tab2_contract/charts.py) |
| ⚙️ **Core: Synthetic Engine** | 24h (96 steps) and 365d (35,040 steps) vectorization | [`core/synthetic_engine.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/synthetic_engine.py) |
| ⚙️ **Core: Financial Engine** | Monthly bills, Zahlungsreihe, TOU, capacity & taxes | [`core/financial_engine.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/financial_engine.py) |
| ⚙️ **Core: CSV Engine** | Encoding detection, heuristics, demo CSV creator | [`core/csv_parser.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/csv_parser.py) |
| ⚙️ **Core: Timeseries Processor**| Resampling, unit scaling ($15\text{-min-kWh} \to \text{kW}$) | [`core/load_processor.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/load_processor.py) |
| ⚙️ **Core: Metrics Engine** | Peak demand, total MWh, duration calculations | [`core/metrics_engine.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/core/metrics_engine.py) |
| 📦 **Model: Consumers** | `SimpleConsumer`, `LoadComponent`, `TimeWindow` | [`models/load_component.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/load_component.py) |
| 📦 **Model: Calendar** | `CalendarConfig` (Year, custom system holidays) | [`models/calendar_config.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/calendar_config.py) |
| 📦 **Model: Financial Models** | `CostLineItem`, `MonthlyPaymentRecord`, `FinancialCostBreakdown` | [`models/financial.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/financial.py) |
| 📦 **Model: Contract** | `Contract` dataclass, dynamic TOU evaluation | [`models/contract.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/contract.py) |
| 📦 **Model: Grid Limits** | `GridLimitConfig`, `OverloadAnalysisResult` | [`models/grid_limit.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/grid_limit.py) |
| 📦 **Model: Presets** | Industry, Office, and EV Hub preset generators | [`models/presets.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/models/presets.py) |

---

## 1. Tab Architecture Details

### Tab 1: `⚡ Consumption` (`ui/tab1_consumption/`)
* **Simulation Horizons**:
  * **24-Hour Typical Day**: 96 quarter-hour intervals with stacked consumer areas.
  * **Full Year (365 Days / 35,040 Intervals)**: Vectorized simulation accounting for individual consumer weekday schedules (Monday..Sunday, default: Mo-Fr), seasonal profiles (Winter/Summer heavy), and system-wide custom holidays (treated as Sundays).
* **Visualizations**: 24h stacked area profile, 365-day interactive time series with range slider, and 24h x 365d Annual Intensity Heatmap.

### Tab 2: `📄 Contract Data` (`ui/tab2_contract/`)
* **Contract Configuration**: Base fee, contracted active capacity ($kW$), capacity tariff, peak penalties, dynamic TOU energy rates table, and dynamic taxes table.
* **Monthly Payment Schedule (Zahlungsreihe)**: Full-duration month-by-month payment series with itemized costs, taxes, gross totals, and overall summary row.

---

## 2. Automated Testing Suite

```bash
python run_tests.py
```
Validates models, core engines, annual simulation, financial calculations, backward compatibility migrations, and codebase compilation across 24 automated test cases.
