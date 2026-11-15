"""
Isolated contract-pillar (DSO, Supplier, Metering & Taxes) and standalone hardware
(Solar, Battery, Generator) Plotly financial breakdown charts.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..combined_sandbox_engine import CombinedSimulationResult

def create_dso_isolated_breakdown_figure(
    sim_res: CombinedSimulationResult,
    height: int = 360,
) -> go.Figure:
    """
    Creates a 2-panel isolated Grid Operator (DSO) contract visual:
      - Left: Stacked annual DSO cost breakdown (Current vs. With System)
      - Right: 12-month DSO bill comparison with monthly grid peak demand (kW)
    """
    fk = sim_res.financial_kpis
    d_df = getattr(sim_res, "dso_monthly_df", pd.DataFrame())
    if fk is None or d_df is None or d_df.empty:
        return go.Figure()

    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.36, 0.64],
        horizontal_spacing=0.09,
        specs=[[{"type": "bar"}, {"secondary_y": True}]],
        subplot_titles=(
            "Annual DSO Cost Structure (EUR/yr)",
            "12-Month DSO Contract Bill (EUR) & Peak (kW)",
        ),
    )

    x_cats = ["Current", "With System"]
    segments = [
        ("Fixed Connection & Transport", [fk.baseline_dso_fixed_eur, fk.combined_dso_fixed_eur], "#64748B"),
        ("Booked Capacity Fee", [fk.baseline_dso_capacity_eur, fk.combined_dso_capacity_eur], "#0EA5E9"),
        ("Monthly Peak Demand Fee", [fk.baseline_dso_peak_eur, fk.combined_dso_peak_eur], "#F59E0B"),
        ("Grid Transport Volume", [fk.baseline_dso_transport_eur, fk.combined_dso_transport_eur], "#6366F1"),
        ("Overload Penalty", [fk.baseline_penalty_cost_eur, fk.combined_grid_penalty_cost_eur], "#EF4444"),
    ]
    if fk.baseline_dso_transformer_rent_eur > 0.0:
        segments.append(
            ("Transformer Rental", [fk.baseline_dso_transformer_rent_eur, fk.combined_dso_transformer_rent_eur], "#A855F7")
        )

    cum_base = [0.0, 0.0]
    for label, vals, color in segments:
        fig.add_trace(
            go.Bar(
                name=label,
                x=x_cats,
                y=vals,
                base=list(cum_base),
                offsetgroup="dso_annual_stack",
                marker_color=color,
                hovertemplate=f"%{{x}}<br>{label}: €%{{y:,.0f}}/yr<extra></extra>",
            ),
            row=1,
            col=1,
        )
        cum_base[0] += float(vals[0])
        cum_base[1] += float(vals[1])

    months = d_df["Month"].tolist()
    fig.add_trace(
        go.Bar(
            name="DSO Current (EUR)",
            x=months,
            y=d_df["DSO Current (€)"].tolist(),
            offsetgroup="dso_mo_curr",
            marker_color="#F87171",
            hovertemplate="%{x}<br>DSO Current: €%{y:,.0f}<extra></extra>",
        ),
        row=1,
        col=2,
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            name="DSO With System (EUR)",
            x=months,
            y=d_df["DSO With System (€)"].tolist(),
            offsetgroup="dso_mo_sys",
            marker_color="#38BDF8",
            hovertemplate="%{x}<br>DSO With System: €%{y:,.0f}<extra></extra>",
        ),
        row=1,
        col=2,
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name="Grid Peak With System (kW)",
            x=months,
            y=d_df["With System Peak (kW)"].tolist(),
            mode="lines+markers",
            line=dict(color="#22C55E", width=2.2),
            marker=dict(size=6, color="#22C55E"),
            hovertemplate="%{x}<br>With System Peak: %{y:,.1f} kW<extra></extra>",
        ),
        row=1,
        col=2,
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            name="Current Peak (kW)",
            x=months,
            y=d_df["Current Peak (kW)"].tolist(),
            mode="lines",
            line=dict(color="rgba(248, 113, 113, 0.55)", width=1.6, dash="dot"),
            hovertemplate="%{x}<br>Current Peak: %{y:,.1f} kW<extra></extra>",
        ),
        row=1,
        col=2,
        secondary_y=True,
    )

    fig.update_layout(
        barmode="group",
        template="plotly_dark",
        height=height,
        margin=dict(l=45, r=45, t=65, b=40),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.16,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10),
        ),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Annual DSO Cost (EUR)", row=1, col=1, gridcolor="rgba(148, 163, 184, 0.12)", rangemode="tozero")
    fig.update_yaxes(title_text="Monthly DSO Cost (EUR)", row=1, col=2, secondary_y=False, gridcolor="rgba(148, 163, 184, 0.12)", rangemode="tozero")
    fig.update_yaxes(title_text="Peak Demand (kW)", row=1, col=2, secondary_y=True, showgrid=False, rangemode="tozero")
    return fig


def create_supplier_isolated_breakdown_figure(
    sim_res: CombinedSimulationResult,
    height: int = 340,
) -> go.Figure:
    """
    Creates the isolated 12-month Energy Supplier contract chart (Current vs. With System cost & MWh).
    """
    s_df = getattr(sim_res, "supplier_monthly_df", pd.DataFrame())
    if s_df is None or s_df.empty:
        return go.Figure()

    months = s_df["Month"].tolist()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            name="Supplier Current (EUR)",
            x=months,
            y=s_df["Supplier Current (€)"].tolist(),
            marker_color="#F87171",
            hovertemplate="%{x}<br>Current Supplier Bill: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            name="Supplier With System (EUR)",
            x=months,
            y=s_df["Supplier With System (€)"].tolist(),
            marker_color="#3B82F6",
            hovertemplate="%{x}<br>With System Supplier Bill: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name="Grid Import (MWh)",
            x=months,
            y=[v / 1000.0 for v in s_df["Grid Import (kWh)"].tolist()],
            mode="lines+markers",
            line=dict(color="#22C55E", width=2.2),
            marker=dict(size=6, color="#22C55E"),
            hovertemplate="%{x}<br>Grid Import: %{y:,.1f} MWh<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_layout(
        barmode="group",
        template="plotly_dark",
        height=height,
        margin=dict(l=45, r=45, t=60, b=40),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text="Isolated Energy Supplier Contract: Monthly Bill (EUR) & Import Volume (MWh)",
            font=dict(size=14, color="#F8FAFC"),
            x=0.0,
        ),
        yaxis=dict(title="Supplier Cost (EUR/mo)", gridcolor="rgba(148, 163, 184, 0.12)", rangemode="tozero"),
        yaxis2=dict(title="Grid Import (MWh)", overlaying="y", side="right", showgrid=False, rangemode="tozero"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        hovermode="x unified",
    )
    return fig


def create_solar_isolated_financial_figure(
    sim_res: CombinedSimulationResult,
    height: int = 330,
) -> go.Figure:
    """
    Creates the isolated 12-month Solar PV financial value vs. O&M chart.
    """
    df = getattr(sim_res, "solar_fin_monthly_df", pd.DataFrame())
    if df is None or df.empty:
        return go.Figure()

    months = df["Month"].tolist()
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Direct Grid Savings (EUR)",
            x=months,
            y=df["Direct Savings (€)"].tolist(),
            marker_color="#FACC15",
            hovertemplate="%{x}<br>Direct Savings: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Battery-Shift Solar Value (EUR)",
            x=months,
            y=df["Battery-Shift Value (€)"].tolist(),
            marker_color="#22C55E",
            hovertemplate="%{x}<br>Battery-Shift Value: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Export Revenue (EUR)",
            x=months,
            y=df["Export Revenue (€)"].tolist(),
            marker_color="#38BDF8",
            hovertemplate="%{x}<br>Export Revenue: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Solar O&M Cost (-EUR)",
            x=months,
            y=[-float(v) for v in df["Solar O&M (€)"].tolist()],
            marker_color="#EF4444",
            hovertemplate="%{x}<br>Solar O&M: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Net Solar Benefit (EUR)",
            x=months,
            y=df["Net Solar Benefit (€)"].tolist(),
            mode="lines+markers",
            line=dict(color="#F8FAFC", width=2.3),
            marker=dict(size=6, color="#F8FAFC"),
            hovertemplate="%{x}<br>Net Solar Benefit: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="relative",
        template="plotly_dark",
        height=height,
        margin=dict(l=45, r=25, t=60, b=40),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(text="Isolated Solar Economics: Monthly Value vs. O&M (EUR/month)", font=dict(size=14, color="#F8FAFC"), x=0.0),
        yaxis=dict(title="Monthly Value / Cost (EUR)", gridcolor="rgba(148, 163, 184, 0.12)", zeroline=True, zerolinecolor="rgba(248, 250, 252, 0.35)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        hovermode="x unified",
    )
    return fig


def create_battery_isolated_financial_figure(
    sim_res: CombinedSimulationResult,
    height: int = 330,
) -> go.Figure:
    """
    Creates the isolated 12-month Battery (BESS) financial value vs. charging & O&M chart.
    """
    df = getattr(sim_res, "battery_fin_monthly_df", pd.DataFrame())
    if df is None or df.empty:
        return go.Figure()

    months = df["Month"].tolist()
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="DSO Peak & Penalty Savings (EUR)",
            x=months,
            y=df["DSO Peak & Penalty Savings (€)"].tolist(),
            marker_color="#10B981",
            hovertemplate="%{x}<br>DSO Peak & Penalty Savings: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Solar Shift Value (EUR)",
            x=months,
            y=df["Solar Shift Value (€)"].tolist(),
            marker_color="#FACC15",
            hovertemplate="%{x}<br>Solar Shift Value: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Grid Charging Cost (-EUR)",
            x=months,
            y=[-float(v) for v in df["Grid Charging Cost (€)"].tolist()],
            marker_color="#F59E0B",
            hovertemplate="%{x}<br>Grid Charging Cost: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Battery O&M Cost (-EUR)",
            x=months,
            y=[-float(v) for v in df["Battery O&M (€)"].tolist()],
            marker_color="#EF4444",
            hovertemplate="%{x}<br>Battery O&M: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Net Battery Benefit (EUR)",
            x=months,
            y=df["Net Battery Benefit (€)"].tolist(),
            mode="lines+markers",
            line=dict(color="#F8FAFC", width=2.3),
            marker=dict(size=6, color="#F8FAFC"),
            hovertemplate="%{x}<br>Net Battery Benefit: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="relative",
        template="plotly_dark",
        height=height,
        margin=dict(l=45, r=25, t=60, b=40),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(text="Isolated Battery Economics: Monthly Value vs. O&M & Grid Charging (EUR/month)", font=dict(size=14, color="#F8FAFC"), x=0.0),
        yaxis=dict(title="Monthly Value / Cost (EUR)", gridcolor="rgba(148, 163, 184, 0.12)", zeroline=True, zerolinecolor="rgba(248, 250, 252, 0.35)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        hovermode="x unified",
    )
    return fig


def create_generator_isolated_financial_figure(
    sim_res: CombinedSimulationResult,
    height: int = 330,
) -> go.Figure:
    """
    Creates the isolated 12-month Backup Generator financial value vs. fuel, service & rental chart.
    """
    df = getattr(sim_res, "generator_fin_monthly_df", pd.DataFrame())
    if df is None or df.empty:
        return go.Figure()

    months = df["Month"].tolist()
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Avoided DSO Value (EUR)",
            x=months,
            y=df["Avoided DSO Value (€)"].tolist(),
            marker_color="#22C55E",
            hovertemplate="%{x}<br>Avoided DSO Value: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Fuel & Service (-EUR)",
            x=months,
            y=[-float(v) for v in df["Fuel & Service (€)"].tolist()],
            marker_color="#F97316",
            hovertemplate="%{x}<br>Fuel & Service: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Rental Cost (-EUR)",
            x=months,
            y=[-float(v) for v in df["Rental (€)"].tolist()],
            marker_color="#EF4444",
            hovertemplate="%{x}<br>Rental Cost: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Net Generator Impact (EUR)",
            x=months,
            y=df["Net Generator Impact (€)"].tolist(),
            mode="lines+markers",
            line=dict(color="#F8FAFC", width=2.3),
            marker=dict(size=6, color="#F8FAFC"),
            hovertemplate="%{x}<br>Net Generator Impact: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="relative",
        template="plotly_dark",
        height=height,
        margin=dict(l=45, r=25, t=60, b=40),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(text="Isolated Generator Economics: Avoided Peak Value vs. Fuel & Service (EUR/month)", font=dict(size=14, color="#F8FAFC"), x=0.0),
        yaxis=dict(title="Monthly Value / Cost (EUR)", gridcolor="rgba(148, 163, 184, 0.12)", zeroline=True, zerolinecolor="rgba(248, 250, 252, 0.35)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        hovermode="x unified",
    )
    return fig


def create_tax_isolated_breakdown_figure(
    sim_res: CombinedSimulationResult,
    height: int = 330,
) -> go.Figure:
    """
    Isolated Metering & Statutory Taxes chart comparing Current vs. With System
    monthly Metering, Net Energy Tax, Surcharge, and VAT.
    """
    df = getattr(sim_res, "tax_monthly_df", pd.DataFrame())
    fig = go.Figure()
    if df is None or df.empty:
        fig.update_layout(template="plotly_dark", height=height, title="No Metering & Tax Data Available")
        return fig

    months = df["Month"].tolist()
    fig.add_trace(
        go.Bar(
            name="Current Metering & Taxes (EUR)",
            x=months,
            y=df["Tax & Metering Current (€)"].tolist(),
            marker_color="rgba(248, 113, 113, 0.65)",
            offsetgroup="curr_tax",
            hovertemplate="%{x}<br>Current: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="With System: Metering (€)",
            x=months,
            y=df["Metering (€)"].tolist(),
            marker_color="#94A3B8",
            offsetgroup="sys_tax_stack",
            hovertemplate="%{x}<br>Metering: €%{y:,.0f}<extra></extra>",
        )
    )
    net_tax_after_credit = [
        float(g) + float(c)
        for g, c in zip(df["Energy Tax Gross (€)"].tolist(), df["Tax Credit (-€)"].tolist())
    ]
    fig.add_trace(
        go.Bar(
            name="With System: Net Energy Tax (€)",
            x=months,
            y=net_tax_after_credit,
            base=df["Metering (€)"].tolist(),
            marker_color="#F59E0B",
            offsetgroup="sys_tax_stack",
            hovertemplate="%{x}<br>Net Energy Tax: €%{y:,.0f}<extra></extra>",
        )
    )
    base_surcharge = [float(m) + float(nt) for m, nt in zip(df["Metering (€)"].tolist(), net_tax_after_credit)]
    fig.add_trace(
        go.Bar(
            name="With System: Surcharge & VAT (€)",
            x=months,
            y=[float(s) + float(v) for s, v in zip(df["Tax Surcharge (€)"].tolist(), df["VAT With System (€)"].tolist())],
            base=base_surcharge,
            marker_color="#38BDF8",
            offsetgroup="sys_tax_stack",
            hovertemplate="%{x}<br>Surcharge & VAT: €%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="group",
        template="plotly_dark",
        height=height,
        margin=dict(l=45, r=25, t=60, b=40),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(text="Isolated Metering & Taxes: Monthly Breakdown (EUR/month)", font=dict(size=14, color="#F8FAFC"), x=0.0),
        yaxis=dict(title="Monthly Cost (EUR)", gridcolor="rgba(148, 163, 184, 0.12)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        hovermode="x unified",
    )
    return fig
