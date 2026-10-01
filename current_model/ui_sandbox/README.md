# :material/science: UI Sandbox & Minimal Contract Lab (`ui_sandbox`)

An isolated, minimal environment for uploading consumption CSV load profiles and configuring electricity supply contracts with live financial calculation **without having to run `app.py`**.

---

## :material/verified_user: Architectural Rules & Dependency Boundary

> [!IMPORTANT]
> **Strict One-Way Dependency Isolation:**
> 1. **Allowed (`ui_sandbox` $\rightarrow$ Project):** Code inside `ui_sandbox/` is permitted to import modules from `core/`, `models/`, and `ui/` to test live functionality against domain engines.
> 2. **Prohibited (Main Project $\rightarrow$ `ui_sandbox`):** The main application (`app.py`), core calculation engines, domain models, or production UI tabs must **NEVER** import or reference anything located in `ui_sandbox/`.
> 3. **Design Standards:** All UI prototypes must strictly adhere to the project's iconography standard (**Streamlit native Google Material Symbols `:material/<icon_name>:`**, zero cartoon emojis) and English UI text.

---

## :material/folder_open: Directory Structure

```text
current_model/ui_sandbox/
├── __init__.py                           # Module package initializer
├── minimal_contract_system.py            # Minimal CSV + Contract single-page app (15-min interval)
├── standalone_monthly_baseline_lab.py    # Autarkic Monthly Baseline & Tariff Lab (Pozo 600 & Enexis)
├── sandbox_app.py                        # Standalone Streamlit test runner & suite selector
└── README.md                             # Sandbox architecture & usage guide
```

---

## :material/play_arrow: Quick Start & Execution

You can run the UI Sandbox directly with Streamlit:

### Run the Suite Runner (Switch between both labs):
```bash
python -m streamlit run current_model/ui_sandbox/sandbox_app.py
```

### Run the Monthly Baseline & Tariff Lab directly:
```bash
python -m streamlit run current_model/ui_sandbox/standalone_monthly_baseline_lab.py
```

### Run the 15-Minute Load Profile & Contract System directly:
```bash
python -m streamlit run current_model/ui_sandbox/minimal_contract_system.py
```

---

## :material/featured_play_list: Core Functionality

1. **:material/bolt: 1. Consumption (CSV Load Profile Ingestion)**:
   - Upload single/multi-channel CSV meter files or load the 15-minute demo dataset via `render_csv_inspector()`.
   - Automatic delimiter detection, column mapping, and 15-minute timeseries visualization.

2. **:material/description: 2. Electricity Contract & Pricing Architecture**:
   - Two-tier contract structure separating **Regulated Grid Operator Level** (Enexis/Liander/EDEMSA) and **Competitive Supplier Level**:
     - **Regulated Grid Level**:
       - `base_monthly_fee`: Fixed monthly standing/metering fee.
       - `contracted_capacity_kw`: Booked grid capacity limit (GTV).
       - `monthly_capacity_tariff`: Fee per reserved kW/month.
       - `demand_capacity_tariff`: Measured peak demand fee per kW/month.
       - `network_volume_tariff`: Regulated transport volume fee per active kWh (e.g. Enexis MS-D: 0.0250 EUR/kWh).
       - `peak_penalty_rate`: Penalty charge per kW exceeding contracted capacity.
     - **Supplier Level**:
       - `pricing_model`: Toggle between **Fixed Time-of-Use (`time_of_use`)** and **Dynamic Spot Market (`day_ahead_dynamic`)**.
       - `supplier_margin`: Fixed supplier service margin / markup added on top of wholesale market price (e.g. 0.0075 EUR/kWh opslag).
       - `market_price_profile_id`: Linked wholesale price time series (`epex_nl_2025` for Netherlands EPEX Spot 2025).
       - `default_energy_rate`: Safety fallback price if data points are missing.
   - **Monthly Contract Validity (`applicable_months`)**: Define validity periods per contract (defaulting to all 12 months). Multi-contract portfolio allows customizing different rates, capacity tariffs, and peak charges per month (e.g. seasonal contracts or tariff transitions).
   - **12-Month Coverage Overview Matrix**: Interactive visual cards display which contract governs each calendar month.
   - **Contract Duplication & Management**: Duplicate contracts with 1 click to create monthly variants (e.g., Q1 vs. Q2-Q4, Summer vs. Winter).
   - **Presets**: Includes European, Argentine, Netherlands commercial multi-tariff, and Netherlands Dynamic Day-Ahead (`Netherlands Dynamic Day-Ahead (Enexis MS-D 2025)`).

3. **:material/analytics: 3. Financial Assessment & Live Billing Engine**:
   - Interval-precise cost calculation coupling 15-minute customer consumption with 60-min / 15-min wholesale spot prices:
     $$\text{Cost}(t) = \text{Consumption}_{\text{kWh}}(t) \times \Big( \text{SpotPrice}(t) + \text{SupplierMargin} + \text{NetworkVolumeTariff} \Big) + \text{CapacityCharges} + \text{Taxes}$$
   - Dynamic Donut chart visualizing itemized distribution (Spot Energy, Opslag, Grid Capacity, Network Volume, Base Fee, Taxes).
   - Monthly payment series schedule (Zahlungsreihe) stacked bar chart across 12 months.
   - Itemized billing table with basis quantity, unit rate, period total, monthly share, and effective unit cost.

4. **:material/calendar_month: 4. Autarkic Monthly Baseline & Tariff Lab (`standalone_monthly_baseline_lab.py`)**:
   - **Zero Production Risk**: Completely decoupled from `app.py` and global application states.
   - **Exact Mathematical Verification Target**: Replicates the original Bodegas Salentein (*Pozo 600*) dataset (Excel Blatt 1.1 & 1.3) down to the cent:
     - High-peak energy cost (88,002 kWh × € 0.182529/kWh): **€ 16,062.92**
     - Low-peak energy cost (133,848 kWh × € 0.113215/kWh): **€ 15,153.66**
     - Annual fixed standing & network charges: **€ 5,018.40**
     - **Cent-precise Grand Total: € 36,234.97** (automated verification badge: deviation $< 0.01\text{ €}$).
   - **Symmetrical Dual-Matrix Workspace**:
     1. *Table A (Consumption Matrix)*: 12-month editor for $P_{\text{contract}}$, measured monthly peak $P_{\text{max}}$, and $N$ dynamic TOU energy windows ($\text{kWh}_i$).
     2. *Table B (Contract & Tariff Matrix)*: 12-month editor for Base Fee, Price/kW Contracted, Price/kW Over Limit, Price/Peak kW Demand, Price per kWh per TOU window, and statutory Tax %.
   - **Transparent Mathematical Billing Engine**:
     - Contracted Capacity Fee: $P_{\text{contract}} \times \text{Price/kW Contracted} \times (1 + \text{Tax}) / \text{FX}$
     - Measured Peak Demand Fee: $P_{\text{max}} \times \text{Price/Peak kW Demand} \times (1 + \text{Tax}) / \text{FX}$
     - Over-Limit Penalty: $\max(0, P_{\text{max}} - P_{\text{contract}}) \times \text{Price/kW Over Limit} \times (1 + \text{Tax}) / \text{FX}$
     - Energy Charges: $\sum_i (\text{kWh}_i \times \text{Rate}_i \times (1 + \text{Tax}) / \text{FX})$
   - **Live Analytics, Interactive Audit & Export**: Status badge, KPI summary cards, stacked monthly Plotly bar chart, itemized 12-month statement table with separate capacity vs peak demand columns, interactive month-by-month calculation audit panel displaying exact numerical intermediate equations, and CSV/JSON baseline data export.
