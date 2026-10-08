# :material/account_balance: Status Quo 2025 Accounting & Audit Sandbox (`status_quo_2025`)

An unbundled, European commercial electricity billing pipeline and automated mathematical verification laboratory for the reference year **2025** ($35,040$ intervals à $0.25\text{ h}$).

---

## :material/layers: Architectural Layers (Separation of Concerns)

```text
current_model/ui_sandbox/status_quo_2025/
├── __init__.py                  # Package exports & clean public API
├── config_and_models.py         # Layer 1: Strict dataclasses & enums (no calculation logic)
├── tariff_defaults_2025.py      # Stage 1: Official Liander 2025 rates & benchmark supplier defaults
├── consumption_pipeline.py      # Layer 2: 35,040 normalization, Europe/Amsterdam timestamps, HT/NT segmentation
├── dso_accounting.py            # Layer 3: Dutch grid operator rules, monthly peaks & capacity breach logic
├── commercial_accounting.py     # Layer 4: Retailer (Fixed, Variable, Dynamic EPEX Spot), Meetbedrijf & Levies
├── status_quo_master.py         # Layer 5: Consolidation, Net total, blended €/kWh, VAT & 15-year TCO NPV
├── audit.py                     # Automated 13-criteria verification battery across 4 audit points
├── status_quo_lab.py            # Interactive Streamlit UI laboratory with Material Symbols & exports
└── README.md                    # Module documentation & mathematical reference
```

---

## :material/sync_alt: Sequential Data Flow & Processing Pipeline

```
[Raw Consumption: 15-min CSV or Synthetic Simulation]
                         │
                         ▼
   [Layer 2: consumption_pipeline.py]
   • Reindex to exact 35,040 steps (Delta_t = 0.25 h)
   • Map calendar months (1 to 12)
   • Classify Liander TOU windows (HT: Mo-Fr 07:00-23:00 vs NT)
   • Extract monthly sums (E_m) and monthly maximums (P_peak,m)
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
[Layer 3: dso_accounting.py]     [Layer 4: commercial_accounting.py]
• Connection fee & Vastrecht     • Retailer: Fixed / Var / Dynamic Spot
• Cable length surcharge         • EPEX Spot NL 2025 step-by-step
• Volumetric HT/NT transport     • Fudura flat annual metering fee
• Monthly peaks (P_peak,m)       • Statutory levies (flat €/kWh)
• Contract capacity breach       • Feed-in compensation = € 0.00
        │                                 │
        └────────────────┬────────────────┘
                         ▼
           [Layer 5: status_quo_master.py]
           • Net Annual Total (DSO + Supp + Meter + Levies)
           • Blended electricity price (€/kWh)
           • Statutory VAT isolation (21% BTW)
           • 15-year TCO NPV lifecycle evaluation
                         │
                         ▼
                 [audit.py]
                 • Automated verification of all 13 criteria
                 • Pass/Fail diagnostic protocol
```

---

## :material/fact_check: The 4 Verification Audit Points & 13 Criteria

| Audit Point | Criterion | Mathematical Rule |
| :--- | :--- | :--- |
| **1. Load Integrity** | **1.1** Step count | Exactly $35,040$ entries ($\Delta t = 0.25\text{ h}$). |
| | **1.2** Energy conservation | $\sum_{t=1}^{35,040} P(t) \cdot 0.25\text{ h} = \sum_{m=1}^{12} E_m$ |
| | **1.3** Time classification | Unique calendar month ($1 \dots 12$) and TOU flag (HT/NT) per interval. |
| **2. DSO Accounting** | **2.1** Monthly peaks | Exactly 12 values for $P_{\text{peak}, m} = \max_{t \in m} P(t)$. |
| | **2.2** Peak demand fees | Total peak fees $= \sum_{m=1}^{12} (P_{\text{peak}, m} \cdot \text{Rate}_{\text{peak}})$. |
| | **2.3** Capacity & Breach | When $P_{\text{peak}, m} > P_{\text{contract}}$, breach flag is logged and capacity is billed on $P_{\text{peak}, m}$. |
| | **2.4** Standing & Volume | Fixed connection/transport on 12 months; volumetric fee $= \sum E_{\text{HT}} \cdot r_{\text{HT}} + \sum E_{\text{NT}} \cdot r_{\text{NT}}$. |
| **3. Commercial Accounting** | **3.1** Pricing mode | Fixed ($E_{\text{total}} \cdot r$), Variable ($\sum E_m \cdot r_m$), or Dynamic ($\sum E(t) \cdot (S(t) + M)$). |
| | **3.2** Metering independence | Strictly flat annual fee (independent of volume or peak kW). |
| | **3.3** Statutory levies | Total levies $= E_{\text{total}} \cdot \text{Rate}_{\text{levy}}$. |
| | **3.4** Feed-in lock | Pure Status Quo baseline feed-in credit $= 0.00\text{ €}$. |
| **4. Master KPI & TCO** | **4.1** Net annual sum | $\text{Cost}_{\text{net}} = \text{DSO} + \text{Supplier} + \text{Metering} + \text{Levies}$. |
| | **4.2** Blended price | $\text{Rate}_{\text{blended}} = \frac{\text{Cost}_{\text{net}}}{E_{\text{total}}}\quad [€/\text{kWh}]$. |
| | **4.3** 15-year TCO NPV | $\text{TCO}_{15} = \sum_{y=1}^{15} \frac{\text{Cost}_{\text{net}} \cdot (1 + g)^{y-1}}{(1 + r)^y}$. |

---

## :material/play_arrow: Execution & Quick Start

You can run the Status Quo 2025 lab directly via Streamlit:

```bash
python -m streamlit run current_model/ui_sandbox/sandbox_app.py
```
Or run the standalone runner for this specific lab:
```bash
python -m streamlit run current_model/ui_sandbox/status_quo_2025/status_quo_lab.py
```
