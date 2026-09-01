# exports/advanced_baseline_export.py
"""
Standalone Advanced Baseline Creation Module
============================================
An entirely independent, minimal, and fully functional load profile generator.
Generates full-year 15-minute resolution synthetic load profiles with 12-month
seasonality, stochastic noise, and dynamic anomaly/event injection.

Can be imported as a library or executed directly with Streamlit:
    streamlit run exports/advanced_baseline_export.py
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import datetime
import uuid
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# =====================================================================
# 1. DATA STRUCTURES & MODELS
# =====================================================================

@dataclass
class AnomalyConfig:
    """Configuration definition for a single dynamic anomaly or scheduled event."""
    id: str
    anomaly_type: str        # 'additional_load', 'fixed_value', 'reduction'
    value_kw: float          # Injected power level (kW)
    frequency_type: str      # 'regular', 'block', 'random'
    start_time: str          # e.g., '08:00'
    end_time: str            # e.g., '14:00'
    regular_days: List[str] = field(default_factory=list)      # e.g., ['Monday', 'Wednesday']
    block_start_date: Optional[str] = None                     # e.g., '2026-07-01'
    block_end_date: Optional[str] = None                       # e.g., '2026-07-21'
    random_dates: List[str] = field(default_factory=list)      # e.g., ['2026-03-14', '2026-09-24']


# =====================================================================
# 2. CORE CALCULATION ENGINE
# =====================================================================

def generate_monthly_synthetic_load(
    monthly_consumption: float,
    days_per_week: int,
    hours_per_day: int,
    base_load_pct: float = 15.0,
    year: int = 2026,
    month: int = 1,
    noise_enabled: bool = True,
    noise_percentage: float = 5.0,
    start_hour: int = 8
) -> pd.DataFrame:
    """
    Generates a 15-minute synthetic load profile for a single month with strict
    energy conservation: sum(P(t) * 0.25h) == monthly_consumption.
    """
    start_date = pd.Timestamp(year, month, 1, 0, 0, 0)
    # End of month timestamp
    if month == 12:
        end_date = pd.Timestamp(year + 1, 1, 1, 0, 0, 0) - pd.Timedelta(minutes=15)
    else:
        end_date = pd.Timestamp(year, month + 1, 1, 0, 0, 0) - pd.Timedelta(minutes=15)

    timestamps = pd.date_range(start=start_date, end=end_date, freq='15min')
    df = pd.DataFrame({'timestamp': timestamps})
    df['hour'] = df['timestamp'].dt.hour
    df['dayofweek'] = df['timestamp'].dt.dayofweek

    base_factor = max(0.0, base_load_pct / 100.0)
    profile = np.full(len(df), base_factor)

    end_hour = start_hour + hours_per_day
    if hours_per_day >= 24:
        op_mask = pd.Series(True, index=df.index)
    elif end_hour > 24:
        op_mask = (df['hour'] >= start_hour) | (df['hour'] < (end_hour % 24))
    else:
        op_mask = (df['hour'] >= start_hour) & (df['hour'] < end_hour)

    working_days_mask = df['dayofweek'] < days_per_week
    active_mask = op_mask & working_days_mask
    profile[active_mask] = 1.0

    # Apply Gaussian stochastic fluctuations
    if noise_enabled and noise_percentage > 0:
        std_dev = noise_percentage / 100.0
        noise = np.random.normal(1.0, std_dev, len(profile))
        profile = profile * noise

    # Clip to avoid negative values or extreme dips below baseline floor
    floor_val = max(0.0, base_factor * 0.5)
    profile = np.clip(profile, a_min=floor_val, a_max=None)

    # Scale strictly to target monthly energy (kWh)
    current_raw_energy_kwh = np.sum(profile) * 0.25  # 15-min intervals = 0.25 h
    scaling_factor = (monthly_consumption / current_raw_energy_kwh) if current_raw_energy_kwh > 0 else 0.0

    df['consumption_kw'] = profile * scaling_factor
    df.drop(columns=['hour', 'dayofweek'], inplace=True)
    return df


def apply_anomalies_to_profile(
    df: pd.DataFrame,
    anomalies: List[AnomalyConfig]
) -> pd.DataFrame:
    """
    Applies custom anomalies and operational deviations onto a time-series dataframe.
    """
    if not anomalies or df.empty:
        return df

    out_df = df.copy()
    out_df['time_only'] = out_df['timestamp'].dt.time
    out_df['date_str'] = out_df['timestamp'].dt.strftime("%Y-%m-%d")
    out_df['day_name'] = out_df['timestamp'].dt.day_name()

    for a in anomalies:
        try:
            a_start_time = datetime.datetime.strptime(a.start_time, "%H:%M").time()
            a_end_time = datetime.datetime.strptime(a.end_time, "%H:%M").time()
        except ValueError:
            continue

        if a_start_time <= a_end_time:
            time_mask = (out_df['time_only'] >= a_start_time) & (out_df['time_only'] <= a_end_time)
        else:
            time_mask = (out_df['time_only'] >= a_start_time) | (out_df['time_only'] <= a_end_time)

        if a.frequency_type == 'regular':
            day_mask = out_df['day_name'].isin(a.regular_days)
        elif a.frequency_type == 'block':
            start_d = a.block_start_date or "1970-01-01"
            end_d = a.block_end_date or "2099-12-31"
            day_mask = (out_df['date_str'] >= start_d) & (out_df['date_str'] <= end_d)
        elif a.frequency_type == 'random':
            day_mask = out_df['date_str'].isin(a.random_dates)
        else:
            day_mask = pd.Series(False, index=out_df.index)

        full_mask = time_mask & day_mask

        if a.anomaly_type == 'additional_load':
            out_df.loc[full_mask, 'consumption_kw'] += a.value_kw
        elif a.anomaly_type == 'fixed_value':
            out_df.loc[full_mask, 'consumption_kw'] = a.value_kw
        elif a.anomaly_type == 'reduction':
            out_df.loc[full_mask, 'consumption_kw'] = (out_df.loc[full_mask, 'consumption_kw'] - a.value_kw).clip(lower=0.0)

    out_df.drop(columns=['time_only', 'date_str', 'day_name'], inplace=True)
    return out_df


def generate_advanced_baseline(
    monthly_configs: Optional[Dict[int, Dict[str, float]]] = None,
    base_load_pct: float = 15.0,
    enable_noise: bool = True,
    noise_percentage: float = 5.0,
    anomalies: Optional[List[AnomalyConfig]] = None,
    year: int = 2026
) -> pd.DataFrame:
    """
    Main programmatic interface to build an annual 15-minute baseline profile.
    
    Parameters:
        monthly_configs: Dict mapping month index (1..12) to:
                         {"consumption": kWh, "days": days_per_week, "hours": hours_per_day}
        base_load_pct: Baseline percentage outside operating hours (e.g. 15.0).
        enable_noise: If True, adds Gaussian fluctuations.
        noise_percentage: Fluctuation standard deviation (e.g. 5.0).
        anomalies: List of AnomalyConfig instances to inject.
        year: Target year (defaults to 2026).
    
    Returns:
        pd.DataFrame with 'timestamp' and 'consumption_kw' (35,040 rows for non-leap year).
    """
    if monthly_configs is None:
        monthly_configs = {
            m: {"consumption": 15000.0, "days": 5, "hours": 8}
            for m in range(1, 13)
        }

    monthly_dfs = []
    for m in range(1, 13):
        cfg = monthly_configs.get(m, {"consumption": 15000.0, "days": 5, "hours": 8})
        m_df = generate_monthly_synthetic_load(
            monthly_consumption=float(cfg["consumption"]),
            days_per_week=int(cfg["days"]),
            hours_per_day=int(cfg["hours"]),
            base_load_pct=base_load_pct,
            year=year,
            month=m,
            noise_enabled=enable_noise,
            noise_percentage=noise_percentage
        )
        monthly_dfs.append(m_df)

    annual_df = pd.concat(monthly_dfs, ignore_index=True)
    annual_df.sort_values("timestamp", inplace=True)
    annual_df.reset_index(drop=True, inplace=True)

    if anomalies:
        annual_df = apply_anomalies_to_profile(annual_df, anomalies)

    return annual_df


def compute_baseline_metrics(df: pd.DataFrame, grid_limit_kw: Optional[float] = None) -> dict:
    """Calculates key statistical and electrical metrics from the baseline profile."""
    if df.empty or 'consumption_kw' not in df.columns:
        return {}

    total_kwh = float(df['consumption_kw'].sum() * 0.25)
    peak_kw = float(df['consumption_kw'].max())
    min_kw = float(df['consumption_kw'].min())
    mean_kw = float(df['consumption_kw'].mean())
    load_factor = (mean_kw / peak_kw * 100.0) if peak_kw > 0 else 0.0

    metrics = {
        "total_energy_kwh": total_kwh,
        "total_energy_mwh": total_kwh / 1000.0,
        "peak_kw": peak_kw,
        "min_kw": min_kw,
        "mean_kw": mean_kw,
        "load_factor_pct": load_factor,
        "total_intervals": len(df)
    }

    if grid_limit_kw is not None and grid_limit_kw > 0:
        over_limit_mask = df['consumption_kw'] > grid_limit_kw
        metrics["exceeded_limit_intervals"] = int(over_limit_mask.sum())
        metrics["max_excess_kw"] = max(0.0, peak_kw - grid_limit_kw)

    return metrics


# =====================================================================
# 3. INTERACTIVE STREAMLIT APPLICATION
# =====================================================================

def render_advanced_baseline_app():
    """Renders the standalone interactive Streamlit application."""
    st.set_page_config(
        page_title="Advanced Baseline Generator",
        page_icon="⚡",
        layout="wide"
    )

    st.title("⚡ Advanced Baseline Load Profile Generator")
    st.caption("Standalone high-precision 15-minute load profile synthesis with 12-month seasonality & dynamic anomaly injection.")

    # Initialize Session State
    if 'adv_anomalies' not in st.session_state:
        st.session_state['adv_anomalies'] = []
    if 'temp_custom_dates' not in st.session_state:
        st.session_state['temp_custom_dates'] = []
    if 'generated_baseline_df' not in st.session_state:
        st.session_state['generated_baseline_df'] = None

    # Sidebar: Global Parameters & Grid Connection
    with st.sidebar:
        st.header("⚙️ Base Configuration")
        default_monthly_cons = st.number_input(
            "Default Monthly Consumption (kWh)",
            min_value=100,
            value=25000,
            step=1000
        )
        default_days = st.slider("Default Working Days / Week", 1, 7, 5)
        default_hours = st.slider("Default Working Hours / Day", 1, 24, 8)
        base_load_pct = st.slider("Base Load Floor (%)", 0, 100, 15, help="Continuous load during nights and weekends.")

        st.divider()
        st.subheader("🔌 Grid Connection")
        num_connections = st.number_input("Grid Connections", min_value=1, value=1)
        amperage = st.number_input("Amperage per Connection (A)", min_value=16, value=250, step=10)
        calc_grid_kw = float(num_connections * amperage * 400 * 1.732 / 1000.0)
        st.info(f"Calculated Capacity: **~{calc_grid_kw:,.1f} kW**")

        st.divider()
        st.subheader("🎲 Stochastic Fluctuation")
        enable_noise = st.toggle("Enable Realistic Noise", value=True)
        noise_pct = st.slider("Noise Intensity (%)", 1, 30, 5) if enable_noise else 0.0

    # Main Area Tabs
    tab_season, tab_anom, tab_preview = st.tabs([
        "📅 1. 12-Month Seasonality",
        "⚡ 2. Anomaly & Event Manager",
        "📊 3. Generation & Analytics"
    ])

    # -------------------------------------------------------------
    # TAB 1: 12-Month Seasonality
    # -------------------------------------------------------------
    with tab_season:
        st.subheader("12-Month Operational Profile Customization")
        st.write("Customize operating days, hours, and energy demand per month to reflect seasonal campaigns, harvest periods, or plant holidays.")

        use_custom_months = st.checkbox("Enable Independent Custom Monthly Inputs", value=False)
        monthly_configs = {}
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        if use_custom_months:
            sub_tabs = st.tabs(month_names)
            for idx, m_tab in enumerate(sub_tabs):
                m_num = idx + 1
                with m_tab:
                    c1, c2, c3 = st.columns(3)
                    m_cons = c1.number_input(f"{month_names[idx]} Consumption (kWh)", min_value=100, value=int(default_monthly_cons), step=500, key=f"adv_m_cons_{m_num}")
                    m_days = c2.slider(f"{month_names[idx]} Working Days", 1, 7, int(default_days), key=f"adv_m_days_{m_num}")
                    m_hours = c3.slider(f"{month_names[idx]} Working Hours", 1, 24, int(default_hours), key=f"adv_m_hours_{m_num}")
                    monthly_configs[m_num] = {"consumption": m_cons, "days": m_days, "hours": m_hours}
        else:
            for m_num in range(1, 13):
                monthly_configs[m_num] = {
                    "consumption": default_monthly_cons,
                    "days": default_days,
                    "hours": default_hours
                }
            st.info(f"All 12 months currently set to **{default_monthly_cons:,.0f} kWh**, **{default_days} days/week**, **{default_hours} hrs/day**.")

    # -------------------------------------------------------------
    # TAB 2: Anomaly & Event Manager
    # -------------------------------------------------------------
    with tab_anom:
        st.subheader("⚡ Dynamic Anomaly & Scheduled Event Manager")
        st.write("Simulate exceptional load behavior, machinery testing, EV fleet charging spikes, or maintenance shutdowns.")

        with st.expander("➕ Inject New Anomaly / Event", expanded=True):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                anom_type = st.selectbox(
                    "Load Modification Mode",
                    options=['additional_load', 'fixed_value', 'reduction'],
                    format_func=lambda x: {
                        'additional_load': "📈 Additional Peak Load (+ kW)",
                        'fixed_value': "📌 Constant Fixed Load (= kW)",
                        'reduction': "📉 Load Curtailment / Shutdown (- kW)"
                    }[x]
                )
                anom_val = st.number_input("Target Value (kW)", min_value=0.0, value=50.0, step=10.0)

            with col_a2:
                st.write("**Daily Active Window**")
                t_start = st.time_input("Start Time", value=datetime.time(8, 0), key="adv_t_start")
                t_end = st.time_input("End Time", value=datetime.time(14, 0), key="adv_t_end")

            st.divider()
            freq_type = st.radio(
                "Distribution & Repetition Pattern",
                options=['regular', 'block', 'random'],
                format_func=lambda x: {
                    'regular': "🔄 Recurring Weekly Pattern (Selected Weekdays)",
                    'block': "📅 Continuous Date Block (Date Range)",
                    'random': "🎯 Specific Calendar Dates (Custom List)"
                }[x],
                horizontal=True
            )

            regular_days = []
            block_start = None
            block_end = None
            random_dates = []

            if freq_type == 'regular':
                regular_days = st.multiselect(
                    "Target Weekdays",
                    options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    default=["Monday", "Wednesday", "Friday"]
                )
            elif freq_type == 'block':
                today = datetime.date(2026, 6, 1)
                date_range = st.date_input("Event Date Horizon", value=[today, today + datetime.timedelta(days=14)])
                if len(date_range) == 2:
                    block_start, block_end = date_range
            elif freq_type == 'random':
                cd1, cd2 = st.columns([3, 1])
                with cd1:
                    pick_date = st.date_input("Select Date to Add", value=datetime.date(2026, 7, 15))
                with cd2:
                    st.write("")
                    st.write("")
                    if st.button("➕ Add Date"):
                        if pick_date not in st.session_state['temp_custom_dates']:
                            st.session_state['temp_custom_dates'].append(pick_date)

                if st.session_state['temp_custom_dates']:
                    st.write("Registered Dates:")
                    st.write(", ".join([d.strftime("%Y-%m-%d") for d in st.session_state['temp_custom_dates']]))
                    random_dates = [d.strftime("%Y-%m-%d") for d in st.session_state['temp_custom_dates']]

            if st.button("💾 Add Anomaly to Pipeline", type="primary", use_container_width=True):
                new_anom = AnomalyConfig(
                    id=str(uuid.uuid4())[:8],
                    anomaly_type=anom_type,
                    value_kw=anom_val,
                    frequency_type=freq_type,
                    start_time=t_start.strftime("%H:%M"),
                    end_time=t_end.strftime("%H:%M"),
                    regular_days=regular_days,
                    block_start_date=block_start.strftime("%Y-%m-%d") if block_start else None,
                    block_end_date=block_end.strftime("%Y-%m-%d") if block_end else None,
                    random_dates=random_dates
                )
                st.session_state['adv_anomalies'].append(new_anom)
                st.session_state['temp_custom_dates'] = []
                st.success("✅ Anomaly added successfully!")
                st.rerun()

        # Display registered anomalies
        if st.session_state['adv_anomalies']:
            st.write("### Active Anomalies in Current Pipeline")
            for idx, a in enumerate(st.session_state['adv_anomalies']):
                c_lbl, c_del = st.columns([5, 1])
                with c_lbl:
                    tag = {"additional_load": "+kW", "fixed_value": "=kW", "reduction": "-kW"}[a.anomaly_type]
                    st.info(f"**{tag} ({a.value_kw} kW)** | {a.start_time}–{a.end_time} | Pattern: *{a.frequency_type}* | ID: `{a.id}`")
                with c_del:
                    if st.button("❌ Remove", key=f"del_anom_{a.id}", use_container_width=True):
                        st.session_state['adv_anomalies'].pop(idx)
                        st.rerun()

    # -------------------------------------------------------------
    # TAB 3: Generation & Analytics
    # -------------------------------------------------------------
    with tab_preview:
        st.subheader("⚡ Execute Baseline Synthesis & Inspect Profile")

        gen_col1, gen_col2 = st.columns([3, 1])
        with gen_col1:
            run_btn = st.button("🚀 Synthesize 15-Minute Full Year Profile", type="primary", use_container_width=True)
        with gen_col2:
            if st.button("🗑️ Clear Cache", use_container_width=True):
                st.session_state['generated_baseline_df'] = None
                st.rerun()

        if run_btn:
            with st.spinner("Generating 35,040 intervals & applying anomaly transformations..."):
                df_result = generate_advanced_baseline(
                    monthly_configs=monthly_configs,
                    base_load_pct=base_load_pct,
                    enable_noise=enable_noise,
                    noise_percentage=noise_pct,
                    anomalies=st.session_state['adv_anomalies'],
                    year=2026
                )
                st.session_state['generated_baseline_df'] = df_result
                st.success("✅ 15-minute annual baseline profile successfully synthesized!")

        df_curr = st.session_state.get('generated_baseline_df')

        if df_curr is not None and not df_curr.empty:
            metrics = compute_baseline_metrics(df_curr, grid_limit_kw=calc_grid_kw)

            # Metric Scorecards
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Annual Energy", f"{metrics['total_energy_mwh']:,.2f} MWh")
            m2.metric("Peak Demand", f"{metrics['peak_kw']:,.1f} kW")
            m3.metric("Min Base Load", f"{metrics['min_kw']:,.1f} kW")
            m4.metric("Load Factor", f"{metrics['load_factor_pct']:.1f}%")
            m5.metric("Grid Capacity", f"{calc_grid_kw:,.1f} kW")

            st.divider()

            # Interactive Plotly Load Curve
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_curr['timestamp'],
                y=df_curr['consumption_kw'],
                mode='lines',
                name='Baseline Load (kW)',
                line=dict(color='#00CC96', width=1.2)
            ))
            fig.add_trace(go.Scatter(
                x=[df_curr['timestamp'].iloc[0], df_curr['timestamp'].iloc[-1]],
                y=[calc_grid_kw, calc_grid_kw],
                mode='lines',
                name='Grid Limit (kW)',
                line=dict(color='red', width=2, dash='dash')
            ))
            fig.update_layout(
                title="Full-Year 15-Minute Electricity Demand Profile",
                xaxis_title="Timeline",
                yaxis_title="Power [kW]",
                hovermode="x unified",
                template="plotly_white",
                height=450
            )
            st.plotly_chart(fig, use_container_width=True)

            # Monthly Aggregations
            df_curr['month'] = df_curr['timestamp'].dt.strftime("%b")
            monthly_summary = df_curr.groupby('month', sort=False).agg(
                Monthly_Energy_kWh=('consumption_kw', lambda x: x.sum() * 0.25),
                Peak_Demand_kW=('consumption_kw', 'max'),
                Avg_Demand_kW=('consumption_kw', 'mean')
            ).reset_index()

            c_bar1, c_bar2 = st.columns(2)
            with c_bar1:
                fig_m_energy = go.Figure(go.Bar(
                    x=monthly_summary['month'],
                    y=monthly_summary['Monthly_Energy_kWh'] / 1000.0,
                    marker_color='#636EFA'
                ))
                fig_m_energy.update_layout(
                    title="Monthly Energy Consumption (MWh)",
                    xaxis_title="Month",
                    yaxis_title="MWh",
                    template="plotly_white",
                    height=300
                )
                st.plotly_chart(fig_m_energy, use_container_width=True)

            with c_bar2:
                fig_m_peak = go.Figure(go.Bar(
                    x=monthly_summary['month'],
                    y=monthly_summary['Peak_Demand_kW'],
                    marker_color='#EF553B'
                ))
                fig_m_peak.update_layout(
                    title="Monthly Peak Demand (kW)",
                    xaxis_title="Month",
                    yaxis_title="Peak kW",
                    template="plotly_white",
                    height=300
                )
                st.plotly_chart(fig_m_peak, use_container_width=True)

            # CSV Export
            csv_data = df_curr[['timestamp', 'consumption_kw']].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Baseline Time-Series CSV (35,040 rows)",
                data=csv_data,
                file_name="synthesized_baseline_profile_15min.csv",
                mime="text/csv",
                use_container_width=True
            )


if __name__ == "__main__":
    render_advanced_baseline_app()
