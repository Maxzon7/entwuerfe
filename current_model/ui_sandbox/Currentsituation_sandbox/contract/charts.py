"""
========================================================================================
Cost Structure & Financial Visualizer (current_model/ui/tab2_contract/charts.py)
========================================================================================

Description:
------------
Generates minimalist, professional Plotly dark-themed charts:
  1. Donut chart visualizing monthly cost distribution across all line item categories.
  2. Stacked Bar chart visualizing monthly payment timeseries (Zahlungsreihe) across full duration.
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
            text="<b>Monthly Payment Schedule across Duration (Zahlungsreihe)</b>",
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
    load_series: Any,
    ht_start_hour: int = 7,
    ht_end_hour: int = 23,
) -> go.Figure:
    """
    Constructs an interactive 24-hour diurnal profile chart displaying:
      1. Shaded Time-of-Use window bands: High Tariff (HT / Normaal: 07:00 - 23:00) vs Off-Peak (NT / Dal).
      2. Average Weekday demand curve (Monday - Friday).
      3. Average Weekend demand curve (Saturday - Sunday).
    """
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
        annotation_text="High Tariff (HT / Normaal Window: Mo-Fr 07:00 - 23:00)",
        annotation_position="top left",
        annotation_font=dict(color="#38BDF8", size=11)
    )

    # 2. Weekday Average Demand Trace
    fig.add_trace(
        go.Scatter(
            x=time_labels,
            y=weekday_avg,
            mode="lines",
            name="Weekday Profile (Mo-Fr)",
            line=dict(color="#38BDF8", width=2.5),
            hovertemplate="<b>Weekday Avg</b>: %{y:.1f} kW<br>Time: %{x}<extra></extra>"
        )
    )

    # 3. Weekend Average Demand Trace
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

