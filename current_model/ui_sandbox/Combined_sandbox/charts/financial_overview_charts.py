"""
Interactive Plotly visualizations for 4-pillar cost comparisons, 15-year TCO trajectories,
annual cost waterfall bridges, monthly cashflows, and 12-month grid bill progression.
"""

from typing import List
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..combined_sandbox_engine import CombinedSimulationResult

def create_financial_cost_comparison_figure(
    sim_res: CombinedSimulationResult,
) -> go.Figure:
    """
    Creates the Side-by-Side Annual Cost Comparison Bar Chart for Sub-Tab 6 (Financials),
    comparing `Current situation (Without System)` vs. `Combined system (With System)`
    across the 4 Tariff Pillars and System Operations (O&M, Fuel, Rental).
    """
    fk = sim_res.financial_kpis
    scenarios = ["Current situation (Without System)", "Combined system (With System)"]

    if fk is None:
        return go.Figure()

    p1_vals = [fk.baseline_pillar1_supply_eur, fk.combined_pillar1_supply_eur]
    p2_net_vals = [
        max(0.0, fk.baseline_pillar2_dso_eur - fk.baseline_penalty_cost_eur),
        max(0.0, fk.combined_pillar2_dso_eur - fk.combined_grid_penalty_cost_eur),
    ]
    pen_vals = [fk.baseline_penalty_cost_eur, fk.combined_grid_penalty_cost_eur]
    p3_vals = [fk.baseline_pillar3_metering_eur, fk.combined_pillar3_metering_eur]
    p4_vals = [fk.baseline_pillar4_taxes_eur, fk.combined_pillar4_taxes_eur]
    sys_opex_vals = [
        0.0,
        fk.solar_om_eur + fk.battery_om_eur + fk.generator_total_opex_eur,
    ]

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            name="Pillar 1: Energy Supply",
            x=scenarios,
            y=p1_vals,
            marker_color="#3B82F6",
            hovertemplate="%{x}<br>Energy Supply: €%{y:,.0f}/yr<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Pillar 2: Grid Network (DSO)",
            x=scenarios,
            y=p2_net_vals,
            marker_color="#0EA5E9",
            hovertemplate="%{x}<br>Grid Network (DSO): €%{y:,.0f}/yr<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Pillar 2: Overload Penalties",
            x=scenarios,
            y=pen_vals,
            marker_color="#EF4444",
            hovertemplate="%{x}<br>Overload Penalties: €%{y:,.0f}/yr<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Pillar 3: Metering",
            x=scenarios,
            y=p3_vals,
            marker_color="#A855F7",
            hovertemplate="%{x}<br>Metering: €%{y:,.0f}/yr<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Pillar 4: Taxes & Levies",
            x=scenarios,
            y=p4_vals,
            marker_color="#F59E0B",
            hovertemplate="%{x}<br>Taxes & Levies: €%{y:,.0f}/yr<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="System O&M, Fuel & Rental",
            x=scenarios,
            y=sys_opex_vals,
            marker_color="#10B981",
            hovertemplate="%{x}<br>System O&M, Fuel & Rental: €%{y:,.0f}/yr<extra></extra>",
        )
    )

    fig.update_layout(
        barmode="stack",
        template="plotly_dark",
        height=420,
        margin=dict(l=55, r=25, t=75, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text="Annual Cost Comparison: Current situation vs. Combined system (€/year)",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        yaxis=dict(
            title="Annual Cost (€/year)",
            gridcolor="rgba(148, 163, 184, 0.12)",
            rangemode="tozero",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        hovermode="x unified",
    )

    return fig


def create_financial_tco_trajectory_figure(
    sim_res: CombinedSimulationResult,
) -> go.Figure:
    """
    Creates the synchronized 2-panel 15-Year Amortization & Annual Cashflow figure:
      - Row 1: Cumulative Net Cashflow (starts at -CAPEX, dips on Repowering, crosses 0 at Break-Even)
      - Row 2: Annual Current System Bill vs. Combined System Annual OPEX & Annual Net Cashflow bars
    """
    df = sim_res.cashflow_15y_df
    fk = sim_res.financial_kpis
    if df.empty or fk is None:
        return go.Figure()

    curr = str(getattr(fk, "currency_code", "EUR") or "EUR")
    curr_sym = "€" if curr == "EUR" else (f"{curr} " if curr == "ARS" else "$")

    years = df["Year"].tolist()
    cum_cf = df["Cumulative Cashflow (€)"].tolist()
    base_bill = df["Current situation Bill (€)"].tolist()
    comb_opex = df["Combined System OPEX (€)"].tolist()
    net_cf = df["Net Cashflow (€)"].tolist()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.14,
        row_heights=[0.52, 0.48],
        subplot_titles=(
            f"1. Amortization Trajectory — Cumulative Net Cashflow ({curr})",
            f"2. Annual Costs vs. Current System & Net Cashflow ({curr}/yr)",
        ),
    )

    # Row 1: Cumulative Net Cashflow & Break-Even Amortization
    fig.add_hline(
        y=0,
        row=1,
        col=1,
        line_color="rgba(248, 250, 252, 0.55)",
        line_width=1.2,
        line_dash="dot",
    )
    fig.add_trace(
        go.Scatter(
            x=years,
            y=cum_cf,
            mode="lines+markers",
            name=f"Cumulative Net Cashflow ({curr})",
            line=dict(color="#38BDF8", width=2.8),
            fill="tozeroy",
            fillcolor="rgba(56, 189, 248, 0.14)",
            hovertemplate=f"Year %{{x}}<br>Cumulative Cashflow: {curr_sym}%{{y:,.0f}}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    if fk.payback_years is not None and 0.0 < fk.payback_years <= 15.0:
        fig.add_vline(
            x=fk.payback_years,
            row=1,
            col=1,
            line_dash="dot",
            line_color="#22C55E",
            line_width=1.8,
            annotation_text=f"Break-Even: {fk.payback_years:.1f} yrs",
            annotation_position="top left",
            annotation_font=dict(color="#22C55E", size=11),
        )
    elif fk.total_capex_eur > 0.0:
        fig.add_annotation(
            x=0.99,
            y=0.06,
            xref="x domain",
            yref="y domain",
            text="No Break-Even within 15 yrs",
            showarrow=False,
            font=dict(color="#F87171", size=11),
            xanchor="right",
        )

    # Row 2: Annual Net Cashflow Bars vs. Annual Costs Comparison
    bar_colors = ["#22C55E" if v >= 0 else "#EF4444" for v in net_cf]
    fig.add_trace(
        go.Bar(
            x=years,
            y=net_cf,
            name=f"Annual Net Cashflow ({curr}/yr)",
            marker_color=bar_colors,
            opacity=0.75,
            hovertemplate=f"Year %{{x}}<br>Net Cashflow: {curr_sym}%{{y:,.0f}}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=years[1:],
            y=base_bill[1:],
            mode="lines+markers",
            name=f"Current System Annual Bill ({curr}/yr)",
            line=dict(color="#F87171", width=2.2, dash="dash"),
            hovertemplate=f"Year %{{x}}<br>Current Bill: {curr_sym}%{{y:,.0f}}/yr<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=years[1:],
            y=comb_opex[1:],
            mode="lines+markers",
            name=f"Combined System Annual Cost ({curr}/yr)",
            line=dict(color="#FACC15", width=2.4),
            hovertemplate=f"Year %{{x}}<br>Combined Cost: {curr_sym}%{{y:,.0f}}/yr<extra></extra>",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        height=560,
        margin=dict(l=60, r=40, t=105, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text=f"15-Year Amortization & Annual Cashflow Comparison ({curr})",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
            y=0.98,
        ),
        xaxis=dict(
            gridcolor="rgba(148, 163, 184, 0.12)",
            tickmode="linear",
            tick0=0,
            dtick=1,
        ),
        xaxis2=dict(
            title="Year",
            gridcolor="rgba(148, 163, 184, 0.12)",
            tickmode="linear",
            tick0=0,
            dtick=1,
        ),
        yaxis=dict(
            title=f"Cumulative Cashflow ({curr})",
            gridcolor="rgba(148, 163, 184, 0.12)",
            zeroline=True,
            zerolinecolor="rgba(248, 250, 252, 0.45)",
            zerolinewidth=1.2,
        ),
        yaxis2=dict(
            title=f"Annual Cashflow & Cost ({curr}/yr)",
            gridcolor="rgba(148, 163, 184, 0.12)",
            zeroline=True,
            zerolinecolor="rgba(248, 250, 252, 0.45)",
            zerolinewidth=1.2,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.06,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        hovermode="x unified",
    )

    return fig


def create_financial_waterfall_bridge_figure(
    sim_res: CombinedSimulationResult,
) -> go.Figure:
    """
    Creates the Year-1 Annual Cost Bridge Waterfall chart, decomposing the transition
    from Current situation Bill down to Combined System Net OPEX.
    """
    fk = sim_res.financial_kpis
    if fk is None:
        return go.Figure()

    supply_sav = -(fk.baseline_pillar1_supply_eur - fk.combined_pillar1_supply_eur)
    dso_base_net = max(0.0, fk.baseline_pillar2_dso_eur - fk.baseline_penalty_cost_eur)
    dso_comb_net = max(0.0, fk.combined_pillar2_dso_eur - fk.combined_grid_penalty_cost_eur)
    dso_sav = -(dso_base_net - dso_comb_net)
    pen_sav = -(fk.baseline_penalty_cost_eur - fk.combined_grid_penalty_cost_eur)
    tax_sav = -(fk.baseline_pillar4_taxes_eur - fk.combined_pillar4_taxes_eur)
    export_rev = -fk.solar_export_revenue_eur
    sol_om = fk.solar_om_eur
    bat_om = fk.battery_om_eur
    gen_opex = fk.generator_total_opex_eur

    x_labels = ["Current situation Bill"]
    y_vals = [fk.baseline_total_opex_eur]
    measures = ["absolute"]

    if abs(supply_sav) > 0.5:
        x_labels.append("Supply Savings")
        y_vals.append(supply_sav)
        measures.append("relative")

    if abs(dso_sav) > 0.5:
        x_labels.append("Grid Capacity Savings")
        y_vals.append(dso_sav)
        measures.append("relative")

    if abs(pen_sav) > 0.5:
        x_labels.append("Avoided Penalties")
        y_vals.append(pen_sav)
        measures.append("relative")

    if abs(tax_sav) > 0.5:
        x_labels.append("Tax Reductions")
        y_vals.append(tax_sav)
        measures.append("relative")

    if abs(export_rev) > 0.5:
        x_labels.append("Solar Feed-in Export")
        y_vals.append(export_rev)
        measures.append("relative")

    if sol_om > 0.5:
        x_labels.append("Solar O&M")
        y_vals.append(sol_om)
        measures.append("relative")

    if bat_om > 0.5:
        x_labels.append("Battery O&M")
        y_vals.append(bat_om)
        measures.append("relative")

    if gen_opex > 0.5:
        x_labels.append("Generator OPEX")
        y_vals.append(gen_opex)
        measures.append("relative")

    x_labels.append("Combined System Net OPEX")
    y_vals.append(0.0)
    measures.append("total")

    fig = go.Figure(
        go.Waterfall(
            name="Cost Bridge",
            orientation="v",
            measure=measures,
            x=x_labels,
            y=y_vals,
            textposition="outside",
            text=[f"€{abs(v):,.0f}" if m != "total" else f"€{fk.total_annual_opex_eur:,.0f}" for v, m in zip(y_vals, measures)],
            connector={"line": {"color": "rgba(148, 163, 184, 0.4)"}},
            decreasing={"marker": {"color": "#22C55E"}},
            increasing={"marker": {"color": "#EF4444"}},
            totals={"marker": {"color": "#3B82F6"}},
            hovertemplate="%{x}<br>Amount: €%{y:,.0f}<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_dark",
        height=430,
        margin=dict(l=55, r=25, t=75, b=65),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text="Year-1 Annual Cost Bridge: Current situation to Combined System (€/year)",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        yaxis=dict(
            title="Annual Cost (€/year)",
            gridcolor="rgba(148, 163, 184, 0.12)",
        ),
        xaxis=dict(
            tickangle=-25,
            gridcolor="rgba(148, 163, 184, 0.12)",
        ),
        hovermode="x unified",
    )

    return fig


def create_financial_monthly_cashflow_figure(
    sim_res: CombinedSimulationResult,
) -> go.Figure:
    """
    Creates the 12-Month Seasonal Financial Cashflow Chart,
    comparing monthly Current situation bills vs. Combined system OPEX,
    with an overlaid line for monthly net savings.
    """
    m_df = sim_res.monthly_cost_df
    if m_df.empty:
        return go.Figure()

    months = m_df["Month"].tolist()
    base_bills = m_df["Current situation Total (€)"].tolist()
    comb_opex = m_df["Combined System Total OPEX (€)"].tolist()
    m_savings = m_df["Monthly Savings (€)"].tolist()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=months,
            y=base_bills,
            name="Current situation Bill (€)",
            marker_color="#F87171",
            hovertemplate="%{x}<br>Current situation: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Bar(
            x=months,
            y=comb_opex,
            name="Combined System OPEX (€)",
            marker_color="#38BDF8",
            hovertemplate="%{x}<br>Combined System: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=months,
            y=m_savings,
            mode="lines+markers",
            name="Monthly Net Savings (€)",
            line=dict(color="#22C55E", width=2.4),
            marker=dict(size=7, color="#22C55E"),
            hovertemplate="%{x}<br>Monthly Savings: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        barmode="group",
        template="plotly_dark",
        height=430,
        margin=dict(l=55, r=55, t=75, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text="Monthly Costs & Net Savings (€/month)",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        yaxis=dict(
            title="Monthly Expense (€/month)",
            gridcolor="rgba(148, 163, 184, 0.12)",
            rangemode="tozero",
        ),
        yaxis2=dict(
            title="Monthly Savings (€/month)",
            gridcolor="rgba(0,0,0,0)",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        hovermode="x unified",
    )

    return fig


def create_monthly_grid_bill_progression_figure(
    sim_res: CombinedSimulationResult,
    view_mode: str = "Combined System Bill",
) -> go.Figure:
    """
    Creates the 12-Month Grid & Electricity Bill Progression Chart (inspired by
    Currentsituation_sandbox), decomposing monthly utility charges across cost drivers.
    Supports:
      - "Combined System Bill": Stacked bars by tariff driver + Total Grid Bill line
      - "Current Situation Bill": Stacked baseline utility charges + Total Bill line
      - "Monthly Bill Comparison": Side-by-side grid bill bars + savings trajectory
    """
    m_df = sim_res.monthly_cost_df
    if m_df is None or m_df.empty:
        return go.Figure()

    months = m_df["Month"].tolist()

    if view_mode == "Monthly Bill Comparison":
        base_bills = m_df["Current situation Total (€)"].tolist()
        comb_grid_bills = [
            float(r["Combined Grid Energy & Taxes (€)"])
            + float(r["Combined Network & Standing (€)"])
            + float(r["Combined Overload Penalty (€)"])
            for _, r in m_df.iterrows()
        ]
        grid_savings = [b - c for b, c in zip(base_bills, comb_grid_bills)]

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(
                x=months,
                y=base_bills,
                name="Current Situation Grid Bill (€)",
                marker_color="#F87171",
                hovertemplate="%{x}<br>Current Bill: €%{y:,.0f}<extra></extra>",
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Bar(
                x=months,
                y=comb_grid_bills,
                name="With System Grid Bill (€)",
                marker_color="#38BDF8",
                hovertemplate="%{x}<br>With System Grid Bill: €%{y:,.0f}<extra></extra>",
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=months,
                y=grid_savings,
                mode="lines+markers",
                name="Gross Monthly Grid Savings (€)",
                line=dict(color="#22C55E", width=2.4),
                marker=dict(size=7, color="#22C55E"),
                hovertemplate="%{x}<br>Grid Bill Savings: €%{y:,.0f}<extra></extra>",
            ),
            secondary_y=True,
        )
        fig.update_layout(
            barmode="group",
            template="plotly_dark",
            height=380,
            margin=dict(l=50, r=50, t=70, b=40),
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.45)",
            title=dict(
                text="Monthly Electricity Bill Comparison (€/month)",
                font=dict(size=14, color="#F8FAFC"),
                x=0.0,
            ),
            yaxis=dict(title="Monthly Bill (€)", gridcolor="rgba(148, 163, 184, 0.12)", rangemode="tozero"),
            yaxis2=dict(title="Grid Bill Savings (€)", gridcolor="rgba(0,0,0,0)", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0.0, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
            hovermode="x unified",
        )
        return fig

    fig = go.Figure()

    if view_mode == "Current Situation Bill":
        series_defs = [
            ("Network, Capacity & Standing (€)", m_df["Current situation Network & Standing (€)"].tolist(), "#F59E0B"),
            ("Electricity & Taxes (€)", m_df["Current situation Energy & Taxes (€)"].tolist(), "#3B82F6"),
            ("Overload Penalties (€)", m_df["Current situation Overload Penalty (€)"].tolist(), "#EF4444"),
        ]
        total_line = m_df["Current situation Total (€)"].tolist()
        chart_title = "Monthly Electricity & Grid Cost Progression — Current Situation (€/month)"
    else:
        has_granular = "Combined Booked Capacity (€)" in m_df.columns
        if has_granular:
            series_defs = [
                ("Standing & Metering", m_df["Combined Standing & Metering (€)"].tolist(), "#8B5CF6"),
                ("Booked Grid Capacity", m_df["Combined Booked Capacity (€)"].tolist(), "#F59E0B"),
                ("Measured Peak Demand Fee", m_df["Combined Peak Demand Fee (€)"].tolist(), "#F97316"),
                ("Grid Transport (kWh)", m_df["Combined DSO Transport (€)"].tolist(), "#06B6D4"),
                ("Electricity Supply & Taxes", m_df["Combined Supply & Tax (€)"].tolist(), "#3B82F6"),
                ("Overload Penalties", m_df["Combined Overload Penalty (€)"].tolist(), "#EF4444"),
            ]
        else:
            series_defs = [
                ("Network & Standing", m_df["Combined Network & Standing (€)"].tolist(), "#F59E0B"),
                ("Electricity & Taxes", m_df["Combined Grid Energy & Taxes (€)"].tolist(), "#3B82F6"),
                ("Overload Penalties", m_df["Combined Overload Penalty (€)"].tolist(), "#EF4444"),
            ]
        total_line = [
            float(r["Combined Grid Energy & Taxes (€)"])
            + float(r["Combined Network & Standing (€)"])
            + float(r["Combined Overload Penalty (€)"])
            for _, r in m_df.iterrows()
        ]
        chart_title = "Monthly Electricity & Grid Cost Progression — Combined System (€/month)"

    for label, vals, color_hex in series_defs:
        if sum(abs(float(v)) for v in vals) > 0.01:
            fig.add_trace(
                go.Bar(
                    x=months,
                    y=vals,
                    name=label,
                    marker_color=color_hex,
                    hovertemplate=f"%{{x}}<br>{label}: €%{{y:,.0f}}<extra></extra>",
                )
            )

    fig.add_trace(
        go.Scatter(
            x=months,
            y=total_line,
            mode="lines+markers",
            name="Total Grid Bill (€)",
            line=dict(color="#F8FAFC", width=2.2),
            marker=dict(size=6, color="#F8FAFC"),
            hovertemplate="%{x}<br>Total Grid Bill: €%{y:,.0f}<extra></extra>",
        )
    )

    fig.update_layout(
        barmode="stack",
        template="plotly_dark",
        height=380,
        margin=dict(l=50, r=20, t=70, b=40),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text=chart_title,
            font=dict(size=14, color="#F8FAFC"),
            x=0.0,
        ),
        yaxis=dict(
            title="Monthly Cost (€)",
            gridcolor="rgba(148, 163, 184, 0.12)",
            rangemode="tozero",
        ),
        xaxis=dict(gridcolor="rgba(148, 163, 184, 0.12)"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        hovermode="x unified",
    )

    return fig
