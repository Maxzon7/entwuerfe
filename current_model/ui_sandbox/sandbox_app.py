"""
========================================================================================
UI Sandbox & Prototyping Laboratory (ui_sandbox/sandbox_app.py)
========================================================================================
Standalone Streamlit application for rapidly prototyping and testing UI components,
custom widgets, layouts, and Plotly charts in complete isolation from the main app.

USAGE:
    From the 'current_model' directory:
        streamlit run ui_sandbox/sandbox_app.py
    
    Or from the project root:
        streamlit run current_model/ui_sandbox/sandbox_app.py

RULES:
    1. One-way dependency: You may import from core, models, and ui.
    2. Zero reverse dependency: Never import from ui_sandbox in main app or core engines.
    3. UI Text & Code: English only.
    4. Icons: Exclusively use Streamlit Material Symbols (:material/<name>:).
========================================================================================
"""

# To run from workspace root ('entwuerfe'):
#   python -m streamlit run current_model/ui_sandbox/sandbox_app.py
#
# To run from 'current_model' directory:
#   python -m streamlit run ui_sandbox/sandbox_app.py

import os
import sys
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# Ensure current_model directory and project root are on sys.path for direct imports
SANDBOX_DIR = os.path.dirname(os.path.abspath(__file__))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(SANDBOX_DIR, ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))

for path in [WORKSPACE_ROOT, CURRENT_MODEL_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Optional imports from main application for demonstration & testing
try:
    from current_model.ui.common.styles import apply_custom_styles
except ImportError:
    try:
        from ui.common.styles import apply_custom_styles
    except ImportError:
        apply_custom_styles = None

try:
    from current_model.ui.common.cards import render_kpi_card
except ImportError:
    try:
        from ui.common.cards import render_kpi_card
    except ImportError:
        render_kpi_card = None

try:
    from current_model.ui.tab1_consumption.csv_inspector.view import render_csv_inspector
except ImportError:
    try:
        from ui.tab1_consumption.csv_inspector.view import render_csv_inspector
    except ImportError:
        render_csv_inspector = None


def main():
    st.set_page_config(
        page_title="UI Sandbox & Component Lab",
        page_icon=":material/science:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Apply global platform styling if available
    if apply_custom_styles:
        apply_custom_styles()

    # Sidebar documentation and controls
    with st.sidebar:
        st.markdown("### :material/science: UI Sandbox")
        st.caption("Isolated Prototyping Environment")
        st.divider()

        st.info(
            "**Architecture Rule:**\n\n"
            ":material/arrow_forward: `ui_sandbox` -> `core` / `models` / `ui` (Allowed)\n\n"
            ":material/block: Main App -> `ui_sandbox` (Prohibited)",
            icon=":material/verified_user:"
        )

        st.divider()
        st.markdown("**Sandbox Mode:**")
        selected_mode = st.radio(
            "Select Lab View:",
            [
                ":material/upload_file: CSV Consumption Input",
                ":material/waving_hand: Hello World & Overview",
                ":material/dashboard: Component Showcase",
                ":material/query_stats: Interactive Chart Lab",
                ":material/edit_note: Scratchpad Playground",
            ],
            index=0,
            label_visibility="collapsed",
        )

    # Main Area Rendering based on selected mode
    if ":material/upload_file:" in selected_mode:
        render_csv_consumption_tab()
    elif ":material/waving_hand:" in selected_mode:
        render_hello_world_tab()
    elif ":material/dashboard:" in selected_mode:
        render_component_showcase_tab()
    elif ":material/query_stats:" in selected_mode:
        render_chart_lab_tab()
    else:
        render_scratchpad_tab()


def render_csv_consumption_tab():
    st.title(":material/upload_file: CSV Consumption Input & Real Meter Lab")
    st.caption("Directly test the production CSV ingestion engine and load profiling pipeline in isolation.")

    st.markdown(
        """
        > [!NOTE]
        > This view imports `render_csv_inspector` directly from `ui.tab1_consumption.csv_inspector.view`.
        > You can upload single or multi-channel meter files, load the 15-minute demo dataset, tune headers,
        > map columns, and verify real-time load analytics without launching `app.py`.
        """
    )

    if render_csv_inspector is not None:
        # Render the full production CSV inspector component
        render_csv_inspector(key_prefix="sandbox_csv_inspector")

        # Additional Sandbox Diagnostics on active session state
        st.markdown("---")
        st.subheader(":material/analytics: Sandbox Data State Inspector")

        active_csv_df = st.session_state.get("active_csv_df")
        if isinstance(active_csv_df, pd.DataFrame) and not active_csv_df.empty:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Total Intervals", f"{len(active_csv_df):,}", delta="Rows Loaded")
            with c2:
                peak_val = active_csv_df["Power_kW"].max() if "Power_kW" in active_csv_df.columns else 0.0
                st.metric("Peak Power", f"{peak_val:,.1f} kW", delta="Max Demand")
            with c3:
                avg_val = active_csv_df["Power_kW"].mean() if "Power_kW" in active_csv_df.columns else 0.0
                st.metric("Average Power", f"{avg_val:,.1f} kW", delta="Base/Mean Load")
            with c4:
                energy_kwh = (active_csv_df["Power_kW"] * 0.25).sum() if "Power_kW" in active_csv_df.columns else 0.0
                st.metric("Total Energy", f"{energy_kwh / 1000.0:,.2f} MWh", delta=f"{energy_kwh:,.0f} kWh")

            with st.expander(":material/table_view: View Active Processed DataFrame Head & Tail", expanded=False):
                st.markdown("**First 5 Intervals:**")
                st.dataframe(active_csv_df.head(), use_container_width=True)
                st.markdown("**Last 5 Intervals:**")
                st.dataframe(active_csv_df.tail(), use_container_width=True)

            # Render the Contract Data & Capacity Tariff Section
            render_contract_tariff_section(active_csv_df=active_csv_df)
        else:
            st.info(
                "No CSV data processed yet. Use the uploader above or click **'Load 15-Min Demo CSV'** to populate session state.",
                icon=":material/info:"
            )
            # Render empty/placeholder contract section with default values
            render_contract_tariff_section(active_csv_df=None)
    else:
        st.error(
            "Could not import `render_csv_inspector` from `ui.tab1_consumption.csv_inspector.view`. "
            "Please check project path configurations.",
            icon=":material/error:"
        )


def render_contract_tariff_section(active_csv_df: pd.DataFrame | None = None) -> None:
    """
    Renders the Electricity Contract & Capacity Tariff Model directly beneath the CSV inspector.
    Recycles the Grid Capacity Limit from above and couples live peak demand from consumption data.
    """
    st.markdown("---")
    st.header(":material/receipt_long: Electricity Contract & Capacity Tariff Model")
    st.caption(
        "Simulate contractual supply charges, recycled grid capacity limits, and demand peak tariffs."
    )

    # 1. Extract Measured Peak Demand from active consumption dataset
    measured_peak_kw = 0.0
    total_energy_kwh = 0.0
    if isinstance(active_csv_df, pd.DataFrame) and not active_csv_df.empty:
        if "Total_Demand_kW" in active_csv_df.columns:
            measured_peak_kw = float(active_csv_df["Total_Demand_kW"].max())
            total_energy_kwh = float(active_csv_df["Total_Demand_kW"].sum() * 0.25)
        elif "Power_kW" in active_csv_df.columns:
            measured_peak_kw = float(active_csv_df["Power_kW"].max())
            total_energy_kwh = float(active_csv_df["Power_kW"].sum() * 0.25)

    # 2. Detect & Recycle Grid Capacity Limit from CSV Inspector session state
    detected_grid_limit = None
    for key, val in st.session_state.items():
        if "sandbox_csv_inspector_limit_val_" in key and isinstance(val, (int, float)) and val > 0:
            detected_grid_limit = float(val)
            break

    # Fallback default for contracted capacity if no grid limit set
    default_contracted_kw = float(detected_grid_limit if detected_grid_limit else (measured_peak_kw if measured_peak_kw > 0 else 500.0))

    if detected_grid_limit:
        st.info(
            f":material/link: **Grid Limit Recycled:** Automatically inherited **{detected_grid_limit:,.1f} kW** from the Grid Capacity Limit configuration above.",
            icon=":material/sync:"
        )

    # Container Card for Tariff Inputs and Inline Results
    with st.container(border=True):
        st.subheader(":material/calculate: Tariff Parameters & Live Fee Calculation")

        # --- Row 1: Base Monthly Fee ---
        st.markdown("#### :material/event_repeat: 1. Base Fixed Standing Fee")
        b_col1, b_col2 = st.columns([2, 2])
        with b_col1:
            base_monthly_fee = st.number_input(
                "Base Monthly Fee (€/month):",
                min_value=0.0,
                max_value=50000.0,
                value=150.0,
                step=10.0,
                help="Fixed meter administration and standing fee charged per billing month.",
                key="sandbox_base_monthly_fee"
            )
        with b_col2:
            base_annual_cost = base_monthly_fee * 12.0
            st.metric(
                label="Annual Base Standing Cost",
                value=f"€{base_annual_cost:,.2f} / year",
                delta=f"€{base_monthly_fee:,.2f} / month",
                delta_color="off"
            )

        st.divider()

        # --- Row 2: Contracted Capacity Tariff (Recycled Grid Limit) ---
        st.markdown("#### :material/speed: 2. Contracted Capacity Tariff (Bereitstellungspreis)")
        c_col1, c_col2, c_col3 = st.columns([2, 2, 2])
        with c_col1:
            contracted_capacity_kw = st.number_input(
                "Contracted Capacity (kW):",
                min_value=1.0,
                max_value=20000.0,
                value=default_contracted_kw,
                step=10.0,
                help="Contracted grid bandwidth / subscribed power capacity (inherited from Grid Limit if defined).",
                key="sandbox_contracted_capacity_kw"
            )
        with c_col2:
            contracted_rate = st.number_input(
                "Contracted Tariff Rate (€/kW/year):",
                min_value=0.0,
                max_value=1000.0,
                value=45.0,
                step=5.0,
                help="Annual standing fee charged per contracted kW of grid capacity.",
                key="sandbox_contracted_rate"
            )
        with c_col3:
            contracted_annual_cost = contracted_capacity_kw * contracted_rate
            st.metric(
                label="Total Contracted Capacity Charge",
                value=f"€{contracted_annual_cost:,.2f} / year",
                delta=f"€{contracted_annual_cost / 12.0:,.2f} / month",
                delta_color="off"
            )

        st.divider()

        # --- Row 3: Measured Peak Demand Tariff ---
        st.markdown("#### :material/bolt: 3. Measured Demand Tariff (Gemessene Jahreshöchstlast)")
        m_col1, m_col2, m_col3 = st.columns([2, 2, 2])
        with m_col1:
            measured_rate = st.number_input(
                "Measured Peak Demand Rate (€/kW/year):",
                min_value=0.0,
                max_value=1000.0,
                value=85.0,
                step=5.0,
                help="Annual fee billed per kW of actual highest recorded peak demand in the consumption interval.",
                key="sandbox_measured_rate"
            )
        with m_col2:
            source_badge = "From Active Load Profile" if measured_peak_kw > 0 else "No Load Loaded"
            st.metric(
                label="Measured Peak Demand (from Consumption)",
                value=f"{measured_peak_kw:,.1f} kW",
                delta=source_badge,
                delta_color="normal" if measured_peak_kw > 0 else "off"
            )
        with m_col3:
            measured_annual_cost = measured_peak_kw * measured_rate
            st.metric(
                label="Resulting Measured Demand Cost",
                value=f"€{measured_annual_cost:,.2f} / year",
                delta=f"€{measured_annual_cost / 12.0:,.2f} / month",
                delta_color="off"
            )

        st.divider()

        # --- Row 4: Grid Capacity Limit Violations & Penalty Surcharge (from Consumption) ---
        st.markdown("#### :material/warning: 4. Grid Capacity Violations & Penalty Surcharges (from Consumption)")

        # Evaluate live overload from active consumption timeseries
        overload_peak_kw = 0.0
        overload_hours = 0.0
        overload_intervals = 0
        overload_energy_kwh = 0.0
        top_violations_df = pd.DataFrame()

        if isinstance(active_csv_df, pd.DataFrame) and not active_csv_df.empty:
            power_series = active_csv_df["Total_Demand_kW"] if "Total_Demand_kW" in active_csv_df.columns else active_csv_df["Power_kW"]
            overload_diff = (power_series - contracted_capacity_kw).clip(lower=0.0)
            overload_peak_kw = float(overload_diff.max())
            overload_intervals = int((power_series > contracted_capacity_kw).sum())
            overload_hours = float(overload_intervals * 0.25)
            overload_energy_kwh = float(overload_diff.sum() * 0.25)

            # Extract top 5 overload violation timestamps
            if overload_peak_kw > 0:
                violation_mask = power_series > contracted_capacity_kw
                v_df = active_csv_df[violation_mask].copy()
                power_col_name = "Total_Demand_kW" if "Total_Demand_kW" in v_df.columns else "Power_kW"
                v_df["Excess_kW"] = v_df[power_col_name] - contracted_capacity_kw
                v_df["Overload_%"] = (v_df["Excess_kW"] / contracted_capacity_kw) * 100.0
                
                if "Timestamp" in v_df.columns:
                    v_df["Time"] = v_df["Timestamp"]
                elif "Datetime" in v_df.columns:
                    v_df["Time"] = v_df["Datetime"]
                else:
                    v_df["Time"] = [str(idx) for idx in v_df.index]

                top_violations_df = v_df.nlargest(5, "Excess_kW")[["Time", power_col_name, "Excess_kW", "Overload_%"]]

        has_violations = overload_peak_kw > 0.0

        v_col1, v_col2, v_col3 = st.columns([2, 2, 2])
        with v_col1:
            penalty_rate_kw = st.number_input(
                "Overload Capacity Penalty Rate (€/kW exceeding):",
                min_value=0.0,
                max_value=2000.0,
                value=120.0,
                step=10.0,
                help="Contractual penalty billed for the highest kW excess exceeding the contracted grid limit.",
                key="sandbox_penalty_rate_kw"
            )
        with v_col2:
            status_delta = f"+{overload_peak_kw:.1f} kW excess ({overload_hours:.1f} hrs)" if has_violations else "Within Contract Limit"
            st.metric(
                label="Maximum Grid Limit Violation (Peak Excess)",
                value=f"{overload_peak_kw:,.1f} kW",
                delta=status_delta,
                delta_color="inverse" if has_violations else "normal"
            )
        with v_col3:
            total_penalty_cost = overload_peak_kw * penalty_rate_kw
            st.metric(
                label="Resulting Overload Penalty Surcharge",
                value=f"€{total_penalty_cost:,.2f} / year",
                delta=f"{overload_intervals} violation intervals" if has_violations else "€0.00 penalty",
                delta_color="inverse" if has_violations else "off"
            )

        # Optional Energy Surcharge on excess kWh
        with st.expander(":material/tune: Advanced Overload Energy Surcharge (€/kWh)", expanded=False):
            e_col1, e_col2, e_col3 = st.columns([2, 2, 2])
            with e_col1:
                excess_kwh_rate = st.number_input(
                    "Excess Energy Penalty Rate (€/kWh):",
                    min_value=0.0,
                    max_value=5.0,
                    value=0.35,
                    step=0.05,
                    key="sandbox_excess_kwh_rate"
                )
            with e_col2:
                st.metric("Total Excess Energy over Limit", f"{overload_energy_kwh:,.1f} kWh", f"{overload_energy_kwh / 1000.0:,.2f} MWh")
            with e_col3:
                excess_energy_cost = overload_energy_kwh * excess_kwh_rate
                st.metric("Excess Energy Surcharge", f"€{excess_energy_cost:,.2f} / year")
                total_penalty_cost += excess_energy_cost

        st.divider()

        # --- Row 5: Time-of-Use (TOU) Energy Working Rates (Arbeitspreis HT / NT) ---
        st.markdown("#### :material/schedule: 5. Time-of-Use (TOU) Energy Working Rates (Arbeitspreis)")

        # Inputs for Off-Peak and Peak TOU Windows
        tou_c1, tou_c2, tou_c3 = st.columns([2, 2, 2])
        with tou_c1:
            offpeak_rate = st.number_input(
                "Standard / Off-Peak Rate NT (€/kWh):",
                min_value=0.0,
                max_value=2.0,
                value=0.18,
                step=0.01,
                format="%.4f",
                help="Base energy rate applied during night, early morning, and weekend off-peak hours.",
                key="sandbox_offpeak_rate"
            )
        with tou_c2:
            peak_rate = st.number_input(
                "High Tariff / Peak Rate HT (€/kWh):",
                min_value=0.0,
                max_value=2.0,
                value=0.28,
                step=0.01,
                format="%.4f",
                help="High tariff energy rate applied during high demand daytime hours.",
                key="sandbox_peak_rate"
            )
        with tou_c3:
            weekend_offpeak = st.toggle(
                "Weekend is strictly Off-Peak (NT)",
                value=True,
                help="If enabled, all Saturday and Sunday hours are billed at the Off-Peak rate regardless of the time window.",
                key="sandbox_weekend_offpeak"
            )

        # TOU Peak Time Window Selection
        w_col1, w_col2, w_col3 = st.columns([2, 2, 2])
        with w_col1:
            peak_start_hour = st.selectbox(
                "Peak Window Start (HT):",
                options=[f"{h:02d}:00" for h in range(24)],
                index=8,
                key="sandbox_peak_start_hour"
            )
        with w_col2:
            peak_end_hour = st.selectbox(
                "Peak Window End (HT):",
                options=[f"{h:02d}:00" for h in range(1, 25)],
                index=19,  # 20:00
                key="sandbox_peak_end_hour"
            )
        with w_col3:
            st.caption(f":material/timer: **Active Peak Window:** Mon–Fri **{peak_start_hour} to {peak_end_hour}** ({peak_rate:.4f} €/kWh)")

        # Evaluate live TOU volume matching on active consumption timeseries
        peak_kwh = 0.0
        offpeak_kwh = 0.0
        peak_cost = 0.0
        offpeak_cost = 0.0
        total_tou_energy_cost = 0.0
        blended_rate = offpeak_rate

        start_min = int(peak_start_hour.split(":")[0]) * 60
        end_min = int(peak_end_hour.split(":")[0]) * 60
        if end_min == 0 or peak_end_hour == "24:00":
            end_min = 1440

        if isinstance(active_csv_df, pd.DataFrame) and not active_csv_df.empty:
            power_series = active_csv_df["Total_Demand_kW"] if "Total_Demand_kW" in active_csv_df.columns else active_csv_df["Power_kW"]
            
            # Extract timestamp series guaranteed as pd.Series
            if "Timestamp" in active_csv_df.columns:
                dt_series = pd.Series(pd.to_datetime(active_csv_df["Timestamp"], errors="coerce"), index=active_csv_df.index)
            elif "Datetime" in active_csv_df.columns:
                dt_series = pd.Series(pd.to_datetime(active_csv_df["Datetime"], errors="coerce"), index=active_csv_df.index)
            elif isinstance(active_csv_df.index, (pd.DatetimeIndex, pd.Index)):
                dt_series = pd.Series(pd.to_datetime(active_csv_df.index, errors="coerce"), index=active_csv_df.index)
            else:
                dt_series = pd.Series([pd.NaT] * len(active_csv_df), index=active_csv_df.index)

            if dt_series.notnull().any():
                minutes_of_day = dt_series.dt.hour * 60 + dt_series.dt.minute
                is_weekend = dt_series.dt.weekday >= 5

                if start_min < end_min:
                    in_window = (minutes_of_day >= start_min) & (minutes_of_day < end_min)
                else:
                    in_window = (minutes_of_day >= start_min) | (minutes_of_day < end_min)

                if weekend_offpeak:
                    is_peak_interval = in_window & (~is_weekend)
                else:
                    is_peak_interval = in_window

                peak_kwh = float((power_series[is_peak_interval] * 0.25).sum())
                offpeak_kwh = float((power_series[~is_peak_interval] * 0.25).sum())
            else:
                # Fallback if no valid datetime: assume 50% split
                total_kwh_fallback = float(power_series.sum() * 0.25)
                peak_kwh = total_kwh_fallback * 0.5
                offpeak_kwh = total_kwh_fallback * 0.5

            peak_cost = peak_kwh * peak_rate
            offpeak_cost = offpeak_kwh * offpeak_rate
            total_tou_energy_cost = peak_cost + offpeak_cost
            total_active_kwh = peak_kwh + offpeak_kwh
            if total_active_kwh > 0:
                blended_rate = total_tou_energy_cost / total_active_kwh

        # Inline TOU Results Breakdown
        st.markdown("##### :material/price_check: TOU Consumption & Working Cost Breakdown")
        r_col1, r_col2, r_col3 = st.columns([2, 2, 2])
        with r_col1:
            st.metric(
                label="High Tariff Energy (HT / Peak)",
                value=f"€{peak_cost:,.2f} / year",
                delta=f"{peak_kwh / 1000.0:,.2f} MWh ({peak_kwh:,.0f} kWh)",
                delta_color="off"
            )
        with r_col2:
            st.metric(
                label="Off-Peak Energy (NT)",
                value=f"€{offpeak_cost:,.2f} / year",
                delta=f"{offpeak_kwh / 1000.0:,.2f} MWh ({offpeak_kwh:,.0f} kWh)",
                delta_color="off"
            )
        with r_col3:
            st.metric(
                label="Total Energy Cost (Arbeitspreis)",
                value=f"€{total_tou_energy_cost:,.2f} / year",
                delta=f"Effective: €{blended_rate:.4f} / kWh",
                delta_color="normal"
            )

    # --- Interactive Overload Violation & TOU Visualizations ---
    if isinstance(active_csv_df, pd.DataFrame) and not active_csv_df.empty:
        tab_chart1, tab_chart2 = st.tabs([
            ":material/monitoring: Grid Capacity & Overload Violation Timeseries",
            ":material/access_time: 24h Average Daily Load & TOU Tariff Windows"
        ])

        with tab_chart1:
            power_col = "Total_Demand_kW" if "Total_Demand_kW" in active_csv_df.columns else "Power_kW"
            if "Timestamp" in active_csv_df.columns:
                time_data = active_csv_df["Timestamp"]
            elif "Datetime" in active_csv_df.columns:
                time_data = active_csv_df["Datetime"]
            else:
                time_data = list(range(len(active_csv_df)))

            v_fig = go.Figure()
            # Baseline consumption curve
            v_fig.add_trace(go.Scatter(
                x=time_data,
                y=active_csv_df[power_col],
                mode="lines",
                name="Measured Load (kW)",
                line=dict(color="#38bdf8", width=1.8),
            ))
            # Contracted capacity / grid limit line
            start_x = time_data.iloc[0] if hasattr(time_data, "iloc") else time_data[0]
            end_x = time_data.iloc[-1] if hasattr(time_data, "iloc") else time_data[-1]
            v_fig.add_trace(go.Scatter(
                x=[start_x, end_x],
                y=[contracted_capacity_kw, contracted_capacity_kw],
                mode="lines",
                name=f"Contract Limit ({contracted_capacity_kw:,.0f} kW)",
                line=dict(color="#f43f5e", width=2.5, dash="dash"),
            ))
            # Overload excess area highlight if violations exist
            if has_violations:
                excess_curve = np.maximum(contracted_capacity_kw, active_csv_df[power_col].values)
                v_fig.add_trace(go.Scatter(
                    x=time_data,
                    y=excess_curve,
                    mode="lines",
                    name="Overload Violation Spikes",
                    line=dict(color="#f43f5e", width=0),
                    fill="tonexty",
                    fillcolor="rgba(244, 63, 94, 0.35)",
                ))

            v_fig.update_layout(
                template="plotly_dark",
                height=380,
                margin=dict(l=20, r=20, t=30, b=20),
                xaxis=dict(title="Timestamp", rangeslider=dict(visible=True)),
                yaxis=dict(title="Power (kW)"),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(v_fig, use_container_width=True)

            # Top Overload Violation Table
            if not top_violations_df.empty:
                with st.expander(":material/table_chart: Top 5 Highest Overload Violation Events", expanded=False):
                    st.dataframe(top_violations_df, use_container_width=True)

        with tab_chart2:
            # Monthly Cost Breakdown Stacked Bar Chart
            st.markdown("#### :material/bar_chart: Monthly Cost & Invoice Breakdown")

            months_labels = []
            m_base_fees = []
            m_contracted_fees = []
            m_measured_fees = []
            m_ht_costs = []
            m_nt_costs = []
            m_penalties = []
            m_totals = []

            # Check if dataset spans multiple calendar months
            unique_months = dt_series.dt.to_period("M").unique() if dt_series.notnull().any() else []

            if len(unique_months) > 1:
                # Group by actual months present in dataset
                for period in sorted(unique_months):
                    m_label = period.strftime("%b %Y")
                    mask = (dt_series.dt.to_period("M") == period)
                    m_pow = power_series[mask]
                    m_dt = dt_series[mask]

                    m_min = m_dt.dt.hour * 60 + m_dt.dt.minute
                    m_wk = m_dt.dt.weekday >= 5
                    if start_min < end_min:
                        m_win = (m_min >= start_min) & (m_min < end_min)
                    else:
                        m_win = (m_min >= start_min) | (m_min < end_min)
                    m_pk_mask = m_win & (~m_wk) if weekend_offpeak else m_win

                    ht_kwh = float((m_pow[m_pk_mask] * 0.25).sum())
                    nt_kwh = float((m_pow[~m_pk_mask] * 0.25).sum())
                    ht_cost = ht_kwh * peak_rate
                    nt_cost = nt_kwh * offpeak_rate

                    base_cost = base_monthly_fee
                    cap_cost = (contracted_capacity_kw * contracted_rate) / 12.0
                    m_pk_kw = float(m_pow.max()) if len(m_pow) > 0 else 0.0
                    dem_cost = (m_pk_kw * measured_rate) / 12.0

                    ov_diff = (m_pow - contracted_capacity_kw).clip(lower=0.0)
                    pen_cost = (float(ov_diff.max()) * penalty_rate_kw) / 12.0 + (float(ov_diff.sum() * 0.25) * excess_kwh_rate)

                    tot = base_cost + cap_cost + dem_cost + ht_cost + nt_cost + pen_cost

                    months_labels.append(m_label)
                    m_base_fees.append(base_cost)
                    m_contracted_fees.append(cap_cost)
                    m_measured_fees.append(dem_cost)
                    m_ht_costs.append(ht_cost)
                    m_nt_costs.append(nt_cost)
                    m_penalties.append(pen_cost)
                    m_totals.append(tot)
            else:
                # 12-Month Annualized Distribution (Standard Calendar View Jan–Dec)
                standard_months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                # Seasonal shape factors for slight realistic variance across year
                seasonal_factors = [1.12, 1.08, 1.02, 0.95, 0.92, 0.96, 1.05, 1.08, 0.98, 0.94, 0.98, 1.10]
                total_factor = sum(seasonal_factors)

                for idx, m_name in enumerate(standard_months):
                    weight = seasonal_factors[idx] / total_factor * 12.0
                    months_labels.append(m_name)
                    base_cost = base_monthly_fee
                    cap_cost = (contracted_capacity_kw * contracted_rate) / 12.0
                    dem_cost = (measured_annual_cost / 12.0) * weight
                    ht_cost = (peak_cost / 12.0) * weight
                    nt_cost = (offpeak_cost / 12.0) * weight
                    pen_cost = (total_penalty_cost / 12.0) * weight
                    tot = base_cost + cap_cost + dem_cost + ht_cost + nt_cost + pen_cost

                    m_base_fees.append(base_cost)
                    m_contracted_fees.append(cap_cost)
                    m_measured_fees.append(dem_cost)
                    m_ht_costs.append(ht_cost)
                    m_nt_costs.append(nt_cost)
                    m_penalties.append(pen_cost)
                    m_totals.append(tot)

            # Build Stacked Bar Chart for Monthly Billing
            monthly_fig = go.Figure()
            monthly_fig.add_trace(go.Bar(x=months_labels, y=m_base_fees, name="Base Standing Fee", marker_color="#94a3b8"))
            monthly_fig.add_trace(go.Bar(x=months_labels, y=m_contracted_fees, name="Contracted Capacity", marker_color="#38bdf8"))
            monthly_fig.add_trace(go.Bar(x=months_labels, y=m_measured_fees, name="Measured Peak Demand", marker_color="#818cf8"))
            monthly_fig.add_trace(go.Bar(x=months_labels, y=m_nt_costs, name="Off-Peak Energy (NT)", marker_color="#10b981"))
            monthly_fig.add_trace(go.Bar(x=months_labels, y=m_ht_costs, name="High Tariff Energy (HT)", marker_color="#f59e0b"))
            if any(p > 0 for p in m_penalties):
                monthly_fig.add_trace(go.Bar(x=months_labels, y=m_penalties, name="Overload Penalties", marker_color="#f43f5e"))

            monthly_fig.update_layout(
                barmode="stack",
                template="plotly_dark",
                height=380,
                margin=dict(l=20, r=20, t=30, b=20),
                xaxis=dict(title="Billing Month"),
                yaxis=dict(title="Monthly Cost (€)", tickprefix="€"),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(monthly_fig, use_container_width=True)

            # Expandable Monthly Summary Table
            with st.expander(":material/table_chart: View Itemized Monthly Billing Table", expanded=False):
                monthly_table_df = pd.DataFrame({
                    "Month": months_labels,
                    "Base Fee (€)": [f"€{v:,.2f}" for v in m_base_fees],
                    "Capacity (€)": [f"€{v:,.2f}" for v in m_contracted_fees],
                    "Peak Demand (€)": [f"€{v:,.2f}" for v in m_measured_fees],
                    "Off-Peak NT (€)": [f"€{v:,.2f}" for v in m_nt_costs],
                    "Peak HT (€)": [f"€{v:,.2f}" for v in m_ht_costs],
                    "Penalties (€)": [f"€{v:,.2f}" for v in m_penalties],
                    "Total Invoice (€)": [f"€{v:,.2f}" for v in m_totals]
                })
                st.dataframe(monthly_table_df, use_container_width=True)

    # --- Comprehensive Total Cost Summary Dashboard ---
    st.subheader(":material/payments: Comprehensive Annual Electricity Bill & Tariff TCO")
    total_annual_bill = base_annual_cost + contracted_annual_cost + measured_annual_cost + total_penalty_cost + total_tou_energy_cost
    total_monthly_avg = total_annual_bill / 12.0
    total_consumed_kwh = peak_kwh + offpeak_kwh
    all_in_rate = (total_annual_bill / total_consumed_kwh) if total_consumed_kwh > 0 else 0.0

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        if render_kpi_card:
            render_kpi_card("Total Annual Electricity Bill", f"€{total_annual_bill:,.2f}", "All fixed, capacity & energy costs")
        else:
            st.metric("Total Annual Bill", f"€{total_annual_bill:,.2f}")
    with k2:
        if render_kpi_card:
            render_kpi_card("Monthly Average Invoice", f"€{total_monthly_avg:,.2f}", "12-month payment share", "info")
        else:
            st.metric("Monthly Avg", f"€{total_monthly_avg:,.2f}")
    with k3:
        if render_kpi_card:
            render_kpi_card("All-In Effective Price", f"€{all_in_rate:.4f} / kWh", f"Total Energy: {total_consumed_kwh/1000.0:,.1f} MWh", "primary")
        else:
            st.metric("All-In Effective Rate", f"€{all_in_rate:.4f} / kWh")
    with k4:
        penalty_status = "alert" if has_violations else "ok"
        penalty_title = "Penalty Surcharges" if has_violations else "Grid Penalty Status"
        penalty_val = f"€{total_penalty_cost:,.2f}" if has_violations else "€0.00 (Zero Penalty)"
        if render_kpi_card:
            render_kpi_card(penalty_title, penalty_val, f"{overload_peak_kw:,.1f} kW peak excess", penalty_status)
        else:
            st.metric(penalty_title, penalty_val)

    # Itemized Cost Breakdown Donut Chart
    with st.expander(":material/pie_chart: View Itemized Annual Cost Distribution Donut", expanded=False):
        cost_labels = ["Base Standing Fees", "Contracted Capacity", "Measured Peak Demand", "TOU Energy (HT/NT)", "Overload Penalties"]
        cost_values = [base_annual_cost, contracted_annual_cost, measured_annual_cost, total_tou_energy_cost, total_penalty_cost]
        cost_colors = ["#94a3b8", "#38bdf8", "#818cf8", "#f59e0b", "#f43f5e"]

        donut_fig = go.Figure(data=[go.Pie(
            labels=cost_labels,
            values=cost_values,
            hole=0.55,
            marker=dict(colors=cost_colors),
            textinfo="label+percent",
            hoverinfo="label+value+percent"
        )])
        donut_fig.update_layout(
            template="plotly_dark",
            height=340,
            margin=dict(l=20, r=20, t=20, b=20),
            showlegend=True
        )
        st.plotly_chart(donut_fig, use_container_width=True)


def render_hello_world_tab():
    st.title(":material/science: UI Sandbox Laboratory")
    st.caption("Quick standalone testing ground for Streamlit elements and widgets without running `app.py`.")

    st.success(
        "**Hello World from the UI Sandbox!** This environment runs independently and allows safe experimentation.",
        icon=":material/check_circle:"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="Environment Status",
            value="Isolated",
            delta="Ready for Testing",
            delta_color="normal"
        )
    with col2:
        st.metric(
            label="Import Boundary",
            value="1-Way Only",
            delta="Core/UI accessible",
            delta_color="normal"
        )
    with col3:
        st.metric(
            label="Icon Standard",
            value="Material Symbols",
            delta=":material/palette:",
            delta_color="off"
        )

    st.markdown("---")
    st.subheader(":material/integration_instructions: Quick Guide")
    st.markdown(
        """
        1. **Create new test components**: Add prototype scripts or functions directly inside `ui_sandbox/`.
        2. **Import existing project tools**: Import domain models, calculations, or UI cards freely.
        3. **Zero Main Impact**: Code in `ui_sandbox` is never bundled or executed by `app.py`.
        4. **Fast Feedback**: Edit and refresh the Streamlit page instantly to test layouts, forms, and charts.
        """
    )


def render_component_showcase_tab():
    st.title(":material/dashboard: Component & Card Showcase")
    st.caption("Test shared design system components and KPI cards.")

    st.subheader(":material/style: Shared KPI Metric Cards")
    c1, c2, c3, c4 = st.columns(4)

    if render_kpi_card:
        with c1:
            render_kpi_card("Total Peak Demand", "1,245 kW", "Status Quo", "primary")
        with c2:
            render_kpi_card("Annual Consumption", "4.82 GWh", "+3.2% vs avg", "success")
        with c3:
            render_kpi_card("BESS Shaving Potential", "320 kW", "25.7% Peak Cut", "info")
        with c4:
            render_kpi_card("Annual Net Savings", "€48,500", "NPV: €312k", "warning")
    else:
        st.warning("`render_kpi_card` not loaded. Check project paths.")

    st.markdown("---")
    st.subheader(":material/tune: Interactive Widget Controls")

    w1, w2 = st.columns(2)
    with w1:
        test_slider = st.slider("Test Battery Power (kW):", min_value=50, max_value=1000, value=250, step=50)
        test_select = st.selectbox("Battery Chemistry Preset:", ["LFP (Lithium Iron Phosphate)", "NMC (Nickel Manganese Cobalt)", "Sodium-Ion"])
    with w2:
        test_number = st.number_input("Target Peak Shaving Cutoff (kW):", min_value=100.0, max_value=2000.0, value=950.0, step=10.0)
        test_toggle = st.toggle("Enable Dynamic TOU Optimization", value=True)

    st.info(
        f"**Live Values:** Battery Power = `{test_slider} kW` | Chemistry = `{test_select}` | Cutoff = `{test_number} kW` | TOU = `{test_toggle}`",
        icon=":material/info:"
    )


def render_chart_lab_tab():
    st.title(":material/query_stats: Interactive Chart Laboratory")
    st.caption("Test and tune Plotly visualization configurations.")

    time_steps = np.arange(0, 24, 0.25)
    base_load = 400 + 350 * np.sin((time_steps - 6) * np.pi / 12) + np.random.normal(0, 15, len(time_steps))
    base_load = np.maximum(base_load, 150)
    
    pv_gen = np.maximum(0, 600 * np.sin((time_steps - 6) * np.pi / 12) ** 2)
    bess_discharge = np.where(base_load > 650, np.minimum(base_load - 650, 180), 0)
    net_grid = base_load - pv_gen - bess_discharge

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=time_steps, y=base_load, mode='lines', name='Baseline Load (kW)', line=dict(color='#94a3b8', width=2, dash='dash')))
    fig.add_trace(go.Scatter(x=time_steps, y=pv_gen, mode='lines', name='Solar PV Yield (kW)', fill='tozeroy', line=dict(color='#f59e0b', width=2), fillcolor='rgba(245, 158, 11, 0.2)'))
    fig.add_trace(go.Scatter(x=time_steps, y=bess_discharge, mode='lines', name='BESS Discharge (kW)', line=dict(color='#10b981', width=2)))
    fig.add_trace(go.Scatter(x=time_steps, y=net_grid, mode='lines', name='Residual Grid Demand (kW)', line=dict(color='#3b82f6', width=3)))

    fig.update_layout(
        title="24h Multi-Asset Power Dispatch Preview (Plotly)",
        xaxis_title="Hour of Day (h)",
        yaxis_title="Electrical Power (kW)",
        template="plotly_dark",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)


def render_scratchpad_tab():
    st.title(":material/edit_note: UI Scratchpad & Rapid Tester")
    st.caption("Place ad-hoc experimental widgets and layouts here.")

    user_text = st.text_input("Test Input Field:", value="Sample UI experiment text")
    st.write(f"**Echo:** {user_text}")

    tab_a, tab_b = st.tabs([":material/code: JSON Inspector", ":material/table_chart: Data Table Test"])
    with tab_a:
        sample_dict = {
            "environment": "ui_sandbox",
            "version": "1.0.0",
            "active_tab": "scratchpad",
            "status": "ready"
        }
        st.json(sample_dict)
    with tab_b:
        st.dataframe(
            {
                "Interval": ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"],
                "Demand [kW]": [210, 195, 450, 780, 620, 390],
                "Tariff [EUR/kWh]": [0.18, 0.18, 0.28, 0.32, 0.28, 0.22]
            },
            use_container_width=True
        )


if __name__ == "__main__":
    main()
