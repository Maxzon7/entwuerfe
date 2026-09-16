"""
========================================================================================
BESS Financial Visualizations & Plotly Chart Constructors (ui/tab4_bess/financial_charts.py)
========================================================================================

Description:
------------
Generates dark-themed, high-contrast Plotly figures for Sub-Tab 4.2 (Financial Viability):
  1. 15-Year Cumulative Cash Flow & Amortisation Payback Curve.
  2. Annual Electricity Cost Breakdown Comparison (Status Quo vs. With BESS).
  3. 15-Year Cumulative Life-Cycle Expenditure Trajectory (Status Quo vs. With BESS).
  4. Turn-Key CAPEX Sizing & Component Donut Chart.
  5. Multi-Parameter Investment Sensitivity Tornado / Comparison Bar Chart.
"""

from typing import List, Dict, Any, Optional
import numpy as np
import plotly.graph_objects as go

from current_model.models.bess import BESSFinancialMetrics


def create_bess_cashflow_payback_figure(
    fin_metrics: BESSFinancialMetrics,
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs a 15-year cumulative cash flow curve starting from -CAPEX,
    identifying the exact break-even amortization year.
    """
    fig = go.Figure()

    years = list(range(len(fin_metrics.cumulative_cash_flow)))
    cum_cf = fin_metrics.cumulative_cash_flow
    total_capex = fin_metrics.total_capex

    # 1. Negative Cash Flow Area (Payback / Recovery Phase)
    neg_cf = [min(0.0, v) for v in cum_cf]
    fig.add_trace(
        go.Scatter(
            x=years,
            y=neg_cf,
            name="CAPEX Recovery Phase",
            fill="tozeroy",
            fillcolor="rgba(239, 68, 68, 0.18)",
            line=dict(color="#EF4444", width=2.0),
            hovertemplate="<b>Year %{x}:</b> Outstanding Investment: <b>%{y:,.0f} " + currency + "</b><extra></extra>"
        )
    )

    # 2. Positive Cash Flow Area (Net Profit Accumulation)
    pos_cf = [max(0.0, v) for v in cum_cf]
    fig.add_trace(
        go.Scatter(
            x=years,
            y=pos_cf,
            name="Cumulative Net Profit",
            fill="tozeroy",
            fillcolor="rgba(16, 185, 129, 0.25)",
            line=dict(color="#10B981", width=2.5),
            hovertemplate="<b>Year %{x}:</b> Cumulative Net Profit: <b>+%{y:,.0f} " + currency + "</b><extra></extra>"
        )
    )

    # Break-even reference line (0.0)
    fig.add_hline(
        y=0.0,
        line_dash="dash",
        line_color="#94A3B8",
        line_width=1.5,
        annotation_text="Break-Even Threshold (0 €)",
        annotation_position="bottom left",
        annotation_font=dict(color="#CBD5E1", size=10)
    )

    # Highlight Payback Year Marker
    pb_year = fin_metrics.simple_payback_years
    if pb_year is not None and pb_year <= (len(years) - 1):
        fig.add_vline(
            x=pb_year,
            line_dash="dot",
            line_color="#F59E0B",
            line_width=2.0,
            annotation_text=f"Amortization: {pb_year:.1f} Years",
            annotation_position="top left",
            annotation_font=dict(color="#FDE68A", size=11, weight="bold")
        )

    pb_disp = f"{pb_year:.1f} Years" if pb_year is not None else ">15 Years"

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>15-Year BESS Cumulative Cash Flow & Amortization Trajectory</b><br>"
                 f"<span style='font-size:11px; color:#94A3B8;'>Initial CAPEX: {total_capex:,.0f} {currency} | Simple Payback: {pb_disp} | 15Y NPV: {fin_metrics.net_present_value:,.0f} {currency}</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Operating Year",
            tickmode="linear",
            tick0=0,
            dtick=1,
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title=f"Cumulative Cash Flow ({currency})",
            gridcolor="#1E293B",
            zerolinecolor="#475569"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11)
        ),
        margin=dict(l=20, r=20, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380
    )

    return fig


def create_bess_annual_cost_comparison_figure(
    fin_metrics: BESSFinancialMetrics,
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs a stacked bar comparison of Annual Electricity & Operating Costs:
    Status Quo (No BESS) vs With BESS Peak Shaving.
    """
    fig = go.Figure()

    categories = ["Status Quo (No BESS)", "With BESS Peak Shaving"]

    # Component values
    demand_sq = fin_metrics.annual_demand_charge_savings + fin_metrics.annual_penalty_savings
    demand_wb = 0.0  # Residual demand charge
    energy_sq = fin_metrics.annual_energy_savings + 1000.0  # Normalized base
    energy_wb = 1000.0
    opex_wb = fin_metrics.annual_opex_year1

    # Stacked Trace 1: Demand & Capacity Charges
    fig.add_trace(
        go.Bar(
            name="Peak Capacity & Overload Charges",
            x=categories,
            y=[fin_metrics.annual_demand_charge_savings + fin_metrics.annual_penalty_savings, 0.0],
            marker_color="#EF4444",
            hovertemplate="<b>%{x}</b><br>Capacity / Penalty Cost: <b>%{y:,.0f} " + currency + "</b><extra></extra>"
        )
    )

    # Stacked Trace 2: Active Energy Charges
    fig.add_trace(
        go.Bar(
            name="Active Energy Import",
            x=categories,
            y=[fin_metrics.annual_energy_savings + 500.0, 500.0],
            marker_color="#38BDF8",
            hovertemplate="<b>%{x}</b><br>Active Energy Cost: <b>%{y:,.0f} " + currency + "</b><extra></extra>"
        )
    )

    # Stacked Trace 3: BESS Annual O&M
    fig.add_trace(
        go.Bar(
            name="BESS Maintenance & O&M",
            x=categories,
            y=[0.0, opex_wb],
            marker_color="#F59E0B",
            hovertemplate="<b>%{x}</b><br>Annual BESS O&M: <b>%{y:,.0f} " + currency + "</b><extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        barmode="stack",
        title=dict(
            text=f"<b>Annual Electricity & Operational Cost Breakdown (Year 1)</b><br>"
                 f"<span style='font-size:11px; color:#94A3B8;'>Gross Bill Savings: {fin_metrics.annual_gross_savings:,.0f} {currency}/yr | Net Annual Benefit: {fin_metrics.annual_net_savings_year1:,.0f} {currency}/yr</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(
            title=f"Annual Expenditure ({currency}/Year)",
            gridcolor="#1E293B"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11)
        ),
        margin=dict(l=20, r=20, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig


def create_bess_cumulative_cost_trajectory_figure(
    fin_metrics: BESSFinancialMetrics,
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs a 15-year cumulative expenditure trajectory comparing
    Status Quo grid expenditure vs With-BESS investment + operational costs.
    """
    fig = go.Figure()

    years = list(range(len(fin_metrics.cumulative_status_quo)))

    # Trace 1: Status Quo Cumulative Grid Bill
    fig.add_trace(
        go.Scatter(
            x=years,
            y=fin_metrics.cumulative_status_quo,
            name="Status Quo Cumulative Spend (Utility Bills)",
            mode="lines+markers",
            line=dict(color="#EF4444", width=2.5),
            marker=dict(size=4),
            hovertemplate="<b>Year %{x} Status Quo:</b> <b>%{y:,.0f} " + currency + "</b><extra></extra>"
        )
    )

    # Trace 2: With BESS (CAPEX + O&M + Residual Bills)
    fig.add_trace(
        go.Scatter(
            x=years,
            y=fin_metrics.cumulative_with_bess,
            name="With BESS Cumulative Spend (CAPEX + OPEX + Grid)",
            mode="lines+markers",
            line=dict(color="#10B981", width=2.5),
            marker=dict(size=4),
            hovertemplate="<b>Year %{x} With BESS:</b> <b>%{y:,.0f} " + currency + "</b><extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>15-Year Life-Cycle Total Cost Trajectory (Status Quo vs. With BESS)</b><br>"
                 f"<span style='font-size:11px; color:#94A3B8;'>Crossover point marks when cumulative savings exceed the upfront storage investment</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Operating Year",
            tickmode="linear",
            tick0=0,
            dtick=1,
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title=f"Cumulative Total Cost ({currency})",
            gridcolor="#1E293B"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11)
        ),
        margin=dict(l=20, r=20, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig


def create_bess_capex_donut_figure(
    capex_dict: Dict[str, float],
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs a modern Donut chart of Turn-Key BESS CAPEX components.
    """
    labels = [
        "Battery Cell Modules & Racks",
        "Power Conversion System (Inverter/PCS)",
        "Balance of System (BOS / HVAC / Enclosure)",
        "Electrical Installation & Grid Interconnection"
    ]
    values = [
        capex_dict.get("capex_cells_modules", 0.0),
        capex_dict.get("capex_inverter_pcs", 0.0),
        capex_dict.get("capex_bos_enclosure", 0.0),
        capex_dict.get("capex_installation_grid", 0.0)
    ]
    colors = ["#3B82F6", "#10B981", "#F59E0B", "#8B5CF6"]

    total_val = capex_dict.get("total_capex", sum(values))

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(colors=colors),
                textinfo="percent+label",
                textposition="outside",
                hovertemplate="<b>%{label}</b><br>Share: <b>%{percent}</b><br>Amount: <b>%{value:,.0f} " + currency + "</b><extra></extra>"
            )
        ]
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>Turn-Key BESS CAPEX Sizing Breakdown</b><br>"
                 f"<span style='font-size:11px; color:#94A3B8;'>Total Turn-Key Investment: {total_val:,.0f} {currency} ({capex_dict.get('capex_per_kwh', 0):,.1f} {currency}/kWh)</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        annotations=[
            dict(
                text=f"<b>{total_val:,.0f}</b><br><span style='font-size:10px; color:#94A3B8;'>{currency} CAPEX</span>",
                x=0.5, y=0.5,
                font_size=13,
                showarrow=False,
                font_color="#F8FAFC"
            )
        ],
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5,
            font=dict(size=10)
        ),
        margin=dict(l=20, r=20, t=55, b=60),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig


def create_bess_sensitivity_figure(
    sensitivity_rows: List[Dict[str, Any]],
    metric: str = "payback_years"
) -> go.Figure:
    """
    Constructs a parameter sensitivity chart comparing changes in Payback Period across ±20% variation in parameters.
    """
    fig = go.Figure()

    params = list(set(r["parameter"] for r in sensitivity_rows))
    colors = ["#38BDF8", "#F59E0B", "#10B981", "#EC4899"]

    for idx, p_name in enumerate(params):
        p_rows = [r for r in sensitivity_rows if r["parameter"] == p_name]
        p_rows.sort(key=lambda r: r["variation_val"])
        x_labels = [r["variation_pct"] for r in p_rows]
        y_vals = [r.get(metric, 0.0) for r in p_rows]

        fig.add_trace(
            go.Bar(
                name=p_name,
                x=x_labels,
                y=y_vals,
                marker_color=colors[idx % len(colors)],
                hovertemplate="<b>%{x} Variation:</b> " + p_name + "<br>Payback: <b>%{y:.1f} Years</b><extra></extra>"
            )
        )

    fig.update_layout(
        template="plotly_dark",
        barmode="group",
        title=dict(
            text="<b>Investment Sensitivity: Simple Payback Period vs. Parameter Variations</b><br>"
                 "<span style='font-size:11px; color:#94A3B8;'>Impact of ±10% and ±20% shifts in CAPEX and Peak Demand Tariffs</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Parameter Shift / Variation",
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="Simple Payback (Years)",
            gridcolor="#1E293B"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11)
        ),
        margin=dict(l=20, r=20, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig
