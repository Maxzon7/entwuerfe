"""
DRACBV Combined System Feasibility Study PDF Report Builder (`pdf_report/report_builder.py`).

Collects active simulation KPIs, light-mode chart snapshots, 4-Pillar financial ledgers,
15-year cashflows, and optional Scenario A vs. B comparison findings into a structured,
DRACBV-branded A4 PDF compiled via WeasyPrint.
"""

from dataclasses import dataclass
import datetime
from typing import Dict, List, Optional

import weasyprint

from ..combined_sandbox_engine import (
    RULE1_OPTIONS,
    RULE2_OPTIONS,
    RULE3_OPTIONS,
    CombinedFinancialConfig,
    CombinedScenarioSnapshot,
    CombinedSimulationResult,
    build_segmented_comparison_tables,
    compute_incremental_bwl_evaluation,
    evaluate_combined_financials,
    fmt_num,
    format_currency_value,
)
from .chart_snapshots import collect_report_chart_data_uris
from .templates_and_css import (
    esc,
    render_data_table,
    render_kpi_grid,
    wrap_html_document,
)


@dataclass
class PdfReportOptions:
    """Configuration options controlling optional sections of the PDF Feasibility Study."""

    site_name: str = "Commercial Energy Facility"
    include_charts: bool = True
    include_15y_cashflow: bool = True
    include_scenario_comparison: bool = True


def _build_cover_and_config_section(
    sim_res: CombinedSimulationResult,
    opts: PdfReportOptions,
) -> str:
    """Builds the Page 1 DRACBV letterhead header, metadata strip, and system brief."""
    cfg = sim_res.system_config
    rules = sim_res.rules_config
    kpis = sim_res.kpis
    fin_cfg = sim_res.financial_config
    curr = str(getattr(fin_cfg, "currency_code", "EUR") or "EUR") if cfg.enable_financials else "N/A (Financials Off)"
    generated_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    active_mods: List[str] = ["Grid Connection"]
    if cfg.enable_solar:
        active_mods.append(f"Solar PV ({fmt_num(sim_res.solar_derivation.installed_kwp, 1)} kWp)")
    if cfg.enable_battery:
        active_mods.append(f"BESS ({fmt_num(cfg.battery_capacity_kwh, 0)} kWh / {fmt_num(cfg.battery_power_kw, 0)} kW)")
    if cfg.enable_generator:
        active_mods.append(f"Generator ({fmt_num(cfg.generator_rated_kw, 0)} kW {cfg.fuel_type})")

    cover_html = (
        '<div class="cover-header">'
        '<div class="cover-title-col">'
        '<div class="report-eyebrow">Feasibility Study Report</div>'
        '<h1 class="report-title">Combined Energy System &amp; Peak-Shaving Assessment</h1>'
        f'<p class="report-subtitle">Technical Dispatch &amp; 15-Year Financial Evaluation — {esc(opts.site_name)}</p>'
        '<div class="meta-strip">'
        f'<strong>Generated:</strong> {esc(generated_str)} &nbsp;|&nbsp; '
        f'<strong>Grid Limit:</strong> {fmt_num(cfg.grid_limit_kw, 0)} kW &nbsp;|&nbsp; '
        f'<strong>Currency:</strong> {esc(curr)}<br>'
        f'<strong>Active Configuration:</strong> {esc(" + ".join(active_mods))}'
        "</div>"
        "</div>"
        '<div class="cover-contact-col">'
        "<strong>DRACBV Green Energy Solutions</strong><br>"
        "Oud-Loosdrechtsedijk 254<br>"
        "1231 NJ Loosdrecht<br>"
        "+31 (0)20 213 77 70<br>"
        "projecten@dracbv.nl &nbsp;|&nbsp; www.dracbv.nl<br>"
        "IBAN: NL98 INGB 0709 4878 78<br>"
        "BTW nr.: NL864308024B01 &nbsp;|&nbsp; KVK: 87487500"
        "</div>"
        "</div>"
    )

    spec_rows: List[List[object]] = [
        ["Baseline Facility Load (Current Situation)", f"{fmt_num(kpis.annual_consumption_kwh, 0)} kWh/yr | Peak: {fmt_num(kpis.original_peak_kw, 1)} kW | Avg: {fmt_num(kpis.average_load_kw, 1)} kW"],
        ["Contracted Grid Limit", f"{fmt_num(cfg.grid_limit_kw, 1)} kW (Current Overload: {fmt_num(kpis.baseline_overload_hours, 1)} hrs / {fmt_num(kpis.baseline_overload_kwh, 0)} kWh)"],
        [
            "Solar PV System",
            f"Enabled: {fmt_num(sim_res.solar_derivation.installed_kwp, 1)} kWp (Yield: {fmt_num(sim_res.solar_derivation.specific_yield_kwh_per_kwp, 0)} kWh/kWp/yr, {sim_res.solar_derivation.data_source_label})"
            if cfg.enable_solar
            else "Inactive",
        ],
        [
            "Battery Storage (BESS)",
            f"Enabled: {fmt_num(cfg.battery_capacity_kwh, 1)} kWh / {fmt_num(cfg.battery_power_kw, 1)} kW | SoC Window: {fmt_num(cfg.min_soc_pct, 0)}%-{fmt_num(cfg.max_soc_pct, 0)}% | RTE: {fmt_num(cfg.round_trip_efficiency_pct, 0)}%"
            if cfg.enable_battery
            else "Inactive",
        ],
        [
            "Peaking Generator",
            f"Enabled: {fmt_num(cfg.generator_rated_kw, 1)} kW ({cfg.fuel_type}, min load {fmt_num(cfg.generator_min_load_pct, 0)}%)"
            if cfg.enable_generator
            else "Inactive",
        ],
        [
            "Dispatch Interaction Rules",
            f"{RULE1_OPTIONS.get(rules.rule1_peak_priority, rules.rule1_peak_priority)} | "
            f"{RULE2_OPTIONS.get(rules.rule2_battery_strategy, rules.rule2_battery_strategy)} | "
            f"{RULE3_OPTIONS.get(rules.rule3_charging_sources, rules.rule3_charging_sources)}",
        ],
    ]
    return (
        cover_html
        + '<div class="section">'
        + '<h2 class="section-heading">1. System Configuration &amp; Operating Assumptions</h2>'
        + render_data_table(["Domain", "Configured Parameter"], spec_rows)
        + "</div>"
    )


def _build_kpi_and_status_section(sim_res: CombinedSimulationResult) -> str:
    """Builds the technical + financial KPI card rows and compliance status banner."""
    kpis = sim_res.kpis
    cfg = sim_res.system_config
    fk = sim_res.financial_kpis if cfg.enable_financials else None

    tech_cards = [
        {
            "title": "Grid Peak Demand",
            "value": f"{fmt_num(kpis.original_peak_kw, 1)} -> {fmt_num(kpis.new_grid_peak_kw, 1)} kW",
            "subtext": f"Shaved -{fmt_num(kpis.peak_reduction_kw, 1)} kW (Limit {fmt_num(cfg.grid_limit_kw, 0)} kW)",
            "tone": "ok" if kpis.grid_limit_met else "alert",
        },
        {
            "title": "Remaining Overload",
            "value": f"{fmt_num(kpis.remaining_overload_hours, 1)} hrs/yr",
            "subtext": f"{fmt_num(kpis.remaining_overload_kwh, 0)} kWh unmet (was {fmt_num(kpis.baseline_overload_hours, 1)} hrs)",
            "tone": "ok" if kpis.grid_limit_met else "alert",
        },
        {
            "title": "On-Site Supply Share",
            "value": f"{fmt_num(max(0.0, 100.0 - kpis.grid_supply_share_pct), 1)}%",
            "subtext": f"Grid {fmt_num(kpis.grid_supply_share_pct, 1)}% | Solar/BESS {fmt_num(kpis.solar_supply_share_pct, 1)}% | Gen {fmt_num(kpis.generator_supply_share_pct, 1)}%",
            "tone": "accent",
        },
        {
            "title": "Storage & Gen Activity",
            "value": f"{fmt_num(kpis.battery_equivalent_cycles, 1)} cyc/yr",
            "subtext": f"BESS Discharged: {fmt_num(kpis.battery_total_discharged_kwh / 1000.0, 1)} MWh | Gen: {fmt_num(kpis.generator_runtime_hours, 1)} hrs",
            "tone": "default",
        },
    ]

    if kpis.grid_limit_met:
        banner_html = (
            '<div class="status-banner ok">'
            f"<strong>Grid Limit Met (Zero Overload):</strong> Peak grid demand stays at {fmt_num(kpis.new_grid_peak_kw, 1)} kW "
            f"within the {fmt_num(cfg.grid_limit_kw, 0)} kW contracted capacity across all 15-minute intervals."
            "</div>"
        )
    else:
        banner_html = (
            '<div class="status-banner warn">'
            f"<strong>Remaining Grid Overload Detected:</strong> Peak demand reaches {fmt_num(kpis.new_grid_peak_kw, 1)} kW "
            f"(+{fmt_num(kpis.remaining_overload_kw, 1)} kW above the {fmt_num(cfg.grid_limit_kw, 0)} kW limit, "
            f"{fmt_num(kpis.remaining_overload_kwh, 0)} kWh across {fmt_num(kpis.remaining_overload_hours, 1)} hrs)."
            "</div>"
        )

    fin_html = ""
    if fk is not None:
        curr = str(getattr(fk, "currency_code", "EUR") or "EUR")
        pb_str = f"{fmt_num(fk.payback_years, 1)} yrs" if fk.payback_years is not None else "> 15 yrs / N/A"
        irr_str = f"{fmt_num(fk.irr_15y_pct, 1)}%" if fk.irr_15y_pct is not None else "N/A"
        fin_cards = [
            {
                "title": "Net CAPEX",
                "value": format_currency_value(fk.total_capex_eur, curr),
                "subtext": f"Gross {format_currency_value(fk.gross_capex_eur, curr)} | Avoided Grid -{format_currency_value(fk.avoided_grid_upgrade_capex_eur, curr)}",
                "tone": "default",
            },
            {
                "title": "Year-1 Net Savings",
                "value": f"{format_currency_value(fk.annual_savings_eur, curr, signed=True)}/yr",
                "subtext": f"New OPEX {format_currency_value(fk.total_annual_opex_eur, curr)} vs. {format_currency_value(fk.baseline_total_opex_eur, curr)} Current Situation",
                "tone": "ok" if fk.annual_savings_eur > 0 else "alert",
            },
            {
                "title": "Payback Period & IRR",
                "value": pb_str,
                "subtext": f"15-Year IRR: {irr_str} | BCR: {fmt_num(fk.benefit_cost_ratio_15y, 2)}x",
                "tone": "ok" if fk.payback_years is not None else "alert",
            },
            {
                "title": "15-Year Net Profit (TCO)",
                "value": format_currency_value(fk.tco_15y_savings_eur, curr, signed=True),
                "subtext": f"15-Year NPV: {format_currency_value(fk.npv_15y_eur, curr, signed=True)}",
                "tone": "ok" if fk.tco_15y_savings_eur > 0 else "alert",
            },
        ]
        fin_html = render_kpi_grid(fin_cards)

    return (
        '<div class="section">'
        '<h2 class="section-heading">2. Executive Feasibility Summary</h2>'
        + banner_html
        + render_kpi_grid(tech_cards)
        + fin_html
        + "</div>"
    )


def _build_visual_section(chart_uris: Dict[str, str]) -> str:
    """Builds the embedded print-light-mode Plotly chart gallery."""
    if not chart_uris:
        return ""
    blocks: List[str] = [
        '<div class="section">',
        '<h2 class="section-heading">3. Technical &amp; Financial Visual Diagnostics</h2>',
    ]

    if "dispatch_peak_week" in chart_uris:
        blocks.append(
            '<div class="chart-card">'
            '<div class="chart-title">Peak-Week 15-Minute Power Flow &amp; Storage Dispatch</div>'
            f'<img src="{chart_uris["dispatch_peak_week"]}" alt="Peak Week Dispatch">'
            "</div>"
        )

    if "supply_mix" in chart_uris or "asset_utilization" in chart_uris:
        blocks.append('<div class="two-col-grid">')
        if "supply_mix" in chart_uris:
            blocks.append(
                '<div class="col-half chart-card">'
                '<div class="chart-title">Annual Electricity Supply Mix</div>'
                f'<img src="{chart_uris["supply_mix"]}" alt="Supply Mix">'
                "</div>"
            )
        if "asset_utilization" in chart_uris:
            blocks.append(
                '<div class="col-half chart-card">'
                '<div class="chart-title">Installed Asset Utilization</div>'
                f'<img src="{chart_uris["asset_utilization"]}" alt="Asset Utilization">'
                "</div>"
            )
        blocks.append("</div>")

    if "financial_tco" in chart_uris:
        blocks.append(
            '<div class="chart-card">'
            '<div class="chart-title">15-Year Cumulative Cashflow &amp; Break-Even Trajectory</div>'
            f'<img src="{chart_uris["financial_tco"]}" alt="15Y TCO Trajectory">'
            "</div>"
        )

    if "financial_waterfall" in chart_uris:
        blocks.append(
            '<div class="chart-card">'
            '<div class="chart-title">Year-1 Annual Cost Bridge (Current Situation vs. Combined System)</div>'
            f'<img src="{chart_uris["financial_waterfall"]}" alt="Annual Cost Bridge">'
            "</div>"
        )

    blocks.append("</div>")
    return "".join(blocks)


def _build_financial_ledger_and_cashflow_section(
    sim_res: CombinedSimulationResult,
    include_15y_cashflow: bool,
) -> str:
    """Builds the 4-Pillar & Hardware Cost Breakdown and 15-Year Cashflow tables."""
    fk = sim_res.financial_kpis
    if not sim_res.system_config.enable_financials or fk is None:
        return ""

    curr = str(getattr(fk, "currency_code", "EUR") or "EUR")
    cost_rows = [
        [
            "Pillar 1: Energy Supply (Retailer)",
            format_currency_value(0.0, curr),
            format_currency_value(fk.baseline_pillar1_supply_eur, curr),
            format_currency_value(fk.combined_pillar1_supply_eur, curr),
            format_currency_value(fk.baseline_pillar1_supply_eur - fk.combined_pillar1_supply_eur, curr, signed=True),
        ],
        [
            "Pillar 2: Grid Network (DSO & Peaks)",
            format_currency_value(-fk.avoided_grid_upgrade_capex_eur, curr, signed=True) if fk.avoided_grid_upgrade_capex_eur > 0 else format_currency_value(0.0, curr),
            format_currency_value(fk.baseline_pillar2_dso_eur, curr),
            format_currency_value(fk.combined_pillar2_dso_eur, curr),
            format_currency_value(fk.baseline_pillar2_dso_eur - fk.combined_pillar2_dso_eur, curr, signed=True),
        ],
        [
            "Pillars 3 & 4: Metering & Taxes",
            format_currency_value(0.0, curr),
            format_currency_value(fk.baseline_pillar3_metering_eur + fk.baseline_pillar4_taxes_eur, curr),
            format_currency_value(fk.combined_pillar3_metering_eur + fk.combined_pillar4_taxes_eur, curr),
            format_currency_value((fk.baseline_pillar3_metering_eur + fk.baseline_pillar4_taxes_eur) - (fk.combined_pillar3_metering_eur + fk.combined_pillar4_taxes_eur), curr, signed=True),
        ],
        [
            "Solar PV System (CAPEX & OPEX)",
            format_currency_value(fk.solar_capex_eur, curr),
            format_currency_value(0.0, curr),
            format_currency_value(fk.solar_om_eur, curr),
            format_currency_value(-fk.solar_om_eur, curr, signed=True),
        ],
        [
            "Battery Storage BESS (CAPEX & OPEX)",
            format_currency_value(fk.battery_capex_eur, curr),
            format_currency_value(0.0, curr),
            format_currency_value(fk.battery_om_eur, curr),
            format_currency_value(-fk.battery_om_eur, curr, signed=True),
        ],
        [
            "Peaking Generator (Fuel & Service OPEX)",
            format_currency_value(fk.generator_capex_eur, curr),
            format_currency_value(0.0, curr),
            format_currency_value(fk.generator_total_opex_eur, curr),
            format_currency_value(-fk.generator_total_opex_eur, curr, signed=True),
        ],
        [
            "Solar Export Feed-in Revenue",
            format_currency_value(0.0, curr),
            format_currency_value(0.0, curr),
            format_currency_value(-fk.solar_export_revenue_eur, curr, signed=True),
            format_currency_value(fk.solar_export_revenue_eur, curr, signed=True),
        ],
        [
            "TOTAL COMBINED SYSTEM (NET)",
            format_currency_value(fk.total_capex_eur, curr),
            format_currency_value(fk.baseline_total_opex_eur, curr),
            format_currency_value(fk.total_annual_opex_eur, curr),
            format_currency_value(fk.annual_savings_eur, curr, signed=True),
        ],
    ]

    html_parts = [
        '<div class="section page-break">',
        f'<h2 class="section-heading">4. Annual Cost Structure &amp; Component Economics ({esc(curr)})</h2>',
        render_data_table(
            ["Cost Component", "CAPEX", "Current Situation (/yr)", "With System (/yr)", "Annual Impact (/yr)"],
            cost_rows,
            numeric_cols=(1, 2, 3, 4),
            summary_last_row=True,
        ),
    ]

    if include_15y_cashflow and sim_res.cashflow_15y_df is not None and not sim_res.cashflow_15y_df.empty:
        cf_df = sim_res.cashflow_15y_df
        cf_rows = []
        for rec in cf_df.to_dict(orient="records"):
            cf_rows.append([
                int(rec["Year"]),
                format_currency_value(float(rec["Current situation Bill (€)"]), curr),
                format_currency_value(float(rec["Combined System OPEX (€)"]), curr),
                format_currency_value(float(rec.get("Investment & Augmentation (€)", 0.0)), curr),
                format_currency_value(float(rec["Net Cashflow (€)"]), curr, signed=True),
                format_currency_value(float(rec["Cumulative Cashflow (€)"]), curr, signed=True),
            ])
        html_parts.append(
            f'<h2 class="section-heading">5. 15-Year Lifecycle Cashflow Schedule ({esc(curr)})</h2>'
            + render_data_table(
                ["Year", "Current Bill", "System OPEX", "CAPEX / Repower", "Net Cashflow", "Cumulative CF"],
                cf_rows,
                numeric_cols=(0, 1, 2, 3, 4, 5),
                summary_last_row=False,
            )
        )

    html_parts.append("</div>")
    return "".join(html_parts)


def _build_scenario_comparison_appendix(
    saved_scenarios: Optional[Dict[str, CombinedScenarioSnapshot]],
    chart_uris: Dict[str, str],
) -> str:
    """Builds an optional Scenario A vs. B comparison section when snapshots exist."""
    if not isinstance(saved_scenarios, dict):
        return ""
    snap_a = saved_scenarios.get("A")
    snap_b = saved_scenarios.get("B")
    if snap_a is None and snap_b is None:
        return ""

    tables = build_segmented_comparison_tables(snap_a, snap_b)
    if not tables:
        return ""

    parts = [
        '<div class="section page-break">',
        '<h2 class="section-heading">Appendix: Saved Scenario A vs. Scenario B Comparison</h2>',
    ]

    inc = compute_incremental_bwl_evaluation(snap_a, snap_b)
    if inc is not None:
        parts.append(
            '<div class="status-banner info">'
            f'<strong>Head-to-Head Verdict ({esc(inc["high_cap_name"])} vs. {esc(inc["low_cap_name"])}):</strong> '
            f'{esc(inc["verdict_title"])} — {esc(inc["verdict_text"])}'
            "</div>"
        )

    if "ab_tco_comparison" in chart_uris:
        parts.append(
            '<div class="chart-card">'
            '<div class="chart-title">15-Year Cumulative Net Cost Trajectory (Scenario A vs. Scenario B)</div>'
            f'<img src="{chart_uris["ab_tco_comparison"]}" alt="Scenario A vs B TCO">'
            "</div>"
        )

    for t_key in ("sizing_rules", "grid_balance", "capex_y1_pnl", "bwl_15y_metrics"):
        spec = tables.get(t_key)
        if spec is None:
            continue
        df = spec["df"]
        rows = [
            [
                rec["Metric / KPI"],
                rec["Current Situation"],
                rec["Scenario A"],
                rec["Scenario B"],
                rec["Delta (B vs. A)"],
            ]
            for rec in df.to_dict(orient="records")
        ]
        clean_hdr = str(spec["header_title"]).replace("&amp;", "&")
        parts.append(f'<p class="chart-title">{esc(clean_hdr)}</p>')
        parts.append(
            render_data_table(
                ["Metric / KPI", "Current Situation", "Scenario A", "Scenario B", "Delta (B vs. A)"],
                rows,
                numeric_cols=(1, 2, 3, 4),
            )
        )

    parts.append("</div>")
    return "".join(parts)


def build_combined_system_pdf_bytes(
    sim_res: CombinedSimulationResult,
    saved_scenarios: Optional[Dict[str, CombinedScenarioSnapshot]] = None,
    options: Optional[PdfReportOptions] = None,
) -> bytes:
    """
    Generates a DRACBV-branded A4 Feasibility Study PDF report in memory and returns raw PDF bytes.
    Respects Lazy Financials: evaluates financials only when `sim_res.system_config.enable_financials` is True.
    """
    opts = options or PdfReportOptions()
    cfg = sim_res.system_config
    if cfg.enable_financials and (sim_res.financial_kpis is None or sim_res.financial_config is None):
        evaluate_combined_financials(sim_res, CombinedFinancialConfig())

    chart_uris = (
        collect_report_chart_data_uris(
            sim_res=sim_res,
            saved_scenarios=saved_scenarios if opts.include_scenario_comparison else None,
        )
        if opts.include_charts
        else {}
    )

    body_sections = [
        _build_cover_and_config_section(sim_res, opts),
        _build_kpi_and_status_section(sim_res),
        _build_visual_section(chart_uris),
        _build_financial_ledger_and_cashflow_section(sim_res, include_15y_cashflow=opts.include_15y_cashflow),
    ]
    if opts.include_scenario_comparison:
        body_sections.append(_build_scenario_comparison_appendix(saved_scenarios, chart_uris))

    full_html = wrap_html_document(
        title=f"DRACBV Feasibility Study - {opts.site_name}",
        body_html="".join(body_sections),
    )
    return weasyprint.HTML(string=full_html).write_pdf()
