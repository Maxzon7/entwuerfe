"""
========================================================================================
Solar & Consumption Integration Visualizations (ui/tab3_solar/integration_charts.py)
========================================================================================

Description:
------------
Generates high-contrast, dark-themed Plotly charts for Sub-Tab 3.2:
  - 15-Minute interactive electrical load dispatch timeseries with range slider
    (Facility Load, Solar Generation, Direct Self-Consumption, Surplus, Residual Grid Import).
  - 12-Month coupled energy balance bar chart (Consumption split vs. Solar split + Monthly Autarky %).
  - Seasonal 24-hour diurnal dispatch overlay (Diurnal profiles across seasons).
  - Sankey / Energy balance flow diagram (Generation sources to facility and grid sinks).
  - BESS Storage Readiness & Surplus Power Duration analysis (Surplus MWh and peak kW).
"""

from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from current_model.models.solar import SolarKPIs


MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]


def create_solar_load_dispatch_figure(
    df: pd.DataFrame,
    dc_capacity_kwp: float,
    inverter_capacity_kw: float
) -> go.Figure:
    """
    Constructs an interactive 15-minute dispatch timeseries figure illustrating
    the exact physical balance between Solar PV and Facility Load.
    """
    fig = go.Figure()

    step = 2 if len(df) > 20000 else 1
    plot_df = df.iloc[::step]
    timestamps = plot_df["timestamp"]

    # 1. Facility Load Demand Line
    if "P_Load_kW" in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df["P_Load_kW"],
                name="Facility Load (kW)",
                line=dict(color="#94A3B8", width=1.5),
                hovertemplate="<b>%{x|%d %b %Y %H:%M}</b><br>Facility Load: <b>%{y:,.1f} kW</b><extra></extra>",
                showlegend=True
            )
        )

    # 2. Solar AC Generation Line
    if "P_AC_kW" in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df["P_AC_kW"],
                name="Solar AC Output (kW)",
                line=dict(color="#F59E0B", width=1.5, dash="dot"),
                hovertemplate="Solar AC Output: <b>%{y:,.1f} kW</b><extra></extra>",
                showlegend=True
            )
        )

    # 3. Direct Self-Consumption (Filled Green Area)
    if "P_Direct_kW" in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df["P_Direct_kW"],
                name="Direct Self-Consumption (kW)",
                line=dict(color="#10B981", width=2.0),
                fill="tozeroy",
                fillcolor="rgba(16, 185, 129, 0.25)",
                hovertemplate="Direct Solar Use: <b>%{y:,.1f} kW</b><extra></extra>",
                showlegend=True
            )
        )

    # 4. PV Surplus / Feed-in Potential (Orange)
    if "P_Surplus_kW" in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df["P_Surplus_kW"],
                name="PV Surplus / Export (kW)",
                line=dict(color="#F97316", width=1.2),
                hovertemplate="PV Surplus: <b>%{y:,.1f} kW</b><extra></extra>",
                showlegend=True
            )
        )

    # 5. Residual Grid Load (Sky Blue)
    if "P_Residual_kW" in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df["P_Residual_kW"],
                name="Residual Grid Import (kW)",
                line=dict(color="#38BDF8", width=1.2, dash="dash"),
                hovertemplate="Residual Grid Import: <b>%{y:,.1f} kW</b><extra></extra>",
                showlegend=True
            )
        )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>15-Minute Electrical Dispatch Profile (Solar vs. Facility Load)</b> "
                 f"<span style='font-size:12px; color:#94A3B8;'>({dc_capacity_kwp:,.0f} kWp DC / {inverter_capacity_kw:,.0f} kW AC)</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Date & Time",
            rangeslider=dict(visible=True, thickness=0.06),
            type="date",
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="Active Power (kW)",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11)
        ),
        margin=dict(l=20, r=20, t=60, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=440
    )

    return fig


def create_monthly_energy_balance_figure(df: pd.DataFrame, dt_hours: float = 0.25) -> go.Figure:
    """
    Constructs a 12-month coupled energy balance bar chart:
      - Left bar per month: Facility Consumption split into Direct Solar (Green) + Grid Import (Blue)
      - Right bar per month: Solar PV Output split into Direct Solar (Green) + PV Surplus / Feed-in (Orange)
      - Secondary Line: Monthly Autarky Rate (%)
    """
    df_calc = df.copy()
    if "timestamp" in df_calc.columns:
        df_calc["month"] = pd.to_datetime(df_calc["timestamp"]).dt.month
    else:
        df_calc["month"] = 1

    months_idx = list(range(1, 13))
    direct_mwh = []
    residual_mwh = []
    surplus_mwh = []
    total_load_mwh = []
    total_solar_mwh = []
    autarky_pct_list = []
    self_cons_pct_list = []

    for m in months_idx:
        m_df = df_calc[df_calc["month"] == m]
        if not m_df.empty:
            d_kwh = float(m_df["P_Direct_kW"].sum() * dt_hours) if "P_Direct_kW" in m_df.columns else 0.0
            r_kwh = float(m_df["P_Residual_kW"].sum() * dt_hours) if "P_Residual_kW" in m_df.columns else 0.0
            s_kwh = float(m_df["P_Surplus_kW"].sum() * dt_hours) if "P_Surplus_kW" in m_df.columns else 0.0
            l_kwh = float(m_df["P_Load_kW"].sum() * dt_hours) if "P_Load_kW" in m_df.columns else (d_kwh + r_kwh)
            pv_kwh = float(m_df["P_AC_kW"].sum() * dt_hours) if "P_AC_kW" in m_df.columns else (d_kwh + s_kwh)

            autarky = (d_kwh / l_kwh * 100.0) if l_kwh > 0 else 0.0
            self_cons = (d_kwh / pv_kwh * 100.0) if pv_kwh > 0 else 0.0
        else:
            d_kwh, r_kwh, s_kwh, l_kwh, pv_kwh, autarky, self_cons = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

        direct_mwh.append(d_kwh / 1000.0)
        residual_mwh.append(r_kwh / 1000.0)
        surplus_mwh.append(s_kwh / 1000.0)
        total_load_mwh.append(l_kwh / 1000.0)
        total_solar_mwh.append(pv_kwh / 1000.0)
        autarky_pct_list.append(autarky)
        self_cons_pct_list.append(self_cons)

    fig = go.Figure()

    # Trace 1: Direct Solar in Load (Green)
    fig.add_trace(
        go.Bar(
            name="Direct Solar in Load",
            x=MONTH_NAMES,
            y=direct_mwh,
            marker_color="#10B981",
            offsetgroup=0,
            hovertemplate="<b>%{x}</b> - Direct Solar: <b>%{y:,.1f} MWh</b><extra></extra>"
        )
    )

    # Trace 2: Residual Grid Import in Load (Blue)
    fig.add_trace(
        go.Bar(
            name="Residual Grid Import",
            x=MONTH_NAMES,
            y=residual_mwh,
            marker_color="#38BDF8",
            offsetgroup=0,
            base=direct_mwh,
            hovertemplate="<b>%{x}</b> - Residual Grid Import: <b>%{y:,.1f} MWh</b><extra></extra>"
        )
    )

    # Trace 3: Direct Solar in PV Bar (Green duplicate on group 1)
    fig.add_trace(
        go.Bar(
            name="Direct Solar (in PV)",
            x=MONTH_NAMES,
            y=direct_mwh,
            marker_color="#059669",
            offsetgroup=1,
            showlegend=False,
            hovertemplate="<b>%{x}</b> - Direct Solar: <b>%{y:,.1f} MWh</b><extra></extra>"
        )
    )

    # Trace 4: PV Surplus Export in PV Bar (Amber)
    fig.add_trace(
        go.Bar(
            name="PV Surplus / Grid Export",
            x=MONTH_NAMES,
            y=surplus_mwh,
            marker_color="#F59E0B",
            offsetgroup=1,
            base=direct_mwh,
            hovertemplate="<b>%{x}</b> - PV Surplus / Export: <b>%{y:,.1f} MWh</b><extra></extra>"
        )
    )

    # Trace 5: Autarky % Line (Secondary Y-Axis)
    fig.add_trace(
        go.Scatter(
            name="Monthly Autarky (%)",
            x=MONTH_NAMES,
            y=autarky_pct_list,
            mode="lines+markers",
            yaxis="y2",
            line=dict(color="#A855F7", width=2.5),
            marker=dict(size=6, color="#C084FC"),
            hovertemplate="<b>%{x} Autarky:</b> <b>%{y:.1f}%</b><extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Monthly Energy Balance: Facility Load vs. Solar Generation (MWh)</b><br>"
                 "<span style='font-size:11px; color:#94A3B8;'>Left bar: Facility Load (Direct Solar + Grid) | Right bar: Solar Generation (Direct Solar + Surplus Export) | Line: Autarky %</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        barmode="group",
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(
            title="Energy (MWh)",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        yaxis2=dict(
            title="Autarky (%)",
            overlaying="y",
            side="right",
            range=[0, 105],
            gridcolor="rgba(168, 85, 247, 0.15)",
            showgrid=False
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11)
        ),
        margin=dict(l=20, r=40, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380
    )

    return fig


def create_seasonal_dispatch_daily_figure(df: pd.DataFrame) -> go.Figure:
    """
    Plots average 24-hour diurnal dispatch profiles across seasonal solstices and equinoxes.
    """
    df_calc = df.copy()
    ts = pd.to_datetime(df_calc["timestamp"])
    df_calc["hour"] = ts.dt.hour
    df_calc["month"] = ts.dt.month

    seasons = [
        ("Summer (Jan)", 1, "#F59E0B"),
        ("Autumn (Apr)", 4, "#FB923C"),
        ("Winter (Jul)", 7, "#38BDF8"),
        ("Spring (Oct)", 10, "#10B981")
    ]

    fig = go.Figure()
    hours = list(range(24))

    for s_name, m_num, s_color in seasons:
        s_df = df_calc[df_calc["month"] == m_num]
        if not s_df.empty:
            avg_load = s_df.groupby("hour")["P_Load_kW"].mean().reindex(hours, fill_value=0.0)
            avg_pv = s_df.groupby("hour")["P_AC_kW"].mean().reindex(hours, fill_value=0.0)
            avg_direct = s_df.groupby("hour")["P_Direct_kW"].mean().reindex(hours, fill_value=0.0)

            fig.add_trace(
                go.Scatter(
                    x=hours,
                    y=avg_load.values,
                    name=f"{s_name} - Facility Load",
                    mode="lines",
                    line=dict(color="#64748B", width=1.5, dash="dot"),
                    hovertemplate=f"<b>{s_name} Load:</b> %{{y:,.1f}} kW<extra></extra>"
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=hours,
                    y=avg_pv.values,
                    name=f"{s_name} - Solar PV",
                    mode="lines",
                    line=dict(color=s_color, width=2.0),
                    hovertemplate=f"<b>{s_name} Solar:</b> %{{y:,.1f}} kW<extra></extra>"
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=hours,
                    y=avg_direct.values,
                    name=f"{s_name} - Direct Use",
                    mode="lines",
                    fill="tozeroy",
                    line=dict(color=s_color, width=1.0),
                    hovertemplate=f"<b>{s_name} Direct Use:</b> %{{y:,.1f}} kW<extra></extra>"
                )
            )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Seasonal Diurnal Dispatch (24-Hour Average Curves)</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Hour of Day (0 - 23)",
            tickmode="linear",
            tick0=0,
            dtick=2,
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="Average Power (kW)",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=10)
        ),
        margin=dict(l=20, r=20, t=60, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig


def create_energy_flow_sankey_figure(kpis: SolarKPIs) -> go.Figure:
    """
    Constructs a Sankey diagram tracing energy flows:
      Sources (Solar PV + Grid) -> Direct Use & Surplus -> Sinks (Facility Load + Grid Export).
    """
    solar_kwh = max(1.0, kpis.annual_energy_kwh)
    direct_kwh = kpis.direct_consumption_kwh
    surplus_kwh = kpis.surplus_generation_kwh
    residual_kwh = kpis.residual_load_kwh
    load_kwh = max(1.0, kpis.total_load_kwh)

    # Proportions
    scr_pct = (direct_kwh / solar_kwh * 100.0)
    surplus_pct = (surplus_kwh / solar_kwh * 100.0)
    autarky_pct = (direct_kwh / load_kwh * 100.0)
    grid_pct = (residual_kwh / load_kwh * 100.0)

    # Nodes:
    # 0: Solar PV Generation
    # 1: Grid Electricity Import
    # 2: Direct Solar Consumption
    # 3: Total Facility Demand
    # 4: PV Surplus / Grid Export
    nodes_labels = [
        f"<b>Solar PV Generation</b><br>{solar_kwh/1000:,.1f} MWh (100%)",
        f"<b>Grid Electricity</b><br>{residual_kwh/1000:,.1f} MWh ({grid_pct:.1f}% load)",
        f"<b>Direct Solar Self-Use</b><br>{direct_kwh/1000:,.1f} MWh ({scr_pct:.1f}% PV)",
        f"<b>Total Facility Demand</b><br>{load_kwh/1000:,.1f} MWh (100%)",
        f"<b>PV Surplus / Grid Export</b><br>{surplus_kwh/1000:,.1f} MWh ({surplus_pct:.1f}% PV)"
    ]

    nodes_colors = [
        "#F59E0B",  # Solar (Amber)
        "#38BDF8",  # Grid (Sky Blue)
        "#10B981",  # Direct (Emerald)
        "#64748B",  # Load (Slate)
        "#F97316"   # Export (Orange)
    ]

    links_source = [0, 0, 1, 2]
    links_target = [2, 4, 3, 3]
    links_value = [
        max(0.1, direct_kwh / 1000.0),
        max(0.1, surplus_kwh / 1000.0),
        max(0.1, residual_kwh / 1000.0),
        max(0.1, direct_kwh / 1000.0)
    ]
    links_color = [
        "rgba(16, 185, 129, 0.45)",  # Solar to Direct
        "rgba(249, 115, 22, 0.45)",  # Solar to Surplus
        "rgba(56, 189, 248, 0.45)",  # Grid to Load
        "rgba(16, 185, 129, 0.45)"   # Direct to Load
    ]

    fig = go.Figure(
        go.Sankey(
            node=dict(
                pad=20,
                thickness=20,
                line=dict(color="#0B0F19", width=1),
                label=nodes_labels,
                color=nodes_colors
            ),
            link=dict(
                source=links_source,
                target=links_target,
                value=links_value,
                color=links_color
            )
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>Energy Balance & Dispatch Flow (Sankey Flow Diagram)</b> "
                 f"<span style='font-size:12px; color:#94A3B8;'>(Autarky: {autarky_pct:.1f}% | Self-Consumption: {scr_pct:.1f}%)</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        margin=dict(l=20, r=20, t=50, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig


def create_bess_readiness_figure(df: pd.DataFrame, dt_hours: float = 0.25) -> go.Figure:
    """
    Constructs a BESS storage readiness chart:
      - Monthly surplus energy available for battery storage (MWh).
      - Peak hourly surplus charging power (kW).
    """
    df_calc = df.copy()
    if "timestamp" in df_calc.columns:
        df_calc["month"] = pd.to_datetime(df_calc["timestamp"]).dt.month
    else:
        df_calc["month"] = 1

    surplus_mwh = []
    peak_surplus_kw = []

    for m in range(1, 13):
        m_df = df_calc[df_calc["month"] == m]
        if not m_df.empty and "P_Surplus_kW" in m_df.columns:
            s_kwh = float(m_df["P_Surplus_kW"].sum() * dt_hours)
            p_kw = float(m_df["P_Surplus_kW"].max())
        else:
            s_kwh, p_kw = 0.0, 0.0
        surplus_mwh.append(s_kwh / 1000.0)
        peak_surplus_kw.append(p_kw)

    fig = go.Figure()

    # Bar: Monthly Surplus MWh
    fig.add_trace(
        go.Bar(
            name="Monthly Surplus Energy (MWh)",
            x=MONTH_NAMES,
            y=surplus_mwh,
            marker_color="#F97316",
            hovertemplate="<b>%{x}</b> Surplus Energy: <b>%{y:,.1f} MWh</b><extra></extra>"
        )
    )

    # Line: Peak Surplus Power (kW) on Secondary Axis
    fig.add_trace(
        go.Scatter(
            name="Peak Surplus Power (kW)",
            x=MONTH_NAMES,
            y=peak_surplus_kw,
            mode="lines+markers",
            yaxis="y2",
            line=dict(color="#38BDF8", width=2.0, dash="dot"),
            marker=dict(size=6, color="#7DD3FC"),
            hovertemplate="<b>%{x} Peak Surplus:</b> <b>%{y:,.1f} kW</b><extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>BESS Storage Potential: Monthly Surplus Solar Energy & Peak Surplus Power</b><br>"
                 "<span style='font-size:11px; color:#94A3B8;'>Surplus energy currently exported/curtailed that could be stored in a Battery Energy Storage System (Tab 5)</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(
            title="Surplus Energy (MWh)",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        yaxis2=dict(
            title="Peak Surplus Power (kW)",
            overlaying="y",
            side="right",
            gridcolor="rgba(56, 189, 248, 0.15)",
            showgrid=False
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11)
        ),
        margin=dict(l=20, r=40, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig
