"""
========================================================================================
Contract Switch & Cost Comparison Engine (ui_sandbox/NewContract_sandbox/contract_comparison_engine.py)
========================================================================================

Description:
------------
Provides high-contrast Plotly figures, delta KPI calculators, and 4-Pillar comparative
audit tables for benchmarking Contract 1 (Baseline / Status Quo) against Contract 2 (Switch / Alternative).
"""

from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
    StatusQuoAnnualResult,
    StatusQuoConfig2025,
    LoadSeries2025,
)
from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import MONTH_NAMES


def compute_contract_switch_kpis(
    res1: StatusQuoAnnualResult,
    res2: StatusQuoAnnualResult,
) -> Dict[str, Any]:
    """
    Computes executive financial and technical deltas between Contract 1 and Contract 2.
    Positive savings = Contract 2 is cheaper than Contract 1.
    """
    curr = getattr(res1.config, "currency_code", "EUR") or "EUR"

    net1 = float(res1.total_status_quo_net)
    net2 = float(res2.total_status_quo_net)
    delta_net = net1 - net2  # Positive = Savings
    pct_net = (delta_net / max(0.01, net1)) * 100.0

    gross1 = float(res1.total_status_quo_gross)
    gross2 = float(res2.total_status_quo_gross)
    delta_gross = gross1 - gross2
    pct_gross = (delta_gross / max(0.01, gross1)) * 100.0

    p1_1 = float(res1.total_supplier_net)
    p1_2 = float(res2.total_supplier_net)
    delta_p1 = p1_1 - p1_2

    p2_1 = float(res1.total_dso_net)
    p2_2 = float(res2.total_dso_net)
    delta_p2 = p2_1 - p2_2

    p3_1 = float(res1.total_metering_net)
    p3_2 = float(res2.total_metering_net)
    delta_p3 = p3_1 - p3_2

    p4_1 = float(res1.total_levies_net)
    p4_2 = float(res2.total_levies_net)
    delta_p4 = p4_1 - p4_2

    rate1 = float(res1.blended_price_net_kwh)
    rate2 = float(res2.blended_price_net_kwh)
    delta_rate = rate1 - rate2

    # DSO Capacity & Penalty Metrics
    dso_recs1 = [r.dso for r in res1.monthly_records]
    dso_recs2 = [r.dso for r in res2.monthly_records]

    pen1 = float(sum(r.excess_penalty_fee for r in dso_recs1))
    pen2 = float(sum(r.excess_penalty_fee for r in dso_recs2))
    delta_pen = pen1 - pen2

    breach1 = int(sum(1 for r in dso_recs1 if r.is_capacity_breached))
    breach2 = int(sum(1 for r in dso_recs2 if r.is_capacity_breached))

    cap1 = float(res1.config.dso.contracted_capacity_kw)
    cap2 = float(res2.config.dso.contracted_capacity_kw)

    # 15-Year Life-Cycle TCO NPV
    tco1 = float(getattr(res1, "tco_15_npv", getattr(res1, "tco_15y_npv", net1 * 10.38)) or (net1 * 10.38))
    tco2 = float(getattr(res2, "tco_15_npv", getattr(res2, "tco_15y_npv", net2 * 10.38)) or (net2 * 10.38))
    delta_tco = tco1 - tco2

    return {
        "currency_code": curr,
        "net1": net1,
        "net2": net2,
        "delta_net": delta_net,
        "pct_net": pct_net,
        "is_saving": delta_net >= 0.0,
        "gross1": gross1,
        "gross2": gross2,
        "delta_gross": delta_gross,
        "pct_gross": pct_gross,
        "p1_1": p1_1,
        "p1_2": p1_2,
        "delta_p1": delta_p1,
        "p2_1": p2_1,
        "p2_2": p2_2,
        "delta_p2": delta_p2,
        "p3_1": p3_1,
        "p3_2": p3_2,
        "delta_p3": delta_p3,
        "p4_1": p4_1,
        "p4_2": p4_2,
        "delta_p4": delta_p4,
        "rate1": rate1,
        "rate2": rate2,
        "delta_rate": delta_rate,
        "cap1": cap1,
        "cap2": cap2,
        "delta_cap": cap2 - cap1,
        "pen1": pen1,
        "pen2": pen2,
        "delta_pen": delta_pen,
        "breach1": breach1,
        "breach2": breach2,
        "tco1": tco1,
        "tco2": tco2,
        "delta_tco": delta_tco,
    }


def create_4pillar_side_by_side_figure(
    res1: StatusQuoAnnualResult,
    res2: StatusQuoAnnualResult,
    label1: str = "Contract 1 (Baseline)",
    label2: str = "Contract 2 (Switch)",
) -> go.Figure:
    """
    Constructs a stacked bar comparison chart illustrating the 4 cost pillars
    (Pillar 1: Supply, Pillar 2: DSO, Pillar 3: Metering, Pillar 4: Taxes) side-by-side.
    """
    curr = getattr(res1.config, "currency_code", "EUR") or "EUR"
    categories = [label1, label2]

    p1_vals = [res1.total_supplier_net, res2.total_supplier_net]
    p2_vals = [res1.total_dso_net, res2.total_dso_net]
    p3_vals = [res1.total_metering_net, res2.total_metering_net]
    p4_vals = [res1.total_levies_net, res2.total_levies_net]

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            name="1. Energy Supply (Retailer)",
            x=categories,
            y=p1_vals,
            marker_color="#38bdf8",
            hovertemplate="<b>1. Supply:</b> " + curr + " %{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="2. Grid Network (DSO)",
            x=categories,
            y=p2_vals,
            marker_color="#f59e0b",
            hovertemplate="<b>2. DSO:</b> " + curr + " %{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="3. Metering",
            x=categories,
            y=p3_vals,
            marker_color="#8b5cf6",
            hovertemplate="<b>3. Metering:</b> " + curr + " %{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="4. Statutory Taxes",
            x=categories,
            y=p4_vals,
            marker_color="#10b981",
            hovertemplate="<b>4. Taxes:</b> " + curr + " %{y:,.2f}<extra></extra>",
        )
    )

    # Add total net annotations above each bar
    tot1 = res1.total_status_quo_net
    tot2 = res2.total_status_quo_net
    delta = tot1 - tot2
    pct = (delta / max(0.01, tot1)) * 100.0
    sign_str = "-" if delta > 0 else "+"
    diff_tag = f" ({sign_str}{abs(pct):.1f}%)" if abs(delta) > 1.0 else ""

    fig.add_annotation(
        x=categories[0],
        y=tot1,
        text=f"<b>{curr} {tot1:,.0f} net</b>",
        showarrow=False,
        yshift=14,
        font=dict(color="#f8fafc", size=12),
    )
    fig.add_annotation(
        x=categories[1],
        y=tot2,
        text=f"<b>{curr} {tot2:,.0f} net{diff_tag}</b>",
        showarrow=False,
        yshift=14,
        font=dict(color="#10b981" if delta >= 0 else "#ef4444", size=12),
    )

    fig.update_layout(
        title=dict(
            text=f"<b>4-Pillar Annual Electricity Cost Structure: {label1} vs. {label2}</b>",
            font=dict(size=14, color="#f8fafc"),
            x=0.01,
            y=0.98,
        ),
        barmode="stack",
        template="plotly_dark",
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.55)",
        height=400,
        margin=dict(l=40, r=30, t=80, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="left",
            x=0.01,
            font=dict(size=11),
        ),
        yaxis=dict(
            title=f"Annual Net Cost ({curr}/year)",
            gridcolor="#1e293b",
            zerolinecolor="#334155",
        ),
        xaxis=dict(gridcolor="#1e293b"),
    )

    return fig


def create_12month_monthly_bill_comparison_figure(
    res1: StatusQuoAnnualResult,
    res2: StatusQuoAnnualResult,
    label1: str = "Contract 1",
    label2: str = "Contract 2",
) -> go.Figure:
    """
    Constructs a 12-month grouped bar chart showing the monthly net bill comparison
    and highlighting month-by-month net savings or cost increases.
    """
    curr = getattr(res1.config, "currency_code", "EUR") or "EUR"
    months = [getattr(r, "month_name", None) or MONTH_NAMES[getattr(r, "month_index", 1) - 1] for r in res1.monthly_records]

    m_net1 = [getattr(r, "total_net", getattr(r, "total_net_bill", 0.0)) for r in res1.monthly_records]
    m_net2 = [getattr(r, "total_net", getattr(r, "total_net_bill", 0.0)) for r in res2.monthly_records]
    m_deltas = [n1 - n2 for n1, n2 in zip(m_net1, m_net2)]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            name=f"{label1} (Net)",
            x=months,
            y=m_net1,
            marker_color="rgba(148, 163, 184, 0.65)",
            hovertemplate="<b>" + label1 + ":</b> " + curr + " %{y:,.2f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            name=f"{label2} (Net)",
            x=months,
            y=m_net2,
            marker_color="#38bdf8",
            hovertemplate="<b>" + label2 + ":</b> " + curr + " %{y:,.2f}<extra></extra>",
        ),
        secondary_y=False,
    )

    # Monthly net savings line
    fig.add_trace(
        go.Scatter(
            name="Monthly Net Savings (Δ)",
            x=months,
            y=m_deltas,
            mode="lines+markers",
            line=dict(color="#10b981", width=2.5),
            marker=dict(size=7, color="#10b981"),
            hovertemplate="<b>Monthly Savings:</b> +" + curr + " %{y:,.2f}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title=dict(
            text="<b>12-Month Net Electricity Invoice Trajectory & Monthly Savings</b>",
            font=dict(size=14, color="#f8fafc"),
            x=0.01,
            y=0.98,
        ),
        barmode="group",
        template="plotly_dark",
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.55)",
        height=380,
        margin=dict(l=40, r=40, t=80, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="left",
            x=0.01,
            font=dict(size=11),
        ),
        xaxis=dict(gridcolor="#1e293b"),
    )
    fig.update_yaxes(title_text=f"Monthly Net Bill ({curr})", gridcolor="#1e293b", secondary_y=False)
    fig.update_yaxes(title_text=f"Net Monthly Delta ({curr})", showgrid=False, secondary_y=True)

    return fig


def create_15year_tco_comparison_figure(
    res1: StatusQuoAnnualResult,
    res2: StatusQuoAnnualResult,
    label1: str = "Contract 1 (Baseline)",
    label2: str = "Contract 2 (Switch)",
) -> go.Figure:
    """
    Constructs a 15-year cumulative expenditure and TCO NPV trajectory chart.
    """
    curr = getattr(res1.config, "currency_code", "EUR") or "EUR"

    net1 = float(res1.total_status_quo_net)
    net2 = float(res2.total_status_quo_net)
    esc1 = getattr(res1.config, "energy_escalation_pct", 2.0) / 100.0
    esc2 = getattr(res2.config, "energy_escalation_pct", 2.0) / 100.0

    years = list(range(0, 16))
    cum1 = [0.0]
    cum2 = [0.0]
    cur_yr1 = net1
    cur_yr2 = net2

    for y in range(1, 16):
        cum1.append(cum1[-1] + cur_yr1)
        cum2.append(cum2[-1] + cur_yr2)
        cur_yr1 *= (1.0 + esc1)
        cur_yr2 *= (1.0 + esc2)

    cum_savings = cum1[-1] - cum2[-1]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            name=label1,
            x=years,
            y=cum1,
            mode="lines+markers",
            line=dict(color="#94a3b8", width=2.5, dash="dash"),
            marker=dict(size=6),
            hovertemplate="<b>" + label1 + " (Yr %{x}):</b> " + curr + " %{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name=label2,
            x=years,
            y=cum2,
            mode="lines+markers",
            line=dict(color="#38bdf8", width=3.0),
            marker=dict(size=7),
            hovertemplate="<b>" + label2 + " (Yr %{x}):</b> " + curr + " %{y:,.0f}<extra></extra>",
        )
    )

    if abs(cum_savings) > 1.0:
        fig.add_annotation(
            x=15,
            y=cum2[-1],
            text=f"<b>15-Yr Cumulative Savings: {('+' if cum_savings >= 0 else '')}{cum_savings:,.0f} {curr}</b>",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#10b981" if cum_savings >= 0 else "#ef4444",
            ax=-80,
            ay=-30,
            bgcolor="rgba(15, 23, 42, 0.9)",
            bordercolor="#10b981" if cum_savings >= 0 else "#ef4444",
            borderwidth=1.5,
            font=dict(color="#f8fafc", size=11),
        )

    fig.update_layout(
        title=dict(
            text=f"<b>15-Year Cumulative Electricity Cost Trajectory (TCO Life-Cycle Projection)</b>",
            font=dict(size=14, color="#f8fafc"),
            x=0.01,
            y=0.98,
        ),
        template="plotly_dark",
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.55)",
        height=380,
        margin=dict(l=40, r=30, t=80, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="left",
            x=0.01,
            font=dict(size=11),
        ),
        xaxis=dict(title="Operational Year (0 to 15)", gridcolor="#1e293b", dtick=1),
        yaxis=dict(title=f"Cumulative Cost ({curr})", gridcolor="#1e293b"),
    )

    return fig


def build_4pillar_comparison_table(
    res1: StatusQuoAnnualResult,
    res2: StatusQuoAnnualResult,
    label1: str = "Contract 1 (Baseline)",
    label2: str = "Contract 2 (Switch)",
) -> pd.DataFrame:
    """
    Constructs a detailed line-by-line comparative audit table across all 4 pillars.
    """
    curr = getattr(res1.config, "currency_code", "EUR") or "EUR"

    dso1 = [r.dso for r in res1.monthly_records]
    dso2 = [r.dso for r in res2.monthly_records]

    cap_fee1 = sum(r.contracted_capacity_fee for r in dso1)
    cap_fee2 = sum(r.contracted_capacity_fee for r in dso2)

    peak_fee1 = sum(r.peak_demand_fee for r in dso1)
    peak_fee2 = sum(r.peak_demand_fee for r in dso2)

    trans_vol1 = sum(r.volumetric_transport_fee for r in dso1)
    trans_vol2 = sum(r.volumetric_transport_fee for r in dso2)

    pen1 = sum(r.excess_penalty_fee for r in dso1)
    pen2 = sum(r.excess_penalty_fee for r in dso2)

    fixed_dso1 = sum(r.fixed_connection_fee + r.fixed_transport_fee for r in dso1)
    fixed_dso2 = sum(r.fixed_connection_fee + r.fixed_transport_fee for r in dso2)

    lines = [
        ("1. Energy Supply (Retailer)", res1.total_supplier_net, res2.total_supplier_net),
        ("2. Grid Network (DSO Total)", res1.total_dso_net, res2.total_dso_net),
        ("   - 2.1 Fixed Connection & Transport Fees", fixed_dso1, fixed_dso2),
        ("   - 2.2 Reserved Contracted Capacity Fee", cap_fee1, cap_fee2),
        ("   - 2.3 Measured Monthly Peak Demand Fee", peak_fee1, peak_fee2),
        ("   - 2.4 Network Volumetric Transport Rates", trans_vol1, trans_vol2),
        ("   - 2.6 Excess Capacity Penalty Fee", pen1, pen2),
        ("3. Certified Metering & Telemetry", res1.total_metering_net, res2.total_metering_net),
        ("4. Statutory Taxes & Levies", res1.total_levies_net, res2.total_levies_net),
        ("TOTAL NET ELECTRICITY BILL", res1.total_status_quo_net, res2.total_status_quo_net),
        ("Value Added Tax (VAT)", res1.total_vat_amount, res2.total_vat_amount),
        ("TOTAL GROSS ELECTRICITY BILL", res1.total_status_quo_gross, res2.total_status_quo_gross),
        ("Effective Blended Rate (Net / kWh)", res1.blended_price_net_kwh, res2.blended_price_net_kwh),
        ("Effective Blended Rate (Gross / kWh)", res1.blended_price_gross_kwh, res2.blended_price_gross_kwh),
    ]

    rows = []
    for item_name, v1, v2 in lines:
        delta = v2 - v1  # standard financial delta: switch - baseline
        pct = (delta / max(0.0001, abs(v1))) * 100.0 if abs(v1) > 0.0001 else 0.0
        is_rate = "Rate" in item_name

        if is_rate:
            rows.append({
                "Line Item": item_name,
                label1: f"{curr} {v1:.4f}/kWh",
                label2: f"{curr} {v2:.4f}/kWh",
                "Delta (Switch - Baseline)": f"{'+' if delta >= 0 else ''}{delta:.4f} {curr}/kWh",
                "Delta (%)": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
            })
        else:
            rows.append({
                "Line Item": item_name,
                label1: f"{curr} {v1:,.2f}",
                label2: f"{curr} {v2:,.2f}",
                "Delta (Switch - Baseline)": f"{'+' if delta >= 0 else ''}{curr} {delta:,.2f}",
                "Delta (%)": f"{'+' if pct >= 0 else ''}{pct:.1f}%",
            })

    return pd.DataFrame(rows)

