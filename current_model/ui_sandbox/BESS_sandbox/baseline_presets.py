"""
========================================================================================
BESS Sandbox: Baseline Presets & Test Benchmarks (baseline_presets.py)
========================================================================================

Pre-configured 15-minute load profiles, utility contracts, and BESS configurations:
  1. Case 1: Dutch Industrial Peak Shaving (Liander AC4b + BESS vs. AC5a Upgrade)
  2. Case 2: Medium Commercial Peak Shaver (Enexis MS-D 2025)
  3. Case 3: Custom CSV / Active Session Profile Adapter
========================================================================================
"""

import os
import sys
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

# Path bootstrapping
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
UI_SANDBOX_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))
for p in [CURRENT_DIR, UI_SANDBOX_DIR, CURRENT_MODEL_DIR, WORKSPACE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Imports from production models & core
try:
    from current_model.models.bess import BESSConfig
    from current_model.models.contract import Contract
except ImportError:
    from models.bess import BESSConfig
    from models.contract import Contract

# Imports from Currentsituation_sandbox engine
try:
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        LIANDER_2025_GRID_TIERS,
        ENEXIS_2025_GRID_TIERS,
    )
except ImportError:
    try:
        from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
            normalize_load_profile_2025,
            synthesize_benchmark_load_profile_2025,
        )
        from current_model.ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
            LIANDER_2025_GRID_TIERS,
            ENEXIS_2025_GRID_TIERS,
        )
    except ImportError:
        normalize_load_profile_2025 = None
        synthesize_benchmark_load_profile_2025 = None
        LIANDER_2025_GRID_TIERS = {}
        ENEXIS_2025_GRID_TIERS = {}


@dataclass
class BaselinePreset:
    """Pre-configured sandbox test scenario."""
    key: str
    title: str
    description: str
    grid_limit_kw: float
    load_df: pd.DataFrame
    contract_baseline: Contract
    contract_bess: Contract
    bess_config: BESSConfig
    avoided_grid_upgrade_capex: float = 0.0
    avoided_monthly_transformer_rent: float = 0.0
    notes: str = ""


# Alias for readability
BaselineComparisonPreset = BaselinePreset


def get_case1_liander_industrial_preset() -> BaselinePreset:
    """
    Case 1: Dutch Industrial Peak Shaving (Liander AC4b + BESS vs. AC5a Upgrade).
    
    Load: ~750 MWh/yr, 350 kW peak demand.
    Baseline alternative (AC5a):
      - Station / connection CAPEX: EUR 45,000 one-time
      - Transformer rent: EUR 354.00/month
      - Contracted GTV: 350 kW @ EUR 2.2233/kW/month
      - Peak demand: EUR 3.4600/kW/month
    BESS alternative (AC4b):
      - Stays at 147 kW low-voltage limit
      - Contracted GTV: 147 kW @ EUR 3.6567/kW/month
      - Peak demand: EUR 3.4600/kW/month
      - Transformer rent: EUR 0.00
      - Avoided CAPEX: EUR 45,000
    """
    # Generate 350 kW peak industrial profile (35,040 steps)
    if synthesize_benchmark_load_profile_2025:
        load_obj = synthesize_benchmark_load_profile_2025(
            profile_type="commercial_hvac",
            nominal_peak_kw=350.0
        )
        load_df = pd.DataFrame({
            "timestamp": load_obj.timestamps,
            "Total_Demand_kW": load_obj.power_kw,
            "P_Load_kW": load_obj.power_kw
        })
    else:
        # Fallback synthetic series
        ts = pd.date_range("2026-01-01 00:00:00", periods=35040, freq="15min")
        base = 80.0 + 40.0 * np.sin(np.linspace(0, 365 * 2 * np.pi, 35040))
        hour = ts.hour.to_numpy()
        workday = (ts.dayofweek < 5).astype(float)
        day_peak = workday * np.where((hour >= 7) & (hour <= 18), 180.0, 0.0)
        spikes = np.where(np.random.RandomState(42).rand(35040) > 0.985, 90.0, 0.0)
        p = np.clip(base + day_peak + spikes, 20.0, 350.0)
        load_df = pd.DataFrame({
            "timestamp": ts,
            "Total_Demand_kW": p,
            "P_Load_kW": p
        })

    # Contract 1: Baseline Upgrade (Liander AC5a Medium Voltage)
    contract_ac5a = Contract(
        name="Liander AC5a (Medium Voltage Upgrade)",
        currency="EUR",
        contracted_capacity_kw=350.0,
        monthly_capacity_tariff=2.2233,    # GTV per kW/mo
        demand_capacity_tariff=3.4600, # kW-max per kW/mo
        peak_penalty_rate=25.0,
        default_energy_rate=0.1850,
        base_monthly_fee=121.24,           # Vastrecht (EUR 441/yr) + Aansluitdienst (EUR 1013.88/yr) / 12
        taxes_and_fees=[{"name": "VAT", "type": "percentage", "value": 21.0}]
    )

    # Contract 2: With BESS (Liander AC4b Low Voltage capped at 147 kW)
    contract_ac4b = Contract(
        name="Liander AC4b (Low Voltage Maintained)",
        currency="EUR",
        contracted_capacity_kw=147.0,
        monthly_capacity_tariff=3.6567,    # GTV per kW/mo
        demand_capacity_tariff=3.4600, # kW-max per kW/mo
        peak_penalty_rate=25.0,
        default_energy_rate=0.1850,
        base_monthly_fee=68.50,            # Vastrecht (EUR 441/yr) + Aansluitdienst (EUR 381/yr) / 12
        taxes_and_fees=[{"name": "VAT", "type": "percentage", "value": 21.0}]
    )

    # BESS hardware configuration: 250 kW / 500 kWh LFP
    bess_cfg = BESSConfig(
        capacity_kwh=500.0,
        unit_count=5,
        unit_capacity_kwh=100.0,
        battery_chemistry="LFP (Lithium Iron Phosphate - Standard)",
        max_charge_power_kw=250.0,
        max_discharge_power_kw=250.0,
        round_trip_efficiency_pct=90.0,
        soc_min_pct=10.0,
        soc_max_pct=95.0,
        initial_soc_pct=90.0,
        max_dod_pct=85.0,
        dispatch_strategy="peak_shaving",
        peak_shaving_threshold_kw=147.0,
        allow_grid_charging=True,
        currency="EUR",
        cost_per_kwh=320.0,
        fixed_installation_cost=8000.0,
        annual_om_pct=1.5,
        cell_replacement_year=10,
        cell_replacement_cost_pct=45.0
    )

    return BaselinePreset(
        key="liander_industrial_ac4b_vs_ac5a",
        title="Liander AC4b vs. AC5a Upgrade (Industrial Peak Shaving)",
        description=(
            "Industrial 350 kW facility evaluating whether a 250 kW / 500 kWh BESS can hold "
            "the 147 kW AC4b limit and eliminate a EUR 45,000 MV transformer station upgrade."
        ),
        grid_limit_kw=147.0,
        load_df=load_df,
        contract_baseline=contract_ac5a,
        contract_bess=contract_ac4b,
        bess_config=bess_cfg,
        avoided_grid_upgrade_capex=45000.0,
        avoided_monthly_transformer_rent=354.0,
        notes="High-impact Dutch C&I business case with avoided MV transformer leasing."
    )


def get_case2_enexis_commercial_preset() -> BaselinePreset:
    """
    Case 2: Medium Commercial Peak Shaver (Enexis MS-D 2025).
    
    Load: 250 kW peak commercial demand against a 150 kW contracted grid capacity limit.
    Intervention: 100 kW / 200 kWh LFP BESS.
    """
    if synthesize_benchmark_load_profile_2025:
        load_obj = synthesize_benchmark_load_profile_2025(
            profile_type="commercial_hvac",
            nominal_peak_kw=250.0
        )
        load_df = pd.DataFrame({
            "timestamp": load_obj.timestamps,
            "Total_Demand_kW": load_obj.power_kw,
            "P_Load_kW": load_obj.power_kw
        })
    else:
        ts = pd.date_range("2026-01-01 00:00:00", periods=35040, freq="15min")
        base = 60.0 + 30.0 * np.sin(np.linspace(0, 365 * 2 * np.pi, 35040))
        hour = ts.hour.to_numpy()
        workday = (ts.dayofweek < 5).astype(float)
        day_peak = workday * np.where((hour >= 8) & (hour <= 17), 130.0, 0.0)
        spikes = np.where(np.random.RandomState(99).rand(35040) > 0.985, 60.0, 0.0)
        p = np.clip(base + day_peak + spikes, 15.0, 250.0)
        load_df = pd.DataFrame({
            "timestamp": ts,
            "Total_Demand_kW": p,
            "P_Load_kW": p
        })

    contract_enexis_base = Contract(
        name="Enexis MS-D 2025 (Status Quo 250 kW)",
        currency="EUR",
        contracted_capacity_kw=250.0,
        monthly_capacity_tariff=2.4400,
        demand_capacity_tariff=3.7100,
        peak_penalty_rate=25.0,
        default_energy_rate=0.1900,
        base_monthly_fee=174.50,           # Vastrecht (EUR 441) + Aansluiting (EUR 1653) / 12
        taxes_and_fees=[{"name": "VAT", "type": "percentage", "value": 21.0}]
    )

    contract_enexis_bess = Contract(
        name="Enexis MS-D 2025 (Optimized 150 kW)",
        currency="EUR",
        contracted_capacity_kw=150.0,
        monthly_capacity_tariff=2.4400,
        demand_capacity_tariff=3.7100,
        peak_penalty_rate=25.0,
        default_energy_rate=0.1900,
        base_monthly_fee=174.50,
        taxes_and_fees=[{"name": "VAT", "type": "percentage", "value": 21.0}]
    )

    bess_cfg = BESSConfig(
        capacity_kwh=200.0,
        unit_count=2,
        unit_capacity_kwh=100.0,
        battery_chemistry="LFP (Lithium Iron Phosphate - Standard)",
        max_charge_power_kw=100.0,
        max_discharge_power_kw=100.0,
        round_trip_efficiency_pct=90.0,
        soc_min_pct=10.0,
        soc_max_pct=95.0,
        initial_soc_pct=90.0,
        max_dod_pct=85.0,
        dispatch_strategy="peak_shaving",
        peak_shaving_threshold_kw=150.0,
        allow_grid_charging=True,
        currency="EUR",
        cost_per_kwh=350.0,
        fixed_installation_cost=5000.0,
        annual_om_pct=1.5,
        cell_replacement_year=10,
        cell_replacement_cost_pct=50.0
    )

    return BaselinePreset(
        key="enexis_commercial_ms_d",
        title="Enexis MS-D Commercial (250 kW Peak vs. 150 kW Cap)",
        description=(
            "Commercial 250 kW facility shaving peak demand down to a 150 kW contracted limit "
            "using a 100 kW / 200 kWh battery storage setup."
        ),
        grid_limit_kw=150.0,
        load_df=load_df,
        contract_baseline=contract_enexis_base,
        contract_bess=contract_enexis_bess,
        bess_config=bess_cfg,
        avoided_grid_upgrade_capex=0.0,
        avoided_monthly_transformer_rent=0.0,
        notes="Standard Dutch regional grid peak demand tariff shaving optimization."
    )


def load_preset_by_key(preset_key: str) -> BaselinePreset:
    """Returns the requested preset instance."""
    if "enexis" in preset_key.lower():
        return get_case2_enexis_commercial_preset()
    return get_case1_liander_industrial_preset()


def build_custom_preset_from_dataframe(
    df: pd.DataFrame,
    grid_limit_kw: float = 150.0,
    power_col: Optional[str] = None
) -> BaselinePreset:
    """Adapts a user-provided DataFrame into a sandbox preset."""
    p_col = power_col or ("Total_Demand_kW" if "Total_Demand_kW" in df.columns else ("P_Load_kW" if "P_Load_kW" in df.columns else df.columns[-1]))
    p_series = pd.to_numeric(df[p_col], errors="coerce").fillna(0.0)
    peak_val = float(p_series.max()) if len(p_series) > 0 else 200.0
    
    clean_df = pd.DataFrame({
        "timestamp": df["timestamp"] if "timestamp" in df.columns else pd.date_range("2026-01-01", periods=len(df), freq="15min"),
        "Total_Demand_kW": p_series.to_numpy(dtype=float),
        "P_Load_kW": p_series.to_numpy(dtype=float)
    })

    contract_base = Contract(
        name="Custom Baseline Contract",
        currency="EUR",
        contracted_capacity_kw=round(peak_val, 1),
        monthly_capacity_tariff=3.50,
        demand_capacity_tariff=3.50,
        peak_penalty_rate=25.0,
        default_energy_rate=0.20,
        base_monthly_fee=50.0
    )

    contract_bess = Contract(
        name="Custom With-BESS Contract",
        currency="EUR",
        contracted_capacity_kw=round(grid_limit_kw, 1),
        monthly_capacity_tariff=3.50,
        demand_capacity_tariff=3.50,
        peak_penalty_rate=25.0,
        default_energy_rate=0.20,
        base_monthly_fee=50.0
    )

    bess_cfg = BESSConfig(
        capacity_kwh=round(max(50.0, (peak_val - grid_limit_kw) * 2.0), 1),
        unit_count=2,
        unit_capacity_kwh=round(max(25.0, (peak_val - grid_limit_kw)), 1),
        battery_chemistry="LFP (Lithium Iron Phosphate - Standard)",
        max_charge_power_kw=round(max(25.0, peak_val - grid_limit_kw), 1),
        max_discharge_power_kw=round(max(25.0, peak_val - grid_limit_kw), 1),
        round_trip_efficiency_pct=90.0,
        soc_min_pct=10.0,
        soc_max_pct=95.0,
        initial_soc_pct=90.0,
        dispatch_strategy="peak_shaving",
        peak_shaving_threshold_kw=grid_limit_kw,
        allow_grid_charging=True,
        currency="EUR",
        cost_per_kwh=350.0,
        fixed_installation_cost=5000.0
    )

    return BaselinePreset(
        key="custom_session_profile",
        title="Custom Profile / Uploaded CSV",
        description=f"User-provided load dataset ({len(clean_df):,} intervals, peak: {peak_val:.1f} kW).",
        grid_limit_kw=grid_limit_kw,
        load_df=clean_df,
        contract_baseline=contract_base,
        contract_bess=contract_bess,
        bess_config=bess_cfg,
        avoided_grid_upgrade_capex=0.0,
        avoided_monthly_transformer_rent=0.0,
        notes="Dynamic user dataset adapted for BESS sizing and peak shaving assessment."
    )


# Alias for compatibility
build_custom_comparison_preset = build_custom_preset_from_dataframe

