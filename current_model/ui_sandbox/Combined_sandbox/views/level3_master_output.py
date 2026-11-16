"""
Level 3 Permanent Master Output view (`Simulation Results`, synced dispatch chart fragment,
on-demand Excel export fragment, and System Comparison table).
"""

from typing import Optional
import numpy as np
import streamlit as st

from .state_and_helpers import (
    render_kpi_card,
    create_combined_dispatch_soc_figure,
    build_combined_verification_excel_bytes,
)

# ======================================================================================
# LEVEL 3: Permanent Master Output (Always Visible Below Sub-Tabs)
# ======================================================================================

@st.fragment
def _render_excel_export_fragment(sim_res) -> None:
    """Renders the on-demand Excel export button without blocking normal simulation reruns."""
    if "comb_cached_excel_bytes" not in st.session_state:
        if st.button(
            "Prepare Excel (.xlsx)",
            icon=":material/table_view:",
            use_container_width=True,
            key="comb_btn_prep_excel",
        ):
            st.session_state["comb_cached_excel_bytes"] = build_combined_verification_excel_bytes(sim_res)

    if "comb_cached_excel_bytes" in st.session_state:
        st.download_button(
            label="Download Excel (.xlsx)",
            data=st.session_state["comb_cached_excel_bytes"],
            file_name="Combined_System_Verification.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/download:",
            use_container_width=True,
            type="primary",
            key="comb_btn_dl_excel",
        )


@st.fragment
def _render_master_dispatch_chart_fragment(sim_res) -> None:
    """Renders the 15-minute dispatch chart matching the BESS Sandbox standard."""
    kpis = getattr(sim_res, "kpis", None)
    if kpis is not None:
        unmet_kwh = float(getattr(kpis, "remaining_overload_kwh", 0.0))
        unmet_hours = float(getattr(kpis, "remaining_overload_hours", 0.0))
    elif hasattr(sim_res, "unmet_overload_kw") and sim_res.unmet_overload_kw is not None:
        unmet_kwh = float(np.sum(sim_res.unmet_overload_kw) * 0.25)
        unmet_hours = float(np.sum(sim_res.unmet_overload_kw > 0.05) * 0.25)
    else:
        unmet_kwh = 0.0
        unmet_hours = 0.0

    has_unmet = (unmet_kwh > 0.05 or unmet_hours > 0.05)
    cfg = getattr(sim_res, "system_config", None)
    has_active_system = (
        cfg is not None
        and (cfg.enable_solar or cfg.enable_battery or cfg.enable_generator)
    )

    live_min_soc: Optional[float] = None
    if cfg is not None and cfg.enable_battery and getattr(sim_res, "bess_soc_pct", None) is not None:
        gaps = getattr(sim_res, "is_gap", None)
        soc_arr = np.asarray(sim_res.bess_soc_pct, dtype=float)
        valid_soc = (
            soc_arr[~np.asarray(gaps, dtype=bool)]
            if gaps is not None and len(gaps) == len(soc_arr)
            else soc_arr
        )
        if valid_soc.size > 0:
            live_min_soc = float(np.min(valid_soc))

    if has_active_system and not has_unmet:
        gen_hrs = float(getattr(kpis, "generator_runtime_hours", 0.0)) if kpis is not None else 0.0
        gen_fuel = float(getattr(kpis, "generator_fuel_total", 0.0)) if kpis is not None else 0.0
        gen_unit = str(getattr(kpis, "generator_fuel_unit", "L")) if kpis is not None else "L"
        if (
            cfg is not None
            and cfg.enable_battery
            and cfg.enable_generator
            and gen_hrs > 0.0
            and live_min_soc is not None
            and live_min_soc <= float(cfg.min_soc_pct) + 1.0
        ):
            success_body = (
                "Your combined system covers all demand peaks above the Grid Limit. "
                f"Battery reached SoC Min ({cfg.min_soc_pct:.0f}%) during multi-peak clusters and the "
                f"Generator stepped in as backup for **{gen_hrs:,.1f} hrs/yr** ({gen_fuel:,.0f} {gen_unit})."
            )
        else:
            success_body = "Your system covers all demand peaks above the Grid Limit."
        st.success(
            "**:material/check_circle: Grid Limit Met (Zero Overload)**\n\n"
            f"{success_body}"
        )
        if (
            cfg is not None
            and cfg.enable_battery
            and live_min_soc is not None
            and live_min_soc > max(50.0, float(cfg.min_soc_pct) + 35.0)
        ):
            cycles_yr = float(getattr(kpis, "battery_equivalent_cycles", 0.0)) if kpis is not None else 0.0
            st.info(
                f"**:material/compress: Battery Utilization Notice (Min SoC {live_min_soc:.1f}% | {cycles_yr:.1f} cyc/yr)**\n\n"
                "Your battery stays above 50% SoC all year. Visit **5. System Mix & Rules** to test a compact "
                "Battery + Generator mix for higher storage utilization."
            )
    elif has_active_system and has_unmet:
        reason_hint = "Some peaks still exceed the Grid Limit. Increase battery or generator size if needed."
        dual_bess_cached = st.session_state.get("comb_cached_dual_bess")
        if cfg is not None and cfg.enable_battery:
            req_kw_hint = (
                float(dual_bess_cached.coupled_100_kw)
                if dual_bess_cached is not None
                else float(getattr(kpis, "baseline_overload_kw", 0.0)) if kpis is not None else 0.0
            )
            if (
                req_kw_hint > float(cfg.battery_power_kw) + 0.5
                and live_min_soc is not None
                and live_min_soc > float(cfg.min_soc_pct) + 10.0
            ):
                reason_hint = (
                    f"**Inverter Power Bottleneck (`kW`):** Battery inverter is limited to "
                    f"**{cfg.battery_power_kw:,.1f} kW** while up to **{req_kw_hint:,.1f} kW** is needed "
                    f"(Min SoC remained {live_min_soc:.1f}%). Increase Inverter Power (`kW`) in **3. Battery**."
                )
            elif live_min_soc is not None and live_min_soc <= float(cfg.min_soc_pct) + 2.0:
                reason_hint = (
                    f"**Storage Capacity Depleted (`kWh`):** Battery emptied to SoC Min ({cfg.min_soc_pct:.0f}%) "
                    "during multi-hour / multi-day clusters. Increase Battery `kWh` or add a Generator in **5. System Mix & Rules**."
                )
        st.warning(
            f"**:material/warning: Remaining Overload ({unmet_kwh:,.0f} kWh across {unmet_hours:,.1f} hrs)**\n\n"
            f"{reason_hint}"
        )

    with st.container(border=True):
        hdr1, hdr2 = st.columns([3.5, 1.3])
        with hdr1:
            st.markdown("#### :material/monitoring: Power Flow & Battery Level")
            st.caption("Zoom or select a timeframe to inspect power flows and battery charge.")
        with hdr2:
            st.write("")
            _render_excel_export_fragment(sim_res)

        fig_master = create_combined_dispatch_soc_figure(sim_res=sim_res)
        st.plotly_chart(
            fig_master,
            use_container_width=True,
            config={
                "scrollZoom": False,
                "displayModeBar": "hover",
                "responsive": True,
            },
            key="comb_master_dispatch_chart",
        )


def render_level3_permanent_master_output(sim_res) -> None:
    """
    Renders Level 3 permanently below the sub-tabs so it stays visible across all tab switches:
      - 4 Compact Master KPIs
      - Synchronized 15-Minute Power Flow & Battery Level Chart (with 7D/1M/3M/All, Range-Slider & Excel Export)
      - Compact System Comparison Table (Active Components vs. Current situation)
    """
    kpis = sim_res.kpis
    cfg = sim_res.system_config
    fin_kpis = sim_res.financial_kpis

    st.markdown("---")
    st.markdown("#### :material/monitoring: Simulation Results")

    # 1. 4 Compact Master KPIs
    mk1, mk2, mk3, mk4 = st.columns(4)
    with mk1:
        limit_status = (
            f"Grid Limit ({kpis.grid_limit_kw:,.0f} kW) Met"
            if kpis.grid_limit_met
            else f"Exceeds Limit by {kpis.remaining_overload_kw:,.1f} kW"
        )
        render_kpi_card(
            title="Grid Peak Demand",
            value=f"{kpis.original_peak_kw:,.1f} → {kpis.new_grid_peak_kw:,.1f} kW",
            subtext=f"{limit_status} (-{kpis.peak_reduction_kw:,.1f} kW shaved)",
            status="ok" if kpis.grid_limit_met else "alert",
        )

    with mk2:
        render_kpi_card(
            title="Remaining Overload",
            value=f"{kpis.remaining_overload_hours:,.1f} hrs | {kpis.remaining_overload_kwh:,.0f} kWh",
            subtext=(
                f"0.0 hrs remaining (Before: {kpis.baseline_overload_hours:,.1f} hrs)"
                if kpis.remaining_overload_hours == 0.0
                else f"{kpis.overload_eliminated_pct:.1f}% of {kpis.baseline_overload_hours:,.1f} hrs eliminated"
            ),
            status="ok" if kpis.remaining_overload_hours == 0.0 else "alert",
        )

    with mk3:
        render_kpi_card(
            title="Energy Supply Split",
            value=(
                f"Grid {kpis.grid_supply_share_pct:.0f}% | "
                f"Solar {kpis.solar_direct_share_pct:.0f}% | "
                f"Bat {kpis.battery_discharge_share_pct:.0f}% | "
                f"Gen {kpis.generator_supply_share_pct:.0f}%"
            ),
            subtext=f"Annual Consumption: {kpis.annual_consumption_kwh:,.0f} kWh",
            status="default",
        )

    with mk4:
        if cfg.enable_financials and fin_kpis is not None:
            pb_txt = f"{fin_kpis.payback_years:.1f} yrs" if fin_kpis.payback_years is not None else "N/A"
            render_kpi_card(
                title="System Operation & Financials",
                value=f"€{fin_kpis.annual_savings_eur:,.0f}/yr | {pb_txt}",
                subtext=(
                    f"BESS: {kpis.battery_equivalent_cycles:.1f} cyc | "
                    f"Gen: {kpis.generator_runtime_hours:,.1f} hrs ({kpis.generator_fuel_total:,.0f} {kpis.generator_fuel_unit})"
                ),
                status="ok" if fin_kpis.annual_savings_eur > 0 else "default",
            )
        else:
            render_kpi_card(
                title="System Operation",
                value=f"{kpis.battery_equivalent_cycles:.1f} cyc | {kpis.generator_runtime_hours:,.1f} hrs",
                subtext=(
                    f"Gen Fuel: {kpis.generator_fuel_total:,.0f} {kpis.generator_fuel_unit} "
                    f"({kpis.generator_starts_count} starts/yr)"
                ),
                status="default",
            )

    # 2. Shared Synchronized 15-Minute Master Chart (isolated in fragment)
    _render_master_dispatch_chart_fragment(sim_res=sim_res)

    # 3. Compact System Comparison Table
    with st.container(border=True):
        st.markdown("##### :material/table_chart: System Comparison")
        if cfg.enable_financials and not sim_res.financial_table_df.empty:
            st.dataframe(
                sim_res.financial_table_df,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.dataframe(
                sim_res.summary_table_df,
                use_container_width=True,
                hide_index=True,
            )
