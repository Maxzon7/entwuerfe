"""
========================================================================================
Shared Foundation: Standalone Baseline Quick-Loader & Snapshot I/O (ui_sandbox/common/baseline_loader.py)
========================================================================================

Allows every standalone scenario sandbox (`NewContract_sandbox`, `Solar_sandbox`,
`BESS_sandbox`, `SolarBESS_sandbox`, `Generator_sandbox`) to run 100% independently
on its own port with:
  - Built-in Flagship Presets:
      1. Preset A: Rotterdam / Dutch WKO Site (Stedin Region - 110 kW Limit, EUR)
      2. Preset B: EDEMSA Mendoza T2 RMT (Bodegas Salentein - 430 kW Limit, ARS)
      3. Preset C: Standard Enexis Commercial MS-D (250 kW Limit, EUR)
      4. Preset D: Liander Industrial MS (350 kW Limit, EUR)
  - Direct 15-Minute CSV Upload (`normalize_load_profile_2025`)
  - Baseline Snapshot JSON Import/Export (`export_baseline_snapshot_json`, `import_baseline_snapshot_json`)
========================================================================================
"""

import os
import json
from typing import Tuple, Dict, Any, Optional
import numpy as np
import pandas as pd
import streamlit as st

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        TariffStage,
        PricingMode,
        LoadSeries2025,
        DSOTariff,
        SupplierTariff,
        MeteringTariff,
        LevyConfig,
        StatusQuoConfig2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        create_reference_2025_timestamps,
        classify_liander_tou_window,
        classify_edemsa_tou_windows,
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
        synthesize_edemsa_salentein_load_profile_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        get_rotterdam_stedin_wko_config_2025,
        get_edemsa_salentein_config_2025,
        get_stage_1_default_config_2025,
        get_dso_tariff_from_catalog,
        get_default_supplier_tariff_2025,
        get_default_metering_tariff_2025,
        get_default_levy_config_2025,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        TariffStage,
        PricingMode,
        LoadSeries2025,
        DSOTariff,
        SupplierTariff,
        MeteringTariff,
        LevyConfig,
        StatusQuoConfig2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        create_reference_2025_timestamps,
        classify_liander_tou_window,
        classify_edemsa_tou_windows,
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
        synthesize_edemsa_salentein_load_profile_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        get_rotterdam_stedin_wko_config_2025,
        get_edemsa_salentein_config_2025,
        get_stage_1_default_config_2025,
        get_dso_tariff_from_catalog,
        get_default_supplier_tariff_2025,
        get_default_metering_tariff_2025,
        get_default_levy_config_2025,
    )


STANDALONE_PRESET_OPTIONS = [
    "Preset A: Rotterdam / Dutch WKO Site (Stedin Region - 110 kW Limit, EUR)",
    "Preset B: EDEMSA Mendoza T2 RMT (Bodegas Salentein - 430 kW Limit, ARS)",
    "Preset C: Standard Enexis Commercial MS-D (250 kW Limit, EUR)",
    "Preset D: Liander Industrial MS (350 kW Limit, EUR)",
    "Custom: Upload 15-Min CSV or Load Baseline Snapshot (.json)",
]


def _load_rotterdam_paula_series() -> Tuple[LoadSeries2025, str]:
    """Loads Paula3_totaal_clean.csv normalized to 35,040 steps for 2025."""
    current_dir = os.path.abspath(os.path.dirname(__file__))
    candidates = [
        os.path.abspath(os.path.join(current_dir, "..", "BESS_sandbox", "data", "Paula3_totaal_clean.csv")),
        os.path.abspath(os.path.join(current_dir, "..", "Currentsituation_sandbox", "data", "Paula3_totaal_clean.csv")),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                raw_df = pd.read_csv(p)
                if "Date" in raw_df.columns and "Time" in raw_df.columns:
                    ts = pd.to_datetime(raw_df["Date"] + " " + raw_df["Time"], format="%d.%m.%Y %H:%M", errors="coerce")
                    raw_df["timestamp"] = ts
                p_col = "Total_Demand_kW" if "Total_Demand_kW" in raw_df.columns else raw_df.columns[-1]
                load_norm, _ = normalize_load_profile_2025(raw_df=raw_df, power_col=p_col, time_col="timestamp")
                return load_norm, "Rotterdam / Dutch WKO Site (Paula3_totaal_clean.csv — 131.4 kW Peak)"
            except Exception:
                pass
    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=131.4)
    return load_bench, "Rotterdam / Dutch WKO Benchmark (131.4 kW Peak)"


def load_preset_baseline_2025(preset_choice: str) -> Tuple[LoadSeries2025, StatusQuoConfig2025, str]:
    """Instantiates `(LoadSeries2025, StatusQuoConfig2025, site_label)` for any preset choice."""
    if "Preset A" in preset_choice or "Rotterdam" in preset_choice:
        load_obj, label = _load_rotterdam_paula_series()
        cfg = get_rotterdam_stedin_wko_config_2025(contracted_capacity_kw=110.0)
        return load_obj, cfg, label
    elif "Preset B" in preset_choice or "EDEMSA" in preset_choice:
        load_obj = synthesize_edemsa_salentein_load_profile_2025()
        cfg = get_edemsa_salentein_config_2025(contracted_capacity_kw=430.0)
        label = "EDEMSA Bodegas Salentein T2 RMT (691.0 kW Max / 649.0 kW Pico vs. 430.0 kW Limit)"
        return load_obj, cfg, label
    elif "Preset D" in preset_choice or "Liander" in preset_choice:
        load_obj = synthesize_benchmark_load_profile_2025(nominal_peak_kw=440.0)
        dso = get_dso_tariff_from_catalog(
            dso_company="Liander Netbeheer B.V.",
            tier_name="MS (> 136 t/m 2.000 kW)",
            contracted_capacity_kw=350.0,
        )
        cfg = StatusQuoConfig2025(
            stage=TariffStage.STAGE_1_DEFAULT,
            dso=dso,
            supplier=get_default_supplier_tariff_2025(pricing_mode=PricingMode.FIXED),
            metering=get_default_metering_tariff_2025(),
            levies=get_default_levy_config_2025(),
            currency_code="EUR",
            market_mode="unbundled_4_pillar",
        )
        return load_obj, cfg, "Liander Industrial Facility MS (440.0 kW Peak vs. 350.0 kW Limit)"
    else:
        load_obj = synthesize_benchmark_load_profile_2025(nominal_peak_kw=295.0)
        cfg = get_stage_1_default_config_2025(pricing_mode=PricingMode.FIXED, contracted_capacity_kw=250.0)
        return load_obj, cfg, "Enexis Commercial MS-D Benchmark (295.0 kW Peak vs. 250.0 kW Limit)"


def export_baseline_snapshot_json(
    load_series: LoadSeries2025,
    config: StatusQuoConfig2025,
    site_label: str,
) -> str:
    """
    Serializes the active `LoadSeries2025` and `StatusQuoConfig2025` into a portable JSON snapshot
    that can be loaded into any standalone scenario sandbox.
    """
    payload = {
        "schema_version": "2025.1",
        "site_label": site_label,
        "currency_code": config.currency_code,
        "market_mode": config.market_mode,
        "enable_pillar_1_supplier": config.enable_pillar_1_supplier,
        "enable_pillar_2_dso": config.enable_pillar_2_dso,
        "enable_pillar_3_metering": config.enable_pillar_3_metering,
        "enable_pillar_4_taxes": config.enable_pillar_4_taxes,
        "discount_rate_pct": config.discount_rate_pct,
        "energy_escalation_pct": config.energy_escalation_pct,
        "evaluation_horizon_years": config.evaluation_horizon_years,
        "dso": config.dso.to_dict(),
        "supplier": config.supplier.to_dict(),
        "metering": config.metering.to_dict(),
        "levies": config.levies.to_dict(),
        "has_edemsa_3win": bool(load_series.tou_window_codes is not None),
        "power_kw": [round(float(x), 3) for x in load_series.power_kw],
    }
    return json.dumps(payload)


def import_baseline_snapshot_json(raw_json: str) -> Tuple[LoadSeries2025, StatusQuoConfig2025, str]:
    """Deserializes a portable Baseline Snapshot JSON back into `(LoadSeries2025, StatusQuoConfig2025, site_label)`."""
    data = json.loads(raw_json)
    site_label = str(data.get("site_label", "Imported Baseline Snapshot"))
    ref_index = create_reference_2025_timestamps()
    p_arr = np.asarray(data.get("power_kw", []), dtype=float)
    if len(p_arr) != 35040:
        p_arr = np.resize(p_arr, 35040)

    has_3win = bool(data.get("has_edemsa_3win", False))
    tou_codes = classify_edemsa_tou_windows(ref_index) if has_3win else None
    is_peak_tou = (tou_codes == 1) if has_3win else classify_liander_tou_window(ref_index)

    load_obj = LoadSeries2025(
        timestamps=ref_index,
        power_kw=p_arr,
        energy_kwh=p_arr * 0.25,
        month_indices=ref_index.month.to_numpy(dtype=int),
        is_peak_tou=is_peak_tou,
        total_steps=35040,
        step_hours=0.25,
        tou_window_codes=tou_codes,
    )

    dso_d = data.get("dso", {})
    dso = DSOTariff(**{k: v for k, v in dso_d.items() if k in DSOTariff.__dataclass_fields__})

    sup_d = dict(data.get("supplier", {}))
    if "pricing_mode" in sup_d and isinstance(sup_d["pricing_mode"], str):
        try:
            sup_d["pricing_mode"] = PricingMode(sup_d["pricing_mode"])
        except Exception:
            sup_d["pricing_mode"] = PricingMode.FIXED
    supplier = SupplierTariff(**{k: v for k, v in sup_d.items() if k in SupplierTariff.__dataclass_fields__})

    met_d = data.get("metering", {})
    metering = MeteringTariff(**{k: v for k, v in met_d.items() if k in MeteringTariff.__dataclass_fields__})

    lev_d = data.get("levies", {})
    levies = LevyConfig(**{k: v for k, v in lev_d.items() if k in LevyConfig.__dataclass_fields__})

    cfg = StatusQuoConfig2025(
        stage=TariffStage.STAGE_2_QUOTE,
        dso=dso,
        supplier=supplier,
        metering=metering,
        levies=levies,
        discount_rate_pct=float(data.get("discount_rate_pct", 5.0)),
        energy_escalation_pct=float(data.get("energy_escalation_pct", 3.0)),
        evaluation_horizon_years=int(data.get("evaluation_horizon_years", 15)),
        currency_code=str(data.get("currency_code", "EUR")),
        market_mode=str(data.get("market_mode", "unbundled_4_pillar")),
        enable_pillar_1_supplier=bool(data.get("enable_pillar_1_supplier", True)),
        enable_pillar_2_dso=bool(data.get("enable_pillar_2_dso", True)),
        enable_pillar_3_metering=bool(data.get("enable_pillar_3_metering", True)),
        enable_pillar_4_taxes=bool(data.get("enable_pillar_4_taxes", True)),
    )
    return load_obj, cfg, site_label


def render_standalone_baseline_control_bar(
    key_prefix: str,
    default_preset_idx: int = 0,
) -> Tuple[LoadSeries2025, StatusQuoConfig2025, str]:
    """
    Renders a unified top control bar for any standalone scenario sandbox so it can be launched
    and tested completely independently while using the exact same `LoadSeries2025` and
    `StatusQuoConfig2025` foundation.
    """
    with st.container(border=True):
        c_sel, c_cap, c_info = st.columns([2.1, 1.0, 1.4])
        with c_sel:
            preset_choice = st.selectbox(
                ":material/dataset: Standalone Baseline Profile & 4-Pillar Contract Preset",
                options=STANDALONE_PRESET_OPTIONS,
                index=default_preset_idx,
                key=f"{key_prefix}_standalone_preset",
                help="Select a built-in calibrated facility benchmark or upload a custom 15-minute CSV / Baseline Snapshot (.json).",
            )

        if "Custom:" in preset_choice:
            u1, u2 = st.columns(2)
            with u1:
                up_json = st.file_uploader(
                    "Load Baseline Snapshot (.json from Currentsituation_sandbox)",
                    type=["json"],
                    key=f"{key_prefix}_up_json",
                )
            with u2:
                up_csv = st.file_uploader(
                    "Or Upload 15-Min Load CSV",
                    type=["csv"],
                    key=f"{key_prefix}_up_csv",
                )

            if up_json is not None:
                try:
                    raw_str = up_json.getvalue().decode("utf-8")
                    load_obj, cfg_obj, site_lbl = import_baseline_snapshot_json(raw_str)
                except Exception as exc:
                    st.warning(f"Failed to parse JSON snapshot ({exc}). Falling back to Preset A.")
                    load_obj, cfg_obj, site_lbl = load_preset_baseline_2025(STANDALONE_PRESET_OPTIONS[0])
            elif up_csv is not None:
                try:
                    df_csv = pd.read_csv(up_csv)
                    p_col = "Total_Demand_kW" if "Total_Demand_kW" in df_csv.columns else df_csv.columns[-1]
                    t_col = "timestamp" if "timestamp" in df_csv.columns else None
                    load_obj, _ = normalize_load_profile_2025(raw_df=df_csv, power_col=p_col, time_col=t_col)
                    _, cfg_obj, _ = load_preset_baseline_2025(STANDALONE_PRESET_OPTIONS[0])
                    site_lbl = f"Custom CSV ({up_csv.name})"
                except Exception as exc:
                    st.warning(f"Failed to parse CSV ({exc}). Falling back to Preset A.")
                    load_obj, cfg_obj, site_lbl = load_preset_baseline_2025(STANDALONE_PRESET_OPTIONS[0])
            elif "shared_baseline_snapshot" in st.session_state:
                snap = st.session_state["shared_baseline_snapshot"]
                load_obj, cfg_obj, site_lbl = snap["load"], snap["config"], snap["site_label"]
            else:
                load_obj, cfg_obj, site_lbl = load_preset_baseline_2025(STANDALONE_PRESET_OPTIONS[0])
        else:
            load_obj, cfg_obj, site_lbl = load_preset_baseline_2025(preset_choice)

        with c_cap:
            custom_limit = st.number_input(
                ":material/speed: Contracted Grid Limit P_contract (kW)",
                min_value=10.0,
                max_value=20000.0,
                value=float(cfg_obj.dso.contracted_capacity_kw),
                step=10.0,
                key=f"{key_prefix}_p_contract_{preset_choice[:8]}",
                help="Active contracted grid capacity limit (GTV / Potencia Contratada) used for overload and 4-Pillar DSO billing.",
            )
            cfg_obj.dso.contracted_capacity_kw = float(custom_limit)

        with c_info:
            peak_kw = load_obj.peak_demand_kw
            excess_kw = max(0.0, peak_kw - cfg_obj.dso.contracted_capacity_kw)
            overload_steps = int(np.sum(load_obj.power_kw > cfg_obj.dso.contracted_capacity_kw))
            overload_hrs = overload_steps * 0.25
            status_color = "#f87171" if excess_kw > 0 else "#4ade80"
            status_txt = f"BREACH: +{excess_kw:,.1f} kW ({overload_hrs:,.1f} hrs/yr)" if excess_kw > 0 else "WITHIN CONTRACT LIMIT"
            st.markdown(
                f"""
                <div style="background:#0f172a; border:1px solid #334155; border-radius:6px; padding:8px 12px; font-size:0.79rem;">
                    <div style="color:#94a3b8; font-weight:600;">Active Facility Baseline ({cfg_obj.currency_code} | {cfg_obj.dso.dso_name})</div>
                    <div style="color:#f8fafc; font-weight:700; margin-top:2px;">
                        Energy: {load_obj.total_energy_kwh:,.0f} kWh/yr &nbsp;|&nbsp; Peak: {peak_kw:,.1f} kW
                    </div>
                    <div style="color:{status_color}; font-weight:700; margin-top:2px;">{status_txt}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    return load_obj, cfg_obj, site_lbl

