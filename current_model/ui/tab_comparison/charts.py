"""
========================================================================================
Master Scenario Comparison Charts (current_model/ui/tab_comparison/charts.py)
========================================================================================

Description:
------------
Provides interactive Plotly visualization figures for the Master Scenario Comparison:
  - 15-Year Multi-Scenario Cumulative Cost Trajectory Curves (Break-Even Analysis & Net Savings Callouts)
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
    currency: str = "EUR"
) -> go.Figure:
    """
    Creates a multi-line Plotly figure illustrating the 15-year cumulative cost development
    across the Base Scenario (Status Quo) and all active Sub-Scenarios.
    Synchronized 100% with Tab 3.1's lifecycle trajectories, break-even markers, and net savings callouts.
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
        series = sc.get("cumulative_costs")

        if not series or len(series) < 16:
            # Trajectory from CAPEX + residual OPEX with inflation
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

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>15-Year Cumulative Cost Trajectories & Break-Even Amortisation ({currency})</b>",
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
