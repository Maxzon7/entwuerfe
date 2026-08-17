# exports/demo_contract_data_export.py
"""
Standalone Demo Mode Contract Data & Tariff Billing Engine
=========================================================
An entirely independent, minimal, and fully functional copy of the grid contract
data model and multi-pillar tariff billing calculation engine as used in Demo Mode.

Includes:
  - 4-Pillar Grid Tariff Structure (Fixed fee, Contracted capacity, Measured peak, Excess penalty)
  - 3-Tier Time-of-Use (ToU) active energy pricing (Peak/Alta, Off-Peak/Baja, Mid-Peak/Resto)
  - Taxes & VAT with support for compounding
  - Custom Surcharges & Credits (Pre-tax and Post-tax)
  - 12-Month Schedule Generator & JSON Import/Export
  - Standalone bill simulation engine & comparison tools
  - Interactive Streamlit Dashboard

Can be imported as a library or executed directly with Streamlit:
    streamlit run exports/demo_contract_data_export.py
"""

from typing import Dict, List, Any, Optional, Tuple
import copy
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# =====================================================================
# 1. DEFAULT DEMO CONTRACT PRESETS & DATA BUILDERS
# =====================================================================

def get_default_demo_contract_params() -> dict:
    """
    Returns the exact default grid contract and tariff parameters used in Demo Mode.
    """
    base_fee = 100.0                # Pillar 1: Fixed monthly service charge (€/month)
    contracted_kw = 100.0           # Pillar 2: Contracted capacity limit (kW)
    contract_price = 5.0            # Pillar 2: Contracted capacity price (€/kW/month)
    peak_penalty = 2.0              # Pillar 3: Measured peak penalty during Peak hours (€/kW/month)
    excess_price = 10.0             # Pillar 4: Excess capacity penalty over contracted limit (€/kW/month)

    alta_pr = 0.18                  # Peak price (€/kWh)
    alta_start = 18                 # Peak start hour (18:00)
    alta_end = 23                   # Peak end hour (23:00)

    baja_pr = 0.10                  # Off-Peak price (€/kWh)
    baja_start = 23                 # Off-Peak start hour (23:00)
    baja_end = 5                    # Off-Peak end hour (05:00)

    resto_pr = 0.14                 # Mid-Peak price (€/kWh)

    prov_taxes = [
        {"Tax Name": "VAT", "Rate (%)": 21.0, "Compound": False}
    ]

    custom_adjustments = [
        {"Charge Name": "Municipal Lighting Fee", "Amount (€)": 150.0, "Is Pre-tax": False},
        {"Charge Name": "Stabilization Credit", "Amount (€)": -500.0, "Is Pre-tax": False}
    ]

    monthly_schedule = {}
    for m in range(1, 13):
        monthly_schedule[str(m)] = {
            "base_fee": base_fee,
            "contracted_capacity_kw": contracted_kw,
            "contracted_capacity_price": contract_price,
            "peak_penalty_price": peak_penalty,
            "excess_penalty_price": excess_price,
            "enable_tou": True,
            "alta": {"price": alta_pr, "start_hour": alta_start, "end_hour": alta_end},
            "baja": {"price": baja_pr, "start_hour": baja_start, "end_hour": baja_end},
            "resto": {"price": resto_pr},
            "tax_pct": 0.0,
            "provincial_taxes": copy.deepcopy(prov_taxes),
            "custom_adjustments": copy.deepcopy(custom_adjustments)
        }

    return {"monthly_tariff_schedule": monthly_schedule}


def build_custom_contract_params(
    base_fee: float = 100.0,
    contracted_kw: float = 100.0,
    contract_price: float = 5.0,
    peak_penalty: float = 2.0,
    excess_price: float = 10.0,
    alta_price: float = 0.18,
    alta_start: int = 18,
    alta_end: int = 23,
    baja_price: float = 0.10,
    baja_start: int = 23,
    baja_end: int = 5,
    resto_price: float = 0.14,
    prov_taxes: Optional[List[dict]] = None,
    custom_adjustments: Optional[List[dict]] = None
) -> dict:
    """Helper to programmatically generate a customized 12-month contract dictionary."""
    if prov_taxes is None:
        prov_taxes = [{"Tax Name": "VAT", "Rate (%)": 21.0, "Compound": False}]
    if custom_adjustments is None:
        custom_adjustments = [
            {"Charge Name": "Municipal Lighting Fee", "Amount (€)": 150.0, "Is Pre-tax": False},
            {"Charge Name": "Stabilization Credit", "Amount (€)": -500.0, "Is Pre-tax": False}
        ]

    monthly_schedule = {}
    for m in range(1, 13):
        monthly_schedule[str(m)] = {
            "base_fee": float(base_fee),
            "contracted_capacity_kw": float(contracted_kw),
            "contracted_capacity_price": float(contract_price),
            "peak_penalty_price": float(peak_penalty),
            "excess_penalty_price": float(excess_price),
            "enable_tou": True,
            "alta": {"price": float(alta_price), "start_hour": int(alta_start), "end_hour": int(alta_end)},
            "baja": {"price": float(baja_price), "start_hour": int(baja_start), "end_hour": int(baja_end)},
            "resto": {"price": float(resto_price)},
            "tax_pct": 0.0,
            "provincial_taxes": copy.deepcopy(prov_taxes),
            "custom_adjustments": copy.deepcopy(custom_adjustments)
        }

    return {"monthly_tariff_schedule": monthly_schedule}


# =====================================================================
# 2. BILLING CALCULATION ENGINE
# =====================================================================

def is_hour_in_range(hour: int, start: int, end: int) -> bool:
    """Checks whether a given hour falls within a time-of-use interval (handles midnight wrap-around)."""
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    else:
        return (hour >= start) | (hour < end)


def get_bill_components(
    df: pd.DataFrame,
    f_params: dict,
    is_optimized: bool = True
) -> Dict[str, float]:
    """
    Calculates annual billing components based on 4-pillar tariff rules, ToU windows, and taxes.
    
    Parameters:
        df: DataFrame containing 'timestamp' and either 'consumption_kw' or 'final_grid_load_kw'.
        f_params: Dict with 'monthly_tariff_schedule'.
        is_optimized: If True, uses 'final_grid_load_kw' if present.
        
    Returns:
        Dict mapping bill category names to annual total costs (€).
    """
    temp_df = df.copy()
    if 'timestamp' in temp_df.columns:
        temp_df['timestamp'] = pd.to_datetime(temp_df['timestamp'])
        temp_df['month'] = temp_df['timestamp'].dt.month
        try:
            delta = temp_df['timestamp'].iloc[1] - temp_df['timestamp'].iloc[0]
            factor = 60.0 / (delta.total_seconds() / 60.0)
        except Exception:
            factor = 1.0
    else:
        temp_df['month'] = 1
        factor = 1.0

    load_col = 'final_grid_load_kw' if (is_optimized and 'final_grid_load_kw' in temp_df.columns) else 'consumption_kw'
    if load_col not in temp_df.columns:
        # Fallback to first numeric column
        numeric_cols = temp_df.select_dtypes(include=[np.number]).columns
        load_col = numeric_cols[0] if len(numeric_cols) > 0 else 'consumption_kw'

    monthly_schedule = f_params.get('monthly_tariff_schedule', {})

    fixed_total = 0.0
    capacity_total = 0.0
    peak_total = 0.0
    excess_total = 0.0
    energy_total = 0.0
    taxes_total = 0.0
    adjustments_total = 0.0

    for m in range(1, 13):
        m_mask = temp_df['month'] == m
        m_df = temp_df[m_mask]
        if len(m_df) == 0:
            continue

        m_peak = float(m_df[load_col].max())

        m_data = monthly_schedule.get(str(m), {}) or monthly_schedule.get(m, {})
        if not m_data:
            m_data = monthly_schedule.get('1', {}) or monthly_schedule.get(1, {})

        base_fee = float(m_data.get('base_fee', 0.0) or 0.0)
        contracted_kw = float(m_data.get('contracted_capacity_kw', 0.0) or 0.0)
        contract_price = float(m_data.get('contracted_capacity_price', 0.0) or 0.0)
        peak_penalty_price = float(m_data.get('peak_penalty_price', 0.0) or 0.0)
        excess_price = float(m_data.get('excess_penalty_price', 0.0) or 0.0)
        subsidy = float(m_data.get('subsidy_amount', 0.0) or 0.0)

        alta_price = float(m_data.get('alta', {}).get('price', 0.0) or 0.0)
        alta_start = int(m_data.get('alta', {}).get('start_hour', 18))
        alta_end = int(m_data.get('alta', {}).get('end_hour', 23))

        baja_price = float(m_data.get('baja', {}).get('price', 0.0) or 0.0)
        baja_start = int(m_data.get('baja', {}).get('start_hour', 23))
        baja_end = int(m_data.get('baja', {}).get('end_hour', 5))

        resto_price = float(m_data.get('resto', {}).get('price', 0.0) or 0.0)

        # Measured Peak (Pico window)
        enable_tou = bool(m_data.get('enable_tou', True))
        pico_peak = m_peak
        if enable_tou and 'timestamp' in m_df.columns:
            m_df_copy = m_df.copy()
            m_df_copy['hour'] = m_df_copy['timestamp'].dt.hour
            alta_mask = m_df_copy['hour'].apply(lambda h: is_hour_in_range(h, alta_start, alta_end))
            pico_df = m_df_copy[alta_mask]
            if len(pico_df) > 0:
                pico_peak = float(pico_df[load_col].max())

        m_fixed_net = base_fee - subsidy
        m_cap_net = contracted_kw * contract_price
        m_peak_penalty = pico_peak * peak_penalty_price
        m_excess = (m_peak - contracted_kw) * excess_price if m_peak > contracted_kw else 0.0

        # Time-of-Use active energy charges
        if 'timestamp' in m_df.columns:
            m_df_copy = m_df.copy()
            m_df_copy['hour'] = m_df_copy['timestamp'].dt.hour
            alta_mask = m_df_copy['hour'].apply(lambda h: is_hour_in_range(h, alta_start, alta_end))
            baja_mask = m_df_copy['hour'].apply(lambda h: is_hour_in_range(h, baja_start, baja_end))
            resto_mask = ~(alta_mask | baja_mask)

            e_alta = float(m_df_copy[alta_mask][load_col].sum() / factor)
            e_baja = float(m_df_copy[baja_mask][load_col].sum() / factor)
            e_resto = float(m_df_copy[resto_mask][load_col].sum() / factor)

            m_energy = (e_alta * alta_price) + (e_baja * baja_price) + (e_resto * resto_price)
        else:
            m_energy = float(m_df[load_col].sum() / factor) * resto_price

        net_m = m_fixed_net + m_cap_net + m_peak_penalty + m_excess + m_energy

        prov_taxes = m_data.get('provincial_taxes', [])
        custom_adjustments = m_data.get('custom_adjustments', [])

        pre_tax_adj = 0.0
        post_tax_adj = 0.0
        for adj in custom_adjustments:
            amt = float(adj.get('Amount (€)', adj.get('amount', 0.0)) or 0.0)
            is_pre = bool(adj.get('Is Pre-tax', adj.get('is_pre_tax', False)))
            if is_pre:
                pre_tax_adj += amt
            else:
                post_tax_adj += amt

        net_with_pre_tax = net_m + pre_tax_adj

        # Calculate VAT and Taxes with compounding support
        total_tax_m = 0.0
        sorted_taxes = sorted(prov_taxes, key=lambda x: bool(x.get('Compound', x.get('compound', False))))

        for p_tax in sorted_taxes:
            rate = float(p_tax.get('Rate (%)', p_tax.get('rate', 0.0)) or 0.0)
            compound = bool(p_tax.get('Compound', p_tax.get('compound', False)))
            if compound:
                tax_val = (net_with_pre_tax + total_tax_m) * (rate / 100.0)
            else:
                tax_val = net_with_pre_tax * (rate / 100.0)
            total_tax_m += tax_val

        fixed_total += m_fixed_net
        capacity_total += m_cap_net
        peak_total += m_peak_penalty
        excess_total += m_excess
        energy_total += m_energy
        taxes_total += total_tax_m

        stabilization_credit = float(m_data.get('stabilization_credit', 0.0) or 0.0)
        adjustments_total += pre_tax_adj + post_tax_adj - stabilization_credit

    return {
        "Fixed connection": fixed_total,
        "Contracted capacity": capacity_total,
        "Peak penalty (Pico)": peak_total,
        "Excess penalty": excess_total,
        "Energy cost": energy_total,
        "Taxes (VAT + Prov)": taxes_total,
        "Adjustments": adjustments_total
    }


def calculate_bill_comparison(
    baseline_df: pd.DataFrame,
    optimized_df: pd.DataFrame,
    f_params: dict
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
    """
    Computes comparative billing breakdown between a baseline load profile and an optimized profile.
    """
    base_comp = get_bill_components(baseline_df, f_params, is_optimized=False)
    opt_comp = get_bill_components(optimized_df, f_params, is_optimized=True)

    base_total = sum(base_comp.values())
    opt_total = sum(opt_comp.values())
    savings_total = base_total - opt_total
    savings_pct = (savings_total / base_total * 100.0) if base_total > 0 else 0.0

    summary = {
        "baseline_total_eur": base_total,
        "optimized_total_eur": opt_total,
        "savings_eur": savings_total,
        "savings_pct": savings_pct
    }

    return base_comp, opt_comp, summary


# =====================================================================
# 3. STANDALONE SYNTHETIC LOAD PROFILE GENERATOR FOR TESTING
# =====================================================================

def generate_demo_test_profiles(
    monthly_consumption_kwh: float = 50000.0,
    solar_kwp: float = 80.0,
    battery_kwh: float = 200.0,
    battery_kw: float = 60.0,
    grid_limit_kw: float = 100.0
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generates baseline and solar+battery shaved test profiles for full year (hourly resolution)."""
    timestamps = pd.date_range(start='2026-01-01', end='2026-12-31 23:00:00', freq='h')
    df_base = pd.DataFrame({'timestamp': timestamps})
    df_base['hour'] = df_base['timestamp'].dt.hour
    df_base['dayofweek'] = df_base['timestamp'].dt.dayofweek

    # Base profile: 15% floor, working hours 08:00 - 20:00 Mo-Fr
    profile = np.full(len(df_base), 0.15)
    work_mask = (df_base['hour'] >= 8) & (df_base['hour'] < 20) & (df_base['dayofweek'] < 5)
    profile[work_mask] = 1.0

    # Add 5% noise
    noise = np.random.normal(1.0, 0.05, len(profile))
    profile = np.clip(profile * noise, 0.075, None)

    # Scale to target
    annual_target = monthly_consumption_kwh * 12.0
    scaling = annual_target / np.sum(profile)
    df_base['consumption_kw'] = profile * scaling

    # Create optimized scenario with simple peak shaving and solar PV
    df_opt = df_base.copy()
    # Synthetic solar generation bell curve (07:00 to 19:00, peak at 13:00)
    solar_hour_factor = np.clip(np.sin((df_opt['hour'] - 6) / 12.0 * np.pi), 0.0, 1.0)
    # Seasonal solar factor (higher in summer)
    day_of_year = df_opt['timestamp'].dt.dayofyear
    seasonal_factor = 0.5 + 0.5 * np.sin((day_of_year - 80) / 365.0 * 2 * np.pi)
    solar_gen = solar_kwp * 0.85 * solar_hour_factor * seasonal_factor

    # Shave load with solar
    net_load = np.maximum(0.0, df_opt['consumption_kw'] - solar_gen)
    # Simple battery peak shaving above grid limit
    battery_shaving = np.clip(net_load - grid_limit_kw, 0.0, battery_kw)
    final_load = np.maximum(0.0, net_load - battery_shaving)

    df_opt['solar_gen_kw'] = solar_gen
    df_opt['final_grid_load_kw'] = final_load

    df_base.drop(columns=['hour', 'dayofweek'], inplace=True)
    df_opt.drop(columns=['hour', 'dayofweek'], inplace=True)

    return df_base, df_opt


# =====================================================================
# 4. INTERACTIVE STREAMLIT APPLICATION
# =====================================================================

def render_demo_contract_app():
    """Renders the standalone interactive Streamlit application for Demo Contract Management."""
    st.set_page_config(
        page_title="Demo Grid Contract & Billing Studio",
        page_icon="💰",
        layout="wide"
    )

    st.title("💰 Demo Mode Grid Contract & Multi-Pillar Billing Studio")
    st.caption("Standalone functional module for configuring 4-pillar grid tariffs, ToU energy prices, taxes, surcharges, and simulating annual utility bills.")

    # Sidebar: 4-Pillar Grid Tariff Configuration
    with st.sidebar:
        st.header("⚙️ 4-Pillar Grid Tariff Setup")

        base_fee = st.number_input(
            "Pillar 1: Fixed Service Charge (€/Month)",
            min_value=0.0, value=100.0, step=10.0,
            help="Fixed monthly grid connection and meter maintenance fee."
        )

        col_p2_1, col_p2_2 = st.columns(2)
        contracted_kw = col_p2_1.number_input("Pillar 2: Capacity Limit (kW)", min_value=1.0, value=100.0, step=10.0)
        contract_price = col_p2_2.number_input("Pillar 2: Price (€/kW/Mo)", min_value=0.0, value=5.0, step=0.5)

        peak_penalty = st.number_input(
            "Pillar 3: Measured Peak Charge (€/kW/Month)",
            min_value=0.0, value=2.0, step=0.5,
            help="Fee applied to maximum peak registered during high-demand (Alta) hours."
        )

        excess_price = st.number_input(
            "Pillar 4: Excess Capacity Penalty (€/kW/Month)",
            min_value=0.0, value=10.0, step=1.0,
            help="Penalty per kW when monthly peak demand exceeds contracted capacity limit."
        )

        st.divider()
        st.header("⏱️ Time-of-Use Active Energy Prices")

        c_a1, c_a2, c_a3 = st.columns(3)
        alta_pr = c_a1.number_input("Peak (€/kWh)", value=0.18, format="%.4f")
        alta_st = c_a2.number_input("Peak Start", min_value=0, max_value=23, value=18)
        alta_ed = c_a3.number_input("Peak End", min_value=0, max_value=23, value=23)

        c_b1, c_b2, c_b3 = st.columns(3)
        baja_pr = c_b1.number_input("Off-Peak (€/kWh)", value=0.10, format="%.4f")
        baja_st = c_b2.number_input("Off-Peak Start", min_value=0, max_value=23, value=23)
        baja_ed = c_b3.number_input("Off-Peak End", min_value=0, max_value=23, value=5)

        resto_pr = st.number_input("Mid-Peak Price (€/kWh)", value=0.14, format="%.4f")

    # Main Tabs
    tab_overview, tab_taxes, tab_comparison, tab_export = st.tabs([
        "📊 1. Simulation & Billing Results",
        "🧾 2. Taxes & Adjustments",
        "🔬 3. Test Profile Generator",
        "💾 4. JSON Preset Export"
    ])

    # -------------------------------------------------------------
    # TAB 2: Taxes & Adjustments
    # -------------------------------------------------------------
    with tab_taxes:
        st.subheader("Taxes, VAT & Custom Adjustments")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown("**🏛️ Taxes & Duties Configuration**")
            default_prov_taxes = [{"Tax Name": "VAT", "Rate (%)": 21.0, "Compound": False}]
            tax_editor = st.data_editor(
                pd.DataFrame(default_prov_taxes),
                num_rows="dynamic",
                column_config={
                    "Tax Name": st.column_config.TextColumn("Tax Name"),
                    "Rate (%)": st.column_config.NumberColumn("Rate (%)", min_value=0.0, max_value=100.0, format="%.2f%%"),
                    "Compound": st.column_config.CheckboxColumn("Compound?")
                },
                key="standalone_tax_editor"
            )
            prov_taxes = tax_editor.to_dict('records')

        with col_t2:
            st.markdown("**⚖️ Custom Adjustments (Surcharges & Credits)**")
            default_adjustments = [
                {"Adjustment Name": "Municipal Lighting Fee", "Amount (€)": 150.0, "Is Pre-tax": False},
                {"Adjustment Name": "Stabilization Credit", "Amount (€)": -500.0, "Is Pre-tax": False}
            ]
            adj_editor = st.data_editor(
                pd.DataFrame(default_adjustments),
                num_rows="dynamic",
                column_config={
                    "Adjustment Name": st.column_config.TextColumn("Adjustment Name"),
                    "Amount (€)": st.column_config.NumberColumn("Amount (€)", format="€%.2f"),
                    "Is Pre-tax": st.column_config.CheckboxColumn("Pre-tax?")
                },
                key="standalone_adj_editor"
            )
            custom_adjustments = [
                {
                    "Charge Name": a.get("Adjustment Name", a.get("Charge Name", "")),
                    "Amount (€)": float(a.get("Amount (€)", 0.0) or 0.0),
                    "Is Pre-tax": bool(a.get("Is Pre-tax", False))
                }
                for a in adj_editor.to_dict('records')
            ]

    # Build active contract dictionary
    contract_params = build_custom_contract_params(
        base_fee=base_fee,
        contracted_kw=contracted_kw,
        contract_price=contract_price,
        peak_penalty=peak_penalty,
        excess_price=excess_price,
        alta_price=alta_pr,
        alta_start=alta_st,
        alta_end=alta_ed,
        baja_price=baja_pr,
        baja_start=baja_st,
        baja_end=baja_ed,
        resto_price=resto_pr,
        prov_taxes=prov_taxes,
        custom_adjustments=custom_adjustments
    )

    # -------------------------------------------------------------
    # TAB 3: Test Profile Generator
    # -------------------------------------------------------------
    with tab_comparison:
        st.subheader("🔬 Simulated Facility & Solar/Battery Assets")
        c_sim1, c_sim2, c_sim3, c_sim4 = st.columns(4)
        sim_cons = c_sim1.number_input("Monthly Demand (kWh)", min_value=1000, value=50000, step=5000)
        sim_pv = c_sim2.number_input("Solar PV Capacity (kWp)", min_value=0.0, value=80.0, step=10.0)
        sim_bat_cap = c_sim3.number_input("Battery Storage (kWh)", min_value=0.0, value=200.0, step=20.0)
        sim_bat_pwr = c_sim4.number_input("Battery Inverter (kW)", min_value=0.0, value=60.0, step=10.0)

        df_base, df_opt = generate_demo_test_profiles(
            monthly_consumption_kwh=sim_cons,
            solar_kwp=sim_pv,
            battery_kwh=sim_bat_cap,
            battery_kw=sim_bat_pwr,
            grid_limit_kw=contracted_kw
        )
        st.success(f"Generated test dataset with {len(df_base):,} hourly timesteps.")

    # -------------------------------------------------------------
    # TAB 1: Simulation & Billing Results
    # -------------------------------------------------------------
    with tab_overview:
        st.subheader("💰 Annual Utility Bill Calculation & Breakdown")

        base_comp, opt_comp, summary = calculate_bill_comparison(df_base, df_opt, contract_params)

        # Metric Cards
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Baseline Annual Bill", f"€ {summary['baseline_total_eur']:,.2f}")
        col_m2.metric("Optimized Annual Bill", f"€ {summary['optimized_total_eur']:,.2f}")
        col_m3.metric("Projected Annual Savings", f"€ {summary['savings_eur']:,.2f}")
        col_m4.metric("Savings Percentage", f"{summary['savings_pct']:.1f} %")

        st.divider()

        # Grouped Plotly Bar Chart
        st.write("### Annual Bill Components Comparison")
        categories = list(base_comp.keys())
        base_vals = [base_comp[c] for c in categories]
        opt_vals = [opt_comp[c] for c in categories]

        fig = go.Figure(data=[
            go.Bar(name='Baseline (Status Quo)', x=categories, y=base_vals, marker_color='#A9A9A9'),
            go.Bar(name='Optimized (Solar + BESS)', x=categories, y=opt_vals, marker_color='#00CC96')
        ])
        fig.update_layout(
            barmode='group',
            yaxis_title="Annual Amount [€]",
            template="plotly_white",
            height=400,
            hovermode="x unified",
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig, use_container_width=True)

        # Tabular Itemized Breakdown
        st.write("### Itemized Financial Summary Table")
        table_df = pd.DataFrame({
            "Bill Component": categories,
            "Baseline Cost (€)": base_vals,
            "Optimized Cost (€)": opt_vals,
            "Variance (€)": [b - o for b, o in zip(base_vals, opt_vals)]
        })
        table_df["Variance (%)"] = [(v / b * 100.0) if b > 0 else 0.0 for v, b in zip(table_df["Variance (€)"], table_df["Baseline Cost (€)"])]
        st.dataframe(
            table_df.style.format({
                "Baseline Cost (€)": "€ {:,.2f}",
                "Optimized Cost (€)": "€ {:,.2f}",
                "Variance (€)": "€ {:,.2f}",
                "Variance (%)": "{:.1f} %"
            }),
            use_container_width=True
        )

    # -------------------------------------------------------------
    # TAB 4: JSON Preset Export
    # -------------------------------------------------------------
    with tab_export:
        st.subheader("💾 Export / Import Tariff Contract Preset")
        json_str = json.dumps(contract_params, indent=2)
        st.text_area("Contract JSON Definition", value=json_str, height=300)

        st.download_button(
            label="📥 Download Contract Preset (JSON)",
            data=json_str,
            file_name="demo_grid_contract_preset.json",
            mime="application/json",
            use_container_width=True
        )


if __name__ == "__main__":
    render_demo_contract_app()
