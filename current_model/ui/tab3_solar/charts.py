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

    # For ultra-smooth GPU WebGL rendering, decimate to 30-min resolution for annual overview (17,520 points)
    step = 2 if len(df) > 20000 else 1
    plot_df = df.iloc[::step]
    timestamps = plot_df["timestamp"]

    # 1. Plane of Array Irradiance (Area / subtle fill)
    if "POA_W_m2" in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df["POA_W_m2"] / 10.0,  # Scaled for visual comparison (1000 W/m² -> 100)
                name="Irradiance (POA / 10 W/m²)",
                line=dict(color="rgba(251, 191, 36, 0.35)", width=1, dash="dot"),
                hoverinfo="skip",
                showlegend=True
            )
        )

    # 2. DC Power (Unclipped / Pre-inverter)
    if "P_DC_kW" in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df["P_DC_kW"],
                name="DC Array Power (kW)",
                line=dict(color="#F59E0B", width=1.5),
                hovertemplate="<b>DC Power:</b> %{y:,.1f} kW<extra></extra>",
                showlegend=True
            )
        )

    # 3. AC Power (Inverter Output)
    if "P_AC_kW" in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df["P_AC_kW"],
                name="AC Grid Power (kW)",
                line=dict(color="#10B981", width=2.0),
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


def create_solar_capex_donut_figure(
    fin_metrics: Any,
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs an interactive donut chart illustrating the itemized initial CAPEX breakdown
    (Modules, Inverter, Substructure, Electrical Installation, Fixed Fees).
    """
    fig = go.Figure()

    labels = []
    values = []
    colors = []

    if getattr(fin_metrics, "capex_modules", 0) > 0:
        labels.append("PV Modules")
        values.append(fin_metrics.capex_modules)
        colors.append("#38BDF8")  # Sky Blue

    if getattr(fin_metrics, "capex_inverter", 0) > 0:
        labels.append("Inverter(s)")
        values.append(fin_metrics.capex_inverter)
        colors.append("#F59E0B")  # Amber

    if getattr(fin_metrics, "capex_substructure", 0) > 0:
        labels.append("Substructure & Mounting")
        values.append(fin_metrics.capex_substructure)
        colors.append("#10B981")  # Emerald

    if getattr(fin_metrics, "capex_installation", 0) > 0:
        labels.append("Installation & Grid Connect")
        values.append(fin_metrics.capex_installation)
        colors.append("#8B5CF6")  # Purple

    if getattr(fin_metrics, "capex_fixed_fees", 0) > 0:
        labels.append("Switchgear & Mobilization")
        values.append(fin_metrics.capex_fixed_fees)
        colors.append("#EC4899")  # Pink

    if not values or sum(values) <= 0:
        return fig

    total_val = sum(values)

    fig.add_trace(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker=dict(colors=colors, line=dict(color="#0B0F19", width=2)),
            textinfo="percent+label",
            textposition="outside",
            hovertemplate="<b>%{label}</b><br>Amount: <b>%{value:,.2f} " + currency + "</b><br>Share: <b>%{percent}</b><extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text=f"<b>Turn-Key CAPEX Investment Breakdown ({total_val:,.0f} {currency})</b>", font=dict(size=14, color="#F8FAFC")),
        showlegend=False,
        margin=dict(l=20, r=20, t=50, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=320,
        annotations=[
            dict(
                text=f"<b>{total_val:,.0f}</b><br><span style='font-size:11px;color:#94A3B8;'>{currency}</span>",
                x=0.5, y=0.5,
                font_size=16,
                showarrow=False
            )
        ]
    )

    return fig


def create_solar_cashflow_payback_figure(
    fin_metrics: Any,
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs a 15-year cumulative cashflow and payback timeline chart (matching the reference Excel diagram).
    Shows the initial investment dip in Year 0 and positive cumulative cashflow crossing the break-even line.
    """
    fig = go.Figure()

    table = getattr(fin_metrics, "cash_flow_table", [])
    if not table:
        return fig

    years = [0] + [row["year"] for row in table]
    cum_cf = getattr(fin_metrics, "cumulative_cash_flow", [])
    if not cum_cf or len(cum_cf) != len(years):
        cum_cf = [-fin_metrics.total_capex] + [row["cumulative_cash_flow"] for row in table]

    annual_cf = [0.0] + [row["net_cash_flow"] for row in table]

    # Zero Break-Even Line
    fig.add_hline(
        y=0.0,
        line_color="#64748B",
        line_width=1.5,
        line_dash="dash",
        annotation_text="Break-Even / Amortisation",
        annotation_position="bottom right"
    )

    # Annual Net Cash Flow Bars
    fig.add_trace(
        go.Bar(
            x=years[1:],
            y=annual_cf[1:],
            name="Annual Net Savings / Benefit",
            marker_color="rgba(56, 189, 248, 0.4)",
            hovertemplate="Year %{x}: <b>+%{y:,.0f} " + currency + "</b> net/year<extra></extra>"
        )
    )

    # Cumulative Cash Flow Line
    fig.add_trace(
        go.Scatter(
            x=years,
            y=cum_cf,
            mode="lines+markers",
            name="Cumulative Net Cash Flow",
            line=dict(color="#10B981", width=3),
            marker=dict(size=7, color="#10B981"),
            hovertemplate="Year %{x}: <b>%{y:,.0f} " + currency + "</b> cumulative<extra></extra>"
        )
    )

    # Add Payback marker if reached within horizon
    pb = getattr(fin_metrics, "payback_period_years", None)
    if pb is not None and pb <= len(years) - 1:
        fig.add_vline(
            x=pb,
            line_color="#F59E0B",
            line_width=2,
            line_dash="dot",
            annotation_text=f"Payback: {pb:.1f} Yrs",
            annotation_position="top left"
        )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text="<b>15-Year Life-Cycle Cash Flow & Amortisation Curve</b>", font=dict(size=14, color="#F8FAFC")),
        xaxis=dict(title="Operational Year", tickmode="linear", dtick=1, gridcolor="#1E293B"),
        yaxis=dict(title=f"Net Cumulative Cash Flow ({currency})", gridcolor="#1E293B"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380
    )

    return fig


def create_cumulative_cost_comparison_figure(
    fin_metrics: Any,
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs an interactive 15-year cumulative cost comparison chart directly comparing:
      1. Status Quo (Grid Only electricity invoice over 15 years, with inflation)
      2. With Solar PV (CAPEX in Year 0 + cumulative residual electricity + OPEX - surplus export)
    Highlights the exact Amortisation / Break-Even intersection point where solar becomes more profitable than grid-only.
    """
    fig = go.Figure()

    table = getattr(fin_metrics, "cash_flow_table", [])
    if not table:
        return fig

    years = [0] + [row["year"] for row in table]
    cum_sq = getattr(fin_metrics, "cumulative_status_quo", [])
    cum_pv = getattr(fin_metrics, "cumulative_with_pv", [])

    if not cum_sq or len(cum_sq) != len(years):
        cum_sq = [0.0] + [row.get("cum_status_quo", 0.0) for row in table]
    if not cum_pv or len(cum_pv) != len(years):
        cum_pv = [fin_metrics.total_capex] + [row.get("cum_with_pv", fin_metrics.total_capex) for row in table]

    # 1. Status Quo Cumulative Line (Grid Only)
    fig.add_trace(
        go.Scatter(
            x=years,
            y=cum_sq,
            mode="lines+markers",
            name="Status Quo (Grid Only / Ohne PV)",
            line=dict(color="#EF4444", width=3, dash="dash"),
            marker=dict(size=6, color="#EF4444"),
            hovertemplate="<b>Status Quo (Ohne PV)</b><br>Year %{x}: <b>%{y:,.0f} " + currency + "</b> total spent<extra></extra>"
        )
    )

    # 2. With Solar PV Cumulative Line (CAPEX + Residual + OPEX)
    fig.add_trace(
        go.Scatter(
            x=years,
            y=cum_pv,
            mode="lines+markers",
            name="Mit Solar PV (CAPEX + Reststrom + OPEX)",
            line=dict(color="#10B981", width=3.5),
            marker=dict(size=7, color="#10B981"),
            hovertemplate="<b>Mit Solar PV</b><br>Year %{x}: <b>%{y:,.0f} " + currency + "</b> total spent<extra></extra>"
        )
    )

    # 3. Payback / Amortisation Intersection Marker
    pb = getattr(fin_metrics, "payback_period_years", None)
    if pb is not None and pb <= len(years) - 1:
        fig.add_vline(
            x=pb,
            line_color="#F59E0B",
            line_width=2.5,
            line_dash="dot",
            annotation_text=f"🎯 Amortisation / Break-Even: {pb:.1f} Jahre",
            annotation_position="top left",
            annotation_font=dict(color="#F59E0B", size=12)
        )

    # Annotation of Total 15-Year Savings
    net_savings = getattr(fin_metrics, "total_lifetime_savings", 0.0)
    if net_savings > 0 and len(years) > 1:
        last_y = years[-1]
        fig.add_annotation(
            x=last_y,
            y=cum_pv[-1],
            text=f"<b>Net Savings: +{net_savings:,.0f} {currency}</b>",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#10B981",
            arrowsize=1,
            arrowwidth=2,
            ax=-80,
            ay=-40,
            bgcolor="rgba(16, 185, 129, 0.2)",
            bordercolor="#10B981",
            borderwidth=1,
            font=dict(color="#F8FAFC", size=11)
        )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>15-Year Cumulative Cost Trajectory & Amortisation Comparison ({currency})</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Operational Year",
            tickmode="linear",
            dtick=1,
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title=f"Cumulative Total Expenses ({currency})",
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
        margin=dict(l=40, r=20, t=55, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380
    )

    return fig


def create_annual_running_costs_comparison_figure(
    fin_metrics: Any,
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs a 15-year annual operating & electricity invoice comparison chart showing:
      - Status Quo Annual Electricity Bill (ohne PV)
      - Residual Electricity Bill (mit PV)
      - Annual PV OPEX / Maintenance (Wartung & Instandhaltung)
      - Annual Surplus Feed-in Revenue (Einspeiseerlös)
      - Net Annual Savings (Netto-Einsparung pro Jahr)
    """
    fig = go.Figure()

    table = getattr(fin_metrics, "cash_flow_table", [])
    if not table:
        return fig

    years = [f"Year {row['year']}" for row in table]
    sq_bills = [row.get("status_quo_bill", row.get("gross_savings", 0.0) * 1.5) for row in table]
    res_bills = [row.get("residual_bill", max(0.0, sq - row.get("gross_savings", 0.0))) for row, sq in zip(table, sq_bills)]
    opex_vals = [row.get("opex_annual", 0.0) for row in table]
    export_vals = [-row.get("export_revenue", 0.0) for row in table]
    net_savings = [row.get("net_cash_flow", 0.0) for row in table]

    # 1. Status Quo Annual Bill Bar
    fig.add_trace(
        go.Bar(
            x=years,
            y=sq_bills,
            name="Status Quo Stromrechnung (ohne PV)",
            marker_color="rgba(239, 68, 68, 0.65)",
            hovertemplate="%{x}<br>Status Quo Bill: <b>%{y:,.0f} " + currency + "</b><extra></extra>"
        )
    )

    # 2. Residual Grid Bill Bar
    fig.add_trace(
        go.Bar(
            x=years,
            y=res_bills,
            name="Reststromrechnung (mit PV)",
            marker_color="rgba(56, 189, 248, 0.75)",
            hovertemplate="%{x}<br>Residual Grid Bill: <b>%{y:,.0f} " + currency + "</b><extra></extra>"
        )
    )

    # 3. PV OPEX / Maintenance Bar
    fig.add_trace(
        go.Bar(
            x=years,
            y=opex_vals,
            name="PV-Wartung & OPEX (Instandhaltung)",
            marker_color="rgba(245, 158, 11, 0.8)",
            hovertemplate="%{x}<br>Annual PV OPEX: <b>%{y:,.0f} " + currency + "</b><extra></extra>"
        )
    )

    # 4. Net Annual Savings Line Overlay
    fig.add_trace(
        go.Scatter(
            x=years,
            y=net_savings,
            mode="lines+markers",
            name="Jährliche Netto-Ersparnis (Vorteil)",
            line=dict(color="#10B981", width=3),
            marker=dict(size=6, color="#10B981"),
            hovertemplate="%{x}<br>Net Annual Savings: <b>+%{y:,.0f} " + currency + "</b>/a<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>15-Year Annual Running Costs & Operating Expenses ({currency}/Year)</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        barmode="group",
        xaxis=dict(
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title=f"Annual Expense / Cost ({currency}/a)",
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
        margin=dict(l=40, r=20, t=55, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380
    )

    return fig



