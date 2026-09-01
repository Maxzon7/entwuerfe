# 📊 Presentation 2: CSV Load Profile Visualizer & Inspector

## 📖 Overview

The **`presentation2`** module provides a complete, robust, and interactive tool for uploading, inspecting, cleaning, converting, and visualizing electrical load profiles from arbitrary CSV files.

It specifically solves common real-world challenges encountered when dealing with European, Dutch, and international utility data:
- **Split Date & Time columns** (e.g. Column `#` containing `01.01.2024` and Column `CODE` containing `00:15`).
- **European date formats** (`DD.MM.YYYY` / `DD/MM/YYYY`) and decimal commas (`12,5` $\rightarrow$ `12.5`).
- **Energy-to-Power conversions** (e.g. Converting $2\,\text{kWh}$ recorded in a 15-minute interval to $8\,\text{kW}$ active electrical power).
- **Interactive File Inspector:** A live raw-table preview window that lets you inspect headers, skip metadata comments, and limit row ranges before processing.

---

## 🏗️ Architecture & Module Structure

```
presentation2/
├── __init__.py           # Package exports & public API
├── parser.py             # File ingestion, encoding fallback, metadata skipping & column detection
├── processor.py          # Multi-column timestamp merging, date parsing, unit normalization
├── metrics.py            # Key Performance Indicators (KPIs) engine (Peak, Baseload, Energy, Duration)
├── visualizer.py         # Dark-themed interactive Plotly time series chart with range sliders
└── README.md             # This in-depth documentation
```

### Module Responsibilities

| Module | Purpose |
| :--- | :--- |
| **`parser.py`** | Reads files with multi-encoding fallbacks (`utf-8`, `latin1`, `cp1252`), sniffs delimiters (`,`, `;`, `\t`), detects metadata rows, and intelligently guesses Date, Time, and Meter columns. Also contains a demo data generator. |
| **`processor.py`** | Merges selected timestamp columns into a unified `pd.to_datetime` series (`dayfirst=True`), cleans numeric formatting, applies unit multipliers, and aggregates total grid demand in kW. |
| **`metrics.py`** | Calculates peak demand ($P_{\max}$), minimum baseload ($P_{\min}$), average power ($\bar{P}$), total energy ($E_{\text{tot}}$ in kWh and MWh), time resolution, and data point counts. |
| **`visualizer.py`** | Renders high-performance Plotly line charts (`plotly_dark`, `#0B0F19`) with sub-meter curves, a distinct white total demand curve, peak annotations, and range sliders for fine-grained time navigation. |

---

## 🔢 Core Mathematical Calculations & Units

### 1. 15-Minute Interval Energy to Power Conversion
When a smart meter records electrical energy $E \,[\text{kWh}]$ consumed over a 15-minute interval ($\Delta t = 15\,\text{min} = 0.25\,\text{h}$), the average active power $P \,[\text{kW}]$ during that interval is:

$$P \,[\text{kW}] = \frac{E \,[\text{kWh}]}{\Delta t \,[\text{h}]} = \frac{E \,[\text{kWh}]}{0.25\,\text{h}} = E \,[\text{kWh}] \times 4.0$$

*Example:* A meter record of $2.0\,\text{kWh}$ in 15 minutes corresponds to an active load of $8.0\,\text{kW}$.

### 2. Supported Units & Multipliers

| Selected Unit Option | Formula Applied | Description |
| :--- | :--- | :--- |
| `kWh (15-min interval) → kW` | $P = E \times 4.0$ | Standard 15-min interval meter energy (e.g. Dutch Kwartierdata) |
| `kW (Active Power - Direct)` | $P = P_{\text{raw}}$ | Direct power reading (no conversion needed) |
| `W (Watt) → kW` | $P = P_{\text{raw}} / 1000.0$ | Sensor readings recorded in Watts |
| `kWh (Hourly interval) → kW` | $P = E \times 1.0$ | Hourly interval energy ($E / 1.0\,\text{h}$) |

### 3. Total Consumption & Energy Integration
For $N$ time intervals with power $P_i$ and interval duration $\Delta t_i \,[\text{h}]$:

- **Peak Power ($P_{\max}$):**
  $$P_{\max} = \max_{i} (P_i)$$
- **Minimum Baseload ($P_{\min}$):**
  $$P_{\min} = \min_{i} (P_i)$$
- **Total Electrical Energy ($E_{\text{tot}}$):**
  $$E_{\text{tot}} = \sum_{i=1}^{N} \left( P_i \times \Delta t_i \right) \,[\text{kWh}]$$
- **Average Active Power ($\bar{P}$):**
  $$\bar{P} = \frac{1}{N} \sum_{i=1}^{N} P_i = \frac{E_{\text{tot}}}{\text{Duration in Hours}} \,[\text{kW}]$$

---

## 🚀 How to Run & Use

### Running from Terminal
```powershell
python -m streamlit run presentation2.py
```

### User Workflow
1. **Upload CSV File(s):** Use the sidebar file uploader or click **„✨ Load Sample Demo CSV“**.
2. **Inspect Raw Table:** Expand the **„CSV Preview & Table Inspector“** to see row indices, column headers, and sample values.
3. **Map Columns:**
   - **Timestamp Column(s):** Select 1 column (if combined) or multiple columns (e.g. `['#', 'CODE']` for Date + Time).
   - **Power Column(s):** Select the numeric meter channel (e.g. `['871687400008864731MV']`).
   - **Unit:** Select `kWh (15-min interval) → kW` or direct `kW`.
4. **Analyze:** Instantly review the KPI metric cards, navigate the interactive dark Plotly chart with the range slider, and inspect the cleaned data table.
