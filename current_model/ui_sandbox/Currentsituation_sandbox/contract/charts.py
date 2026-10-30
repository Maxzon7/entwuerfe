"""
========================================================================================
Cost Structure & Financial Visualizer (current_model/ui/tab2_contract/charts.py)
========================================================================================

Description:
------------
Generates minimalist, professional Plotly dark-themed charts:
  1. Donut chart visualizing monthly cost distribution across all line item categories.
  2. Stacked Bar chart visualizing monthly payment timeseries across full duration.
"""

from typing import Optional, List, Dict, Any
import plotly.graph_objects as go
from current_model.models.financial import FinancialCostBreakdown, MonthlyPaymentRecord

COST_PALETTE: Dict[str, str] = {
    "Energy (Active)": "#38BDF8",       # Sky Blue
    "Capacity (Contracted)": "#F59E0B",  # Amber
    "Demand (Measured)": "#FB923C",      # Orange
    "Peak Penalty": "#EF4444",          # Red
    "Base Fee": "#8B5CF6",              # Violet
    "Network (Volume)": "#06B6D4",      # Cyan
    "Taxes & Levies": "#10B981",        # Emerald
    "Other": "#94A3B8"                  # Slate
}


def create_cost_donut_figure(breakdown: FinancialCostBreakdown) -> go.Figure:
    """
    Constructs a clean, modern Donut chart displaying monthly cost distribution across all line items.
    """
    is_synthetic_annual = (len(breakdown.monthly_series) == 12 and breakdown.duration_days <= 1.5)
    category_totals: Dict[str, float] = {}
    for item in breakdown.line_items:
        cat = item.category
        val = item.cost_monthly if (breakdown.duration_days > 35 or is_synthetic_annual) else item.cost_period
        if val > 0:
            category_totals[cat] = category_totals.get(cat, 0.0) + val

    labels = list(category_totals.keys())
    values = list(category_totals.values())
    colors = [COST_PALETTE.get(cat, COST_PALETTE["Other"]) for cat in labels]

    if not values:
        labels = ["No Cost Data"]
        values = [1.0]
        colors = ["#64748B"]

    currency = breakdown.currency

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.58,
                textinfo="percent",
                textposition="inside",
                insidetextorientation="horizontal",
                marker=dict(colors=colors, line=dict(color="#0B0F19", width=2)),
                hovertemplate=f"<b>%{{label}}</b><br>Amount: %{{value:,.2f}} {currency}<br>Share: %{{percent}}<extra></extra>"
            )
        ]
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Cost Component Distribution</b>",
            font=dict(size=14, color="#F8FAFC"),
            x=0.05,
            y=0.96
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.06,
            xanchor="center",
            x=0.5,
            font=dict(size=11)
        ),
        margin=dict(l=10, r=10, t=35, b=60),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=370
    )

    return fig



def create_monthly_payment_series_figure(
    breakdown: FinancialCostBreakdown,
    highlight_month: Optional[str] = None
) -> go.Figure:
    """
    Constructs an interactive stacked bar chart visualizing monthly payment timeseries across full duration.
    """
    fig = go.Figure()
    currency = breakdown.currency

    if not breakdown.monthly_series:
        fig.update_layout(
            template="plotly_dark",
            title="No monthly payment data available",
            plot_bgcolor="#0B0F19",
            paper_bgcolor="#0B0F19"
        )
        return fig

    months = [m.period_label for m in breakdown.monthly_series]
    energy_costs = [m.energy_cost_net for m in breakdown.monthly_series]
    capacity_costs = [m.capacity_cost_net for m in breakdown.monthly_series]
    penalty_costs = [m.penalty_cost_net for m in breakdown.monthly_series]
    base_fees = [m.base_fee_net for m in breakdown.monthly_series]
    taxes = [m.taxes_and_levies for m in breakdown.monthly_series]
    gross_totals = [m.total_gross for m in breakdown.monthly_series]

    # Stacked Bars
    fig.add_trace(
        go.Bar(
            x=months,
            y=energy_costs,
            name="Active Energy",
            marker_color=COST_PALETTE["Energy (Active)"],
            hovertemplate=f"<b>Active Energy</b>: %{{y:,.2f}} {currency}<extra></extra>"
        )
    )

    fig.add_trace(
        go.Bar(
            x=months,
            y=capacity_costs,
            name="Capacity Charge",
            marker_color=COST_PALETTE["Capacity (Contracted)"],
            hovertemplate=f"<b>Capacity</b>: %{{y:,.2f}} {currency}<extra></extra>"
        )
    )

    network_costs = [getattr(m, "network_cost_net", 0.0) for m in breakdown.monthly_series]
    if any(n > 0 for n in network_costs):
        fig.add_trace(
            go.Bar(
                x=months,
                y=network_costs,
                name="Network (Volume)",
                marker_color=COST_PALETTE["Network (Volume)"],
                hovertemplate=f"<b>Network Volume</b>: %{{y:,.2f}} {currency}<extra></extra>"
            )
        )

    if any(p > 0 for p in penalty_costs):
        fig.add_trace(
            go.Bar(
                x=months,
                y=penalty_costs,
                name="Peak Penalty",
                marker_color=COST_PALETTE["Peak Penalty"],
                hovertemplate=f"<b>Penalty</b>: %{{y:,.2f}} {currency}<extra></extra>"
            )
        )

    fig.add_trace(
        go.Bar(
            x=months,
            y=base_fees,
            name="Base Fee",
            marker_color=COST_PALETTE["Base Fee"],
            hovertemplate=f"<b>Base Fee</b>: %{{y:,.2f}} {currency}<extra></extra>"
        )
    )

    fig.add_trace(
        go.Bar(
            x=months,
            y=taxes,
            name="Taxes & Levies",
            marker_color=COST_PALETTE["Taxes & Levies"],
            hovertemplate=f"<b>Taxes</b>: %{{y:,.2f}} {currency}<extra></extra>"
        )
    )

    # Line trace for Total Gross Cost
    fig.add_trace(
        go.Scatter(
            x=months,
            y=gross_totals,
            mode="lines+markers",
            name="Total Gross Invoice",
            line=dict(color="#FFFFFF", width=2.5),
            marker=dict(size=6, color="#FFFFFF"),
            hovertemplate=f"<b>Total Gross</b>: %{{y:,.2f}} {currency}<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        barmode="stack",
        title=dict(
            text="<b>Monthly Payment Schedule across Duration</b>",
            font=dict(size=15, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Billing Period",
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title=f"Total Invoice Amount ({currency})",
            gridcolor="#1E293B",
            rangemode="tozero"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=40, r=20, t=60, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380
    )

    if highlight_month and highlight_month in months:
        fig.add_vrect(
            x0=months.index(highlight_month) - 0.4,
            x1=months.index(highlight_month) + 0.4,
            fillcolor="#38BDF8",
            opacity=0.15,
            line_width=2,
            line_color="#38BDF8",
            annotation_text=f"Selected: {highlight_month}",
            annotation_position="top left",
            annotation_font_color="#38BDF8"
        )

    return fig


def create_tou_schedule_diurnal_figure(
    load_series: Any = None,
    ht_start_hour: int = 7,
    ht_end_hour: int = 23,
    load: Any = None,
    ht_rate_label: Optional[str] = None,
    nt_rate_label: Optional[str] = None,
) -> go.Figure:
    """
    Constructs an interactive 24-hour diurnal profile chart displaying:
      1. Shaded Time-of-Use window bands: High Tariff (HT / Normaal: 07:00 - 23:00) vs Off-Peak (NT / Dal).
      2. Average Weekday demand curve (Monday - Friday).
      3. Average Weekend demand curve (Saturday - Sunday).
    """
    if load_series is None:
        load_series = load
    import numpy as np
    import pandas as pd

    fig = go.Figure()

    # Generate 96 quarter-hour points across the day [0.0 to 23.75]
    step_hours = np.linspace(0, 23.75, 96)
    time_labels = [f"{int(h):02d}:{int((h % 1) * 60):02d}" for h in step_hours]

    weekday_avg = np.zeros(96)
    weekend_avg = np.zeros(96)

    has_data = hasattr(load_series, "timestamps") and hasattr(load_series, "power_kw") and len(load_series.power_kw) == 35040
    if has_data:
        ts = load_series.timestamps
        p = load_series.power_kw
        # 0 = Monday, ..., 6 = Sunday
        is_weekday = ts.dayofweek < 5
        # Minute of day [0, 1440) -> step index [0, 96)
        minute_indices = (ts.hour * 60 + ts.minute) // 15

        df_steps = pd.DataFrame({
            "step": minute_indices,
            "is_weekday": is_weekday,
            "power": p
        })

        wk_grp = df_steps[df_steps["is_weekday"]].groupby("step")["power"].mean()
        we_grp = df_steps[~df_steps["is_weekday"]].groupby("step")["power"].mean()

        for idx in range(96):
            weekday_avg[idx] = wk_grp.get(idx, 0.0)
            weekend_avg[idx] = we_grp.get(idx, 0.0)
    else:
        # Indicative curve
        weekday_avg = 200.0 + 80.0 * np.sin(np.pi * (step_hours - 6) / 12).clip(0, 1)
        weekend_avg = 150.0 + 30.0 * np.sin(np.pi * (step_hours - 8) / 10).clip(0, 1)

    max_p = max(float(np.max(weekday_avg)), float(np.max(weekend_avg)), 10.0) * 1.15

    # 1. Shaded background for High Tariff (HT) window on Weekdays (07:00 to 23:00)
    fig.add_vrect(
        x0=f"{ht_start_hour:02d}:00",
        x1=f"{ht_end_hour:02d}:00",
        fillcolor="#0284C7",
        opacity=0.12,
        line_width=1,
        line_dash="dot",
        line_color="#38BDF8",
        annotation_text=f"Peak Hours (HT: {ht_start_hour:02d}:00 - {ht_end_hour:02d}:00){' | ' + ht_rate_label if ht_rate_label else ''}",
        annotation_position="top left",
        annotation_font=dict(color="#38BDF8", size=11)
    )

    # 2. Weekday Average Demand Trace
    wk_name = "Weekday Profile (Mo-Fr)"
    fig.add_trace(
        go.Scatter(
            x=time_labels,
            y=weekday_avg,
            mode="lines",
            name=wk_name,
            line=dict(color="#38BDF8", width=2.5),
            hovertemplate="<b>Weekday Avg</b>: %{y:.1f} kW<br>Time: %{x}<extra></extra>"
        )
    )

    # 3. Weekend Average Demand Trace
    we_name = f"Weekend Profile (Sa-Su Off-Peak{' | ' + nt_rate_label if nt_rate_label else ''})"
    fig.add_trace(
        go.Scatter(
            x=time_labels,
            y=weekend_avg,
            mode="lines",
            name="Weekend Profile (Sa-Su, Always Off-Peak / NT)",
            line=dict(color="#10B981", width=2.0, dash="dash"),
            hovertemplate="<b>Weekend Avg</b>: %{y:.1f} kW<br>Time: %{x}<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Diurnal 24-Hour Load Profile & Time-of-Use (TOU) Windows</b>",
            font=dict(size=15, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Time of Day (HH:MM)",
            gridcolor="#1E293B",
            tickmode="array",
            tickvals=[time_labels[i] for i in range(0, 96, 8)], # every 2 hours
            ticktext=[time_labels[i] for i in range(0, 96, 8)]
        ),
        yaxis=dict(
            title="Average Power Demand (kW)",
            gridcolor="#1E293B",
            range=[0, max_p]
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=40, r=20, t=60, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=350,
        hovermode="x unified"
    )

    return fig


def create_15_year_lifecycle_cost_figure(result: Any, start_year: int = 2025) -> go.Figure:
    """
    Constructs an executive-grade 15-year lifecycle cost projection figure:
      - Stacked bars for the 3 main cost parties: DSO Grid, Energy Supplier, Metering & Taxes.
      - Line trace for Discounted Present Value (PV @ WACC).
      - Secondary Y-axis line trace for Cumulative Lifetime Cashflow.
    """
    horizon = int(getattr(result.config, "evaluation_horizon_years", 15))
    g = float(getattr(result.config, "energy_escalation_pct", 3.0)) / 100.0
    r = float(getattr(result.config, "discount_rate_pct", 5.0)) / 100.0

    years = [start_year + i for i in range(horizon)]
    year_labels = [f"Yr {i+1} ({start_year + i})" for i in range(horizon)]

    base_dso = float(getattr(result, "total_dso_net", 0.0))
    base_supp = float(getattr(result, "total_supplier_net", 0.0))
    base_meter_taxes = float(getattr(result, "total_metering_net", 0.0)) + float(getattr(result, "total_levies_net", 0.0))

    dso_series: List[float] = []
    supp_series: List[float] = []
    meter_taxes_series: List[float] = []
    total_series: List[float] = []
    pv_series: List[float] = []
    cumulative_series: List[float] = []
    cum_sum = 0.0

    for i in range(horizon):
        esc = (1.0 + g) ** i
        df = 1.0 / ((1.0 + r) ** (i + 1))

        dso_val = round(base_dso * esc, 2)
        supp_val = round(base_supp * esc, 2)
        met_val = round(base_meter_taxes * esc, 2)
        tot_val = round(dso_val + supp_val + met_val, 2)
        pv_val = round(tot_val * df, 2)

        cum_sum += tot_val

        dso_series.append(dso_val)
        supp_series.append(supp_val)
        meter_taxes_series.append(met_val)
        total_series.append(tot_val)
        pv_series.append(pv_val)
        cumulative_series.append(round(cum_sum, 2))

    fig = go.Figure()
    currency = getattr(result.config, "currency_code", "EUR") if hasattr(result, "config") else "EUR"

    # 1. Stacked Bars: DSO Grid
    fig.add_trace(
        go.Bar(
            x=year_labels,
            y=dso_series,
            name="Pillar 2: Grid Network (DSO)",
            marker=dict(color="#F59E0B"),
            hovertemplate=f"<b>Grid Network (DSO)</b>: {currency} %{{y:,.2f}}<extra></extra>"
        )
    )

    # 2. Stacked Bars: Energy Supplier
    fig.add_trace(
        go.Bar(
            x=year_labels,
            y=supp_series,
            name="Pillar 1: Energy Supply (Retailer)",
            marker=dict(color="#38BDF8"),
            hovertemplate=f"<b>Energy Supply (Retailer)</b>: {currency} %{{y:,.2f}}<extra></extra>"
        )
    )

    # 3. Stacked Bars: Metering & Taxes
    fig.add_trace(
        go.Bar(
            x=year_labels,
            y=meter_taxes_series,
            name="Pillars 3 & 4: Metering & Statutory Taxes",
            marker=dict(color="#10B981"),
            hovertemplate=f"<b>Metering & Taxes</b>: {currency} %{{y:,.2f}}<extra></extra>"
        )
    )

    # 4. Present Value Curve (Discounted Cashflow)
    fig.add_trace(
        go.Scatter(
            x=year_labels,
            y=pv_series,
            name=f"Discounted PV (@ {r*100:.1f}% WACC)",
            mode="lines+markers",
            line=dict(color="#A78BFA", width=3, dash="dot"),
            marker=dict(size=7, color="#A78BFA"),
            hovertemplate=f"<b>Present Value (PV)</b>: {currency} %{{y:,.2f}}<extra></extra>"
        )
    )

    # 5. Cumulative Lifetime Expenditure (Secondary Y-Axis)
    fig.add_trace(
        go.Scatter(
            x=year_labels,
            y=cumulative_series,
            name="Cumulative Total Spend (Nominal)",
            mode="lines+markers",
            line=dict(color="#F43F5E", width=2.5),
            marker=dict(size=6, color="#F43F5E"),
            yaxis="y2",
            hovertemplate=f"<b>Cumulative 15y Spend</b>: {currency} %{{y:,.2f}}<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>15-Year Long-Term Cost Structure & Lifecycle Projection ({years[0]} – {years[-1]})</b>",
            font=dict(size=15, color="#F8FAFC")
        ),
        barmode="stack",
        xaxis=dict(
            title="Projection Year",
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title=f"Annual Expenditure ({currency} / year)",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        yaxis2=dict(
            title=dict(
                text=f"Cumulative 15-Year Spend ({currency})",
                font=dict(color="#F43F5E")
            ),
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False,
            tickfont=dict(color="#F43F5E")
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        ),
        margin=dict(l=50, r=60, t=80, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=450,
        hovermode="x unified"
    )

    return fig


def create_supplier_benchmark_figure(benchmark_costs: Dict[str, float], currency: str = "EUR") -> go.Figure:
    """
    Constructs a clean horizontal bar chart benchmarking pure supplier costs across the 3 core models:
    - Fixed Dual Rate (HT/NT)
    - Fixed Single Rate (24/7 Flat)
    - Dynamic Day-Ahead (EPEX Spot NL)
    """
    fig = go.Figure()

    model_names = list(benchmark_costs.keys())
    costs = [benchmark_costs[k] for k in model_names]

    # Palette: Fixed Dual -> #38BDF8 (Sky), Fixed Single -> #818CF8 (Indigo), Dynamic -> #34D399 (Emerald)
    colors = ["#38BDF8", "#818CF8", "#34D399"][:len(model_names)]

    fig.add_trace(
        go.Bar(
            y=model_names,
            x=costs,
            orientation="h",
            marker=dict(
                color=colors,
                line=dict(color="#1E293B", width=1.5),
            ),
            text=[f"{currency} {c:,.2f}" for c in costs],
            textposition="auto",
            hovertemplate=f"<b>%{{y}}</b><br>Net Supplier Cost: {currency} %{{x:,.2f}}<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Pure Supplier Cost Benchmark (3 Pricing Models)</b>",
            font=dict(size=14, color="#F8FAFC"),
            x=0.02,
            y=0.95
        ),
        xaxis=dict(
            title=f"Total Supplier Cost (Net {currency})",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=12)
        ),
        margin=dict(l=20, r=20, t=45, b=35),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=260,
    )

    return fig


def create_dynamic_price_consumption_figure(
    timestamps: Any,
    power_kw: Any,
    spot_prices_eur_mwh: Any,
    title_suffix: str = "",
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs a dual-axis interactive Plotly chart correlating electricity demand (kW)
    on the primary axis with synchronous EPEX Spot Day-Ahead prices ({currency}/MWh) on the secondary axis.
    """
    fig = go.Figure()

    # 1. Primary Y-Axis: Power Consumption (kW)
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=power_kw,
            name="Electricity Demand (kW)",
            mode="lines",
            line=dict(color="#38BDF8", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(56, 189, 248, 0.12)",
            hovertemplate="<b>Demand</b>: %{y:,.1f} kW<extra></extra>"
        )
    )

    # 2. Secondary Y-Axis: EPEX Spot Price ({currency}/MWh)
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=spot_prices_eur_mwh,
            name=f"EPEX Spot Price ({currency}/MWh)",
            mode="lines",
            line=dict(color="#F59E0B", width=1.5),
            yaxis="y2",
            hovertemplate=f"<b>Spot Price</b>: {currency} %{{y:,.2f}}/MWh<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>Dynamic Correlation: Power Demand (kW) vs. EPEX Spot Price ({currency}/MWh)</b> {title_suffix}",
            font=dict(size=14, color="#F8FAFC"),
            x=0.02,
            y=0.96
        ),
        xaxis=dict(
            title="Date / Time (Europe/Amsterdam)",
            gridcolor="#1E293B",
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            title=dict(text="Load Demand (kW)", font=dict(color="#38BDF8")),
            gridcolor="#1E293B",
            zerolinecolor="#334155",
            tickfont=dict(color="#38BDF8")
        ),
        yaxis2=dict(
            title=dict(text=f"EPEX Spot Price ({currency}/MWh)", font=dict(color="#F59E0B")),
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=True,
            zerolinecolor="#EF4444",
            tickfont=dict(color="#F59E0B")
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        ),
        margin=dict(l=40, r=50, t=55, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=320,
        hovermode="x unified"
    )

    return fig


def create_dso_monthly_peak_figure(
    dso_monthly_results: List[Any],
    contracted_capacity_kw: float
) -> go.Figure:
    """
    Constructs a monthly peak demand bar chart comparing actual 15-minute monthly peak
    demands (kW) against the contracted reserved grid capacity (kW), highlighting breach months in red.
    """
    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]

    peaks = []
    colors = []
    custom_hover = []

    for idx, r in enumerate(dso_monthly_results):
        p_val = getattr(r, "measured_peak_demand_kw", getattr(r, "peak_demand_kw", 0.0))
        is_breach = getattr(r, "is_capacity_breached", p_val > (contracted_capacity_kw + 1e-4))
        peaks.append(p_val)
        m_name = month_names[idx] if idx < len(month_names) else f"M{idx+1}"

        if is_breach:
            colors.append("#EF4444")  # Red for overload
            excess = p_val - contracted_capacity_kw
            custom_hover.append(f"{m_name}<br>Peak: {p_val:,.1f} kW<br>Status: Capacity Breach (+{excess:,.1f} kW)")
        else:
            colors.append("#38BDF8")  # Sky Blue for normal
            margin = contracted_capacity_kw - p_val
            custom_hover.append(f"{m_name}<br>Peak: {p_val:,.1f} kW<br>Status: Within Limit (Headroom: {margin:,.1f} kW)")

    fig = go.Figure()

    # 1. Bar Trace: Monthly Peak Demands
    fig.add_trace(
        go.Bar(
            x=month_names[:len(peaks)],
            y=peaks,
            name="Monthly Peak (kW)",
            marker_color=colors,
            hoverinfo="text",
            hovertext=custom_hover,
            opacity=0.9
        )
    )

    # 2. Horizontal Reference Line: Reserved Grid Capacity
    fig.add_trace(
        go.Scatter(
            x=month_names[:len(peaks)],
            y=[contracted_capacity_kw] * len(peaks),
            mode="lines",
            name=f"Contracted Capacity ({contracted_capacity_kw:,.0f} kW)",
            line=dict(color="#F59E0B", width=2.5, dash="dash"),
            hoverinfo="skip"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Monthly Peak Demand vs. Reserved Grid Capacity</b>",
            font=dict(size=14, color="#F8FAFC"),
            x=0.02,
            y=0.96
        ),
        xaxis=dict(
            title="Billing Month",
            gridcolor="#1E293B",
        ),
        yaxis=dict(
            title="Peak Power (kW)",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        ),
        margin=dict(l=40, r=30, t=55, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=320,
        hovermode="closest"
    )

    return fig



