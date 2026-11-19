"""
Pure Python scenario snapshot, restoration, preset-pair generation, and A/B comparison
matrix engine for Combined System Sandbox (`ui_sandbox/Combined_sandbox/engine/`).

Strictly Streamlit-free to guarantee unit testability and zero UI coupling.
"""

import copy
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np
import pandas as pd

from .models_and_presets import (
    ENGINE_VERSION,
    RULE1_OPTIONS,
    RULE2_OPTIONS,
    RULE3_OPTIONS,
    SOLAR_SITE_PRESETS,
    CombinedSystemConfig,
    InteractionRulesConfig,
    CombinedFinancialConfig,
    CombinedSimulationResult,
    CombinedScenarioSnapshot,
)
from .solar_and_sizing import (
    determine_smart_modular_units,
    get_unit_solar_generation_profile,
)
from .dispatch_simulation import simulate_combined_system_dispatch
from .utilization_and_tables import (
    compute_coordinated_mix_sizing,
    compute_system_utilization_diagnostics,
)
from .financial_engine import evaluate_combined_financials
from .formatting import curr_prefix, fmt_curr, fmt_num


_BASELINE_TARIFF_FIELDS: Tuple[str, ...] = (
    "currency_code",
    "market_mode",
    "enable_pillar_1_supplier",
    "enable_pillar_2_dso",
    "enable_pillar_3_metering",
    "enable_pillar_4_taxes",
    "supplier_energy_price_eur_kwh",
    "supplier_fixed_fee_eur_month",
    "supplier_pricing_mode",
    "supplier_peak_ht_eur_kwh",
    "supplier_offpeak_nt_eur_kwh",
    "supplier_gvo_surcharge_eur_kwh",
    "dso_capacity_fee_eur_kw_month",
    "dso_peak_demand_fee_eur_kw_month",
    "dso_connection_fee_eur_month",
    "dso_fixed_fee_eur_month",
    "dso_transport_eur_kwh",
    "dso_enable_three_window_tou",
    "dso_transport_peak_eur_kwh",
    "dso_transport_offpeak_eur_kwh",
    "dso_transport_shoulder_eur_kwh",
    "grid_overload_penalty_eur_kw",
    "dso_enable_excess_capacity_penalty",
    "dso_adjust_capacity_on_breach",
    "dso_bill_peak_on_pico_only",
    "dso_regulatory_adjustments_eur_month",
    "avoided_transformer_rent_eur_month",
    "metering_fixed_fee_eur_month",
    "energy_tax_eur_kwh",
    "tax_surcharge_pct",
    "annual_tax_reduction_credit_eur",
    "vat_rate_pct",
    "vat_applies_to_levies",
    "grid_energy_price_eur_kwh",
    "grid_capacity_fee_eur_kw_month",
    "grid_fixed_fee_eur_month",
    "solar_export_feed_in_eur_kwh",
    "discount_rate_pct",
    "tariff_escalation_pct_pa",
    "om_inflation_pct_pa",
    "system_degradation_pct_pa",
)


def _curr_sym(currency_code: str = "EUR") -> str:
    """Returns compact currency symbol for unit-rate formatting (€, $, or ISO code)."""
    return curr_prefix(currency_code)


SCENARIO_COMPARISON_PALETTE: Tuple[str, ...] = (
    "#38BDF8",
    "#10B981",
    "#F59E0B",
    "#A855F7",
    "#EC4899",
    "#06B6D4",
)


def normalize_scenario_list(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> List[CombinedScenarioSnapshot]:
    """
    Normalizes either pairwise `(snap_a, snap_b)` or an arbitrary `1..N` sequence
    of `CombinedScenarioSnapshot` objects into a clean ordered list for charts/tables.
    """
    if scenarios is not None:
        return [s for s in scenarios if s is not None]
    return [s for s in (snap_a, snap_b) if s is not None]


def format_currency_value(
    val: float,
    currency_code: str = "EUR",
    signed: bool = False,
    decimals: int = 0,
) -> str:
    """Formats a monetary value with currency prefix for plain text, DataFrames, and Excel cells."""
    return fmt_curr(val, currency_code=currency_code, decimals=decimals, signed=signed)


def build_load_fingerprint_from_series(load_series: Any) -> Tuple[int, float, float]:
    """Returns a fast O(1) tuple fingerprint of an active 35,040-step load series."""
    power_kw = getattr(load_series, "power_kw", np.zeros(0, dtype=float))
    total_kwh = getattr(load_series, "total_energy_kwh", float(np.sum(power_kw) * 0.25))
    peak_kw = getattr(load_series, "peak_demand_kw", float(np.max(power_kw)) if len(power_kw) > 0 else 0.0)
    return (
        len(power_kw),
        round(float(total_kwh), 2),
        round(float(peak_kw), 2),
    )


def build_baseline_tariff_fingerprint(fin_cfg: CombinedFinancialConfig) -> Tuple:
    """
    Returns an immutable tuple capturing currency, market mode, Pillar 1-4 tariff rates,
    and 15-year escalation/discount assumptions used as the shared comparison yardstick.
    """
    vals: List[Any] = []
    for fname in _BASELINE_TARIFF_FIELDS:
        v = getattr(fin_cfg, fname, None)
        if isinstance(v, float):
            vals.append(round(v, 6))
        else:
            vals.append(v)
    return tuple(vals)


def build_physical_snapshot_fingerprint(
    sys_cfg: CombinedSystemConfig,
    rules_cfg: InteractionRulesConfig,
) -> Tuple:
    """Returns a deterministic physical + rule fingerprint when no UI tuple is passed explicitly."""
    return (
        ENGINE_VERSION,
        bool(sys_cfg.enable_grid),
        round(float(sys_cfg.grid_limit_kw), 2),
        bool(sys_cfg.enable_solar),
        round(float(sys_cfg.latitude), 4),
        round(float(sys_cfg.longitude), 4),
        str(sys_cfg.solar_sizing_method),
        round(float(sys_cfg.solar_kwp), 2),
        round(float(sys_cfg.target_consumption_share_pct), 2),
        round(float(sys_cfg.inverter_ac_limit_kw), 2),
        bool(getattr(sys_cfg, "disable_solar_inverter_limit", False)),
        round(float(sys_cfg.inverter_efficiency_pct), 2),
        str(getattr(sys_cfg, "solar_weather_mode", "single_year")),
        int(getattr(sys_cfg, "solar_weather_year", 2025)),
        bool(sys_cfg.enable_battery),
        round(float(sys_cfg.battery_capacity_kwh), 2),
        round(float(sys_cfg.battery_power_kw), 2),
        round(float(sys_cfg.min_soc_pct), 2),
        round(float(sys_cfg.max_soc_pct), 2),
        round(float(sys_cfg.round_trip_efficiency_pct), 2),
        bool(sys_cfg.enable_generator),
        round(float(sys_cfg.generator_rated_kw), 2),
        round(float(sys_cfg.generator_min_load_pct), 2),
        str(sys_cfg.fuel_type),
        str(rules_cfg.rule1_peak_priority),
        str(rules_cfg.rule2_battery_strategy),
        round(float(rules_cfg.peak_reserve_soc_pct), 2),
        str(rules_cfg.rule3_charging_sources),
    )


def sync_baseline_tariff_fields(
    target_fin: CombinedFinancialConfig,
    source_fin: CombinedFinancialConfig,
) -> CombinedFinancialConfig:
    """
    Returns a copy of `target_fin` with currency, Pillar 1-4 tariff rates, and 15Y lifecycle
    yardsticks synchronized from `source_fin`, preserving scenario-specific hardware quotes.
    """
    updated = copy.deepcopy(target_fin)
    for fname in _BASELINE_TARIFF_FIELDS:
        setattr(updated, fname, copy.deepcopy(getattr(source_fin, fname, None)))
    return updated


def capture_scenario_snapshot(
    sim_res: CombinedSimulationResult,
    fin_cfg: CombinedFinancialConfig,
    slot_id: str,
    custom_name: str,
    load_fp: Tuple[int, float, float],
    physical_fp: Optional[Tuple] = None,
) -> CombinedScenarioSnapshot:
    """
    Captures a lightweight (< 50 KB) snapshot from `sim_res` and `fin_cfg`.

    Guarantees Lazy-Financials evaluation on a shallow copy of `sim_res` if `financial_kpis`
    is None or stale, without mutating the caller's live `sim_res` or duplicating 35,040-step arrays.
    """
    sys_copy = copy.deepcopy(sim_res.system_config)
    rules_copy = copy.deepcopy(sim_res.rules_config)
    fin_copy = copy.deepcopy(fin_cfg)
    for k, v in CombinedFinancialConfig().__dict__.items():
        if not hasattr(fin_copy, k):
            setattr(fin_copy, k, v)

    needs_fin_eval = (
        sim_res.financial_kpis is None
        or sim_res.financial_config is None
        or sim_res.financial_config != fin_copy
        or sim_res.monthly_cost_df is None
        or sim_res.monthly_cost_df.empty
        or sim_res.cashflow_15y_df is None
        or sim_res.cashflow_15y_df.empty
    )

    sim_eval = copy.copy(sim_res)
    if needs_fin_eval:
        sim_eval.system_config = sys_copy
        sim_eval.rules_config = rules_copy
        evaluate_combined_financials(sim_eval, fin_copy)

    util_diag = compute_system_utilization_diagnostics(sim_eval)
    eff_name = (custom_name or "").strip() or f"Scenario {slot_id}"
    eff_phys_fp = (
        physical_fp
        if physical_fp is not None
        else build_physical_snapshot_fingerprint(sys_copy, rules_copy)
    )

    return CombinedScenarioSnapshot(
        slot_id=str(slot_id),
        name=eff_name,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        load_fingerprint=tuple(load_fp),
        baseline_tariff_fingerprint=build_baseline_tariff_fingerprint(fin_copy),
        physical_fingerprint=eff_phys_fp,
        system_config=sys_copy,
        rules_config=rules_copy,
        financial_config=fin_copy,
        solar_derivation=copy.deepcopy(sim_eval.solar_derivation),
        kpis=copy.deepcopy(sim_eval.kpis),
        financial_kpis=copy.deepcopy(sim_eval.financial_kpis),
        utilization_diagnostics=copy.deepcopy(util_diag),
        monthly_balance_df=(
            sim_eval.monthly_balance_df.copy()
            if sim_eval.monthly_balance_df is not None
            else pd.DataFrame()
        ),
        monthly_cost_df=(
            sim_eval.monthly_cost_df.copy()
            if sim_eval.monthly_cost_df is not None
            else pd.DataFrame()
        ),
        cashflow_15y_df=(
            sim_eval.cashflow_15y_df.copy()
            if sim_eval.cashflow_15y_df is not None
            else pd.DataFrame()
        ),
        grid_import_kw_f32=np.asarray(sim_eval.grid_import_kw, dtype=np.float32).copy() if getattr(sim_eval, "grid_import_kw", None) is not None else None,
        bess_soc_pct_f32=np.asarray(sim_eval.bess_soc_pct, dtype=np.float32).copy() if getattr(sim_eval, "bess_soc_pct", None) is not None else None,
        unmet_overload_kw_f32=np.asarray(sim_eval.unmet_overload_kw, dtype=np.float32).copy() if getattr(sim_eval, "unmet_overload_kw", None) is not None else None,
        dispatch_f32_dict={
            k_arr: np.asarray(val_arr, dtype=np.float32).copy()
            for k_arr, val_arr in (
                ("solar_gen_kw", getattr(sim_eval, "solar_gen_kw", None)),
                ("solar_direct_kw", getattr(sim_eval, "solar_direct_kw", None)),
                ("solar_potential_kw", getattr(sim_eval, "solar_potential_kw", None)),
                ("bess_discharge_kw", getattr(sim_eval, "bess_discharge_kw", None)),
                ("gen_output_kw", getattr(sim_eval, "gen_output_kw", None)),
                (
                    "bess_charge_total_kw",
                    (np.asarray(sim_eval.bess_charge_solar_kw, dtype=np.float32) + np.asarray(sim_eval.bess_charge_grid_kw, dtype=np.float32) + np.asarray(sim_eval.bess_charge_gen_kw, dtype=np.float32))
                    if getattr(sim_eval, "bess_charge_solar_kw", None) is not None else None,
                ),
            )
            if val_arr is not None
        },
    )


def recalculate_snapshot_on_active_load(
    snapshot: CombinedScenarioSnapshot,
    load_series: Any,
    active_fin_cfg: Optional[CombinedFinancialConfig] = None,
) -> CombinedScenarioSnapshot:
    """
    Re-simulates an existing snapshot on an updated 35,040-step load profile and optionally
    synchronizes the baseline electricity tariff & currency from `active_fin_cfg`.
    """
    sys_cfg = copy.deepcopy(snapshot.system_config)
    rules_cfg = copy.deepcopy(snapshot.rules_config)
    fin_cfg = (
        sync_baseline_tariff_fields(snapshot.financial_config, active_fin_cfg)
        if active_fin_cfg is not None
        else copy.deepcopy(snapshot.financial_config)
    )

    sim_res = simulate_combined_system_dispatch(
        load_kw=load_series.power_kw,
        timestamps=load_series.timestamps,
        system_cfg=sys_cfg,
        rules_cfg=rules_cfg,
        is_gap=getattr(load_series, "is_gap", None),
    )
    load_fp = build_load_fingerprint_from_series(load_series)
    return capture_scenario_snapshot(
        sim_res=sim_res,
        fin_cfg=fin_cfg,
        slot_id=snapshot.slot_id,
        custom_name=snapshot.name,
        load_fp=load_fp,
        physical_fp=build_physical_snapshot_fingerprint(sys_cfg, rules_cfg),
    )


def generate_quick_ab_preset_snapshots(
    load_series: Any,
    base_sys_cfg: CombinedSystemConfig,
    base_rules_cfg: InteractionRulesConfig,
    fin_cfg: CombinedFinancialConfig,
) -> Tuple[CombinedScenarioSnapshot, CombinedScenarioSnapshot]:
    """
    Automatically sizes, simulates, and snapshots a turnkey A/B comparison pair on the
    active load profile, grid limit, rules, and solar configuration:
      - Slot A: `pure_battery_100` (100% Battery - Zero Overload)
      - Slot B: `hybrid_2h` (Compact 2h Battery + Generator Backup)
    """
    load_fp = build_load_fingerprint_from_series(load_series)
    ann_kwh = float(getattr(load_series, "total_energy_kwh", 0.0))

    solar_enabled = bool(base_sys_cfg.enable_solar)
    if solar_enabled:
        if base_sys_cfg.solar_sizing_method == "target_share_pct":
            solar_share_pct = float(base_sys_cfg.target_consumption_share_pct)
        else:
            azim = 180.0 if float(base_sys_cfg.latitude) >= 0.0 else 0.0
            _, spec_y, _ = get_unit_solar_generation_profile(
                latitude=float(base_sys_cfg.latitude),
                longitude=float(base_sys_cfg.longitude),
                tilt_deg=float(base_sys_cfg.tilt_deg),
                azimuth_deg=azim,
                dc_ac_ratio=float(base_sys_cfg.dc_ac_ratio),
                weather_mode=str(getattr(base_sys_cfg, "solar_weather_mode", "single_year")),
                selected_year=int(getattr(base_sys_cfg, "solar_weather_year", 2025)),
            )
            eff_factor = float(np.clip(base_sys_cfg.inverter_efficiency_pct, 80.0, 100.0)) / 98.0
            solar_share_pct = (
                (float(base_sys_cfg.solar_kwp) * max(100.0, spec_y) * eff_factor / max(1.0, ann_kwh)) * 100.0
                if ann_kwh > 0.0
                else float(base_sys_cfg.target_consumption_share_pct)
            )
    else:
        solar_share_pct = 0.0

    def _build_slot(slot_id: str, strategy_key: str, slot_name: str, gen_cover: bool) -> CombinedScenarioSnapshot:
        rec = compute_coordinated_mix_sizing(
            load_kw=load_series.power_kw,
            system_cfg=base_sys_cfg,
            rules_cfg=base_rules_cfg,
            strategy_key=strategy_key,
            target_grid_limit_kw=float(base_sys_cfg.grid_limit_kw),
            solar_share_pct=solar_share_pct,
            solar_enabled=solar_enabled,
            bess_duration_hours=2.0,
            gen_cover_remaining_peaks=gen_cover,
            is_gap=getattr(load_series, "is_gap", None),
        )
        cfg = copy.deepcopy(base_sys_cfg)
        cfg.enable_grid = True
        cfg.grid_limit_kw = float(rec.grid_limit_kw)
        cfg.enable_solar = bool(rec.solar_enabled)
        if cfg.enable_solar and base_sys_cfg.solar_sizing_method == "direct_kwp":
            cfg.solar_sizing_method = "direct_kwp"
            cfg.solar_kwp = float(base_sys_cfg.solar_kwp)
        elif cfg.enable_solar:
            cfg.solar_sizing_method = "target_share_pct"
            cfg.target_consumption_share_pct = float(rec.solar_share_pct)
            cfg.solar_kwp = float(rec.solar_kwp)
        cfg.enable_battery = bool(rec.battery_enabled)
        cfg.battery_capacity_kwh = float(rec.battery_capacity_kwh) if rec.battery_enabled else 0.0
        cfg.battery_power_kw = float(rec.battery_power_kw) if rec.battery_enabled else 0.0
        cfg.enable_generator = bool(rec.generator_enabled)
        cfg.generator_rated_kw = float(rec.generator_rated_kw) if rec.generator_enabled else 0.0

        rules_copy = copy.deepcopy(base_rules_cfg)
        sim_out = simulate_combined_system_dispatch(
            load_kw=load_series.power_kw,
            timestamps=load_series.timestamps,
            system_cfg=cfg,
            rules_cfg=rules_copy,
            is_gap=getattr(load_series, "is_gap", None),
        )
        return capture_scenario_snapshot(
            sim_res=sim_out,
            fin_cfg=fin_cfg,
            slot_id=slot_id,
            custom_name=slot_name,
            load_fp=load_fp,
            physical_fp=build_physical_snapshot_fingerprint(cfg, rules_copy),
        )

    snap_a = _build_slot(
        slot_id="A",
        strategy_key="pure_battery_100",
        slot_name="Scenario A: 100% Battery (Zero Overload)",
        gen_cover=False,
    )
    snap_b = _build_slot(
        slot_id="B",
        strategy_key="hybrid_2h",
        slot_name="Scenario B: Compact 2h Battery + Generator",
        gen_cover=True,
    )
    return snap_a, snap_b


def _resolve_solar_site_labels(sys_cfg: CombinedSystemConfig) -> Tuple[str, str]:
    """Resolves `(preset_choice, site_display_name)` matching Sub-Tab 2 location selectors."""
    if sys_cfg.site_preset in SOLAR_SITE_PRESETS:
        p = SOLAR_SITE_PRESETS[sys_cfg.site_preset]
        if (
            abs(float(p["latitude"]) - float(sys_cfg.latitude)) < 1e-3
            and abs(float(p["longitude"]) - float(sys_cfg.longitude)) < 1e-3
        ):
            return str(sys_cfg.site_preset), str(p["name"])
    for p_key, p_data in SOLAR_SITE_PRESETS.items():
        if (
            abs(float(p_data["latitude"]) - float(sys_cfg.latitude)) < 1e-3
            and abs(float(p_data["longitude"]) - float(sys_cfg.longitude)) < 1e-3
        ):
            return str(p_key), str(p_data["name"])
    return (
        "Custom GPS Coordinates",
        f"Custom ({float(sys_cfg.latitude):.4f}°N, {float(sys_cfg.longitude):.4f}°E)",
    )


def _bill_mode_label_for_fin_cfg(fin_cfg: CombinedFinancialConfig) -> str:
    """Maps `market_mode` to Sub-Tab 6.1 Bill Structure selector label."""
    mode = str(getattr(fin_cfg, "market_mode", "unbundled_4_pillar")).lower()
    if "single" in mode:
        return "Single Utility Company (1 Combined Bill — Argentina EDEMSA)"
    if "custom" in mode:
        return "Custom Bill Parts"
    return "Separate Suppliers (4-Part Bill — NL / EU)"


def build_restore_widget_sync_payload(
    snapshot: CombinedScenarioSnapshot,
    current_dso_tou_v: int = 0,
) -> Dict[str, Any]:
    """
    Produces complete deep-copied configuration objects plus staged widget sync dictionaries
    (`comb_pending_mix_widget_sync`, `comb_pending_solar_widget_sync`, `comb_pending_fin_widget_sync`)
    so restoring a snapshot updates Level 1 and Sub-Tabs 2-6 safely prior to widget instantiation.
    """
    sys_cfg = copy.deepcopy(snapshot.system_config)
    rules_cfg = copy.deepcopy(snapshot.rules_config)
    fin_cfg = copy.deepcopy(snapshot.financial_config)
    for k, v in CombinedFinancialConfig().__dict__.items():
        if not hasattr(fin_cfg, k):
            setattr(fin_cfg, k, v)

    if sys_cfg.enable_battery and sys_cfg.battery_capacity_kwh > 0.0:
        units, unit_kwh = determine_smart_modular_units(float(sys_cfg.battery_capacity_kwh))
    else:
        units, unit_kwh = (2, 50.0)

    eff_sol_share = (
        float(sys_cfg.target_consumption_share_pct)
        if sys_cfg.solar_sizing_method == "target_share_pct"
        else float(getattr(snapshot.solar_derivation, "effective_share_pct", sys_cfg.target_consumption_share_pct))
    )
    sol_slider_val = int(round(np.clip(eff_sol_share if sys_cfg.enable_solar else 0.0, 0.0, 150.0)))

    preset_choice, site_name = _resolve_solar_site_labels(sys_cfg)
    default_inv_ac = float(max(0.0, float(sys_cfg.inverter_ac_limit_kw)))

    mix_widget_sync: Dict[str, Any] = {
        # Level 1 Overview Bar
        "comb_grid_limit_input": float(max(10.0, sys_cfg.grid_limit_kw)),
        "comb_enable_solar_toggle": bool(sys_cfg.enable_solar),
        "comb_enable_battery_toggle": bool(sys_cfg.enable_battery),
        "comb_enable_generator_toggle": bool(sys_cfg.enable_generator),
        "comb_enable_financials_toggle": bool(sys_cfg.enable_financials),
        # Sub-Tab 3 Battery
        "comb_bess_lock_05c": False,
        "comb_bess_lock_05c_box": False,
        "comb_bess_unit_count": int(units),
        "comb_bess_unit_kwh": float(unit_kwh),
        "comb_bess_unit_count_num": int(units),
        "comb_bess_unit_kwh_num": float(unit_kwh),
        "comb_battery_power_kw_num": float(max(1.0, sys_cfg.battery_power_kw)),
        "comb_battery_rte_slider": int(round(np.clip(sys_cfg.round_trip_efficiency_pct, 70.0, 98.0))),
        "comb_battery_min_soc_slider": int(round(np.clip(sys_cfg.min_soc_pct, 0.0, 40.0))),
        "comb_battery_max_soc_slider": int(round(np.clip(sys_cfg.max_soc_pct, 60.0, 100.0))),
        "comb_bess_user_configured": True,
        # Sub-Tab 4 Generator
        "comb_generator_rated_kw_num": float(max(10.0, sys_cfg.generator_rated_kw)),
        "comb_generator_fuel_type_select": str(sys_cfg.fuel_type),
        "comb_generator_min_load_num": int(round(np.clip(sys_cfg.generator_min_load_pct, 15.0, 50.0))),
        # Sub-Tab 5 System Mix & Rules
        "comb_mix_grid_limit_num": float(max(10.0, sys_cfg.grid_limit_kw)),
        "comb_mix_solar_share_slider": sol_slider_val,
        "comb_mix_bess_kwh_num": float(sys_cfg.battery_capacity_kwh if sys_cfg.enable_battery else 0.0),
        "comb_mix_bess_kw_num": float(sys_cfg.battery_power_kw if sys_cfg.enable_battery else 0.0),
        "comb_mix_gen_kw_num": float(sys_cfg.generator_rated_kw if sys_cfg.enable_generator else 0.0),
        "comb_rule1_select": str(rules_cfg.rule1_peak_priority),
        "comb_rule2_select": str(rules_cfg.rule2_battery_strategy),
        "comb_rule2_reserve_slider": int(round(np.clip(rules_cfg.peak_reserve_soc_pct, 10.0, 90.0))),
        "comb_rule3_select": str(rules_cfg.rule3_charging_sources),
    }

    solar_widget_sync: Dict[str, Any] = {
        "comb_solar_lat": float(sys_cfg.latitude),
        "comb_solar_lon": float(sys_cfg.longitude),
        "comb_solar_site_name": site_name,
        "comb_solar_preset_choice": preset_choice,
        "comb_solar_preset_select": preset_choice,
        "comb_solar_weather_mode_sel": (
            "Specific Year (Solar Data)"
            if str(getattr(sys_cfg, "solar_weather_mode", "single_year")) == "single_year"
            else "Typical Year (PVGIS TMY)"
        ),
        "comb_solar_weather_year_sel": int(getattr(sys_cfg, "solar_weather_year", 2025)),
        "comb_solar_sizing_radio": (
            "% of Annual Consumption"
            if sys_cfg.solar_sizing_method == "target_share_pct"
            else "Direct Size (kWp)"
        ),
        "comb_solar_target_share_num": float(np.clip(sys_cfg.target_consumption_share_pct, 0.1, 1000.0)),
        "comb_solar_direct_kwp_num": float(max(1.0, sys_cfg.solar_kwp)),
        "comb_solar_disable_inv_limit_chk": bool(getattr(sys_cfg, "disable_solar_inverter_limit", False)),
        "comb_solar_inv_ac_limit_num": float(max(0.0, default_inv_ac)),
        "comb_solar_inv_eff_num": int(round(np.clip(sys_cfg.inverter_efficiency_pct, 85.0, 100.0))),
    }

    fin_widget_sync: Dict[str, Any] = {
        "comb_strict_congestion_toggle": bool(fin_cfg.strict_grid_congestion_mode),
        "comb_fin_bill_mode_sel": _bill_mode_label_for_fin_cfg(fin_cfg),
        "comb_fin_curr_sel": str(getattr(fin_cfg, "currency_code", "EUR") or "EUR"),
        "comb_fin_en_p1_chk": bool(fin_cfg.enable_pillar_1_supplier),
        "comb_fin_en_p2_chk": bool(fin_cfg.enable_pillar_2_dso),
        "comb_fin_en_p3_chk": bool(fin_cfg.enable_pillar_3_metering),
        "comb_fin_en_p4_chk": bool(fin_cfg.enable_pillar_4_taxes),
        "comb_fin_supp_mode": (
            "Dual TOU Rate (Peak HT / Off-Peak NT)"
            if fin_cfg.supplier_pricing_mode == "dual_tou"
            else "Single Flat Rate"
        ),
        "comb_fin_supp_kwh": float(fin_cfg.supplier_energy_price_eur_kwh),
        "comb_fin_supp_ht": float(fin_cfg.supplier_peak_ht_eur_kwh),
        "comb_fin_supp_nt": float(fin_cfg.supplier_offpeak_nt_eur_kwh),
        "comb_fin_supp_gvo": float(fin_cfg.supplier_gvo_surcharge_eur_kwh),
        "comb_fin_supp_fix": float(fin_cfg.supplier_fixed_fee_eur_month),
        "comb_fin_solar_fi": float(fin_cfg.solar_export_feed_in_eur_kwh),
        "comb_fin_dso_conn": float(fin_cfg.dso_connection_fee_eur_month),
        "comb_fin_dso_fix": float(fin_cfg.dso_fixed_fee_eur_month),
        "comb_fin_dso_cap": float(fin_cfg.dso_capacity_fee_eur_kw_month),
        "comb_fin_dso_peak": float(fin_cfg.dso_peak_demand_fee_eur_kw_month),
        "comb_fin_dso_vol": float(fin_cfg.dso_transport_eur_kwh),
        "comb_fin_dso_3win_chk": bool(fin_cfg.dso_enable_three_window_tou),
        "comb_fin_dso_pen": float(fin_cfg.grid_overload_penalty_eur_kw),
        "comb_fin_dso_pen_chk": bool(fin_cfg.dso_enable_excess_capacity_penalty),
        "comb_fin_dso_breach_adj": bool(fin_cfg.dso_adjust_capacity_on_breach),
        "comb_fin_dso_pico_only": bool(fin_cfg.dso_bill_peak_on_pico_only),
        "comb_fin_dso_reg_adj": float(fin_cfg.dso_regulatory_adjustments_eur_month),
        "comb_fin_avoided_trafo": float(fin_cfg.avoided_transformer_rent_eur_month),
        "comb_fin_meter_fix": float(fin_cfg.metering_fixed_fee_eur_month),
        "comb_fin_tax_kwh": float(fin_cfg.energy_tax_eur_kwh),
        "comb_fin_tax_pct": float(fin_cfg.tax_surcharge_pct),
        "comb_fin_tax_credit": float(fin_cfg.annual_tax_reduction_credit_eur),
        "comb_fin_vat_pct": float(fin_cfg.vat_rate_pct),
        "comb_fin_vat_levies_chk": bool(fin_cfg.vat_applies_to_levies),
        # Hardware CAPEX & OPEX (Sub-Tab 6.2)
        "comb_fin_sol_turnkey": float(fin_cfg.solar_turnkey_eur_kwp),
        "comb_fin_sol_om": float(fin_cfg.solar_om_pct_of_capex),
        "comb_fin_sol_use_detail": bool(fin_cfg.solar_use_detailed_breakdown),
        "comb_fin_sol_mod": float(fin_cfg.solar_modules_eur_wp),
        "comb_fin_sol_inv": float(fin_cfg.solar_inverter_eur_w),
        "comb_fin_sol_mnt": float(fin_cfg.solar_mounting_eur_wp),
        "comb_fin_sol_lump_capex": float(fin_cfg.solar_lump_sum_capex_eur),
        "comb_fin_sol_lump_om": float(fin_cfg.solar_lump_sum_om_eur_year),
        "comb_fin_bat_rack": float(fin_cfg.battery_capex_eur_kwh),
        "comb_fin_bat_inv": float(fin_cfg.battery_capex_eur_kw),
        "comb_fin_bat_bop": float(fin_cfg.battery_fixed_bop_eur),
        "comb_fin_bat_om": float(fin_cfg.battery_om_pct_of_capex),
        "comb_fin_bat_aug_chk": bool(fin_cfg.enable_battery_augmentation),
        "comb_fin_bat_aug_yr": int(fin_cfg.battery_augmentation_year),
        "comb_fin_bat_aug_pct": float(fin_cfg.battery_augmentation_pct_of_racks),
        "comb_fin_bat_aug_lump": float(fin_cfg.battery_augmentation_lump_sum_eur),
        "comb_fin_bat_lump_capex": float(fin_cfg.battery_lump_sum_capex_eur),
        "comb_fin_bat_lump_om": float(fin_cfg.battery_lump_sum_om_eur_year),
        "comb_fin_gen_model": str(fin_cfg.generator_cost_model),
        "comb_fin_gen_capex": float(fin_cfg.generator_capex_eur),
        "comb_fin_gen_rent": float(fin_cfg.generator_rental_eur_month),
        "comb_fin_gen_rent_active_only": bool(fin_cfg.generator_rental_active_months_only),
        "comb_fin_gen_fuel": float(fin_cfg.fuel_price_eur_per_unit),
        "comb_fin_gen_maint": float(fin_cfg.generator_maintenance_eur_per_hour),
        "comb_fin_gen_lump_capex": float(fin_cfg.generator_lump_sum_capex_eur),
        "comb_fin_gen_lump_svc": float(fin_cfg.generator_lump_sum_service_opex_eur_year),
        "comb_fin_avoided_upgrade": (
            0.0 if fin_cfg.strict_grid_congestion_mode else float(fin_cfg.avoided_grid_upgrade_capex_eur)
        ),
        # Long-Term Projection (Sub-Tab 6.3)
        "comb_fin_tariff_esc": float(fin_cfg.tariff_escalation_pct_pa),
        "comb_fin_om_inf": float(fin_cfg.om_inflation_pct_pa),
        "comb_fin_sys_deg": float(fin_cfg.system_degradation_pct_pa),
        "comb_fin_disc_rate": float(fin_cfg.discount_rate_pct),
        "comb_fin_dso_tou_v": int(current_dso_tou_v) + 1,
    }

    return {
        "system_config": sys_cfg,
        "rules_config": rules_cfg,
        "financial_config": fin_cfg,
        "comb_pending_mix_widget_sync": mix_widget_sync,
        "comb_pending_solar_widget_sync": solar_widget_sync,
        "comb_pending_fin_widget_sync": fin_widget_sync,
    }


def _describe_hardware_solar(snap: CombinedScenarioSnapshot) -> str:
    if not snap.system_config.enable_solar:
        return "Off"
    return f"{fmt_num(snap.solar_derivation.installed_kwp, 1)} kWp ({fmt_num(snap.solar_derivation.effective_share_pct, 0)}%)"


def _describe_hardware_bess(snap: CombinedScenarioSnapshot) -> str:
    cfg = snap.system_config
    if not cfg.enable_battery:
        return "Off"
    dur_h = cfg.battery_capacity_kwh / max(1.0, cfg.battery_power_kw)
    return f"{fmt_num(cfg.battery_capacity_kwh, 0)} kWh / {fmt_num(cfg.battery_power_kw, 0)} kW ({fmt_num(dur_h, 1)}h)"


def _describe_hardware_gen(snap: CombinedScenarioSnapshot) -> str:
    cfg = snap.system_config
    if not cfg.enable_generator:
        return "Off"
    return f"{fmt_num(cfg.generator_rated_kw, 0)} kW ({cfg.fuel_type})"


def _describe_rules(snap: CombinedScenarioSnapshot) -> str:
    r = snap.rules_config
    r1 = "Bat 1st" if r.rule1_peak_priority == "battery_first" else "Gen 1st"
    r2 = (
        f"SC+Res({r.peak_reserve_soc_pct:.0f}%)"
        if r.rule2_battery_strategy == "self_consumption_reserve"
        else "Peak Shave"
    )
    r3_map = {
        "solar_only": "Sol",
        "solar_and_grid": "Sol+Grd",
        "solar_and_generator": "Sol+Gen",
        "all_sources": "All",
    }
    r3 = r3_map.get(r.rule3_charging_sources, r.rule3_charging_sources)
    return f"R1: {r1} | R2: {r2} | R3: {r3}"


def build_ab_comparison_matrix_df(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> pd.DataFrame:
    """
    Constructs a structured comparison DataFrame across Current Situation (Baseline),
    Scenario A, Scenario B, and Delta (B vs. A) covering Dimensioning, Technical KPIs,
    and 4-Pillar + 15-Year Financial outcomes. Accepts optional `scenarios` list (`1..N` ready).
    """
    if scenarios is not None and snap_a is None and snap_b is None:
        clean_list = [s for s in scenarios if s is not None]
        snap_a = clean_list[0] if len(clean_list) >= 1 else None
        snap_b = clean_list[1] if len(clean_list) >= 2 else None

    cols = ["Category", "Metric / KPI", "Current Situation", "Scenario A", "Scenario B", "Delta (B vs. A)"]
    ref = snap_a if snap_a is not None else snap_b
    if ref is None:
        return pd.DataFrame(columns=cols)

    same_curr = bool(
        snap_a is not None
        and snap_b is not None
        and snap_a.financial_config.currency_code == snap_b.financial_config.currency_code
    )
    ref_curr = str(ref.financial_config.currency_code or "EUR")

    def _fmt_curr_snap(snap: Optional[CombinedScenarioSnapshot], val_fn, signed: bool = False) -> str:
        if snap is None:
            return "—"
        c = str(snap.financial_config.currency_code or "EUR")
        return format_currency_value(float(val_fn(snap)), currency_code=c, signed=signed)

    def _fmt_curr_delta(val_fn) -> str:
        if snap_a is None or snap_b is None:
            return "—"
        if not same_curr:
            return "Mixed Currency"
        diff = float(val_fn(snap_b)) - float(val_fn(snap_a))
        return format_currency_value(diff, currency_code=ref_curr, signed=True)

    def _fmt_num_delta(val_fn, unit: str = "", decimals: int = 1) -> str:
        if snap_a is None or snap_b is None:
            return "—"
        diff = float(val_fn(snap_b)) - float(val_fn(snap_a))
        return f"{fmt_num(diff, decimals, signed=True)}{(' ' + unit) if unit else ''}"

    def _opt_payback(pb: Optional[float]) -> str:
        return f"{fmt_num(pb, 1)} yrs" if pb is not None else "N/A"

    def _opt_payback_delta(attr: str) -> str:
        if snap_a is None or snap_b is None:
            return "—"
        va = getattr(snap_a.financial_kpis, attr, None)
        vb = getattr(snap_b.financial_kpis, attr, None)
        if va is None or vb is None:
            return "N/A"
        return f"{fmt_num(float(vb) - float(va), 1, signed=True)} yrs"

    def _opt_pct(val: Optional[float]) -> str:
        return f"{fmt_num(val, 1)}%" if val is not None else "N/A"

    def _opt_pct_delta(attr: str) -> str:
        if snap_a is None or snap_b is None:
            return "—"
        va = getattr(snap_a.financial_kpis, attr, None)
        vb = getattr(snap_b.financial_kpis, attr, None)
        if va is None or vb is None:
            return "N/A"
        return f"{fmt_num(float(vb) - float(va), 1, signed=True)} pp"

    rows: List[Dict[str, str]] = []

    def add_row(cat: str, metric: str, cur_v: str, a_v: str, b_v: str, d_v: str) -> None:
        rows.append({
            "Category": cat,
            "Metric / KPI": metric,
            "Current Situation": cur_v,
            "Scenario A": a_v,
            "Scenario B": b_v,
            "Delta (B vs. A)": d_v,
        })

    # 1. Dimensioning & Rules
    add_row("Dimensioning & Rules", "Scenario Name", "Status Quo (No Add-On Hardware)", snap_a.name if snap_a else "—", snap_b.name if snap_b else "—", "—")
    add_row("Dimensioning & Rules", "Contracted Grid Limit (kW)", f"{fmt_num(ref.system_config.grid_limit_kw, 0)} kW", f"{fmt_num(snap_a.system_config.grid_limit_kw, 0)} kW" if snap_a else "—", f"{fmt_num(snap_b.system_config.grid_limit_kw, 0)} kW" if snap_b else "—", _fmt_num_delta(lambda s: s.system_config.grid_limit_kw, "kW", 0))
    add_row("Dimensioning & Rules", "Solar PV Size", "Off", _describe_hardware_solar(snap_a) if snap_a else "—", _describe_hardware_solar(snap_b) if snap_b else "—", _fmt_num_delta(lambda s: s.solar_derivation.installed_kwp if s.system_config.enable_solar else 0.0, "kWp", 1))
    add_row("Dimensioning & Rules", "Battery Storage (kWh / kW)", "Off", _describe_hardware_bess(snap_a) if snap_a else "—", _describe_hardware_bess(snap_b) if snap_b else "—", _fmt_num_delta(lambda s: s.system_config.battery_capacity_kwh if s.system_config.enable_battery else 0.0, "kWh", 0))
    add_row("Dimensioning & Rules", "Peaking Generator (kW & Fuel)", "Off", _describe_hardware_gen(snap_a) if snap_a else "—", _describe_hardware_gen(snap_b) if snap_b else "—", _fmt_num_delta(lambda s: s.system_config.generator_rated_kw if s.system_config.enable_generator else 0.0, "kW", 0))
    add_row("Dimensioning & Rules", "Operating Rules (R1 / R2 / R3)", "Grid Only", _describe_rules(snap_a) if snap_a else "—", _describe_rules(snap_b) if snap_b else "—", "—")

    # 2. Technical Performance
    tech_num_specs = [
        ("Peak Grid Demand (kW)", f"{fmt_num(ref.kpis.original_peak_kw, 1)} kW", lambda s: s.kpis.new_grid_peak_kw, "kW", 1, "kW"),
        ("Peak Demand Shaved (kW)", f"{fmt_num(0.0, 1)} kW", lambda s: s.kpis.peak_reduction_kw, "kW", 1, "kW"),
        ("Remaining Overload (hrs/yr)", f"{fmt_num(ref.kpis.baseline_overload_hours, 1)} hrs", lambda s: s.kpis.remaining_overload_hours, "hrs", 1, "hrs"),
        ("Remaining Overload Energy (kWh/yr)", f"{fmt_num(ref.kpis.baseline_overload_kwh, 0)} kWh", lambda s: s.kpis.remaining_overload_kwh, "kWh", 0, "kWh"),
        ("Overload Eliminated (%)", f"{fmt_num(0.0, 1)}%", lambda s: s.kpis.overload_eliminated_pct, "%", 1, "pp"),
        ("On-Site Autarky Share (%)", f"{fmt_num(0.0, 1)}%", lambda s: max(0.0, 100.0 - s.utilization_diagnostics.grid_direct_pct), "%", 1, "pp"),
        ("Supply Share: Grid (%)", f"{fmt_num(100.0, 1)}%", lambda s: s.utilization_diagnostics.grid_direct_pct, "%", 1, "pp"),
        ("Supply Share: Solar Direct (%)", f"{fmt_num(0.0, 1)}%", lambda s: s.utilization_diagnostics.solar_direct_pct, "%", 1, "pp"),
        ("Supply Share: Battery Discharge (%)", f"{fmt_num(0.0, 1)}%", lambda s: s.utilization_diagnostics.battery_discharge_pct, "%", 1, "pp"),
        ("Supply Share: Generator (%)", f"{fmt_num(0.0, 1)}%", lambda s: s.utilization_diagnostics.generator_direct_pct, "%", 1, "pp"),
        ("Annual Residual Grid Import (MWh/yr)", f"{fmt_num(ref.kpis.annual_consumption_kwh / 1000.0, 1)} MWh", lambda s: s.kpis.grid_import_total_kwh / 1000.0, "MWh", 1, "MWh"),
        ("Solar Exported Surplus (MWh/yr)", f"{fmt_num(0.0, 1)} MWh", lambda s: (s.kpis.solar_export_kwh / 1000.0) if s.system_config.enable_solar else 0.0, "MWh", 1, "MWh"),
    ]
    for m_lbl, cur_str, fn, disp_unit, dec, d_unit in tech_num_specs:
        sep_u = "" if disp_unit == "%" else f" {disp_unit}"
        add_row("Technical Performance", m_lbl, cur_str, f"{fmt_num(fn(snap_a), dec)}{sep_u}" if snap_a else "—", f"{fmt_num(fn(snap_b), dec)}{sep_u}" if snap_b else "—", _fmt_num_delta(fn, d_unit, dec))

    add_row(
        "Technical Performance",
        "Solar Generation / Used On-Site",
        "Off",
        f"{fmt_num(snap_a.kpis.solar_total_generation_kwh / 1000.0, 1)} MWh ({fmt_num(snap_a.utilization_diagnostics.solar_utilization_pct, 0)}% used)" if snap_a and snap_a.system_config.enable_solar else ("Off" if snap_a else "—"),
        f"{fmt_num(snap_b.kpis.solar_total_generation_kwh / 1000.0, 1)} MWh ({fmt_num(snap_b.utilization_diagnostics.solar_utilization_pct, 0)}% used)" if snap_b and snap_b.system_config.enable_solar else ("Off" if snap_b else "—"),
        _fmt_num_delta(lambda s: (s.kpis.solar_total_generation_kwh / 1000.0) if s.system_config.enable_solar else 0.0, "MWh", 1),
    )
    add_row(
        "Technical Performance",
        "Battery Cycles / Capacity Used",
        f"{fmt_num(0.0, 1)} cyc",
        f"{fmt_num(snap_a.kpis.battery_equivalent_cycles, 1)} cyc ({fmt_num(snap_a.utilization_diagnostics.bess_capacity_utilization_pct, 0)}%)" if snap_a and snap_a.system_config.enable_battery else ("Off" if snap_a else "—"),
        f"{fmt_num(snap_b.kpis.battery_equivalent_cycles, 1)} cyc ({fmt_num(snap_b.utilization_diagnostics.bess_capacity_utilization_pct, 0)}%)" if snap_b and snap_b.system_config.enable_battery else ("Off" if snap_b else "—"),
        _fmt_num_delta(lambda s: s.kpis.battery_equivalent_cycles, "cyc", 1),
    )
    add_row(
        "Technical Performance",
        "Battery Min SoC / Unused Reserve",
        "Off",
        f"Min {fmt_num(snap_a.utilization_diagnostics.bess_min_soc_reached_pct, 0)}% ({fmt_num(snap_a.utilization_diagnostics.bess_unused_usable_kwh, 0)} kWh unused)" if snap_a and snap_a.system_config.enable_battery else ("Off" if snap_a else "—"),
        f"Min {fmt_num(snap_b.utilization_diagnostics.bess_min_soc_reached_pct, 0)}% ({fmt_num(snap_b.utilization_diagnostics.bess_unused_usable_kwh, 0)} kWh unused)" if snap_b and snap_b.system_config.enable_battery else ("Off" if snap_b else "—"),
        _fmt_num_delta(lambda s: s.utilization_diagnostics.bess_unused_usable_kwh if s.system_config.enable_battery else 0.0, "kWh", 0),
    )
    add_row(
        "Technical Performance",
        "Generator Runtime & Fuel",
        f"{fmt_num(0.0, 1)} hrs",
        f"{fmt_num(snap_a.kpis.generator_runtime_hours, 1)} hrs ({fmt_num(snap_a.kpis.generator_fuel_total, 0)} {snap_a.kpis.generator_fuel_unit})" if snap_a and snap_a.system_config.enable_generator else ("Off" if snap_a else "—"),
        f"{fmt_num(snap_b.kpis.generator_runtime_hours, 1)} hrs ({fmt_num(snap_b.kpis.generator_fuel_total, 0)} {snap_b.kpis.generator_fuel_unit})" if snap_b and snap_b.system_config.enable_generator else ("Off" if snap_b else "—"),
        _fmt_num_delta(lambda s: s.kpis.generator_runtime_hours, "hrs", 1),
    )

    # 3. Economics & 15-Year Financials (only when Financials was enabled on at least one snapshot)
    has_fin_a = bool(snap_a is not None and getattr(snap_a.system_config, "enable_financials", False))
    has_fin_b = bool(snap_b is not None and getattr(snap_b.system_config, "enable_financials", False))
    if not (has_fin_a or has_fin_b):
        return pd.DataFrame(rows, columns=cols)

    fin_ref = snap_a if has_fin_a else snap_b
    assert fin_ref is not None
    fin_ref_curr = str(fin_ref.financial_config.currency_code or "EUR")

    def _fin_curr_cell(snap: Optional[CombinedScenarioSnapshot], fn, signed: bool = False) -> str:
        if snap is None:
            return "—"
        if not getattr(snap.system_config, "enable_financials", False):
            return "Financials Off"
        return _fmt_curr_snap(snap, fn, signed=signed)

    def _fin_curr_delta_cell(fn) -> str:
        return _fmt_curr_delta(fn) if (has_fin_a and has_fin_b) else "—"

    econ_curr_specs = [
        ("Gross Hardware CAPEX", 0.0, lambda s: s.financial_kpis.gross_capex_eur, False),
        ("Avoided Grid Upgrade Credit", 0.0, lambda s: s.financial_kpis.avoided_grid_upgrade_capex_eur, False),
        ("Net CAPEX", 0.0, lambda s: s.financial_kpis.total_capex_eur, False),
        ("Year-1 Pillar 1: Energy Supply", fin_ref.financial_kpis.baseline_pillar1_supply_eur, lambda s: s.financial_kpis.combined_pillar1_supply_eur, False),
        ("Year-1 Pillar 2: DSO Network (excl. Penalties)", max(0.0, fin_ref.financial_kpis.baseline_pillar2_dso_eur - fin_ref.financial_kpis.baseline_penalty_cost_eur), lambda s: max(0.0, s.financial_kpis.combined_pillar2_dso_eur - s.financial_kpis.combined_grid_penalty_cost_eur), False),
        ("Year-1 Pillar 2: Overload Penalties", fin_ref.financial_kpis.baseline_penalty_cost_eur, lambda s: s.financial_kpis.combined_grid_penalty_cost_eur, False),
        ("Year-1 Pillar 3 & 4: Metering & Taxes", fin_ref.financial_kpis.baseline_pillar3_metering_eur + fin_ref.financial_kpis.baseline_pillar4_taxes_eur, lambda s: s.financial_kpis.combined_pillar3_metering_eur + s.financial_kpis.combined_pillar4_taxes_eur, False),
        ("Year-1 Total Grid Bill (4-Pillar)", fin_ref.financial_kpis.baseline_total_opex_eur, lambda s: s.financial_kpis.combined_grid_total_eur, False),
        ("Year-1 Hardware OPEX & Fuel", 0.0, lambda s: s.financial_kpis.system_om_and_fuel_y1_eur, False),
        ("Year-1 Solar Export Revenue", 0.0, lambda s: s.financial_kpis.solar_export_revenue_eur, False),
        ("Year-1 Total Annual OPEX", fin_ref.financial_kpis.baseline_total_opex_eur, lambda s: s.financial_kpis.total_annual_opex_eur, False),
        ("Year-1 Net Annual Savings (vs. Current)", 0.0, lambda s: s.financial_kpis.annual_savings_eur, True),
    ]
    for m_lbl, cur_val, fn, signed in econ_curr_specs:
        add_row("Economics & 15-Year Financials", m_lbl, format_currency_value(cur_val, fin_ref_curr), _fin_curr_cell(snap_a, fn, signed=signed), _fin_curr_cell(snap_b, fn, signed=signed), _fin_curr_delta_cell(fn))

    add_row("Economics & 15-Year Financials", "Payback Period", "—", (_opt_payback(snap_a.financial_kpis.payback_years) if has_fin_a else "Financials Off") if snap_a else "—", (_opt_payback(snap_b.financial_kpis.payback_years) if has_fin_b else "Financials Off") if snap_b else "—", _opt_payback_delta("payback_years") if (has_fin_a and has_fin_b) else "—")
    add_row("Economics & 15-Year Financials", "Discounted Payback Period", "—", (_opt_payback(snap_a.financial_kpis.discounted_payback_years) if has_fin_a else "Financials Off") if snap_a else "—", (_opt_payback(snap_b.financial_kpis.discounted_payback_years) if has_fin_b else "Financials Off") if snap_b else "—", _opt_payback_delta("discounted_payback_years") if (has_fin_a and has_fin_b) else "—")

    econ_15y_specs = [
        ("15-Year Cumulative TCO", fin_ref.financial_kpis.tco_15y_baseline_eur, lambda s: s.financial_kpis.tco_15y_combined_eur, False),
        ("15-Year TCO Net Savings (vs. Current)", 0.0, lambda s: s.financial_kpis.tco_15y_savings_eur, True),
        ("15-Year Net Present Value (NPV)", 0.0, lambda s: s.financial_kpis.npv_15y_eur, True),
    ]
    for m_lbl, cur_val, fn, signed in econ_15y_specs:
        add_row("Economics & 15-Year Financials", m_lbl, format_currency_value(cur_val, fin_ref_curr), _fin_curr_cell(snap_a, fn, signed=signed), _fin_curr_cell(snap_b, fn, signed=signed), _fin_curr_delta_cell(fn))

    add_row("Economics & 15-Year Financials", "15-Year Internal Rate of Return (IRR)", "—", (_opt_pct(snap_a.financial_kpis.irr_15y_pct) if has_fin_a else "Financials Off") if snap_a else "—", (_opt_pct(snap_b.financial_kpis.irr_15y_pct) if has_fin_b else "Financials Off") if snap_b else "—", _opt_pct_delta("irr_15y_pct") if (has_fin_a and has_fin_b) else "—")
    add_row("Economics & 15-Year Financials", "15-Year Benefit-Cost Ratio (BCR)", "—", (f"{fmt_num(snap_a.financial_kpis.benefit_cost_ratio_15y, 2)}x" if has_fin_a else "Financials Off") if snap_a else "—", (f"{fmt_num(snap_b.financial_kpis.benefit_cost_ratio_15y, 2)}x" if has_fin_b else "Financials Off") if snap_b else "—", _fmt_num_delta(lambda s: s.financial_kpis.benefit_cost_ratio_15y, "x", 2) if (has_fin_a and has_fin_b) else "—")
    add_row(
        "Economics & 15-Year Financials",
        "On-Site System LCOE (per kWh)",
        f"{fmt_curr(fin_ref.financial_kpis.effective_blended_grid_rate_eur_kwh, fin_ref_curr, decimals=3)}/kWh (Grid)",
        (f"{fmt_curr(snap_a.financial_kpis.system_lcoe_eur_kwh, str(snap_a.financial_config.currency_code or 'EUR'), decimals=3)}/kWh" if has_fin_a else "Financials Off") if snap_a else "—",
        (f"{fmt_curr(snap_b.financial_kpis.system_lcoe_eur_kwh, str(snap_b.financial_config.currency_code or 'EUR'), decimals=3)}/kWh" if has_fin_b else "Financials Off") if snap_b else "—",
        f"{fmt_num(snap_b.financial_kpis.system_lcoe_eur_kwh - snap_a.financial_kpis.system_lcoe_eur_kwh, 3, signed=True)}/kWh" if (has_fin_a and has_fin_b and same_curr) else "—",
    )
    add_row(
        "Economics & 15-Year Financials",
        "Annualized Cost per Shaved Peak kW",
        "—",
        (_fin_curr_cell(snap_a, lambda s: s.financial_kpis.annualized_cost_per_shaved_kw_eur) + "/kW/yr" if has_fin_a else "Financials Off") if snap_a else "—",
        (_fin_curr_cell(snap_b, lambda s: s.financial_kpis.annualized_cost_per_shaved_kw_eur) + "/kW/yr" if has_fin_b else "Financials Off") if snap_b else "—",
        _fin_curr_delta_cell(lambda s: s.financial_kpis.annualized_cost_per_shaved_kw_eur),
    )

    return pd.DataFrame(rows, columns=cols)


def build_multi_scenario_leaderboard_df(
    scenarios: Sequence[CombinedScenarioSnapshot],
) -> pd.DataFrame:
    """
    Ranks `1..N` scenario snapshots in a decision matrix (1-to-N ready).
    Sorts by 15-Year TCO (when financials are enabled across all scenarios in one currency)
    or by Remaining Overload -> Grid Peak -> On-Site Autarky in technical-only mode.
    """
    clean = [s for s in scenarios if s is not None]
    if not clean:
        return pd.DataFrame()

    all_fin = all(bool(getattr(s.system_config, "enable_financials", False)) for s in clean)
    any_fin = any(bool(getattr(s.system_config, "enable_financials", False)) for s in clean)
    same_curr = len({str(s.financial_config.currency_code or "EUR") for s in clean}) == 1

    if all_fin and same_curr:
        ranked = sorted(clean, key=lambda s: (float(s.financial_kpis.tco_15y_combined_eur), float(s.kpis.remaining_overload_hours), float(s.kpis.new_grid_peak_kw)))
    else:
        ranked = sorted(clean, key=lambda s: (float(s.kpis.remaining_overload_hours), float(s.kpis.new_grid_peak_kw), -(100.0 - float(s.utilization_diagnostics.grid_direct_pct))))

    rows: List[Dict[str, Any]] = []
    for idx, s in enumerate(ranked, start=1):
        hw_parts = []
        if s.system_config.enable_solar:
            hw_parts.append(f"PV {fmt_num(s.solar_derivation.installed_kwp, 0)} kWp")
        if s.system_config.enable_battery:
            hw_parts.append(f"BESS {fmt_num(s.system_config.battery_capacity_kwh, 0)} kWh")
        if s.system_config.enable_generator:
            hw_parts.append(f"Gen {fmt_num(s.system_config.generator_rated_kw, 0)} kW")
        hw_mix = " + ".join(hw_parts) if hw_parts else "Grid Only"
        autarky = round(max(0.0, 100.0 - float(s.utilization_diagnostics.grid_direct_pct)), 1)
        row: Dict[str, Any] = {
            "Rank": idx,
            "Scenario": s.name,
            "Hardware Mix": hw_mix,
            "Grid Peak (kW)": round(float(s.kpis.new_grid_peak_kw), 1),
            "Remaining Overload (hrs)": round(float(s.kpis.remaining_overload_hours), 1),
            "On-Site Autarky (%)": autarky,
        }
        if any_fin:
            has_f = bool(getattr(s.system_config, "enable_financials", False))
            c = str(s.financial_config.currency_code or "EUR")
            fk = s.financial_kpis
            row["Net CAPEX"] = format_currency_value(fk.total_capex_eur, c) if has_f else "Financials Off"
            row["Year-1 Net Savings"] = format_currency_value(fk.annual_savings_eur, c, signed=True) if has_f else "Financials Off"
            row["Payback Period"] = (f"{fmt_num(fk.payback_years, 1)} yrs" if fk.payback_years is not None else "N/A") if has_f else "Financials Off"
            row["15-Year TCO"] = format_currency_value(fk.tco_15y_combined_eur, c) if has_f else "Financials Off"
            row["15-Year NPV"] = format_currency_value(fk.npv_15y_eur, c, signed=True) if has_f else "Financials Off"
        rows.append(row)
    return pd.DataFrame(rows)
