"""
========================================================================================
Master Scenario Comparison Charts (current_model/ui/tab_comparison/charts.py)
========================================================================================

Description:
------------
Provides interactive Plotly visualization figures for the Master Scenario Comparison:
  - 15-Year Multi-Scenario Cumulative Cost Trajectory Curves (Break-Even Analysis & Net Savings Callouts)
  - Scope-adaptive trajectories (Facility Total TCO vs. Standalone Solar PV Investment Scope)
  - CAPEX vs. OPEX Capital Shift Grouped / Stacked Bar Chart (Status Quo vs Sub-Scenarios)
  - Side-by-Side Dual Subplot: Solar Autarky & Self-Consumption (%) + Simple Payback Period (Years)
  - Multi-Scenario Annual Electrical Energy Balance Grouped Bar Chart (Demand, Generation, Self-Consumption, Grid Import, Export)
  - Peak Demand Shaving (kW) & Carbon Avoidance (Tons CO2/a) Comparative Dual Figure
"""

from typing import List, Dict, Any, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np


def create_multi_scenario_cumulative_cost_figure(
    scenarios_data: List[Dict[str, Any]],
    base_annual_cost: float = 344141.21,
    baseline_series: Optional[List[float]] = None,
    currency: str = "EUR",
    scope_mode: str = "facility"
) -> go.Figure:
    """
    Creates a multi-line Plotly figure illustrating the 15-year cumulative cost development
    across the Base Scenario (Status Quo) and all active Sub-Scenarios.
    Supports dual scopes:
      - 'facility': Total Facility TCO including all baseline utility billing + interventions
      - 'solar': Standalone Solar PV plant economics matching Tab 3.1 100%
    """
    fig = go.Figure()
    years = list(range(0, 16))

    # 1. Base Scenario (Status Quo Line)
    if baseline_series and len(baseline_series) >= 16:
        base_y = baseline_series[:16]
    else:
        # Status Quo escalation (3% inflation per year)
        base_y = [0.0]
        cum = 0.0
        for y in range(1, 16):
            cum += base_annual_cost * ((1.0 + 0.03) ** (y - 1))
            base_y.append(cum)

    fig.add_trace(go.Scatter(
        x=years,
        y=base_y,
        mode="lines+markers",
        name="Status Quo (Grid Only)",
        line=dict(color="#EF4444", width=3, dash="dash"),
        marker=dict(size=6, color="#EF4444"),
        hovertemplate="<b>Status Quo (Grid Only)</b><br>Year %{x}: <b>%{y:,.0f} " + currency + "</b> total<extra></extra>"
    ))

    # 2. Sub-Scenarios
    palette = ["#10B981", "#38BDF8", "#F59E0B", "#A855F7", "#EC4899", "#06B6D4"]
    for idx, sc in enumerate(scenarios_data):
        name = sc.get("name", f"Sub-Scenario {idx+1}")
        color = sc.get("color") or palette[idx % len(palette)]
        
        # Select series based on active scope
        if scope_mode == "solar" and sc.get("solar_cum_costs"):
            series = sc["solar_cum_costs"]
        elif scope_mode == "facility" and sc.get("facility_cum_costs"):
            series = sc["facility_cum_costs"]
        else:
            series = sc.get("cumulative_costs")

        if not series or len(series) < 16:
            capex = sc.get("capex", 0.0)
            opex = sc.get("annual_opex", base_annual_cost * 0.65)
            series = [capex]
            cum = capex
            for y in range(1, 16):
                cum += opex * ((1.0 + 0.03) ** (y - 1))
                series.append(cum)

        fig.add_trace(go.Scatter(
            x=years,
            y=series[:16],
            mode="lines+markers",
            name=name,
            line=dict(color=color, width=3.5 if idx == 0 else 3),
            marker=dict(size=7 if idx == 0 else 6, color=color),
            hovertemplate=f"<b>{name}</b><br>Year %{{x}}: <b>%{{y:,.0f}} {currency}</b> total<extra></extra>"
        ))

        # 3. Payback / Amortisation Intersection Marker
        pb = sc.get("payback_years")
        if pb is not None and isinstance(pb, (int, float)) and 0 < pb <= 15:
            fig.add_vline(
                x=pb,
                line_color=color,
                line_width=2.0,
                line_dash="dot",
                annotation_text=f"Amortisation ({name}): {pb:.1f} Yrs",
                annotation_position="top left",
                annotation_font=dict(color=color, size=11)
            )

        # 4. Terminal Net Savings Callout Badge
        net_savings = sc.get("net_savings")
        if net_savings is not None and net_savings > 0 and len(series) >= 16:
            last_y = years[-1]
            fig.add_annotation(
                x=last_y,
                y=series[15],
                text=f"<b>Net Savings ({name}): +{net_savings:,.0f} {currency}</b>",
                showarrow=True,
                arrowhead=2,
                arrowcolor=color,
                arrowsize=1,
                arrowwidth=2,
                ax=-80 - (idx * 20),
                ay=-35 - (idx * 25),
                bgcolor="rgba(15, 23, 42, 0.85)",
                bordercolor=color,
                borderwidth=1,
                font=dict(color="#F8FAFC", size=11)
            )

    scope_title = "Facility Overall TCO Scope" if scope_mode == "facility" else "Solar PV Investment Scope"

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>15-Year Cumulative Cost Trajectories & Break-Even Amortisation ({currency})</b> - <i>{scope_title}</i>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Operational Year",
            tickmode="linear",
            dtick=1,
            gridcolor="#1E293B",
            showgrid=True
        ),
        yaxis=dict(
            title=f"Cumulative Total Expenses ({currency})",
            gridcolor="#1E293B",
            showgrid=True,
            tickformat=",.0f",
            zerolinecolor="#334155"
        ),
        paper_bgcolor="#0B0F19",
        plot_bgcolor="#0B0F19",
        font=dict(color="#E2E8F0"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.8)",
            bordercolor="#334155",
            borderwidth=1,
            font=dict(size=11)
        ),
        margin=dict(l=50, r=30, t=75, b=45),
        hovermode="x unified",
        height=420
    )

    return fig


def create_capex_opex_breakdown_figure(
    scenarios_data: List[Dict[str, Any]],
    currency: str = "EUR"
) -> go.Figure:
    """
    Creates a stacked bar chart illustrating Turn-Key CAPEX vs 15-Year OPEX/Utility Energy Costs
    comparing the Status Quo Baseline against all Sub-Scenarios.
    """
    names = [s.get("name", "Scenario") for s in scenarios_data]
    capex_vals = [s.get("capex", 0.0) for s in scenarios_data]
    opex_vals = [s.get("total_15y_opex", s.get("annual_opex", 0.0) * 18.5989) for s in scenarios_data]
    total_tco = [c + o for c, o in zip(capex_vals, opex_vals)]

    fig = go.Figure()

    # CAPEX Layer
    fig.add_trace(go.Bar(
        name="Turn-Key Initial CAPEX",
        x=names,
        y=capex_vals,
        marker_color="#38BDF8",
        hovertemplate="<b>%{x}</b><br>Initial CAPEX: <b>%{y:,.0f} " + currency + "</b><extra></extra>"
    ))

    # 15-Year OPEX Layer
    fig.add_trace(go.Bar(
        name="15-Year OPEX & Residual Electricity Bills",
        x=names,
        y=opex_vals,
        marker_color="#F59E0B",
        hovertemplate="<b>%{x}</b><br>15-Year OPEX & Utility: <b>%{y:,.0f} " + currency + "</b><extra></extra>"
    ))

    # Add total TCO annotations above each bar
    annotations = []
    for name, tot in zip(names, total_tco):
        annotations.append(dict(
            x=name,
            y=tot * 1.02,
            text=f"<b>{tot:,.0f} {currency}</b>",
            showarrow=False,
            font=dict(color="#F8FAFC", size=12),
            yanchor="bottom"
        ))

    fig.update_layout(
        template="plotly_dark",
        barmode="stack",
        title=dict(
            text=f"<b>Total Cost of Ownership (15-Year TCO): CAPEX vs. OPEX Structure ({currency})</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(
            title=f"15-Year Total Expenditure ({currency})",
            gridcolor="#1E293B",
            tickformat=",.0f"
        ),
        paper_bgcolor="#0B0F19",
        plot_bgcolor="#0B0F19",
        font=dict(color="#E2E8F0"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.8)",
            font=dict(size=11)
        ),
        annotations=annotations,
        margin=dict(l=50, r=30, t=75, b=45),
        height=380
    )

    return fig


def create_autarky_payback_figure(
    scenarios_data: List[Dict[str, Any]]
) -> go.Figure:
    """
    Creates a clear, side-by-side dual-panel visualization:
      Panel 1: Solar Autarky (%) & Self-Consumption Rate (%)
      Panel 2: Simple Payback Period (Years) & ROI Amortisation
    """
    sub_scenarios = [s for s in scenarios_data if s.get("id") != "base"]
    if not sub_scenarios:
        sub_scenarios = scenarios_data

    names = [s.get("name", "Scenario") for s in sub_scenarios]
    autarky_vals = [s.get("autarky_pct", 0.0) for s in sub_scenarios]
    self_cons_vals = [s.get("self_consumption_pct", 0.0) for s in sub_scenarios]
    payback_vals = [s.get("payback_years", 0.0) for s in sub_scenarios]

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=[
            "<b>Solar Autarky & Self-Consumption (%)</b>",
            "<b>Simple Payback Period (Years)</b>"
        ],
        horizontal_spacing=0.14
    )

    # Panel 1: Autarky & Self-Consumption
    fig.add_trace(
        go.Bar(
            name="Solar Autarky Rate (%)",
            x=names,
            y=autarky_vals,
            marker_color="#10B981",
            text=[f"{v:.1f}%" for v in autarky_vals],
            textposition="outside",
            textfont=dict(color="#10B981", size=11),
            hovertemplate="<b>%{x}</b><br>Autarky: <b>%{y:.1f}%</b><extra></extra>"
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Bar(
            name="Self-Consumption Rate (%)",
            x=names,
            y=self_cons_vals,
            marker_color="#38BDF8",
            text=[f"{v:.1f}%" if v > 0 else "-" for v in self_cons_vals],
            textposition="outside",
            textfont=dict(color="#38BDF8", size=11),
            hovertemplate="<b>%{x}</b><br>Self-Consumption: <b>%{y:.1f}%</b><extra></extra>"
        ),
        row=1, col=1
    )

    # Panel 2: Payback Period
    max_pb = max(payback_vals) if payback_vals else 5.0
    fig.add_trace(
        go.Bar(
            name="Amortization Period (Years)",
            x=names,
            y=payback_vals,
            marker_color="#818CF8",
            text=[f"{v:.1f} Yrs" if v > 0 else "N/A" for v in payback_vals],
            textposition="outside",
            textfont=dict(color="#818CF8", size=11),
            hovertemplate="<b>%{x}</b><br>Amortization: <b>%{y:.1f} Years</b><extra></extra>"
        ),
        row=1, col=2
    )

    fig.update_layout(
        template="plotly_dark",
        barmode="group",
        title=dict(
            text="<b>Performance Benchmarks: Energy Autarky vs. Capital Amortization</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        paper_bgcolor="#0B0F19",
        plot_bgcolor="#0B0F19",
        font=dict(color="#E2E8F0"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.05,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.8)",
            font=dict(size=11)
        ),
        margin=dict(l=50, r=40, t=75, b=45),
        height=380
    )

    fig.update_yaxes(
        title_text="Coverage Share (%)",
        range=[0, 115],
        gridcolor="#1E293B",
        row=1, col=1
    )

    fig.update_yaxes(
        title_text="Payback Horizon (Years)",
        range=[0, max(5.0, max_pb * 1.35)],
        gridcolor="#1E293B",
        row=1, col=2
    )

    fig.update_xaxes(gridcolor="#1E293B", row=1, col=1)
    fig.update_xaxes(gridcolor="#1E293B", row=1, col=2)

    return fig


def create_multi_scenario_energy_balance_figure(
    records: List[Dict[str, Any]]
) -> go.Figure:
    """
    Constructs a grouped bar chart comparing annual electricity flows (MWh) across all scenarios:
      - Facility Total Demand (MWh)
      - Clean Solar PV Generation (MWh)
      - Direct On-Site Consumption (MWh)
      - Residual Grid Purchase (MWh)
      - Surplus Grid Export (MWh)
    """
    names = [r.get("name", "Scenario") for r in records]
    demand_vals = [r.get("total_load_mwh", 0.0) for r in records]
    gen_vals = [r.get("generation_mwh", 0.0) for r in records]
    direct_vals = [r.get("direct_consumption_mwh", 0.0) for r in records]
    residual_vals = [r.get("residual_grid_mwh", r.get("total_load_mwh", 0.0)) for r in records]
    export_vals = [r.get("surplus_export_mwh", 0.0) for r in records]

    fig = go.Figure()

    # 1. Total Demand
    fig.add_trace(go.Bar(
        name="Facility Total Demand",
        x=names,
        y=demand_vals,
        marker_color="#94A3B8",
        text=[f"{v:,.1f}" for v in demand_vals],
        textposition="outside",
        textfont=dict(color="#94A3B8", size=10),
        hovertemplate="<b>%{x}</b><br>Facility Demand: <b>%{y:,.1f} MWh/a</b><extra></extra>"
    ))

    # 2. Solar Generation
    fig.add_trace(go.Bar(
        name="Solar PV Generation",
        x=names,
        y=gen_vals,
        marker_color="#F59E0B",
        text=[f"{v:,.1f}" if v > 0 else "-" for v in gen_vals],
        textposition="outside",
        textfont=dict(color="#F59E0B", size=10),
        hovertemplate="<b>%{x}</b><br>PV Generation: <b>%{y:,.1f} MWh/a</b><extra></extra>"
    ))

    # 3. Direct Self-Consumption
    fig.add_trace(go.Bar(
        name="Direct Self-Consumption",
        x=names,
        y=direct_vals,
        marker_color="#10B981",
        text=[f"{v:,.1f}" if v > 0 else "-" for v in direct_vals],
        textposition="outside",
        textfont=dict(color="#10B981", size=10),
        hovertemplate="<b>%{x}</b><br>Direct Consumption: <b>%{y:,.1f} MWh/a</b><extra></extra>"
    ))

    # 4. Residual Grid Purchase
    fig.add_trace(go.Bar(
        name="Residual Grid Import",
        x=names,
        y=residual_vals,
        marker_color="#38BDF8",
        text=[f"{v:,.1f}" for v in residual_vals],
        textposition="outside",
        textfont=dict(color="#38BDF8", size=10),
        hovertemplate="<b>%{x}</b><br>Residual Grid: <b>%{y:,.1f} MWh/a</b><extra></extra>"
    ))

    # 5. Surplus Export
    fig.add_trace(go.Bar(
        name="Surplus Grid Feed-in",
        x=names,
        y=export_vals,
        marker_color="#A855F7",
        text=[f"{v:,.1f}" if v > 0 else "-" for v in export_vals],
        textposition="outside",
        textfont=dict(color="#A855F7", size=10),
        hovertemplate="<b>%{x}</b><br>Surplus Export: <b>%{y:,.1f} MWh/a</b><extra></extra>"
    ))

    max_val = max(max(demand_vals or [100.0]), max(gen_vals or [100.0]))

    fig.update_layout(
        template="plotly_dark",
        barmode="group",
        title=dict(
            text="<b>Multi-Scenario Annual Electrical Energy Balance (MWh/Year)</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(
            title="Annual Electricity (MWh/a)",
            gridcolor="#1E293B",
            zerolinecolor="#334155",
            range=[0, max_val * 1.25]
        ),
        paper_bgcolor="#0B0F19",
        plot_bgcolor="#0B0F19",
        font=dict(color="#E2E8F0"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.8)",
            font=dict(size=11)
        ),
        margin=dict(l=50, r=30, t=75, b=45),
        height=390
    )

    return fig


def create_multi_scenario_peak_and_co2_figure(
    records: List[Dict[str, Any]]
) -> go.Figure:
    """
    Constructs a dual subplot comparing:
      Panel 1: Peak Demand Shaving (kW) and Residual Facility Peak (kW)
      Panel 2: Annual Clean Energy Carbon Emission Avoidance (Tons CO2/Year)
    """
    names = [r.get("name", "Scenario") for r in records]
    shaved_kw = [r.get("shaved_peak_kw", 0.0) for r in records]
    res_peak = [r.get("residual_peak_kw", r.get("baseline_peak_kw", 0.0)) for r in records]
    co2_vals = [r.get("co2_avoided_tons", 0.0) for r in records]

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=[
            "<b>Peak Demand Shaving & Residual Peak (kW)</b>",
            "<b>Annual Clean Energy Carbon Avoidance (Tons CO₂/a)</b>"
        ],
        horizontal_spacing=0.14
    )

    # Panel 1: Peak Demand Shaving
    fig.add_trace(
        go.Bar(
            name="Peak Demand Shaved (kW)",
            x=names,
            y=shaved_kw,
            marker_color="#38BDF8",
            text=[f"-{v:.1f} kW" if v > 0 else "-" for v in shaved_kw],
            textposition="outside",
            textfont=dict(color="#38BDF8", size=11),
            hovertemplate="<b>%{x}</b><br>Peak Shaved: <b>%{y:.1f} kW</b><extra></extra>"
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Bar(
            name="Residual Peak Load (kW)",
            x=names,
            y=res_peak,
            marker_color="#64748B",
            text=[f"{v:,.1f} kW" for v in res_peak],
            textposition="outside",
            textfont=dict(color="#64748B", size=11),
            hovertemplate="<b>%{x}</b><br>Residual Peak: <b>%{y:,.1f} kW</b><extra></extra>"
        ),
        row=1, col=1
    )

    # Panel 2: Carbon Offsets
    fig.add_trace(
        go.Bar(
            name="Avoided CO₂ Emissions (t/a)",
            x=names,
            y=co2_vals,
            marker_color="#10B981",
            text=[f"{v:,.1f} t CO₂" if v > 0 else "-" for v in co2_vals],
            textposition="outside",
            textfont=dict(color="#10B981", size=11),
            hovertemplate="<b>%{x}</b><br>CO₂ Avoided: <b>%{y:,.1f} Tons/Year</b><extra></extra>"
        ),
        row=1, col=2
    )

    max_p = max(res_peak or [100.0])
    max_c = max(co2_vals or [10.0])

    fig.update_layout(
        template="plotly_dark",
        barmode="group",
        title=dict(
            text="<b>Power Grid & Environmental Benchmarks: Peak Load Shaving & CO₂ Offsets</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        paper_bgcolor="#0B0F19",
        plot_bgcolor="#0B0F19",
        font=dict(color="#E2E8F0"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.05,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.8)",
            font=dict(size=11)
        ),
        margin=dict(l=50, r=40, t=75, b=45),
        height=380
    )

    fig.update_yaxes(
        title_text="Active Power (kW)",
        range=[0, max_p * 1.3],
        gridcolor="#1E293B",
        row=1, col=1
    )

    fig.update_yaxes(
        title_text="Emissions (Tons CO₂/a)",
        range=[0, max(10.0, max_c * 1.3)],
        gridcolor="#1E293B",
        row=1, col=2
    )

    fig.update_xaxes(gridcolor="#1E293B", row=1, col=1)
    fig.update_xaxes(gridcolor="#1E293B", row=1, col=2)

    return fig


def create_residual_grid_load_comparison_figure(
    records: List[Dict[str, Any]],
    chart_mode: str = "monthly_curve"
) -> go.Figure:
    """
    Constructs a dedicated comparison figure focusing on Facility Total Demand
    versus the Residual Grid Load (übrig gebliebene Netzlast / remaining utility grid imports)
    across the full year (January - December) and overall annual totals.

    Supported chart modes:
      - 'monthly_curve': Multi-line spline curves comparing Facility Load across Jan-Dec
                         with each Sub-Scenario's residual grid consumption curve.
      - 'monthly_grouped': 12-month grouped bar chart comparing monthly grid demands.
      - 'annual_totals': Direct Benchmark Bar Chart of annual MWh totals.
    """
    fig = go.Figure()

    if not records:
        return fig

    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    base_rec = records[0]
    base_demand = float(base_rec.get("total_load_mwh", 0.0))
    base_monthly = base_rec.get("monthly_load_mwh") or [round(base_demand / 12.0, 1)] * 12
    sub_recs = records[1:] if len(records) > 1 else []

    if chart_mode in ["monthly_curve", "monthly_trajectory", "curves"]:
        # 1. Baseline Facility Demand Curve (Top Benchmark)
        fig.add_trace(go.Scatter(
            x=month_labels,
            y=base_monthly,
            mode="lines+markers",
            name="Facility Total Demand (Status Quo)",
            line=dict(color="#CBD5E1", width=3, dash="dash"),
            marker=dict(size=7, color="#CBD5E1", symbol="circle"),
            hovertemplate="<b>Facility Demand (Status Quo)</b><br>Month: <b>%{x}</b><br>Consumption: <b>%{y:,.1f} MWh</b><extra></extra>"
        ))

        # 2. Each Sub-Scenario Residual Grid Curve
        for r in sub_recs:
            sub_res_monthly = r.get("monthly_residual_mwh") or list(base_monthly)
            sc_name = r.get("name", "Sub-Scenario")
            sc_color = r.get("color", "#38BDF8")

            custom_data = []
            for bm, sm in zip(base_monthly, sub_res_monthly):
                saved = max(0.0, bm - sm)
                pct = (saved / max(0.1, bm)) * 100.0
                custom_data.append([pct, saved])

            fig.add_trace(go.Scatter(
                x=month_labels,
                y=sub_res_monthly,
                mode="lines+markers",
                name=f"{sc_name} (Residual Grid)",
                line=dict(color=sc_color, width=3.5, shape="spline"),
                marker=dict(size=8, color=sc_color, symbol="diamond"),
                customdata=custom_data,
                hovertemplate=(
                    f"<b>{sc_name}</b><br>"
                    f"Month: <b>%{{x}}</b><br>"
                    f"Remaining Grid Import: <b>%{{y:,.1f}} MWh</b><br>"
                    f"Grid Reduction: <b>▼ -%{{customdata[0]:.1f}}%</b> (-%{{customdata[1]:,.1f}} MWh saved)<extra></extra>"
                )
            ))

        max_val = max([max(base_monthly or [10.0])] + [max(r.get("monthly_residual_mwh", [10.0])) for r in sub_recs])
        y_range = [0, max_val * 1.25]
        y_title = "Monthly Electricity Demand (MWh/Month)"
        x_title = "Month of Year (January – December)"
        barmode = None

    elif chart_mode in ["monthly_grouped", "grouped"]:
        # Grouped Bar Chart across 12 months
        fig.add_trace(go.Bar(
            name="Facility Total Demand",
            x=month_labels,
            y=base_monthly,
            marker_color="#64748B",
            text=[f"{v:,.1f}" for v in base_monthly],
            textposition="outside",
            textfont=dict(color="#64748B", size=9),
            hovertemplate="<b>Facility Demand</b><br>%{x}: <b>%{y:,.1f} MWh</b><extra></extra>"
        ))

        for r in sub_recs:
            sub_res_monthly = r.get("monthly_residual_mwh") or list(base_monthly)
            sc_name = r.get("name", "Sub-Scenario")
            sc_color = r.get("color", "#38BDF8")
            fig.add_trace(go.Bar(
                name=f"{sc_name} (Residual)",
                x=month_labels,
                y=sub_res_monthly,
                marker_color=sc_color,
                text=[f"{v:,.1f}" for v in sub_res_monthly],
                textposition="outside",
                textfont=dict(color=sc_color, size=9),
                hovertemplate=f"<b>{sc_name}</b><br>%{{x}}: <b>%{{y:,.1f}} MWh</b><extra></extra>"
            ))

        max_val = max([max(base_monthly or [10.0])] + [max(r.get("monthly_residual_mwh", [10.0])) for r in sub_recs])
        y_range = [0, max_val * 1.3]
        y_title = "Monthly Electricity Demand (MWh/Month)"
        x_title = "Month of Year"
        barmode = "group"

    else:
        # Annual Totals Benchmark Bar Chart
        bar_names = ["Facility Total Demand<br>(Status Quo)"]
        bar_vals = [base_demand]
        bar_colors = ["#94A3B8"]
        bar_texts = [f"<b>{base_demand:,.1f} MWh</b><br>(100% Grid)"]
        hover_texts = [
            f"<b>Status Quo Facility Demand</b><br>Total Consumption: <b>{base_demand:,.1f} MWh/a</b><extra></extra>"
        ]

        for r in sub_recs:
            res_mwh = float(r.get("residual_grid_mwh", base_demand))
            avoided_mwh = max(0.0, base_demand - res_mwh)
            red_pct = (avoided_mwh / max(0.1, base_demand)) * 100.0
            sc_name = r.get("name", "Sub-Scenario")

            bar_names.append(f"{sc_name}<br>(Residual Grid)")
            bar_vals.append(res_mwh)
            bar_colors.append(r.get("color", "#38BDF8"))

            if avoided_mwh > 0:
                bar_texts.append(f"<b>{res_mwh:,.1f} MWh</b><br><span style='color:#10B981; font-weight:bold;'>▼ -{red_pct:.1f}%</span>")
            else:
                bar_texts.append(f"<b>{res_mwh:,.1f} MWh</b><br>(0.0%)")

            hover_texts.append(
                f"<b>{sc_name}</b><br>"
                f"Remaining Grid Import: <b>{res_mwh:,.1f} MWh/a</b><br>"
                f"Avoided Grid Energy: <b>{avoided_mwh:,.1f} MWh/a</b><br>"
                f"Grid Import Reduction: <b>-{red_pct:.1f}%</b><extra></extra>"
            )

        fig.add_trace(go.Bar(
            name="Residual Grid Import (Netzbezug)",
            x=bar_names,
            y=bar_vals,
            marker_color=bar_colors,
            text=bar_texts,
            textposition="outside",
            textfont=dict(size=11),
            hovertext=hover_texts,
            hoverinfo="text"
        ))

        fig.add_hline(
            y=base_demand,
            line_dash="dash",
            line_color="#CBD5E1",
            line_width=2,
            annotation_text=f"Baseline Facility Demand: {base_demand:,.1f} MWh/a",
            annotation_position="top right",
            annotation_font=dict(color="#CBD5E1", size=11)
        )

        max_y = max(max(bar_vals or [100.0]), base_demand)
        y_range = [0, max_y * 1.25]
        y_title = "Annual Electrical Energy (MWh/a)"
        x_title = "Scenario"
        barmode = "group"

    layout_kwargs = dict(
        template="plotly_dark",
        title=dict(
            text="<b>Annual Grid Demand Trajectory: Facility Load vs. Sub-Scenario Residual Grid Imports (Jan – Dec)</b>" if chart_mode in ["monthly_curve", "monthly_trajectory", "curves"] else ("<b>Monthly Grid Demand Comparison by Scenario (Jan – Dec)</b>" if chart_mode in ["monthly_grouped", "grouped"] else "<b>Facility Total Demand vs. Remaining Residual Grid Load (MWh/Year)</b>"),
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(title=x_title, gridcolor="#1E293B"),
        yaxis=dict(
            title=y_title,
            gridcolor="#1E293B",
            zerolinecolor="#334155",
            range=y_range
        ),
        paper_bgcolor="#0B0F19",
        plot_bgcolor="#0B0F19",
        font=dict(color="#E2E8F0"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.8)",
            font=dict(size=11)
        ),
        margin=dict(l=50, r=30, t=75, b=50),
        height=420
    )

    if barmode:
        layout_kwargs["barmode"] = barmode

    fig.update_layout(**layout_kwargs)

    return fig
