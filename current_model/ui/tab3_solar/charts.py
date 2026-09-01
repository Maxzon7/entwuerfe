"""
========================================================================================
Solar PV Visualizations & Plotly Charts (current_model/ui/tab3_solar/charts.py)
========================================================================================

Description:
------------
Generates dark-themed, high-contrast Plotly figures for pure Solar PV analysis:
  - 15-Minute interactive power timeseries with range slider (POA, DC power, AC power, Inverter limit)
  - 12-Month energy yield (MWh) and specific yield (kWh/kWp) bar chart
  - System Loss Waterfall diagram (Irradiance potential -> Thermal -> BOS -> Inverter -> AC Net)
  - Seasonal 24-hour average daily generation profiles (Summer vs. Winter curves)
"""

from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from current_model.models.solar import SolarMonthlyYield


def create_solar_timeseries_figure(
    df: pd.DataFrame,
    dc_capacity_kwp: float,
    inverter_capacity_kw: float
) -> go.Figure:
    """
    Constructs an interactive time-series figure of AC & DC solar generation with range slider.
    """
    fig = go.Figure()
    timestamps = df["timestamp"]

    # 1. Plane of Array Irradiance (Area / subtle fill)
    if "POA_W_m2" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=df["POA_W_m2"] / 10.0,  # Scaled for visual comparison (1000 W/m² -> 100)
                name="Irradiance (POA / 10 W/m²)",
                line=dict(color="rgba(251, 191, 36, 0.35)", width=1, dash="dot"),
                hoverinfo="skip",
                showlegend=True
            )
        )

    # 2. DC Power (Unclipped / Pre-inverter)
    if "P_DC_kW" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=df["P_DC_kW"],
                name="DC Array Power (kW)",
                line=dict(color="#F59E0B", width=1.5),
                hovertemplate="<b>DC Power:</b> %{y:,.1f} kW<extra></extra>",
                showlegend=True
            )
        )

    # 3. AC Power (Inverter Output)
    if "P_AC_kW" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=df["P_AC_kW"],
                name="AC Grid Power (kW)",
                line=dict(color="#10B981", width=2.2),
                fill="tozeroy",
                fillcolor="rgba(16, 185, 129, 0.15)",
                hovertemplate="<b>%{x|%d %b %Y %H:%M}</b><br><b>AC Output:</b> %{y:,.1f} kW<extra></extra>",
                showlegend=True
            )
        )

    # 4. Inverter Max AC Capacity Limit Line
    fig.add_hline(
        y=inverter_capacity_kw,
        line_dash="dash",
        line_color="#EF4444",
        line_width=1.5,
        annotation_text=f"Inverter AC Limit ({inverter_capacity_kw:,.0f} kW)",
        annotation_position="top right",
        annotation_font_color="#EF4444"
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>Solar PV Generation Timeseries Profile</b> ({dc_capacity_kwp:,.0f} kWp DC / {inverter_capacity_kw:,.0f} kW AC - 15-Min Resolution)",
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
        height=420
    )

    return fig


def create_solar_monthly_bar_figure(
    monthly_yields: List[SolarMonthlyYield],
    dc_capacity_kwp: float
) -> go.Figure:
    """
    Constructs a monthly energy yield (MWh) and specific yield (kWh/kWp) bar chart.
    """
    months = [m.month_name[:3] for m in monthly_yields]
    mwh_values = [m.energy_mwh for m in monthly_yields]
    spec_yields = [m.specific_yield_kwh_kwp for m in monthly_yields]
    cf_values = [m.capacity_factor_pct for m in monthly_yields]

    fig = go.Figure()

    # Bar chart for MWh
    fig.add_trace(
        go.Bar(
            x=months,
            y=mwh_values,
            name="Monthly Yield (MWh)",
            marker=dict(
                color=mwh_values,
                colorscale="Viridis",
                showscale=False,
                line=dict(color="#0B0F19", width=1)
            ),
            customdata=np.stack((spec_yields, cf_values), axis=-1),
            hovertemplate="<b>%{x}</b><br>Energy: <b>%{y:.2f} MWh</b><br>Specific Yield: <b>%{customdata[0]:.1f} kWh/kWp</b><br>Capacity Factor: <b>%{customdata[1]:.1f} %</b><extra></extra>",
            text=[f"{v:.1f}" for v in mwh_values],
            textposition="outside",
            textfont=dict(size=10, color="#CBD5E1")
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Monthly Solar Energy Yield (MWh)</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(
            title="Energy Output (MWh)",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        margin=dict(l=20, r=20, t=45, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=320
    )

    return fig


def create_solar_seasonal_daily_figure(df: pd.DataFrame) -> go.Figure:
    """
    Plots average 24-hour daily generation profiles for representative seasonal solstices/equinoxes.
    """
    df_copy = df.copy()
    df_copy["hour"] = df_copy["timestamp"].dt.hour
    df_copy["month"] = df_copy["timestamp"].dt.month

    seasons = {
        "January (Solstice / Summer)": df_copy[df_copy["month"] == 1],
        "April (Autumn Equinox)": df_copy[df_copy["month"] == 4],
        "July (Winter Solstice)": df_copy[df_copy["month"] == 7],
        "October (Spring Equinox)": df_copy[df_copy["month"] == 10]
    }

    colors = {
        "January (Solstice / Summer)": "#F59E0B",
        "April (Autumn Equinox)": "#10B981",
        "July (Winter Solstice)": "#3B82F6",
        "October (Spring Equinox)": "#8B5CF6"
    }

    fig = go.Figure()
    hours = list(range(24))

    for s_name, s_df in seasons.items():
        if not s_df.empty:
            avg_hourly = s_df.groupby("hour")["P_AC_kW"].mean().reindex(hours, fill_value=0.0)
            fig.add_trace(
                go.Scatter(
                    x=hours,
                    y=avg_hourly.values,
                    name=s_name,
                    mode="lines",
                    line=dict(color=colors.get(s_name, "#CBD5E1"), width=2.5),
                    hovertemplate=f"<b>{s_name}</b><br>Hour %{{x}}:00: <b>%{{y:,.1f}} kW</b><extra></extra>"
                )
            )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Average 24-Hour Daily Generation Profile by Season</b>",
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
            title="Average Active Power (kW)",
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
        margin=dict(l=20, r=20, t=55, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=320
    )

    return fig


def create_solar_loss_waterfall_figure(loss_breakdown: Dict[str, float]) -> go.Figure:
    """
    Constructs a Waterfall figure illustrating physical energy loss stages from raw sunlight to grid AC.
    """
    pot = loss_breakdown.get("Nominal Plane-of-Array Potential", 100000.0)
    therm = loss_breakdown.get("Thermal Losses (Temperature Derate)", 5000.0)
    bos = loss_breakdown.get("BOS & System Losses (Soiling, DC Wiring)", 4000.0)
    inv = loss_breakdown.get("Inverter Conversion Loss", 2000.0)
    clip = loss_breakdown.get("Inverter Clipping Loss", 500.0)
    net = loss_breakdown.get("Net AC Energy Delivered", 88500.0)

    measures = ["absolute", "relative", "relative", "relative", "relative", "total"]
    x_labels = [
        "Nominal Potential",
        "Thermal Derate",
        "BOS & Soiling",
        "Inverter Losses",
        "Inverter Clipping",
        "Net AC Energy"
    ]
    y_vals = [
        pot / 1000.0,
        -therm / 1000.0,
        -bos / 1000.0,
        -inv / 1000.0,
        -clip / 1000.0,
        net / 1000.0
    ]

    fig = go.Figure(
        go.Waterfall(
            name="Energy Cascade",
            orientation="v",
            measure=measures,
            x=x_labels,
            y=y_vals,
            textposition="outside",
            text=[f"{v:+,.1f} MWh" if m == "relative" else f"{v:,.1f} MWh" for v, m in zip(y_vals, measures)],
            connector=dict(line=dict(color="#475569")),
            decreasing=dict(marker=dict(color="#EF4444")),
            increasing=dict(marker=dict(color="#10B981")),
            totals=dict(marker=dict(color="#3B82F6"))
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Solar PV System Loss Waterfall (Physical Energy Flow from Sun to AC Grid)</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        yaxis=dict(
            title="Energy (MWh)",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        xaxis=dict(gridcolor="#1E293B"),
        margin=dict(l=20, r=20, t=45, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=340
    )

    return fig


def create_technology_comparison_figure(tech_items: List[Any]) -> go.Figure:
    """
    Constructs a comparative grouped bar chart comparing electricity production (MWh)
    across Year 1, Year 5, Year 10, and Year 15 for PERC, TOPCon, and Backcontact.
    """
    years = ["Year 1", "Year 5", "Year 10", "Year 15"]
    colors = {
        "PERC": "#94A3B8",        # Slate
        "TOPCon": "#38BDF8",      # Sky Blue
        "Backcontact": "#10B981"  # Emerald
    }

    fig = go.Figure()

    for item in tech_items:
        mwh_vals = [
            item.year_1_kwh / 1000.0,
            item.year_5_kwh / 1000.0,
            item.year_10_kwh / 1000.0,
            item.year_15_kwh / 1000.0
        ]
        color = colors.get(item.tech_key, "#F59E0B")
        gain_str = f" (+{item.gain_pct_vs_perc:.1f}%)" if item.gain_pct_vs_perc > 0 else " (Baseline)"

        fig.add_trace(
            go.Bar(
                x=years,
                y=mwh_vals,
                name=f"{item.tech_key} ({item.module_power_wp:.0f} Wp){gain_str}",
                marker=dict(color=color),
                text=[f"{v:,.1f} MWh" for v in mwh_vals],
                textposition="outside",
                textfont=dict(size=10, color="#CBD5E1"),
                hovertemplate=f"<b>{item.tech_name}</b><br>%{{x}}: <b>%{{y:,.1f}} MWh</b><extra></extra>"
            )
        )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Multi-Technology Production Comparison (Identical Module Count & Area)</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        barmode="group",
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(
            title="Annual Electricity Yield (MWh)",
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
        height=360
    )

    return fig

