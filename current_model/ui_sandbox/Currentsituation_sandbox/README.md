# Current Situation (Status Quo) Sandbox: Dutch Commercial Grootverbruik Market

## 1. Overview & Purpose
The `Currentsituation_sandbox` folder provides an authoritative, self-contained reference modeling the Dutch commercial electricity market (*Grootverbruik* > 3×80A / Medium Voltage) according to the regulatory standards set by the Authority for Consumers and Markets (ACM) and regional grid operators (DSOs: Liander, Enexis, Stedin).

This sandbox serves two core functions:
1. **Consumption Profile Ingestion & Inspector (`consumption/`)**: Ingests 15-minute interval meter data (35,040 intervals per non-leap year), analyzes peak demand, overload exceedances, load factor, and diurnal time-of-use distributions.
2. **4-Pillar Unbundled Billing & Procurement Advisory Suite (`contract/` & `engine/`)**: Models the true unbundled reality of Dutch commercial electricity procurement where grid transport, commodity supply, certified metering, and transformer equipment are contracted independently across separate market actors.

---

## 2. Complete Program & Directory Structure

```text
current_model/ui_sandbox/Currentsituation_sandbox/
├── __init__.py                                 <- Package initializer exporting main workbench renderers
├── README.md                                   <- Comprehensive architectural documentation (this file)
├── app.py                                      <- Standalone Streamlit application entrypoint
├── ui_theme.py                                 <- Modern dark theme tokens, Google Fonts, Plotly template & badges
│
├── engine/                                     <- Authoritative Dutch Grootverbruik Accounting Subsystem
│   ├── __init__.py                             <- Public API exports for models, accounting, and advisory
│   ├── config_and_models.py                    <- Data models: 4 pillars, AC categories, PAV, 12-month ratchet,
│   │                                              Tranche/Click blocks, Trafo rental, and unbundled result containers
│   ├── consumption_pipeline.py                 <- 35,040 15-min interval normalizer & synthetic profile generators
│   │                                              (Benchmark Profile A: 360 MWh, Benchmark Profile B: 1.2 GWh)
│   ├── dso_accounting.py                       <- 6-component ACM formula: PAV_mnd, Vastrecht, GTV, Maandpiek,
│   │                                              Transport kWh, Blindvermogen (cos φ < 0.85), & 12-month ratchet lock
│   ├── commercial_accounting.py                <- 5-component supplier invoice: Wholesale Base (Fixed/Spot/Tranche),
│   │                                              Opslag markup, Onbalanskosten, GvO green certificates, Vastrecht
│   ├── tax_accounting.py                       <- Degressive 5-bracket Energiebelasting (2025/2026) & Vermindering rebate
│   ├── trafo_accounting.py                     <- Medium Voltage transformer station rental & NEN 3840 maintenance
│   ├── status_quo_master.py                    <- 4-pillar consolidation master, 12-month series, 15-year TCO trajectory,
│   │                                              and legacy adapter for financial cost breakdowns
│   ├── procurement_engine.py                   <- Executive strategic advisory: 3-Route Sourcing Comparator,
│   │                                              Voltage Transition Advisor (AC4b vs AC5a), & BESS Flex Calculator
│   ├── tariff_defaults_2025.py                 <- Official Liander AC2–AC6 catalogs, 4 supplier market segments,
│   │                                              EMV metering catalog, and transformer station rental presets
│   └── audit.py                                <- 5-point mathematical audit battery & gross/net reconciliation
│
├── consumption/                                <- Interval Consumption Inspector
│   ├── __init__.py
│   ├── view.py                                 <- Mode switcher: CSV upload vs Synthetic Benchmark Generator
│   ├── csv_inspector/
│   │   ├── __init__.py
│   │   ├── view.py                             <- CSV Inspector with Plotly time series & KPI cards
│   │   ├── charts.py                           <- Interactive load curve & monthly breakdown figures
│   │   └── forms.py                            <- Delimiter auto-detector, skiprows, and column mapping form
│   └── synthetic/
│       ├── __init__.py
│       ├── view.py                             <- 24h & 365-day diurnal synthetic profile simulator
│       ├── charts.py                           <- Daily load profile curves & seasonal heatmaps
│       └── forms.py                            <- Commercial appliance parametrization form
│
└── contract/                                   <- Status Quo Billing & Advisory Views
    ├── __init__.py
    ├── view.py                                 <- 4-pillar form-driven contract configuration & billing view
    ├── charts.py                               <- Cost share donut, 12-month payment series, & 15-year TCO figures
    ├── form.py                                 <- Legacy parameter form adapter
    ├── procurement_view.py                     <- Executive Advisory: 3-Route Comparator, Voltage Transition, BESS
    ├── comparison_view.py                      <- Multi-contract scenario comparison view
    └── comparison_charts.py                    <- Scenario comparison figures
```

---

## 3. The 4-Pillar Unbundled Market Architecture

In the Dutch commercial sector (> 3×80A), energy billing is unbundled into four distinct legal contracts and regulatory relationships:

```
+---------------------------------------------------------------------------------------------------+
|                                 DUTCH COMMERCIAL ELECTRICITY SPEND                                |
+---------------------------------+---------------------------------+-------------------------------+
| 1. REGULATED GRID (DSO)         | 2. ENERGY RETAILER              | 3. CERTIFIED METERING (EMV)   |
| ACM Tariff Decision (Liander)   | Free Market Contract            | Commercial Telemetry Contract |
| - PAV (Fixed Connection)        | - Wholesale Base (Spot/Tranche) | - 15-Min Telemetry Data       |
| - Vastrecht (Admin)             | - Opslag (Supplier Markup)      | - NEDU Clearinghouse          |
| - GTV (Contracted kW)           | - Onbalanskosten (Imbalance)    | - Tiered by Voltage Level     |
| - Maandpiek (Measured Peak kW)  | - GvO (Green Certificates)      |                               |
| - Transport kWh (Day/Night)     | - Vastrecht levering (Admin)    | 4. TRANSFORMER RENTAL         |
| - Blindvermogen (cos φ < 0.85)  +---------------------------------+ Rented Substation (Fudura)    |
| - 12-Month Ratchet Lock         | STATUTORY TAXES: Energiebelasting (5 Degressive Brackets)       |
|                                 | & Vermindering Heffingskorting (€524.95 / €519.80 Credit)       |
+---------------------------------+-----------------------------------------------------------------+
```

### Pillar 1: Regulated Verteilnetzbetreiber (DSO / Netbeheerder)
The regional DSO (Liander, Enexis, Stedin) operates physical grid lines under rates set by the ACM. The monthly grid invoice follows the 6-part formula:

$$\text{DSO}_{\text{month}} = \text{PAV}_{\text{mnd}} + \text{Vastrecht}_{\text{mnd}} + \left(\text{GTV} \times \frac{\text{Tarif}_{\text{GTV}}}{12}\right) + \left(\max(P_{\text{peak}}, \text{GTV}) \times \text{Tarif}_{\text{peak}}\right) + \left(E_{\text{kWh}} \times \text{Tarif}_{\text{trans}}\right) + \text{Penalty}_{\text{blind}}$$

- **PAV (Periodieke Aansluitvergoeding)**: Connection capacity charge based on official Liander categories:
  - `AC2` (Low Voltage $\le 3\times 80\text{ A}$): €5.10 / month
  - `AC4a` (Low Voltage $> 3\times 80\text{ A}$, cable $\le 25\text{ m}$): €28.98 / month
  - `AC4b` (Low Voltage $> 3\times 80\text{ A}$, standard): €57.73 / month
  - `AC5a` (Medium Voltage, compact station $630\text{ kVA}$): €160.57 / month
  - `AC5b` (Medium Voltage, standard): €160.57 / month
  - `AC5` (Medium Voltage general): €160.57 / month
  - `AC6` (High Voltage connection): €160.57 / month
- **Vastrecht transport**: Fixed monthly administrative fee (€4.38 / month = €52.54 / year for Liander AC4b/AC5a).
- **GTV (Gecontracteerd Transportvermogen)**: Monthly fee for reserved capacity in kW (€43.88/kW/yr for AC4b; €26.68/kW/yr for AC5a).
- **Maandpiek**: Monthly fee per kW of registered monthly maximum 15-min demand (€3.46/kW/month for AC4b; €2.32/kW/month for AC5a).
- **12-Month Ratchet Clause vs. Net Congestion (Netcongestie)**:
  - *Standard Grid Area*: If monthly peak demand exceeds contracted capacity ($P_{\text{peak}} > \text{GTV}$), DSOs treat the event as a tacit capacity upgrade, locking the elevated capacity fee for **at least 12 consecutive months**.
  - *Congested Grid Area (Netcongestie)*: In congested zones (e.g. North Brabant, Gelderland, Utrecht), capacity increases are legally and physically blocked. Exceeding GTV is treated as a **contract breach**, carrying statutory fines and the immediate threat of **forced curtailment or complete grid disconnection**.
- **Peak Overload Penalty Rate (`peak_penalty_rate_kw`)**: Configurable variable for excess charges per kW (defaulting to €0.00/kW for standard Dutch ACM ratchet; customizable for international tariff frameworks).
- **Strategic BESS Peak Shaving**: Buffers 15-minute load spikes below GTV, preventing 12-month ratchet lock-ins and eliminating grid congestion violation risks.
- **Blindvermogen (Reactive Power)**: Surcharge per kvarh incurred whenever the average power factor drops below $\cos \varphi = 0.85$.

### Pillar 2: Commercial Energy Supplier (Energieleverancier)
Procurement in the free market across 4 market segments:
1. **Major Integrated Utilities**: Vattenfall Zakelijk, Eneco Zakelijk, Essent Zakelijk, PZEM.
2. **B2B Portfolio Specialists**: Scholt Energy, ENGIE Commercial, SEFE Energy.
3. **Dynamic Spot Specialists**: NieuweStroom, Energyhouse, Tibber Commercial.
4. **Green Sourcing & Independent**: Greenchoice Zakelijk, Shell Energy Europe, Audax, Clean Energy.

The supplier invoice is unbundled into 5 distinct cost components:
1. **Wholesale Base Commodity**: Settled via EPEX Spot (15-min day-ahead index), Fixed All-In rates, or **Tranche / Click contracts** (baseload/peakload forward blocks + spot residual).
2. **Opslag (Supplier Retail Markup)**: €0.0050 to €0.0150 / kWh.
3. **Onbalanskosten (Imbalance Fee)**: €0.0030 to €0.0080 / kWh.
4. **GvO (Garanties van Oorsprong)**: Green certificate premium (€0.0020 to €0.0070 / kWh).
5. **Vastrecht levering**: Standing customer management fee (€120 to €600 / year).

### Pillar 3: Certified Metering Company (Erkend Meetverantwoordelijke - EMV)
Regulated telemetry and interval data handling (Fudura, Kenter, Joulz):
- 15-minute interval data collection and daily dispatch to the NEDU clearinghouse.
- Annual service fees:
  - Low Voltage (`LS`): €600 / year
  - Medium Voltage $\le 1\text{ MW}$ (`MS`): €840 / year
  - Medium Voltage $\le 2\text{ MW}$: €1,800 / year
  - High Voltage (`HS`): €3,500 / year

### Pillar 4: Transformer Station Rental & Maintenance (Trafo-Station)
For Medium Voltage customers (AC5a, AC5b, AC5, AC6), taking delivery at medium voltage (10 kV / 20 kV) requires a dedicated transformer substation:
- Equipment rental from Fudura, Kenter, or Joulz.
- Statutory maintenance under NEN 3840 / NEN 3140 with certified Installatieverantwoordelijke (IV-er).
- Standard market rental tiers:
  - $400 - 630\text{ kVA}$: €4,248 / year (€354 / month)
  - $1,000\text{ kVA}$: €6,200 / year
  - $1,600 - 2,000\text{ kVA}$: €9,200 / year
  - $5\text{ MVA}$: €18,500 / year

### Statutory Taxes (Energiebelasting)
Dutch 5-bracket degressive tax schedule applied cumulatively across the calendar year:

| Bracket | Annual kWh Range | 2025 Rate (€/kWh) | 2026 Rate (€/kWh) |
|:---|:---|:---:|:---:|
| Bracket 1 | $0 - 2,900\text{ kWh}$ | €0.10880 | €0.10600 |
| Bracket 2 | $2,900 - 10,000\text{ kWh}$ | €0.10880 | €0.10600 |
| Bracket 3 | $10,000 - 50,000\text{ kWh}$ | €0.06740 | €0.06560 |
| Bracket 4 | $50,000 - 10,000,000\text{ kWh}$ | €0.03900 | €0.03800 |
| Bracket 5 | $> 10,000,000\text{ kWh}$ | €0.00050 | €0.00050 |

- **Vermindering Energiebelasting (Tax Credit)**: Fixed statutory credit for connections with a residential/work function (*verblijfsfunctie*):
  - 2025: **€524.95** per connection per year
  - 2026: **€519.80** per connection per year
- **BTW**: 21% Dutch VAT applied to the net consolidated total.

---

## 4. Benchmark Validation & Mathematical Verification

The calculation engine is rigorously verified against authoritative reference profiles via automated pytest suites:

### Profile A: Commercial SME / Office (AC4b Low Voltage)
- **Profile Parameters**: 360 MWh annual consumption, 147 kW peak demand, 140 kW contracted GTV.
- **DSO Grid Spend**: €20,907.90 net
  - PAV: €692.76 (€57.73/mo)
  - Vastrecht: €52.54
  - GTV: €6,143.20 (€43.88/kW)
  - Maandpiek: €6,103.40 (accounting for peak exceedance)
  - Transport kWh: €7,916.00
- **Supplier Spend**: €39,960.00 net (Blended rate €0.1110/kWh)
- **Metering (EMV)**: €600.00 net
- **Trafo Rental**: €0.00 (Customer connected at Low Voltage)
- **Energiebelasting**: €14,643.20 net (€15,168.15 gross tax minus €524.95 credit)
- **Consolidated Net Spend**: **€76,111.10 / year** (Blended €0.2114 / kWh)
- **Consolidated Gross (incl. 21% BTW)**: **€92,094.43 / year**

### Profile B: Medium-Voltage Industrial (AC5a Medium Voltage)
- **Profile Parameters**: 1,200 MWh annual consumption, 536 kW peak demand, 500 kW contracted GTV, 630 kVA rented transformer.
- **DSO Grid Spend**: €62,915.36 net
  - PAV: €1,926.84 (€160.57/mo)
  - Vastrecht: €52.54
  - GTV: €13,340.00 (€26.68/kW)
  - Maandpiek: €14,923.98 (€2.32/kW/mo with breach ratchet)
  - Transport kWh: €32,672.00
- **Supplier Spend**: €132,600.00 net (Blended rate €0.1105/kWh)
- **Metering (EMV)**: €840.00 net
- **Trafo Station Rental**: €4,248.00 net (630 kVA compact station from Fudura)
- **Energiebelasting**: €46,017.20 net (€46,542.15 gross tax minus €524.95 credit)
- **Consolidated Net Spend**: **€246,620.56 / year** (Blended €0.2055 / kWh)
- **Consolidated Gross (incl. 21% BTW)**: **€298,410.88 / year**

---

## 5. Executive Advisory Suite

The engine provides three strategic procurement advisory models in `engine/procurement_engine.py`:

1. **3-Route Sourcing Comparator**:
   - Simultaneously calculates active load against **Fixed All-In**, **Tranche / Click (40% Hedged)**, and **100% Dynamic Spot**.
   - Displays annual total spend, blended €/kWh delta, and monthly risk-variance charts.
2. **Voltage Level Transition Advisor (AC4b vs. AC5a)**:
   - Evaluates the business case for stepping up from Low Voltage (AC4b) to Medium Voltage (AC5a).
   - Lowers GTV capacity rates from €43.88 to €26.68/kW/yr and Maandpiek from €3.46 to €2.32/kW/mo.
   - Offsets these grid savings against the annual transformer station rental (€4,248/yr), pinpointing the exact break-even peak demand (~150–200 kW).
3. **BESS Peak Shaving & Congestion Flexibility (CBC) Advisor**:
   - Quantifies demand-charge reductions on Maandpiek and contracted GTV downscaling.
   - Computes capacity availability compensation under the ACM Capacity Limiting Contract (Capaciteitsbeperkingscontract - CBC) framework.

---

## 6. Breached Capacity Warning & Ratchet Trap Model

When measured facility peak demand exceeds the contracted transport capacity ($GTV$), the platform provides an intelligent dual-case warning system:

1. **Case A: Historical High Ratchet Trap ($P_{\text{history}} > GTV$, but Current Year Peak $\le GTV$)**:
   - The facility operates within its contracted capacity this year, but is locked into an elevated billing floor due to the official ACM 12-month rolling peak ratchet rule:
     $$\text{Billable Peak} = \max(P_{\text{month}}, \max_{t-12}(P_t), GTV)$$
   - Displays an informational alert detailing the monthly demand surcharge caused by historical spikes.

2. **Case B: Active Netcongestie Contract Breach ($P_{\text{measured, active}} > GTV$)**:
   - The measured peak in the active year physically breaches the grid operator's contracted transmission capacity limit.
   - Under Dutch Netcongestie protocols, grid operators strictly enforce contracted capacity. Breaches can incur severe financial penalties (€/kW overage fee) or mandatory connection throttling.
   - The UI displays an executive call-to-action recommending Battery Energy Storage Systems (BESS) for peak shaving to eliminate overages without requiring grid reinforcement.

---

## 7. Development & Hot-Reload Architecture

To enable rapid iteration and testing without restarting the Streamlit runtime, `app.py` incorporates a permanent module hot-reloading architecture (`importlib.reload`):

```python
# Permanent Hot-Reloading in app.py (DO NOT REMOVE)
importlib.reload(_ui_theme)
importlib.reload(_con_charts)
importlib.reload(_strat_view)
importlib.reload(_con_view)
importlib.reload(_c_view)
```

- When any view, chart, or calculation module in `Currentsituation_sandbox` is modified, clicking **Rerun** or pressing `R` in the Streamlit browser UI reloads all submodules from disk immediately.
- Cached engine modules in `Currentsituation_sandbox.engine` are also reloaded cleanly before UI views execute.

---

## 8. Testing & Quality Assurance

Run the test suite from the project root:

```bash
# Run isolated Dutch Grootverbruik engine tests
python -m pytest tests/test_currsit_sandbox_engine.py -v

# Run status_quo_2025 regression tests
python -m pytest tests/test_status_quo_2025.py -v
```

All tests execute with **100% pass rates** with zero regressions.

---

## 9. How to Launch

Launch the sandbox workbench standalone from `current_model`:
```bash
cd current_model
streamlit run ui_sandbox/Currentsituation_sandbox/app.py
```
Or from the workspace root:
```bash
streamlit run current_model/ui_sandbox/Currentsituation_sandbox/app.py
```

Or access it via the multi-sandbox suite launcher:
```bash
cd current_model
streamlit run ui_sandbox/sandbox_app.py
```
