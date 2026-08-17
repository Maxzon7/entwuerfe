# Standalone Energy Simulator Exports

This directory contains standalone, minimal, and fully functional modules extracted from the simulator for independent execution, sharing, testing, and integration.

---

## 📁 Contents

### 1. `advanced_baseline_export.py`
A completely self-contained **15-minute resolution synthetic load profile generator** with:
- **12-Month Seasonality**: Configurable monthly consumption (kWh), working days per week, and working hours per day.
- **Base Load Floor & Stochastic Noise**: Gaussian fluctuations with configurable intensity.
- **Strict Energy Conservation**: $\sum P(t) \cdot 0.25\,\text{h} \equiv E_m$.
- **Dynamic Anomaly & Event Injection**:
  - `additional_load` ($+\text{kW}$), `fixed_value` ($=\text{kW}$), and `reduction` ($-\text{kW}$).
  - Recurring weekly patterns, date range blocks, or arbitrary calendar dates.
- **Direct Interactive Streamlit App** with KPI metrics, Plotly visualizations, and CSV exporter.

#### Running as a Standalone App:
```bash
streamlit run exports/advanced_baseline_export.py
```

#### Importing in Python:
```python
from exports.advanced_baseline_export import generate_advanced_baseline, AnomalyConfig

# Define optional anomalies
anomaly = AnomalyConfig(
    id="test_01",
    anomaly_type="additional_load",
    value_kw=75.0,
    frequency_type="regular",
    start_time="09:00",
    end_time="12:00",
    regular_days=["Monday", "Wednesday"]
)

# Generate full-year 15-min profile (35,040 rows)
df = generate_advanced_baseline(
    base_load_pct=15.0,
    enable_noise=True,
    noise_percentage=5.0,
    anomalies=[anomaly],
    year=2026
)
print(df.head())
```

---

### 2. `demo_contract_data_export.py`
A completely self-contained **Grid Contract Data Model & Multi-Pillar Tariff Billing Engine** matching the Demo Mode configuration:
- **4-Pillar Grid Tariff**:
  1. *Pillar 1*: Fixed monthly service charge (€/month).
  2. *Pillar 2*: Contracted capacity limit ($\text{kW}$) & rate (€/$\text{kW}$/month).
  3. *Pillar 3*: Measured peak charge / Pico penalty (€/$\text{kW}$/month).
  4. *Pillar 4*: Excess capacity penalty (€/$\text{kW}$/month).
- **Time-of-Use (ToU) Active Energy**: Peak (*Alta*), Off-Peak (*Baja*), and Mid-Peak (*Resto*) hourly pricing windows.
- **Taxes & VAT**: Surcharges with non-compounded and compounded rate support.
- **Custom Adjustments**: Pre-tax and post-tax credits/debits.
- **Direct Interactive Streamlit App** with live bill calculation, comparison charts, and JSON preset export/import.

#### Running as a Standalone App:
```bash
streamlit run exports/demo_contract_data_export.py
```

#### Importing in Python:
```python
from exports.demo_contract_data_export import (
    get_default_demo_contract_params,
    get_bill_components,
    generate_demo_test_profiles,
    calculate_bill_comparison
)

# 1. Get default demo contract parameters
contract = get_default_demo_contract_params()

# 2. Generate demo baseline and optimized load profiles
df_base, df_opt = generate_demo_test_profiles(monthly_consumption_kwh=50000.0)

# 3. Calculate financial billing breakdown
base_bill, opt_bill, summary = calculate_bill_comparison(df_base, df_opt, contract)

print("Baseline Annual Bill:", f"€{summary['baseline_total_eur']:,.2f}")
print("Optimized Annual Bill:", f"€{summary['optimized_total_eur']:,.2f}")
print("Projected Savings:", f"€{summary['savings_eur']:,.2f} ({summary['savings_pct']:.1f}%)")
```
