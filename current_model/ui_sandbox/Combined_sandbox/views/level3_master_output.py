"""
Level 3 Permanent Master Output view (`Simulation Results`, synced dispatch chart fragment,
on-demand Excel export fragment, and System Comparison table).
"""

from typing import Optional
import numpy as np
import pandas as pd
import streamlit as st

from .state_and_helpers import (
    DEFAULT_POWERFLOW_COLORS,
    render_kpi_card,
    create_combined_dispatch_soc_figure,
    build_combined_verification_excel_bytes,
    extract_bess_phase_events,
    summarize_bess_window_energy,
    extract_combined_solar_phase_events,
    summarize_solar_window_energy,
    normalize_date_range_input,
)

# ======================================================================================
# LEVEL 3: Permanent Master Output (Always Visible Below Sub-Tabs)
# ======================================================================================

@st.fragment
def _render_excel_export_fragment(sim_res) -> None:
    """Renders the on-demand Excel export button without blocking normal simulation reruns."""
    saved_scenarios = st.session_state.get("comb_saved_scenarios")
    scen_sig = (
        tuple(
            (k, getattr(v, "name", ""), getattr(v, "created_at", ""), getattr(v, "physical_fingerprint", ()))
            for k, v in sorted(saved_scenarios.items())
            if v is not None
        )
        if isinstance(saved_scenarios, dict)
        else ()
    )
    if st.session_state.get("comb_cached_excel_scen_sig") != scen_sig:
        st.session_state.pop("comb_cached_excel_bytes", None)
        st.session_state["comb_cached_excel_scen_sig"] = scen_sig

    if "comb_cached_excel_bytes" not in st.session_state:
        if st.button(
            "Prepare Excel (.xlsx)",
            icon=":material/table_view:",
            use_container_width=True,
            key="comb_btn_prep_excel",
        ):
            st.session_state["comb_cached_excel_bytes"] = build_combined_verification_excel_bytes(
                sim_res,
                saved_scenarios=saved_scenarios if isinstance(saved_scenarios, dict) and saved_scenarios else None,
            )

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


def _render_bess_phase_log_expander(sim_res) -> None:
    """Renders a collapsible BESS Charge/Discharge Phase Event Log & Date-Range Energy Calculator."""
    ts_raw = getattr(sim_res, "timestamps", None)
    if ts_raw is None or len(ts_raw) == 0:
        return
    ts_idx = pd.DatetimeIndex(ts_raw)
    min_d = ts_idx.min().date()
    max_d = ts_idx.max().date()

    with st.expander("Battery Charge & Discharge Phases (Energy per Event)", expanded=False, icon=":material/bolt:"):
        c1, c2, c3 = st.columns([1.2, 1.3, 1.5])
        with c1:
            phase_filter = st.radio(
                "Phase Type",
                options=["All", "Discharge", "Charge"],
                index=0,
                horizontal=True,
                key="comb_bess_phase_type_filter",
            )
        with c2:
            st.write("")
            merge_pauses = st.checkbox(
                "Merge pauses <= 30 min",
                value=False,
                key="comb_bess_phase_merge_pauses",
                help=(
                    "Combines adjacent phases separated by up to two 15-minute idle intervals "
                    "(never across data gaps or opposite BESS activity)."
                ),
            )
        with c3:
            raw_range = st.date_input(
                "Date Range Filter",
                value=(min_d, max_d),
                min_value=min_d,
                max_value=max_d,
                key="comb_bess_phase_date_range",
            )

        start_dt, end_dt, d0, d1 = normalize_date_range_input(raw_range)

        phase_res = extract_bess_phase_events(
            sim_res,
            merge_gap_steps=2 if merge_pauses else 0,
        )
        win = summarize_bess_window_energy(sim_res, start_dt, end_dt)

        df_ev = phase_res.events_df
        if not df_ev.empty:
            s_dt = pd.to_datetime(df_ev["Start"])
            e_dt = pd.to_datetime(df_ev["End"])
            df_win = df_ev[(s_dt <= end_dt) & (e_dt >= start_dt)].copy()
        else:
            df_win = df_ev.copy()

        if phase_filter != "All" and not df_win.empty:
            df_show = df_win[df_win["Type"] == phase_filter].copy()
        else:
            df_show = df_win

        dis_df = df_win[df_win["Type"] == "Discharge"] if not df_win.empty else df_win
        chg_df = df_win[df_win["Type"] == "Charge"] if not df_win.empty else df_win

        if not dis_df.empty:
            top_dis = dis_df.loc[dis_df["Energy AC (kWh)"].idxmax()]
            max_dis_kwh = float(top_dis["Energy AC (kWh)"])
            max_dis_h = float(top_dis["Duration (h)"])
        else:
            max_dis_kwh, max_dis_h = 0.0, 0.0

        if not chg_df.empty:
            top_chg = chg_df.loc[chg_df["Energy AC (kWh)"].idxmax()]
            max_chg_kwh = float(top_chg["Energy AC (kWh)"])
            max_chg_h = float(top_chg["Duration (h)"])
        else:
            max_chg_kwh, max_chg_h = 0.0, 0.0

        chg_tot = max(1e-6, win["charge_total_kwh"])
        solar_pct = (win["charge_solar_kwh"] / chg_tot) * 100.0 if win["charge_total_kwh"] > 0 else 0.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric(
            "Window Discharge (AC)",
            f"{win['discharge_kwh']:,.1f} kWh",
            delta=f"{len(dis_df)} phases | Peak {win['peak_discharge_kw']:,.1f} kW",
            delta_color="off",
        )
        k2.metric(
            "Largest Single Discharge",
            f"{max_dis_kwh:,.1f} kWh",
            delta=f"{max_dis_h:.2f} h event",
            delta_color="off",
        )
        k3.metric(
            "Window Charge (AC)",
            f"{win['charge_total_kwh']:,.1f} kWh",
            delta=f"{len(chg_df)} phases | Solar {solar_pct:.0f}%",
            delta_color="off",
        )
        k4.metric(
            "Largest Single Charge",
            f"{max_chg_kwh:,.1f} kWh",
            delta=f"{max_chg_h:.2f} h event",
            delta_color="off",
        )

        if df_show.empty:
            st.info("No Charge/Discharge phases matched the selected date range and filter.")
        else:
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            st.download_button(
                label="Download Phase Log (.csv)",
                data=df_show.to_csv(index=False).encode("utf-8"),
                file_name=f"BESS_Phase_Events_{d0}_{d1}.csv",
                mime="text/csv",
                icon=":material/download:",
                key="comb_bess_phase_csv_dl",
            )
        st.caption(
            "Phase energies represent AC-side energy delivered or absorbed (kWh), which differs from "
            "internal SoC energy change by inverter and round-trip efficiency (RTE). Toggle "
            "**BESS Phase Energy (kWh)** in the chart legend to show peak labels directly on the plot."
        )


def _render_solar_phase_log_expander(sim_res) -> None:
    """Renders a collapsible Solar Production & Direct Use Phase Event Log with Date-Range Energy Summary."""
    ts_raw = getattr(sim_res, "timestamps", None)
    if ts_raw is None or len(ts_raw) == 0:
        return
    ts_idx = pd.DatetimeIndex(ts_raw)
    min_d, max_d = ts_idx.min().date(), ts_idx.max().date()

    with st.expander("Solar Production & Direct Use Phases (Energy per Day)", expanded=False, icon=":material/solar_power:"):
        raw_range = st.date_input(
            "Date Range Filter",
            value=(min_d, max_d),
            min_value=min_d,
            max_value=max_d,
            key="comb_solar_phase_date_range",
        )
        start_dt, end_dt, d0, d1 = normalize_date_range_input(raw_range)

        solar_res = extract_combined_solar_phase_events(sim_res)
        win = summarize_solar_window_energy(
            timestamps=ts_idx,
            start_ts=start_dt,
            end_ts=end_dt,
            solar_production_kw=sim_res.solar_gen_kw,
            solar_potential_kw=getattr(sim_res, "solar_potential_kw", None),
            solar_direct_kw=sim_res.solar_direct_kw,
            bess_charge_solar_kw=sim_res.bess_charge_solar_kw,
            solar_export_kw=sim_res.solar_export_kw,
            is_gap=getattr(sim_res, "is_gap", None),
        )

        df_ev = solar_res.events_df
        if not df_ev.empty:
            s_dt = pd.to_datetime(df_ev["Start"])
            e_dt = pd.to_datetime(df_ev["End"])
            df_win = df_ev[(s_dt <= end_dt) & (e_dt >= start_dt)].copy()
        else:
            df_win = df_ev.copy()

        if not df_win.empty:
            top_day = df_win.loc[df_win["Solar Production AC (kWh)"].idxmax()]
            max_day_kwh = float(top_day["Solar Production AC (kWh)"])
            max_day_h = float(top_day["Daylight (h)"])
        else:
            max_day_kwh, max_day_h = 0.0, 0.0

        prod_tot = max(1e-6, win["production_kwh"])
        dir_share = (win["direct_kwh"] / prod_tot) * 100.0 if win["production_kwh"] > 0 else 0.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric(
            "Window Solar Production (AC)",
            f"{win['production_kwh']:,.1f} kWh",
            delta=f"{len(df_win)} phases | Peak {win['peak_production_kw']:,.1f} kW",
            delta_color="off",
        )
        k2.metric(
            "Window Direct Load Use",
            f"{win['direct_kwh']:,.1f} kWh",
            delta=f"{dir_share:.0f}% direct | Peak {win['peak_direct_kw']:,.1f} kW",
            delta_color="off",
        )
        k3.metric(
            "To Battery / Grid Export",
            f"{win['to_battery_kwh']:,.1f} / {win['export_kwh']:,.1f} kWh",
            delta=f"Clipped: {win['clipped_kwh']:,.1f} kWh",
            delta_color="off",
        )
        k4.metric(
            "Peak Solar Production Day",
            f"{max_day_kwh:,.1f} kWh",
            delta=f"{max_day_h:.2f} h daylight",
            delta_color="off",
        )

        if df_win.empty:
            st.info("No Solar production phases matched the selected date range.")
        else:
            st.dataframe(df_win, use_container_width=True, hide_index=True)
            st.download_button(
                label="Download Solar Phase Log (.csv)",
                data=df_win.to_csv(index=False).encode("utf-8"),
                file_name=f"Solar_Phase_Events_{d0}_{d1}.csv",
                mime="text/csv",
                icon=":material/download:",
                key="comb_solar_phase_csv_dl",
            )
        st.caption(
            "Shows usable AC solar generation per daylight phase, split into direct facility consumption, "
            "BESS charging, and grid export. Toggle **Solar Direct Phase (kWh)** in the chart legend above "
            "to show peak energy labels directly on the plot."
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

        color_overrides = dict(st.session_state.get("comb_powerflow_colors") or DEFAULT_POWERFLOW_COLORS)
        merge_pauses = bool(st.session_state.get("comb_bess_phase_merge_pauses", False))
        fig_master = create_combined_dispatch_soc_figure(
            sim_res=sim_res,
            color_overrides=color_overrides,
            merge_phase_gap_steps=2 if merge_pauses else 0,
        )
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

        if cfg is not None and cfg.enable_battery:
            _render_bess_phase_log_expander(sim_res)
        if cfg is not None and cfg.enable_solar:
            _render_solar_phase_log_expander(sim_res)

        with st.expander("Customize Chart Colors", expanded=False, icon=":material/palette:"):
            st.caption("Adjust the line and fill colors of each component in the Power Flow chart.")
            cc1, cc2, cc3, cc4 = st.columns(4)
            updated_colors = dict(color_overrides)
            with cc1:
                st.markdown("**Load & Grid**")
                updated_colors["facility_load"] = st.color_picker("Facility Load", color_overrides["facility_load"], key="comb_clr_facility_load")
                updated_colors["grid_import"] = st.color_picker("Grid Import", color_overrides["grid_import"], key="comb_clr_grid_import")
                updated_colors["grid_limit"] = st.color_picker("Grid Limit", color_overrides["grid_limit"], key="comb_clr_grid_limit")
                updated_colors["grid_excess"] = st.color_picker("Grid Excess", color_overrides["grid_excess"], key="comb_clr_grid_excess")
            with cc2:
                st.markdown("**Solar**")
                updated_colors["solar_direct"] = st.color_picker("Solar Direct", color_overrides["solar_direct"], key="comb_clr_solar_direct")
                updated_colors["solar_production"] = st.color_picker("Solar Production", color_overrides["solar_production"], key="comb_clr_solar_production")
                updated_colors["solar_potential"] = st.color_picker("Solar Potential", color_overrides["solar_potential"], key="comb_clr_solar_potential")
                updated_colors["inverter_limit"] = st.color_picker("Inverter Limit", color_overrides["inverter_limit"], key="comb_clr_inverter_limit")
            with cc3:
                st.markdown("**Battery**")
                updated_colors["bess_discharge"] = st.color_picker("BESS Discharge", color_overrides["bess_discharge"], key="comb_clr_bess_discharge")
                updated_colors["bess_charge"] = st.color_picker("BESS Charge", color_overrides["bess_charge"], key="comb_clr_bess_charge")
                updated_colors["bess_soc"] = st.color_picker("Battery SoC (%)", color_overrides["bess_soc"], key="comb_clr_bess_soc")
            with cc4:
                st.markdown("**Generator & Reset**")
                updated_colors["generator_output"] = st.color_picker("Generator Output", color_overrides["generator_output"], key="comb_clr_generator_output")
                st.write("")
                if st.button("Reset Default Colors", icon=":material/restart_alt:", use_container_width=True, key="comb_clr_reset_btn"):
                    st.session_state["comb_powerflow_colors"] = dict(DEFAULT_POWERFLOW_COLORS)
                    for ck, cv in DEFAULT_POWERFLOW_COLORS.items():
                        st.session_state[f"comb_clr_{ck}"] = cv
                    st.rerun(scope="fragment")
            if updated_colors != st.session_state.get("comb_powerflow_colors"):
                st.session_state["comb_powerflow_colors"] = updated_colors
                st.rerun(scope="fragment")


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
            c_code = str(getattr(fin_kpis, "currency_code", "EUR") or "EUR")
            c_sym = "€" if c_code == "EUR" else (f"{c_code} " if c_code == "ARS" else "$")
            render_kpi_card(
                title="System Operation & Financials",
                value=f"{c_sym}{fin_kpis.annual_savings_eur:,.0f}/yr | {pb_txt}",
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
