"""
Interactive Plotly (`plotly_dark`) visualizations for Scenario A vs. Scenario B vs.
Current Situation comparison in Sub-Tab 7 (`ui_sandbox/Combined_sandbox/charts/`).

Operates strictly on pre-computed `CombinedScenarioSnapshot` summary objects
with zero simulation overhead (< 20 ms).
"""

from typing import List, Optional, Tuple
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..combined_sandbox_engine import CombinedScenarioSnapshot


def _resolve_snapshot_currency(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
) -> Tuple[str, str, str]:
    """Resolves `(currency_code, prefix_symbol, unit_label)` from available snapshots."""
    ref = snap_a if snap_a is not None else snap_b
    curr = str(getattr(getattr(ref, "financial_config", None), "currency_code", "EUR") or "EUR")
    if curr == "EUR":
        return "EUR", "€", "€"
    if curr == "USD":
        return "USD", "$", "USD"
    return curr, f"{curr} ", curr


def _short_slot_label(slot_id: str, name: str, max_len: int = 24) -> str:
    """Formats a unique, concise x-axis label for Scenario A / Scenario B."""
    clean = (name or f"Scenario {slot_id}").strip()
    prefix = f"{slot_id}: "
    if clean.upper().startswith(f"SCENARIO {slot_id}:"):
        clean = clean[len(f"SCENARIO {slot_id}:"):].strip()
    elif clean.upper().startswith(f"{slot_id}:"):
        clean = clean[len(f"{slot_id}:"):].strip()
    label = f"{prefix}{clean}" if clean else f"Scenario {slot_id}"
    return (label[: max_len - 1] + "…") if len(label) > max_len else label


def _empty_comparison_figure(title: str, height: int = 420) -> go.Figure:
    """Returns a styled empty Plotly placeholder figure when no snapshot is stored."""
    fig = go.Figure()
    fig.add_annotation(
        text="Save Scenario A and/or Scenario B to render this comparison chart.",
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=14, color="#94A3B8"),
    )
    fig.update_layout(
        template="plotly_dark",
        height=height,
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(text=title, font=dict(size=15, color="#F8FAFC"), x=0.0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def create_ab_15y_tco_comparison_figure(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
    height: int = 440,
) -> go.Figure:
    """
    Plots cumulative 15-Year Total Cost of Ownership (TCO) trajectories comparing
    Current Situation (dashed red) vs. Scenario A (solid blue) vs. Scenario B (solid emerald),
    including Break-Even intersection markers and Battery Repowering step markers.
    """
    ref = snap_a if snap_a is not None else snap_b
    if ref is None or ref.cashflow_15y_df is None or ref.cashflow_15y_df.empty:
        return _empty_comparison_figure("15-Year Cumulative TCO Comparison", height=height)

    curr, curr_sym, c_lbl = _resolve_snapshot_currency(snap_a, snap_b)
    base_df = ref.cashflow_15y_df
    years_base = base_df["Year"].tolist()
    tco_base = base_df["Cumulative TCO Current situation (€)"].tolist()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=years_base,
            y=tco_base,
            mode="lines+markers",
            name="Current Situation (Baseline)",
            line=dict(color="#F87171", width=2.4, dash="dash"),
            marker=dict(size=5, color="#F87171"),
            hovertemplate=f"Year %{{x}}<br>Current TCO: {curr_sym}%{{y:,.0f}}<extra></extra>",
        )
    )

    slot_specs = [
        ("A", snap_a, "#38BDF8", "circle"),
        ("B", snap_b, "#10B981", "diamond"),
    ]
    for idx_s, (slot_id, snap, color, marker_sym) in enumerate(slot_specs):
        if snap is None or snap.cashflow_15y_df is None or snap.cashflow_15y_df.empty:
            continue
        df_s = snap.cashflow_15y_df
        yrs_s = df_s["Year"].tolist()
        tco_s = df_s["Cumulative TCO Combined system (€)"].tolist()
        lbl = _short_slot_label(slot_id, snap.name, max_len=34)

        fig.add_trace(
            go.Scatter(
                x=yrs_s,
                y=tco_s,
                mode="lines+markers",
                name=lbl,
                line=dict(color=color, width=3.0),
                marker=dict(size=6, symbol=marker_sym, color=color),
                hovertemplate=f"{lbl}<br>Year %{{x}}<br>Cumulative TCO: {curr_sym}%{{y:,.0f}}<extra></extra>",
            )
        )

        # Highlight Battery Repowering step if active inside Years 1..15
        fin_cfg = snap.financial_config
        fk = snap.financial_kpis
        if (
            snap.system_config.enable_battery
            and fin_cfg.enable_battery_augmentation
            and fk.battery_augmentation_eur > 0.0
        ):
            aug_yr = int(fin_cfg.battery_augmentation_year)
            if aug_yr in yrs_s:
                pos_idx = yrs_s.index(aug_yr)
                fig.add_trace(
                    go.Scatter(
                        x=[aug_yr],
                        y=[tco_s[pos_idx]],
                        mode="markers",
                        name=f"{slot_id} Repowering (Yr {aug_yr})",
                        marker=dict(
                            size=11,
                            symbol="triangle-up",
                            color="#F59E0B",
                            line=dict(color=color, width=1.5),
                        ),
                        hovertemplate=(
                            f"{slot_id} Battery Repowering (Yr {aug_yr})<br>"
                            f"Cost: +{curr_sym}{fk.battery_augmentation_eur:,.0f}<br>"
                            f"Cumulative TCO: {curr_sym}{tco_s[pos_idx]:,.0f}<extra></extra>"
                        ),
                    )
                )

        # Break-Even crossover marker where Scenario TCO drops below Current Situation TCO
        pb = fk.payback_years
        if pb is not None and 0.0 < float(pb) <= 15.0 and len(years_base) > 1:
            pb_f = float(pb)
            y_cross = float(np.interp(pb_f, years_base, tco_base))
            fig.add_trace(
                go.Scatter(
                    x=[pb_f],
                    y=[y_cross],
                    mode="markers+text",
                    name=f"Break-Even {slot_id} ({pb_f:.1f} yrs)",
                    text=[f"BE {slot_id}: {pb_f:.1f}y"],
                    textposition="top left" if idx_s == 0 else "bottom right",
                    textfont=dict(color=color, size=11),
                    marker=dict(size=11, symbol="star", color=color, line=dict(color="#FFFFFF", width=1.2)),
                    hovertemplate=f"Break-Even {slot_id}: {pb_f:.1f} yrs<br>TCO at Crossover: {curr_sym}{y_cross:,.0f}<extra></extra>",
                )
            )

    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=60, r=25, t=85, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text=f"15-Year Cumulative TCO & Break-Even Comparison ({c_lbl})",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        xaxis=dict(
            title="Project Year (Year 0 = Upfront Net CAPEX)",
            dtick=1,
            gridcolor="rgba(148, 163, 184, 0.12)",
        ),
        yaxis=dict(
            title=f"Cumulative Total Cost ({c_lbl})",
            gridcolor="rgba(148, 163, 184, 0.12)",
            rangemode="tozero",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        hovermode="x unified",
    )
    return fig


def create_ab_annual_cost_stack_figure(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
    height: int = 440,
) -> go.Figure:
    """
    Creates a stacked Year-1 annual cost breakdown comparing Current Situation vs.
    Scenario A vs. Scenario B across all 4 Tariff Pillars, Overload Penalties,
    Solar/BESS O&M, Generator OPEX, and Solar Export Feed-in Credit.
    """
    ref = snap_a if snap_a is not None else snap_b
    if ref is None:
        return _empty_comparison_figure("Year-1 Annual Cost Structure Comparison", height=height)

    curr, curr_sym, c_lbl = _resolve_snapshot_currency(snap_a, snap_b)
    ref_fk = ref.financial_kpis

    x_labels: List[str] = ["Current Situation"]
    p1_vals: List[float] = [float(ref_fk.baseline_pillar1_supply_eur)]
    p2_dso_vals: List[float] = [max(0.0, float(ref_fk.baseline_pillar2_dso_eur) - float(ref_fk.baseline_penalty_cost_eur))]
    p2_pen_vals: List[float] = [float(ref_fk.baseline_penalty_cost_eur)]
    p34_vals: List[float] = [float(ref_fk.baseline_pillar3_metering_eur) + float(ref_fk.baseline_pillar4_taxes_eur)]
    om_sol_bat_vals: List[float] = [0.0]
    gen_opex_vals: List[float] = [0.0]
    export_credit_vals: List[float] = [0.0]
    net_total_vals: List[float] = [float(ref_fk.baseline_total_opex_eur)]

    for slot_id, snap in [("A", snap_a), ("B", snap_b)]:
        if snap is None:
            continue
        fk = snap.financial_kpis
        x_labels.append(_short_slot_label(slot_id, snap.name, max_len=28))
        p1_vals.append(float(fk.combined_pillar1_supply_eur))
        p2_dso_vals.append(max(0.0, float(fk.combined_pillar2_dso_eur) - float(fk.combined_grid_penalty_cost_eur)))
        p2_pen_vals.append(float(fk.combined_grid_penalty_cost_eur))
        p34_vals.append(float(fk.combined_pillar3_metering_eur) + float(fk.combined_pillar4_taxes_eur))
        om_sol_bat_vals.append(float(fk.solar_om_eur) + float(fk.battery_om_eur))
        gen_opex_vals.append(float(fk.generator_total_opex_eur))
        export_credit_vals.append(-float(fk.solar_export_revenue_eur))
        net_total_vals.append(float(fk.total_annual_opex_eur))

    fig = go.Figure()
    bar_specs = [
        ("Pillar 1: Energy Supply", p1_vals, "#3B82F6"),
        ("Pillar 2: Grid Network (DSO)", p2_dso_vals, "#0EA5E9"),
        ("Pillar 2: Overload Penalties", p2_pen_vals, "#EF4444"),
        ("Pillar 3 & 4: Metering & Taxes", p34_vals, "#A855F7"),
        ("Solar & Battery O&M", om_sol_bat_vals, "#F59E0B"),
        ("Generator OPEX (Fuel/Maint/Rent)", gen_opex_vals, "#FB923C"),
        ("Solar Export Credit", export_credit_vals, "#10B981"),
    ]
    for name, vals, color in bar_specs:
        fig.add_trace(
            go.Bar(
                name=name,
                x=x_labels,
                y=vals,
                marker_color=color,
                hovertemplate=f"%{{x}}<br>{name}: {curr_sym}%{{y:,.0f}}/yr<extra></extra>",
            )
        )

    fig.add_trace(
        go.Scatter(
            name="Net Annual Operating Cost",
            x=x_labels,
            y=net_total_vals,
            mode="markers+text",
            text=[f"{curr_sym}{v:,.0f}" for v in net_total_vals],
            textposition="top center",
            textfont=dict(color="#F8FAFC", size=11),
            marker=dict(size=10, symbol="diamond", color="#FFFFFF", line=dict(color="#0F172A", width=1.5)),
            hovertemplate=f"%{{x}}<br>Net Annual Cost: {curr_sym}%{{y:,.0f}}/yr<extra></extra>",
        )
    )

    fig.update_layout(
        barmode="relative",
        template="plotly_dark",
        height=height,
        margin=dict(l=60, r=25, t=90, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text=f"Year-1 Annual Cost Structure: Current vs. Scenario A vs. Scenario B ({c_lbl}/yr)",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        yaxis=dict(
            title=f"Annual Cost / Credit ({c_lbl}/yr)",
            gridcolor="rgba(148, 163, 184, 0.12)",
            zeroline=True,
            zerolinecolor="rgba(248, 250, 252, 0.35)",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        hovermode="x unified",
    )
    return fig


def create_ab_supply_and_utilization_figure(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
    height: int = 420,
) -> go.Figure:
    """
    2-Panel comparison figure:
      - Left: 100% stacked bar chart of Annual Electricity Supply Mix (%)
      - Right: Grouped bar chart of Grid Peak vs. Limit (%) and Component Utilization (%)
    """
    ref = snap_a if snap_a is not None else snap_b
    if ref is None:
        return _empty_comparison_figure("Electricity Supply Mix & Asset Utilization Comparison", height=height)

    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.46, 0.54],
        horizontal_spacing=0.11,
        subplot_titles=(
            "1. Annual Electricity Supply Split (%)",
            "2. Grid Peak vs. Limit & Asset Utilization (%)",
        ),
    )

    # Panel 1: Supply Mix (%) using offsetgroup="mix" so it stacks cleanly in row=1, col=1
    x_mix: List[str] = ["Current Situation"]
    g_pcts: List[float] = [100.0]
    s_pcts: List[float] = [0.0]
    b_pcts: List[float] = [0.0]
    gen_pcts: List[float] = [0.0]

    for slot_id, snap in [("A", snap_a), ("B", snap_b)]:
        if snap is None:
            continue
        u = snap.utilization_diagnostics
        x_mix.append(_short_slot_label(slot_id, snap.name, max_len=20))
        g_pcts.append(round(float(u.grid_direct_pct), 1))
        s_pcts.append(round(float(u.solar_direct_pct), 1))
        b_pcts.append(round(float(u.battery_discharge_pct), 1))
        gen_pcts.append(round(float(u.generator_direct_pct), 1))

    mix_traces = [
        ("Grid Import (%)", g_pcts, "#60A5FA"),
        ("Solar Direct (%)", s_pcts, "#FACC15"),
        ("Battery Discharge (%)", b_pcts, "#22C55E"),
        ("Generator (%)", gen_pcts, "#F97316"),
    ]
    for name, vals, color in mix_traces:
        fig.add_trace(
            go.Bar(
                name=name,
                x=x_mix,
                y=vals,
                marker_color=color,
                offsetgroup="mix",
                legendgroup="mix",
                hovertemplate=f"%{{x}}<br>{name}: %{{y:.1f}}%<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # Panel 2: Grouped Utilization (%) using distinct offsetgroups per scenario
    util_metrics = [
        "Grid Peak (% of Limit)",
        "Solar Yield Used (%)",
        "BESS Capacity Used (%)",
        "Generator Power Used (%)",
    ]
    ref_grid_lim = max(1.0, float(ref.system_config.grid_limit_kw))
    cur_peak_pct = round((float(ref.kpis.original_peak_kw) / ref_grid_lim) * 100.0, 1)
    fig.add_trace(
        go.Bar(
            name="Current Situation",
            x=util_metrics,
            y=[cur_peak_pct, 0.0, 0.0, 0.0],
            marker_color="#F87171",
            offsetgroup="util_cur",
            legendgroup="util",
            hovertemplate="Current Situation<br>%{x}: %{y:.1f}%<extra></extra>",
        ),
        row=1,
        col=2,
    )

    for slot_id, snap, color in [("A", snap_a, "#38BDF8"), ("B", snap_b, "#10B981")]:
        if snap is None:
            continue
        u = snap.utilization_diagnostics
        lbl = _short_slot_label(slot_id, snap.name, max_len=24)
        y_util = [
            round(float(u.grid_utilization_pct), 1),
            round(float(u.solar_utilization_pct) if u.solar_enabled else 0.0, 1),
            round(float(u.bess_capacity_utilization_pct) if u.bess_enabled else 0.0, 1),
            round(float(u.gen_power_utilization_pct) if u.gen_enabled else 0.0, 1),
        ]
        fig.add_trace(
            go.Bar(
                name=lbl,
                x=util_metrics,
                y=y_util,
                marker_color=color,
                offsetgroup=f"util_{slot_id}",
                legendgroup="util",
                hovertemplate=f"{lbl}<br>%{{x}}: %{{y:.1f}}%<extra></extra>",
            ),
            row=1,
            col=2,
        )

    fig.add_hline(
        y=100.0,
        row=1,
        col=2,
        line_dash="dash",
        line_color="#EF4444",
        line_width=1.4,
        annotation_text="100% Grid Limit / Capacity",
        annotation_position="top right",
        annotation_font_color="#FCA5A5",
    )

    fig.update_yaxes(title_text="Share of Annual Consumption (%)", range=[0, 105], gridcolor="rgba(148, 163, 184, 0.12)", row=1, col=1)
    fig.update_yaxes(title_text="Utilization / Peak Ratio (%)", rangemode="tozero", gridcolor="rgba(148, 163, 184, 0.12)", row=1, col=2)

    fig.update_layout(
        barmode="relative",
        template="plotly_dark",
        height=height,
        margin=dict(l=55, r=25, t=95, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text="Electricity Supply Mix & Component Utilization Comparison",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
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
    )
    return fig
