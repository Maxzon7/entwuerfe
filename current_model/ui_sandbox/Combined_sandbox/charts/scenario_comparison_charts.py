"""
Interactive Plotly (`plotly_dark`) visualizations for Scenario Comparison
(Current Situation vs. Scenario A vs. Scenario B — natively `1..N` ready for Stage 2)
in Sub-Tab 7 (`ui_sandbox/Combined_sandbox/charts/`).

Operates strictly on pre-computed `CombinedScenarioSnapshot` summary objects
with zero simulation overhead (< 20 ms).
"""

from typing import List, Optional, Sequence, Tuple
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..combined_sandbox_engine import (
    CombinedScenarioSnapshot,
    SCENARIO_COMPARISON_PALETTE,
    get_plotly_separators,
    normalize_scenario_list,
)

BASELINE_LINE_COLOR = "#F87171"

_MARKER_SYMBOLS: Tuple[str, ...] = (
    "circle",
    "diamond",
    "square",
    "triangle-up",
    "cross",
    "pentagon",
)


def _resolve_snapshot_currency(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> Tuple[str, str, str]:
    """Resolves `(currency_code, prefix_symbol, unit_label)` from available snapshots."""
    items = normalize_scenario_list(snap_a, snap_b, scenarios=scenarios)
    ref = items[0] if items else None
    curr = str(getattr(getattr(ref, "financial_config", None), "currency_code", "EUR") or "EUR")
    if curr == "EUR":
        return "EUR", "€", "€"
    if curr == "USD":
        return "USD", "$", "USD"
    return curr, f"{curr} ", curr


def _short_slot_label(slot_id: str, name: str, max_len: int = 24) -> str:
    """Formats a unique, concise axis/legend label for any scenario snapshot."""
    clean = (name or f"Scenario {slot_id}").strip()
    prefix = f"{slot_id}: "
    if clean.upper().startswith(f"SCENARIO {slot_id.upper()}:"):
        clean = clean[len(f"SCENARIO {slot_id}:"):].strip()
    elif clean.upper().startswith(f"{slot_id.upper()}:"):
        clean = clean[len(f"{slot_id}:"):].strip()
    label = f"{prefix}{clean}" if clean else f"Scenario {slot_id}"
    return (label[: max_len - 1] + "…") if len(label) > max_len else label


def _palette_style(idx: int) -> Tuple[str, str]:
    """Returns `(hex_color, marker_symbol)` for scenario index `idx`."""
    color = SCENARIO_COMPARISON_PALETTE[idx % len(SCENARIO_COMPARISON_PALETTE)]
    marker = _MARKER_SYMBOLS[idx % len(_MARKER_SYMBOLS)]
    return color, marker


def _apply_comparison_layout(
    fig: go.Figure,
    title_text: str,
    height: int,
    *,
    barmode: Optional[str] = None,
    margin_t: int = 128,
    margin_l: int = 58,
    legend_y: float = 1.08,
    hovermode: Optional[str] = None,
) -> None:
    """Applies unified dark Plotly theme, spacing, and top horizontal legend without title overlap."""
    layout_kwargs = dict(
        template="plotly_dark",
        separators=get_plotly_separators(),
        height=height,
        margin=dict(l=margin_l, r=25, t=max(margin_t, 120), b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(text=title_text, font=dict(size=15, color="#F8FAFC"), x=0.0, y=0.98, yanchor="top"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=legend_y,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
    )
    if barmode is not None:
        layout_kwargs["barmode"] = barmode
    if hovermode is not None:
        layout_kwargs["hovermode"] = hovermode
    fig.update_layout(**layout_kwargs)


def _empty_comparison_figure(
    title: str,
    height: int = 420,
    message: str = "Save Scenario A and/or Scenario B to render this comparison chart.",
) -> go.Figure:
    """Returns a styled empty Plotly placeholder figure when no matching snapshot exists."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=14, color="#94A3B8"),
    )
    _apply_comparison_layout(fig, title, height, margin_t=70)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _fin_snapshots(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> List[CombinedScenarioSnapshot]:
    """Filters ordered snapshots to those with Financials enabled."""
    return [
        s
        for s in normalize_scenario_list(snap_a, snap_b, scenarios=scenarios)
        if getattr(s.system_config, "enable_financials", False) and s.financial_kpis is not None
    ]


def create_ab_15y_tco_comparison_figure(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    height: int = 440,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> go.Figure:
    """
    Plots cumulative 15-Year Total Cost of Ownership (TCO) trajectories comparing
    Current Situation (dashed red) vs. all active scenarios, including Break-Even
    crossover markers and Battery Repowering step markers.
    """
    fin_snaps = _fin_snapshots(snap_a, snap_b, scenarios=scenarios)
    ref = next(
        (s for s in fin_snaps if s.cashflow_15y_df is not None and not s.cashflow_15y_df.empty),
        None,
    )
    if ref is None:
        return _empty_comparison_figure(
            "15-Year Cumulative TCO Comparison (Financials Disabled)",
            height=height,
            message="Enable Financials on at least one scenario to render 15-year TCO curves.",
        )

    _, curr_sym, c_lbl = _resolve_snapshot_currency(scenarios=fin_snaps)
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
            line=dict(color=BASELINE_LINE_COLOR, width=2.4, dash="dash"),
            marker=dict(size=5, color=BASELINE_LINE_COLOR),
            hovertemplate=f"Year %{{x}}<br>Current TCO: {curr_sym}%{{y:,.0f}}<extra></extra>",
        )
    )

    for idx_s, snap in enumerate(fin_snaps):
        if snap.cashflow_15y_df is None or snap.cashflow_15y_df.empty:
            continue
        color, marker_sym = _palette_style(idx_s)
        slot_id = snap.slot_id or str(idx_s + 1)
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
                    textposition="top left" if idx_s % 2 == 0 else "bottom right",
                    textfont=dict(color=color, size=11),
                    marker=dict(size=11, symbol="star", color=color, line=dict(color="#FFFFFF", width=1.2)),
                    hovertemplate=f"Break-Even {slot_id}: {pb_f:.1f} yrs<br>TCO at Crossover: {curr_sym}{y_cross:,.0f}<extra></extra>",
                )
            )

    fig.update_xaxes(title_text="Project Year (Year 0 = Upfront Net CAPEX)", dtick=1, gridcolor="rgba(148, 163, 184, 0.12)")
    fig.update_yaxes(title_text=f"Cumulative Total Cost ({c_lbl})", gridcolor="rgba(148, 163, 184, 0.12)", rangemode="tozero")
    _apply_comparison_layout(
        fig,
        f"15-Year Cumulative TCO & Break-Even Comparison ({c_lbl})",
        height,
        margin_t=85,
        margin_l=60,
        legend_y=1.03,
        hovermode="x unified",
    )
    return fig


def create_ab_annual_cost_stack_figure(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    height: int = 440,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> go.Figure:
    """
    Creates a stacked Year-1 annual cost breakdown comparing Current Situation vs.
    all financial scenarios across the 4 Tariff Pillars, Overload Penalties,
    Solar/BESS O&M, Generator OPEX, and Solar Export Feed-in Credit.
    """
    fin_snaps = _fin_snapshots(snap_a, snap_b, scenarios=scenarios)
    if not fin_snaps:
        return _empty_comparison_figure(
            "Year-1 Annual Cost Structure Comparison (Financials Disabled)",
            height=height,
            message="Enable Financials on at least one scenario to inspect Year-1 cost stacks.",
        )

    ref = fin_snaps[0]
    _, curr_sym, c_lbl = _resolve_snapshot_currency(scenarios=fin_snaps)
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

    for idx_s, snap in enumerate(fin_snaps):
        fk = snap.financial_kpis
        slot_id = snap.slot_id or str(idx_s + 1)
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

    fig.update_yaxes(
        title_text=f"Annual Cost / Credit ({c_lbl}/yr)",
        gridcolor="rgba(148, 163, 184, 0.12)",
        zeroline=True,
        zerolinecolor="rgba(248, 250, 252, 0.35)",
    )
    _apply_comparison_layout(
        fig,
        f"Year-1 Annual Cost Structure: Current vs. Scenarios ({c_lbl}/yr)",
        height,
        barmode="relative",
        margin_t=90,
        margin_l=60,
        legend_y=1.03,
        hovermode="x unified",
    )
    return fig


def create_ab_supply_and_utilization_figure(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    height: int = 420,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> go.Figure:
    """
    2-Panel technical comparison figure (`1..N` scenarios):
      - Left: 100% stacked bar chart of Annual Electricity Supply Mix (%)
      - Right: Grouped bar chart of Grid Peak vs. Limit (%) and Component Utilization (%)
    """
    items = normalize_scenario_list(snap_a, snap_b, scenarios=scenarios)
    if not items:
        return _empty_comparison_figure("Electricity Supply Mix & Asset Utilization Comparison", height=height)
    ref = items[0]

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

    x_mix: List[str] = ["Current Situation"]
    g_pcts: List[float] = [100.0]
    s_pcts: List[float] = [0.0]
    b_pcts: List[float] = [0.0]
    gen_pcts: List[float] = [0.0]

    for idx_s, snap in enumerate(items):
        u = snap.utilization_diagnostics
        slot_id = snap.slot_id or str(idx_s + 1)
        x_mix.append(_short_slot_label(slot_id, snap.name, max_len=20))
        g_pcts.append(round(float(u.grid_direct_pct), 1))
        s_pcts.append(round(float(u.solar_direct_pct), 1))
        b_pcts.append(round(float(u.battery_discharge_pct), 1))
        gen_pcts.append(round(float(u.generator_direct_pct), 1))

    for name, vals, color in [
        ("Grid Import (%)", g_pcts, "#60A5FA"),
        ("Solar Direct (%)", s_pcts, "#FACC15"),
        ("Battery Discharge (%)", b_pcts, "#22C55E"),
        ("Generator (%)", gen_pcts, "#F97316"),
    ]:
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
            marker_color=BASELINE_LINE_COLOR,
            offsetgroup="util_cur",
            legendgroup="util",
            hovertemplate="Current Situation<br>%{x}: %{y:.1f}%<extra></extra>",
        ),
        row=1,
        col=2,
    )

    for idx_s, snap in enumerate(items):
        color, _ = _palette_style(idx_s)
        slot_id = snap.slot_id or str(idx_s + 1)
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
                offsetgroup=f"util_{idx_s}",
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
    _apply_comparison_layout(
        fig,
        "Electricity Supply Mix & Component Utilization Comparison",
        height,
        barmode="relative",
        margin_l=55,
    )
    return fig


def create_ab_monthly_peak_and_grid_import_figure(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    height: int = 460,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> go.Figure:
    """
    2-Row seasonal comparison (`1..N` scenarios):
      - Top: Monthly Grid Peak Demand (kW) vs. Grid Connection Limit
      - Bottom: Monthly Residual Grid Energy Imported (MWh/mo)
    """
    items = normalize_scenario_list(snap_a, snap_b, scenarios=scenarios)
    ref = next(
        (s for s in items if s.monthly_balance_df is not None and not s.monthly_balance_df.empty),
        None,
    )
    if ref is None:
        return _empty_comparison_figure("Monthly Grid Peak Shaving & Residual Grid Import", height=height)

    base_df = ref.monthly_balance_df
    months = base_df["Month"].tolist()
    base_peaks = base_df["Current situation Peak (kW)"].tolist()
    base_import_mwh = [float(v) / 1000.0 for v in base_df["Consumption (kWh)"].tolist()]
    grid_limit_kw = float(ref.system_config.grid_limit_kw)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        row_heights=[0.52, 0.48],
        subplot_titles=(
            "1. Monthly Peak Grid Demand vs. Connection Limit (kW)",
            "2. Monthly Residual Grid Energy Imported (MWh/month)",
        ),
    )

    fig.add_trace(
        go.Scatter(
            x=months,
            y=base_peaks,
            mode="lines+markers",
            name="Current Situation Peak",
            line=dict(color=BASELINE_LINE_COLOR, width=2.2, dash="dash"),
            marker=dict(size=5, color=BASELINE_LINE_COLOR),
            legendgroup="cur",
            hovertemplate="%{x}<br>Current Peak: %{y:,.1f} kW<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=months,
            y=base_import_mwh,
            name="Current Grid Import (MWh)",
            marker_color="rgba(248, 113, 113, 0.45)",
            legendgroup="cur",
            hovertemplate="%{x}<br>Current Import: %{y:,.1f} MWh<extra></extra>",
        ),
        row=2,
        col=1,
    )

    for idx_s, snap in enumerate(items):
        if snap.monthly_balance_df is None or snap.monthly_balance_df.empty:
            continue
        color, marker_sym = _palette_style(idx_s)
        slot_id = snap.slot_id or str(idx_s + 1)
        lbl = _short_slot_label(slot_id, snap.name, max_len=24)
        df_s = snap.monthly_balance_df
        m_s = df_s["Month"].tolist()
        peaks_s = df_s["Combined Grid Peak (kW)"].tolist()
        imp_mwh_s = [float(v) / 1000.0 for v in df_s["Combined Grid Import (kWh)"].tolist()]

        fig.add_trace(
            go.Scatter(
                x=m_s,
                y=peaks_s,
                mode="lines+markers",
                name=f"{lbl} Peak",
                line=dict(color=color, width=2.6),
                marker=dict(size=6, symbol=marker_sym, color=color),
                legendgroup=f"sc_{idx_s}",
                hovertemplate=f"{lbl} %{{x}}<br>Peak: %{{y:,.1f}} kW<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Bar(
                x=m_s,
                y=imp_mwh_s,
                name=f"{lbl} Import",
                marker_color=color,
                legendgroup=f"sc_{idx_s}",
                hovertemplate=f"{lbl} %{{x}}<br>Grid Import: %{{y:,.1f}} MWh<extra></extra>",
            ),
            row=2,
            col=1,
        )

    fig.add_hline(
        y=grid_limit_kw,
        row=1,
        col=1,
        line_dash="dot",
        line_color="#FACC15",
        line_width=1.6,
        annotation_text=f"Grid Limit ({grid_limit_kw:,.0f} kW)",
        annotation_position="top right",
        annotation_font_color="#FDE047",
    )

    fig.update_yaxes(title_text="Monthly Peak (kW)", rangemode="tozero", gridcolor="rgba(148, 163, 184, 0.12)", row=1, col=1)
    fig.update_yaxes(title_text="Grid Import (MWh)", rangemode="tozero", gridcolor="rgba(148, 163, 184, 0.12)", row=2, col=1)
    fig.update_xaxes(gridcolor="rgba(148, 163, 184, 0.08)", row=2, col=1)
    _apply_comparison_layout(
        fig,
        "Monthly Grid Peak Shaving & Residual Grid Import Comparison",
        height,
        barmode="group",
        legend_y=1.05,
        hovermode="x unified",
    )
    return fig


def create_ab_energy_flow_balance_figure(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    height: int = 430,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> go.Figure:
    """
    2-Panel absolute annual energy comparison (`1..N` scenarios, MWh/yr):
      - Left: Stacked Demand Coverage (`Grid Direct + Solar Direct + Battery Discharge + Generator`)
      - Right: Grouped Energy Volume Comparison (`Total Grid Import vs. Solar On-Site vs. Export vs. BESS Discharged`)
    """
    items = normalize_scenario_list(snap_a, snap_b, scenarios=scenarios)
    if not items:
        return _empty_comparison_figure("Annual Energy Flow & Solar Utilization Balance", height=height)
    ref = items[0]
    cons_mwh = float(ref.kpis.annual_consumption_kwh) / 1000.0

    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.46, 0.54],
        horizontal_spacing=0.11,
        subplot_titles=(
            "1. Annual Load Coverage Breakdown (MWh/yr)",
            "2. Grid Import vs. Solar Allocation & BESS Flow (MWh/yr)",
        ),
    )

    x_cov: List[str] = ["Current Situation"]
    g_cov: List[float] = [round(cons_mwh, 1)]
    s_cov: List[float] = [0.0]
    b_cov: List[float] = [0.0]
    gen_cov: List[float] = [0.0]

    for idx_s, snap in enumerate(items):
        slot_id = snap.slot_id or str(idx_s + 1)
        x_cov.append(_short_slot_label(slot_id, snap.name, max_len=20))
        u = snap.utilization_diagnostics
        c_s_mwh = float(snap.kpis.annual_consumption_kwh) / 1000.0
        g_cov.append(round((float(u.grid_direct_pct) / 100.0) * c_s_mwh, 1))
        s_cov.append(round((float(u.solar_direct_pct) / 100.0) * c_s_mwh, 1))
        b_cov.append(round((float(u.battery_discharge_pct) / 100.0) * c_s_mwh, 1))
        gen_cov.append(round((float(u.generator_direct_pct) / 100.0) * c_s_mwh, 1))

    for name, vals, color in [
        ("Grid Direct to Load (MWh)", g_cov, "#60A5FA"),
        ("Solar Direct to Load (MWh)", s_cov, "#FACC15"),
        ("Battery Discharge to Load (MWh)", b_cov, "#22C55E"),
        ("Generator to Load (MWh)", gen_cov, "#F97316"),
    ]:
        fig.add_trace(
            go.Bar(
                name=name,
                x=x_cov,
                y=vals,
                marker_color=color,
                offsetgroup="cov",
                legendgroup="cov",
                hovertemplate=f"%{{x}}<br>{name}: %{{y:,.1f}} MWh/yr<extra></extra>",
            ),
            row=1,
            col=1,
        )

    flow_metrics = [
        "Total Grid Import",
        "Solar On-Site (Dir + BESS)",
        "Solar Export Surplus",
        "Total BESS Discharge",
    ]
    fig.add_trace(
        go.Bar(
            name="Current Situation",
            x=flow_metrics,
            y=[round(cons_mwh, 1), 0.0, 0.0, 0.0],
            marker_color=BASELINE_LINE_COLOR,
            offsetgroup="flow_cur",
            legendgroup="flow",
            hovertemplate="Current Situation<br>%{x}: %{y:,.1f} MWh/yr<extra></extra>",
        ),
        row=1,
        col=2,
    )

    for idx_s, snap in enumerate(items):
        color, _ = _palette_style(idx_s)
        slot_id = snap.slot_id or str(idx_s + 1)
        lbl = _short_slot_label(slot_id, snap.name, max_len=24)
        k = snap.kpis
        y_flow = [
            round(float(k.grid_import_total_kwh) / 1000.0, 1),
            round((float(k.solar_direct_kwh) + float(k.solar_via_battery_kwh)) / 1000.0, 1),
            round(float(k.solar_export_kwh) / 1000.0, 1),
            round(float(k.battery_total_discharged_kwh) / 1000.0, 1),
        ]
        fig.add_trace(
            go.Bar(
                name=lbl,
                x=flow_metrics,
                y=y_flow,
                marker_color=color,
                offsetgroup=f"flow_{idx_s}",
                legendgroup="flow",
                hovertemplate=f"{lbl}<br>%{{x}}: %{{y:,.1f}} MWh/yr<extra></extra>",
            ),
            row=1,
            col=2,
        )

    fig.update_yaxes(title_text="Annual Energy (MWh/yr)", rangemode="tozero", gridcolor="rgba(148, 163, 184, 0.12)", row=1, col=1)
    fig.update_yaxes(title_text="Energy Volume (MWh/yr)", rangemode="tozero", gridcolor="rgba(148, 163, 184, 0.12)", row=1, col=2)
    _apply_comparison_layout(
        fig,
        "Annual Energy Flow & Solar Allocation Balance (MWh/yr)",
        height,
        barmode="relative",
        margin_l=55,
    )
    return fig


def create_ab_capex_vs_opex_shift_figure(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    height: int = 440,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> go.Figure:
    """
    2-Panel investment & 15-Year value structure (`1..N` financial scenarios):
      - Left: Stacked 15-Year Cost Composition (Upfront Net CAPEX + Battery Repowering + 15-Yr Cumulative OPEX)
      - Right: Grouped Upfront Investment vs. Avoided Grid Upgrade & 15-Yr Net TCO Advantage
    """
    fin_snaps = _fin_snapshots(snap_a, snap_b, scenarios=scenarios)
    if not fin_snaps:
        return _empty_comparison_figure(
            "CAPEX vs. 15-Year OPEX Shift Comparison (Financials Disabled)",
            height=height,
            message="Enable Financials on at least one scenario to compare CAPEX vs. 15-year OPEX shifts.",
        )

    ref = fin_snaps[0]
    ref_fk = ref.financial_kpis
    _, curr_sym, c_lbl = _resolve_snapshot_currency(scenarios=fin_snaps)

    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.48, 0.52],
        horizontal_spacing=0.11,
        subplot_titles=(
            f"1. 15-Year Cost Shift: CAPEX vs. OPEX ({c_lbl})",
            f"2. Investment vs. 15-Year Value Created ({c_lbl})",
        ),
    )

    x_shift: List[str] = ["Current Situation"]
    capex_vals: List[float] = [0.0]
    repower_vals: List[float] = [0.0]
    opex15_vals: List[float] = [float(ref_fk.tco_15y_baseline_eur)]
    tco_markers: List[float] = [float(ref_fk.tco_15y_baseline_eur)]

    for idx_s, snap in enumerate(fin_snaps):
        fk = snap.financial_kpis
        slot_id = snap.slot_id or str(idx_s + 1)
        x_shift.append(_short_slot_label(slot_id, snap.name, max_len=20))
        cap_v = float(fk.total_capex_eur)
        rep_v = float(fk.battery_augmentation_eur) if snap.system_config.enable_battery else 0.0
        tco_v = float(fk.tco_15y_combined_eur)
        capex_vals.append(cap_v)
        repower_vals.append(rep_v)
        opex15_vals.append(tco_v - cap_v - rep_v)
        tco_markers.append(tco_v)

    for name, vals, color in [
        ("Upfront Net CAPEX", capex_vals, "#38BDF8"),
        ("Battery Repowering (Yr 8-12)", repower_vals, "#F59E0B"),
        ("15-Yr Cumulative Net OPEX", opex15_vals, "#6366F1"),
    ]:
        fig.add_trace(
            go.Bar(
                name=name,
                x=x_shift,
                y=vals,
                marker_color=color,
                offsetgroup="tco_shift",
                legendgroup="tco_shift",
                hovertemplate=f"%{{x}}<br>{name}: {curr_sym}%{{y:,.0f}}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Scatter(
            name="15-Year Total TCO",
            x=x_shift,
            y=tco_markers,
            mode="markers+text",
            text=[f"{curr_sym}{v / 1000.0:,.0f}k" for v in tco_markers],
            textposition="top center",
            textfont=dict(color="#F8FAFC", size=10),
            marker=dict(size=9, symbol="diamond", color="#FFFFFF", line=dict(color="#0F172A", width=1.4)),
            legendgroup="tco_shift",
            hovertemplate=f"%{{x}}<br>15Y TCO: {curr_sym}%{{y:,.0f}}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    val_metrics = [
        "Upfront Net CAPEX",
        "Avoided Grid Upgrade",
        "15Y Gross OPEX Saved",
        "15Y Net TCO Savings",
    ]
    for idx_s, snap in enumerate(fin_snaps):
        color, _ = _palette_style(idx_s)
        slot_id = snap.slot_id or str(idx_s + 1)
        lbl = _short_slot_label(slot_id, snap.name, max_len=24)
        fk = snap.financial_kpis
        rep_v = float(fk.battery_augmentation_eur) if snap.system_config.enable_battery else 0.0
        opex_15_s = float(fk.tco_15y_combined_eur) - float(fk.total_capex_eur) - rep_v
        y_val = [
            float(fk.total_capex_eur),
            float(fk.avoided_grid_upgrade_capex_eur),
            float(fk.tco_15y_baseline_eur) - opex_15_s,
            float(fk.tco_15y_baseline_eur) - float(fk.tco_15y_combined_eur),
        ]
        fig.add_trace(
            go.Bar(
                name=lbl,
                x=val_metrics,
                y=y_val,
                marker_color=color,
                offsetgroup=f"val_{idx_s}",
                legendgroup="val",
                hovertemplate=f"{lbl}<br>%{{x}}: {curr_sym}%{{y:,.0f}}<extra></extra>",
            ),
            row=1,
            col=2,
        )

    fig.update_yaxes(title_text=f"15-Year Cumulative Spend ({c_lbl})", rangemode="tozero", gridcolor="rgba(148, 163, 184, 0.12)", row=1, col=1)
    fig.update_yaxes(
        title_text=f"Capital / 15-Year Value ({c_lbl})",
        gridcolor="rgba(148, 163, 184, 0.12)",
        zeroline=True,
        zerolinecolor="rgba(248, 250, 252, 0.35)",
        row=1,
        col=2,
    )
    _apply_comparison_layout(
        fig,
        f"Capital Expenditure vs. 15-Year OPEX Shift & Value Created ({c_lbl})",
        height,
        barmode="relative",
        margin_l=60,
    )
    return fig
