"""
========================================================================================
Monthly Baseline & Commercial Tariff Charts & Visualizations
(current_model/ui_sandbox/monthly_charts.py)
========================================================================================

Description:
------------
Plotly interactive chart builders for the 12-Month Baseline & Commercial Tariff Lab.
- Stacked monthly billing ledger (Energy TOU tiers, Capacity, Demand, Base fee, Penalties).
- Monthly energy consumption volume distribution (kWh by TOU window).
- Peak demand vs. contracted capacity envelope ($P_{max}$ vs. $P_{contract}$).
========================================================================================
"""

from typing import List
import plotly.graph_objects as go

# Safe imports
try:
    from current_model.ui_sandbox.monthly_presets import TOUTierConfig
    from current_model.ui_sandbox.monthly_calc import AnnualBillingSummary
except ImportError:
    from monthly_presets import TOUTierConfig
    from monthly_calc import AnnualBillingSummary


def create_monthly_billing_breakdown_chart(
    summary: AnnualBillingSummary,
    active_tiers: List[TOUTierConfig]
) -> go.Figure:
    """
    Constructs an interactive Plotly stacked bar chart showing itemized monthly electricity costs
    (Energy per TOU tier, Contracted Capacity fee, Base & Exempt fees, Peak Demand, Penalties).
    """
    months_list = [r.month_name for r in summary.monthly_results]
    fig = go.Figure()

    # 1. Add Energy Volume Cost for each TOU Tier
    for tier in active_tiers:
        tier_costs = [r.cost_energy_by_tier_eur.get(tier.id, 0.0) for r in summary.monthly_results]
        fig.add_trace(go.Bar(
            x=months_list,
            y=tier_costs,
            name=f"Energy: {tier.name}",
            marker_color=tier.color,
            hovertemplate=f"<b>%{{x}}</b><br>{tier.name}: € %{{y:,.2f}}<extra></extra>"
        ))

    # 2. Add Contracted Capacity Fee
    if summary.cost_contracted_capacity_annual_eur > 0:
        fig.add_trace(go.Bar(
            x=months_list,
            y=[r.cost_contracted_capacity_eur for r in summary.monthly_results],
            name="Contracted Capacity Fee",
            marker_color="#10B981",
            hovertemplate="<b>%{x}</b><br>Contracted Capacity Fee: € %{y:,.2f}<extra></extra>"
        ))

    # 3. Add Base & Exempt Standing Fees
    if (summary.cost_base_fee_annual_eur + summary.cost_exempt_surcharge_annual_eur) > 0:
        fig.add_trace(go.Bar(
            x=months_list,
            y=[r.cost_base_fee_eur + r.cost_exempt_surcharge_eur for r in summary.monthly_results],
            name="Base Fee & Surcharges",
            marker_color="#06B6D4",
            hovertemplate="<b>%{x}</b><br>Base & Standing Fees: € %{y:,.2f}<extra></extra>"
        ))

    # 4. Add Measured Demand Charges if applicable
    if summary.cost_measured_demand_annual_eur > 0:
        fig.add_trace(go.Bar(
            x=months_list,
            y=[r.cost_measured_demand_eur for r in summary.monthly_results],
            name="Measured Peak Demand Fee",
            marker_color="#8B5CF6",
            hovertemplate="<b>%{x}</b><br>Peak Demand Fee: € %{y:,.2f}<extra></extra>"
        ))

    # 5. Add Exceedance Penalties if applicable
    if summary.cost_penalty_annual_eur > 0:
        fig.add_trace(go.Bar(
            x=months_list,
            y=[r.cost_penalty_eur for r in summary.monthly_results],
            name="Exceedance Penalties",
            marker_color="#DC2626",
            hovertemplate="<b>%{x}</b><br>Exceedance Penalty: € %{y:,.2f}<extra></extra>"
        ))

    # 6. Add Meetbedrijf Metering Fee if applicable
    if summary.cost_metering_annual_eur > 0:
        fig.add_trace(go.Bar(
            x=months_list,
            y=[r.cost_metering_eur for r in summary.monthly_results],
            name="Meetbedrijf Meter Fee",
            marker_color="#D946EF",
            hovertemplate="<b>%{x}</b><br>Meetbedrijf Meter Fee: € %{y:,.2f}<extra></extra>"
        ))

    fig.update_layout(
        barmode="stack",
        height=390,
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title=None),
        yaxis=dict(title="Monthly Cost (€)", tickprefix="€ "),
        template="plotly_white"
    )

    return fig


def create_monthly_energy_volume_chart(
    summary: AnnualBillingSummary,
    active_tiers: List[TOUTierConfig]
) -> go.Figure:
    """
    Constructs an interactive Plotly stacked bar chart showing energy consumption volumes (kWh)
    across all 12 calendar months split by Time-of-Use window.
    """
    months_list = [r.month_name for r in summary.monthly_results]
    fig = go.Figure()

    for tier in active_tiers:
        tier_kwh = [r.kwh_by_tier.get(tier.id, 0.0) for r in summary.monthly_results]
        fig.add_trace(go.Bar(
            x=months_list,
            y=tier_kwh,
            name=f"{tier.name}",
            marker_color=tier.color,
            hovertemplate=f"<b>%{{x}}</b><br>{tier.name}: %{{y:,.0f}} kWh<extra></extra>"
        ))

    fig.update_layout(
        barmode="stack",
        height=320,
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title=None),
        yaxis=dict(title="Energy Volume (kWh)", ticksuf=" kWh"),
        template="plotly_white"
    )

    return fig
