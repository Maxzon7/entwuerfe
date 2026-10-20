# BESS Peak Shaving & 15-Year Life-Cycle TCO Sandbox

A dedicated, isolated Streamlit engineering and financial laboratory located at `ui_sandbox/BESS_sandbox/`.
It allows testing, sizing, and validating Battery Energy Storage System (BESS) peak shaving feasibility and multi-year economics without interacting with the main production workflow or navigating through multi-scenario setups.

---

## 1. Quick Start

Run the sandbox directly in isolated mode:

```bash
python -m streamlit run "ui_sandbox/BESS_sandbox/app.py"
```

Or run via Streamlit:

```bash
streamlit run ui_sandbox/BESS_sandbox/app.py
```

---

## 2. Architecture & Modules

```
ui_sandbox/BESS_sandbox/
├── __init__.py               # Package exports: render_bess_sandbox, engines, presets
├── app.py                    # Main standalone Streamlit entrypoint & scenario coordinator
├── baseline_presets.py       # Pre-configured Dutch industrial & commercial benchmark profiles
├── sandbox_bess_engine.py    # Physical gross sizing, dynamic degradation, & 15-year TCO engine
├── view_technical.py         # Tab 1: Peak shaving feasibility, diagnostics, & 15-min dispatch
├── view_financial.py         # Tab 2: Avoided grid upgrade CAPEX vs. BESS 15Y TCO & NPV
├── view_optimizer.py         # Tab 3: Parametric capacity sweep & sensitivity tornado
└── README.md                 # Complete sandbox documentation
```

---

## 3. Core Features & Capabilities

### Tab 1: Peak Shaving & Physical Dispatch (`view_technical.py`)
- **Grid Diagnostic Analyzer:** Computes peak facility demand, peak overload above contracted grid limit (kW), cumulative overload duration (hours & % of year), and worst continuous deficit event energy (kWh).
- **Automated Gross Nameplate Sizing:** Automatically calculates the true battery nameplate size accounting for:
  $$\text{Usable DoD Window} = \text{SoC}_{\max} - \text{SoC}_{\min}$$
  $$\text{Discharge Efficiency} = \sqrt{\text{RTE}}$$
  $$\text{Gross Capacity (kWh)} = \frac{\text{Worst Event Energy (kWh)}}{\text{Usable DoD} \times \sqrt{\text{RTE}}} \times (1 + \text{Safety Margin})$$
- **100% Feasibility Badge:** Explicit green/red verdict verifying whether all peak spikes are completely eliminated or if residual overloads remain.
- **Plotly Visualizations:**
  - 15-Minute interactive power dispatch timeseries with 14-day default zoom and range slider.
  - 7-Day representative Monday–Sunday weekly cycling profile.
  - Load Duration Curve comparing original facility load vs. post-BESS profile.
  - 24-Hour $\times$ 7-Day State of Charge (SoC) Heatmap.

### Tab 2: Financial Viability & 15-Year TCO (`view_financial.py`)
- **Direct Baseline Comparison:** Compares investing in physical grid reinforcement (avoided transformer station upgrade CAPEX + avoided monthly transformer rental fees) against deploying BESS.
- **Unbundled Tariff Reductions:** Evaluates monthly peak demand charge savings ($\Delta \text{kW-max} \times \text{Tariff}$) and contracted capacity savings ($\Delta \text{GTV} \times \text{Tariff}$).
- **Dynamic 15-Year Battery Degradation:** Multi-year capacity retention model factoring in:
  - Calendar aging (1.0%/yr)
  - Cycling throughput wear (0.04% per 100 Equivalent Full Cycles)
  - Ambient temperature stress penalties ($+0.05\%$ per °C above 25°C)
  - Year-10 cell stack overhaul (restoring capacity to 95%)
- **Itemized Annual Operational Cost Comparison Table:** Baseline Upgrade vs. With-BESS vs. Delta.
- **Financial Visualizations:**
  - 15-Year Cumulative Life-Cycle Expenditure Trajectory.
  - Cumulative Cash Flow & Amortization Break-Even Payback Curve.
  - Stacked Annual Cost Breakdown Bar Chart.
  - Turn-Key CAPEX Sizing Donut.

### Tab 3: Sizing Optimizer & Sensitivity Analysis (`view_optimizer.py`)
- **Parametric Sizing Sweep:** Simulates 6 strategic capacity multiples ($0.5\times$ to $2.0\times$ recommended size) to identify:
  - **Minimum Feasible Sizing:** Lowest turnkey investment that achieves 100% peak shaving.
  - **Optimal Economic Sizing:** Sizing that maximizes 15-year Net Present Value (NPV).
- **One-Click Application:** Instant form population with the optimal parameters.
- **Multi-Variable Sensitivity Tornado:** Tests investment sensitivity across $\pm 10\%$ and $\pm 20\%$ variations in BESS CAPEX, Avoided Grid Upgrade CAPEX, and Demand Tariffs.

---

## 4. Benchmark Presets

1. **Case 1: Liander Industrial Peak Shaving (AC4b vs. AC5a Upgrade)**
   - Facility Load: 350 kW peak manufacturing profile with intermittent high-demand machinery cycles.
   - Grid Limit: Maintained on low-voltage AC4b contracted connection (147 kW limit).
   - Baseline Alternative: Upgrading to medium-voltage AC5a (350 kW) requiring €85,000 station CAPEX and €450/month transformer rental.
   - BESS Solution: 260 kW / 500 kWh LFP modular system.

2. **Case 2: Enexis Commercial Facility (MS-D Tariff)**
   - Facility Load: 250 kW peak commercial logistics building.
   - Grid Limit: Contracted capacity capped at 150 kW.
   - Avoided Upgrade: €45,000 transformer expansion.
   - BESS Solution: 150 kW / 250 kWh LFP modular system.

3. **Custom / Uploaded Profile Adapter**
   - Automatically ingests 15-minute load CSV data uploaded by the user or shared from `ui_sandbox/Currentsituation_sandbox/` via `st.session_state["active_csv_df"]`.

---

## 5. Architectural Isolation Rules

- **Strict One-Way Dependency:** `ui_sandbox/BESS_sandbox/` may import from `core/`, `models/`, `ui/`, and other sandbox packages.
- **Production Guard:** Core production modules (`core/`, `models/`, `ui/`, and root `app.py`) **MUST NEVER** import from `ui_sandbox/`.
