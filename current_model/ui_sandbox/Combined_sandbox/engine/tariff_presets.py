"""
Utility tariff preset catalogs (DSO, Energy Supplier, Metering) and 1-click preset loader.
"""

from typing import Any, Dict, List, Optional
import pandas as pd

from .models_and_presets import (
    CombinedFinancialConfig,
    CombinedFinancialKPIs,
    CombinedSystemConfig,
    CombinedTechnicalKPIs,
    SolarDerivationInfo,
)

# ======================================================================================
# 7. Utility Tariff Preset Catalogs & 1-Click Template Loader
# ======================================================================================

UTILITY_DSO_PRESETS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "Enexis Netbeheer B.V.": {
        "MV-D (125 to 1,500 kW)": {
            "capacity_fee_kw_mo": 2.44,
            "peak_fee_kw_mo": 3.71,
            "connection_fee_mo": round(1653.0 / 12.0, 2),
            "fixed_fee_mo": round(441.0 / 12.0, 2),
            "transport_eur_kwh": 0.025,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
        "MV/LV (> 50 to 125 kW)": {
            "capacity_fee_kw_mo": 4.20,
            "peak_fee_kw_mo": 3.71,
            "connection_fee_mo": round(381.0 / 12.0, 2),
            "fixed_fee_mo": round(441.0 / 12.0, 2),
            "transport_eur_kwh": 0.025,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
        "LV (up to 50 kW)": {
            "capacity_fee_kw_mo": 1.34,
            "peak_fee_kw_mo": 0.00,
            "connection_fee_mo": round(381.0 / 12.0, 2),
            "fixed_fee_mo": round(18.0 / 12.0, 2),
            "transport_eur_kwh": 0.061,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
        "MV-T (> 1,500 kW)": {
            "capacity_fee_kw_mo": 2.31,
            "peak_fee_kw_mo": 3.10,
            "connection_fee_mo": round(1653.0 / 12.0, 2),
            "fixed_fee_mo": round(441.0 / 12.0, 2),
            "transport_eur_kwh": 0.015,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
    },
    "Liander Netbeheer B.V.": {
        "MV-D (125 to 1,500 kW)": {
            "capacity_fee_kw_mo": 2.50,
            "peak_fee_kw_mo": 3.65,
            "connection_fee_mo": round(1620.0 / 12.0, 2),
            "fixed_fee_mo": round(430.0 / 12.0, 2),
            "transport_eur_kwh": 0.024,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
        "MV/LV (> 50 to 125 kW)": {
            "capacity_fee_kw_mo": 4.15,
            "peak_fee_kw_mo": 3.65,
            "connection_fee_mo": round(375.0 / 12.0, 2),
            "fixed_fee_mo": round(430.0 / 12.0, 2),
            "transport_eur_kwh": 0.024,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
        "LV (up to 50 kW)": {
            "capacity_fee_kw_mo": 1.40,
            "peak_fee_kw_mo": 0.00,
            "connection_fee_mo": round(375.0 / 12.0, 2),
            "fixed_fee_mo": round(18.0 / 12.0, 2),
            "transport_eur_kwh": 0.058,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
        "MV-T (> 1,500 kW)": {
            "capacity_fee_kw_mo": 2.25,
            "peak_fee_kw_mo": 3.05,
            "connection_fee_mo": round(1620.0 / 12.0, 2),
            "fixed_fee_mo": round(430.0 / 12.0, 2),
            "transport_eur_kwh": 0.014,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
    },
    "Stedin Netbeheer B.V.": {
        "MV (125 to 1,500 kW)": {
            "capacity_fee_kw_mo": 2.40,
            "peak_fee_kw_mo": 3.80,
            "connection_fee_mo": round(1590.0 / 12.0, 2),
            "fixed_fee_mo": round(450.0 / 12.0, 2),
            "transport_eur_kwh": 0.026,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
        "Transformer MV/LV (> 50 to 125 kW)": {
            "capacity_fee_kw_mo": 4.25,
            "peak_fee_kw_mo": 3.80,
            "connection_fee_mo": round(390.0 / 12.0, 2),
            "fixed_fee_mo": round(450.0 / 12.0, 2),
            "transport_eur_kwh": 0.026,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
        "LV (up to 50 kW)": {
            "capacity_fee_kw_mo": 1.55,
            "peak_fee_kw_mo": 0.00,
            "connection_fee_mo": round(74.44 / 12.0, 2),
            "fixed_fee_mo": round(18.0 / 12.0, 2),
            "transport_eur_kwh": 0.060,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
        "Transformer HV+TS/MV (> 1,500 kW)": {
            "capacity_fee_kw_mo": 3.79,
            "peak_fee_kw_mo": 5.30,
            "connection_fee_mo": round(3642.0 / 12.0, 2),
            "fixed_fee_mo": round(2760.0 / 12.0, 2),
            "transport_eur_kwh": 0.012,
            "penalty_kw": 15.00,
            "adjust_capacity_on_breach": True,
            "tax_credit_yr": 635.0,
        },
    },
    "EDEMSA Mendoza (Single-Utility)": {
        "T2 RMT (Bodegas Salentein 430 kW)": {
            "currency_code": "ARS",
            "market_mode": "single_utility",
            "enable_pillar_1_supplier": False,
            "enable_pillar_2_dso": True,
            "enable_pillar_3_metering": False,
            "enable_pillar_4_taxes": True,
            "capacity_fee_kw_mo": 40607.0460,
            "peak_fee_kw_mo": 8554.4390,
            "connection_fee_mo": 0.0,
            "fixed_fee_mo": 514145.55,
            "transport_eur_kwh": 66.773700,
            "enable_three_window_tou": True,
            "transport_peak_kwh": 68.433566,
            "transport_offpeak_kwh": 66.101706,
            "transport_shoulder_kwh": 66.773700,
            "penalty_kw": 40607.0460,
            "enable_excess_capacity_penalty": True,
            "adjust_capacity_on_breach": False,
            "bill_peak_demand_on_peak_tou_only": True,
            "regulatory_adjustments_monthly": 7848661.60,
            "energy_tax_kwh": 0.0,
            "tax_surcharge_pct": 12.51602578,
            "tax_credit_yr": 0.0,
            "vat_rate_pct": 27.0,
            "vat_applies_to_levies": False,
        },
    },
}

UTILITY_SUPPLIER_PRESETS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "Vattenfall Business": {
        "Fixed 1-Year (Dual TOU HT/NT)": {
            "energy_price_eur_kwh": 0.125,
            "pricing_mode": "dual_tou",
            "peak_ht_eur_kwh": 0.134,
            "offpeak_nt_eur_kwh": 0.116,
            "gvo_surcharge_eur_kwh": 0.003,
            "fixed_fee_mo": round(180.0 / 12.0, 2),
        },
        "Fixed 3-Year (Standard Single Rate)": {
            "energy_price_eur_kwh": 0.121,
            "pricing_mode": "single",
            "peak_ht_eur_kwh": 0.129,
            "offpeak_nt_eur_kwh": 0.113,
            "gvo_surcharge_eur_kwh": 0.002,
            "fixed_fee_mo": round(195.0 / 12.0, 2),
        },
        "Dynamic EPEX Spot Business": {
            "energy_price_eur_kwh": 0.120,
            "pricing_mode": "dual_tou",
            "peak_ht_eur_kwh": 0.128,
            "offpeak_nt_eur_kwh": 0.110,
            "gvo_surcharge_eur_kwh": 0.004,
            "fixed_fee_mo": round(180.0 / 12.0, 2),
        },
    },
    "Eneco Business": {
        "Fixed 1-Year (Dual TOU HT/NT)": {
            "energy_price_eur_kwh": 0.127,
            "pricing_mode": "dual_tou",
            "peak_ht_eur_kwh": 0.136,
            "offpeak_nt_eur_kwh": 0.118,
            "gvo_surcharge_eur_kwh": 0.003,
            "fixed_fee_mo": round(160.0 / 12.0, 2),
        },
        "Fixed 3-Year (Standard Single Rate)": {
            "energy_price_eur_kwh": 0.122,
            "pricing_mode": "single",
            "peak_ht_eur_kwh": 0.130,
            "offpeak_nt_eur_kwh": 0.114,
            "gvo_surcharge_eur_kwh": 0.002,
            "fixed_fee_mo": round(175.0 / 12.0, 2),
        },
    },
    "Essent Business": {
        "Fixed 1-Year (Dual TOU HT/NT)": {
            "energy_price_eur_kwh": 0.123,
            "pricing_mode": "dual_tou",
            "peak_ht_eur_kwh": 0.132,
            "offpeak_nt_eur_kwh": 0.114,
            "gvo_surcharge_eur_kwh": 0.003,
            "fixed_fee_mo": round(190.0 / 12.0, 2),
        },
        "Fixed 3-Year (Standard Single Rate)": {
            "energy_price_eur_kwh": 0.120,
            "pricing_mode": "single",
            "peak_ht_eur_kwh": 0.128,
            "offpeak_nt_eur_kwh": 0.112,
            "gvo_surcharge_eur_kwh": 0.002,
            "fixed_fee_mo": round(205.0 / 12.0, 2),
        },
    },
    "Shell Energy": {
        "Direct Fixed 1-Year": {
            "energy_price_eur_kwh": 0.126,
            "pricing_mode": "single",
            "peak_ht_eur_kwh": 0.133,
            "offpeak_nt_eur_kwh": 0.119,
            "gvo_surcharge_eur_kwh": 0.002,
            "fixed_fee_mo": round(200.0 / 12.0, 2),
        },
    },
}

UTILITY_METERING_PRESETS: Dict[str, Dict[str, Dict[str, float]]] = {
    "Fudura B.V.": {
        "15-Min Interval Telemetry MV (Large Consumer)": {
            "fixed_fee_mo": round(900.0 / 12.0, 2),
        },
        "Instrument Transformers MV (CT/VT)": {
            "fixed_fee_mo": round(1550.0 / 12.0, 2),
        },
        "Small Consumer / Sub-Metering": {
            "fixed_fee_mo": round(420.0 / 12.0, 2),
        },
    },
    "Joulz Metering": {
        "Large Consumer Telemetry MV": {
            "fixed_fee_mo": round(850.0 / 12.0, 2),
        },
        "Instrument Transformers MV": {
            "fixed_fee_mo": round(1480.0 / 12.0, 2),
        },
    },
    "Kenter B.V.": {
        "Large Consumer 15-Min Telemetry": {
            "fixed_fee_mo": round(880.0 / 12.0, 2),
        },
        "Telemetry + Transformers Bundle": {
            "fixed_fee_mo": round(2350.0 / 12.0, 2),
        },
    },
}

_PRESET_KEY_ALIASES: Dict[str, str] = {
    "MS-D (125 t/m 1.500 kW)": "MV-D (125 to 1,500 kW)",
    "MS/LS (> 50 t/m 125 kW)": "MV/LV (> 50 to 125 kW)",
    "LS (t/m 50 kW)": "LV (up to 50 kW)",
    "MS-T (> 1.500 kW)": "MV-T (> 1,500 kW)",
    "MS (125 t/m 1.500 kW)": "MV (125 to 1,500 kW)",
    "Trafo MS/LS (> 50 t/m 125 kW)": "Transformer MV/LV (> 50 to 125 kW)",
    "Trafo HS+TS/MS (> 1.500 kW)": "Transformer HV+TS/MV (> 1,500 kW)",
    "Vattenfall Zakelijk": "Vattenfall Business",
    "Eneco Zakelijk": "Eneco Business",
    "Essent Zakelijk": "Essent Business",
    "Vast 1 Jaar (Dubbeltarief HT/NT)": "Fixed 1-Year (Dual TOU HT/NT)",
    "Vast 3 Jaar (Zekerheid)": "Fixed 3-Year (Standard Single Rate)",
    "Dynamisch EPEX Spot Zakelijk": "Dynamic EPEX Spot Business",
    "Kwartierdata Telemetrie MS (Grootverbruik RLM)": "15-Min Interval Telemetry MV (Large Consumer)",
    "Meettransformatoren MS (Trafo CT/VT)": "Instrument Transformers MV (CT/VT)",
    "Kleinverbruik / Tussenmeting": "Small Consumer / Sub-Metering",
    "Joulz Meetbedrijf": "Joulz Metering",
    "Grootverbruik Telemetrie MS": "Large Consumer Telemetry MV",
    "Meettransformatoren MS": "Instrument Transformers MV",
    "Grootverbruik Kwartierdata Telemetrie": "Large Consumer 15-Min Telemetry",
    "Combinatie Telemetrie + Transformatoren": "Telemetry + Transformers Bundle",
}


def get_dso_preset_options() -> Dict[str, List[str]]:
    """Returns mapping of DSO provider name to available voltage/capacity tiers."""
    return {dso: list(tiers.keys()) for dso, tiers in UTILITY_DSO_PRESETS.items()}


def get_supplier_preset_options() -> Dict[str, List[str]]:
    """Returns mapping of energy supplier name to available contract products."""
    return {supp: list(plans.keys()) for supp, plans in UTILITY_SUPPLIER_PRESETS.items()}


def get_metering_preset_options() -> Dict[str, List[str]]:
    """Returns mapping of certified metering company to metering packages."""
    return {meter: list(plans.keys()) for meter, plans in UTILITY_METERING_PRESETS.items()}


def apply_utility_tariff_presets(
    dso_choice: str,
    tier_choice: str,
    supp_choice: str,
    supp_plan: str,
    meter_choice: str,
    meter_tier: str,
    fin_cfg: CombinedFinancialConfig,
) -> CombinedFinancialConfig:
    """
    Applies real-world DSO, Supplier, and Metering benchmark rates to CombinedFinancialConfig.
    Returns the updated configuration.
    """
    dso_choice_clean = _PRESET_KEY_ALIASES.get(dso_choice, dso_choice)
    tier_choice_clean = _PRESET_KEY_ALIASES.get(tier_choice, tier_choice)
    supp_choice_clean = _PRESET_KEY_ALIASES.get(supp_choice, supp_choice)
    supp_plan_clean = _PRESET_KEY_ALIASES.get(supp_plan, supp_plan)
    meter_choice_clean = _PRESET_KEY_ALIASES.get(meter_choice, meter_choice)
    meter_tier_clean = _PRESET_KEY_ALIASES.get(meter_tier, meter_tier)

    # DSO & Market Structure
    dso_tiers = UTILITY_DSO_PRESETS.get(dso_choice_clean, {})
    dso_data = dso_tiers.get(tier_choice_clean)
    if not dso_data and dso_tiers:
        dso_data = next(iter(dso_tiers.values()))
    if dso_data:
        fin_cfg.currency_code = str(dso_data.get("currency_code", "EUR"))
        fin_cfg.market_mode = str(dso_data.get("market_mode", "unbundled_4_pillar"))
        fin_cfg.enable_pillar_1_supplier = bool(dso_data.get("enable_pillar_1_supplier", True))
        fin_cfg.enable_pillar_2_dso = bool(dso_data.get("enable_pillar_2_dso", True))
        fin_cfg.enable_pillar_3_metering = bool(dso_data.get("enable_pillar_3_metering", True))
        fin_cfg.enable_pillar_4_taxes = bool(dso_data.get("enable_pillar_4_taxes", True))

        fin_cfg.dso_capacity_fee_eur_kw_month = float(dso_data.get("capacity_fee_kw_mo", fin_cfg.dso_capacity_fee_eur_kw_month))
        fin_cfg.dso_peak_demand_fee_eur_kw_month = float(dso_data.get("peak_fee_kw_mo", fin_cfg.dso_peak_demand_fee_eur_kw_month))
        fin_cfg.dso_connection_fee_eur_month = float(dso_data.get("connection_fee_mo", fin_cfg.dso_connection_fee_eur_month))
        fin_cfg.dso_fixed_fee_eur_month = float(dso_data.get("fixed_fee_mo", fin_cfg.dso_fixed_fee_eur_month))
        fin_cfg.dso_transport_eur_kwh = float(dso_data.get("transport_eur_kwh", fin_cfg.dso_transport_eur_kwh))
        fin_cfg.dso_enable_three_window_tou = bool(dso_data.get("enable_three_window_tou", False))
        t_pk = dso_data.get("transport_peak_kwh")
        t_off = dso_data.get("transport_offpeak_kwh")
        fin_cfg.dso_transport_peak_eur_kwh = float(t_pk) if t_pk is not None else float(fin_cfg.dso_transport_eur_kwh)
        fin_cfg.dso_transport_offpeak_eur_kwh = float(t_off) if t_off is not None else float(fin_cfg.dso_transport_eur_kwh)
        fin_cfg.dso_transport_shoulder_eur_kwh = float(dso_data.get("transport_shoulder_kwh", 0.0))

        fin_cfg.grid_overload_penalty_eur_kw = float(dso_data.get("penalty_kw", fin_cfg.grid_overload_penalty_eur_kw))
        fin_cfg.dso_enable_excess_capacity_penalty = bool(dso_data.get("enable_excess_capacity_penalty", True))
        fin_cfg.dso_adjust_capacity_on_breach = bool(dso_data.get("adjust_capacity_on_breach", fin_cfg.dso_adjust_capacity_on_breach))
        fin_cfg.dso_bill_peak_on_pico_only = bool(dso_data.get("bill_peak_demand_on_peak_tou_only", False))
        fin_cfg.dso_regulatory_adjustments_eur_month = float(dso_data.get("regulatory_adjustments_monthly", 0.0))

        fin_cfg.energy_tax_eur_kwh = float(dso_data.get("energy_tax_kwh", 0.0125))
        fin_cfg.tax_surcharge_pct = float(dso_data.get("tax_surcharge_pct", 0.0))
        fin_cfg.annual_tax_reduction_credit_eur = float(dso_data.get("tax_credit_yr", fin_cfg.annual_tax_reduction_credit_eur))
        fin_cfg.vat_rate_pct = float(dso_data.get("vat_rate_pct", 21.0))
        fin_cfg.vat_applies_to_levies = bool(dso_data.get("vat_applies_to_levies", True))

    # Supplier (only overwrite when Pillar 1 is active so bypassed Single-Utility stays clean)
    if fin_cfg.enable_pillar_1_supplier:
        supp_plans = UTILITY_SUPPLIER_PRESETS.get(supp_choice_clean, {})
        supp_data = supp_plans.get(supp_plan_clean)
        if not supp_data and supp_plans:
            supp_data = next(iter(supp_plans.values()))
        if supp_data:
            fin_cfg.supplier_energy_price_eur_kwh = float(supp_data.get("energy_price_eur_kwh", fin_cfg.supplier_energy_price_eur_kwh))
            fin_cfg.supplier_pricing_mode = str(supp_data.get("pricing_mode", fin_cfg.supplier_pricing_mode))
            fin_cfg.supplier_peak_ht_eur_kwh = float(supp_data.get("peak_ht_eur_kwh", fin_cfg.supplier_peak_ht_eur_kwh))
            fin_cfg.supplier_offpeak_nt_eur_kwh = float(supp_data.get("offpeak_nt_eur_kwh", fin_cfg.supplier_offpeak_nt_eur_kwh))
            fin_cfg.supplier_gvo_surcharge_eur_kwh = float(supp_data.get("gvo_surcharge_eur_kwh", fin_cfg.supplier_gvo_surcharge_eur_kwh))
            fin_cfg.supplier_fixed_fee_eur_month = float(supp_data.get("fixed_fee_mo", fin_cfg.supplier_fixed_fee_eur_month))

    # Metering (only overwrite when Pillar 3 is active)
    if fin_cfg.enable_pillar_3_metering:
        meter_tiers = UTILITY_METERING_PRESETS.get(meter_choice_clean, {})
        meter_data = meter_tiers.get(meter_tier_clean)
        if not meter_data and meter_tiers:
            meter_data = next(iter(meter_tiers.values()))
        if meter_data:
            fin_cfg.metering_fixed_fee_eur_month = float(meter_data.get("fixed_fee_mo", fin_cfg.metering_fixed_fee_eur_month))

    return fin_cfg


def sync_financial_config_from_status_quo(
    sq_cfg: Any,
    fin_cfg: CombinedFinancialConfig,
) -> CombinedFinancialConfig:
    """
    Imports a StatusQuoConfig2025 configuration snapshot directly from Currentsituation_sandbox
    so Combined_sandbox evaluates the exact same 4-Pillar or Single-Utility contract.
    """
    if sq_cfg is None:
        return fin_cfg

    raw_mode = str(getattr(sq_cfg, "market_mode", "unbundled_4_pillar")).lower()
    if "single" in raw_mode:
        fin_cfg.market_mode = "single_utility"
    elif "custom" in raw_mode:
        fin_cfg.market_mode = "custom"
    else:
        fin_cfg.market_mode = "unbundled_4_pillar"

    fin_cfg.currency_code = str(getattr(sq_cfg, "currency_code", "EUR") or "EUR")
    fin_cfg.enable_pillar_1_supplier = bool(getattr(sq_cfg, "enable_pillar_1_supplier", True))
    fin_cfg.enable_pillar_2_dso = bool(getattr(sq_cfg, "enable_pillar_2_dso", True))
    fin_cfg.enable_pillar_3_metering = bool(getattr(sq_cfg, "enable_pillar_3_metering", True))
    fin_cfg.enable_pillar_4_taxes = bool(getattr(sq_cfg, "enable_pillar_4_taxes", True))

    dso = getattr(sq_cfg, "dso", None)
    if dso is not None:
        fin_cfg.dso_connection_fee_eur_month = round(float(getattr(dso, "fixed_connection_annual", 0.0)) / 12.0, 2)
        fin_cfg.dso_fixed_fee_eur_month = round(float(getattr(dso, "fixed_transport_annual", 0.0)) / 12.0, 2)
        fin_cfg.dso_capacity_fee_eur_kw_month = float(getattr(dso, "rate_contracted_capacity", 0.0))
        fin_cfg.dso_peak_demand_fee_eur_kw_month = float(getattr(dso, "rate_peak_demand", 0.0))
        r_pk = float(getattr(dso, "rate_transport_peak_kwh", 0.0))
        r_off = float(getattr(dso, "rate_transport_offpeak_kwh", 0.0))
        r_sh = float(getattr(dso, "rate_transport_shoulder_kwh", 0.0))
        fin_cfg.dso_enable_three_window_tou = bool(getattr(dso, "enable_three_window_tou", False))
        fin_cfg.dso_transport_peak_eur_kwh = r_pk
        fin_cfg.dso_transport_offpeak_eur_kwh = r_off
        fin_cfg.dso_transport_shoulder_eur_kwh = r_sh
        fin_cfg.dso_transport_eur_kwh = r_sh if (fin_cfg.dso_enable_three_window_tou and r_sh > 0.0) else r_pk
        fin_cfg.grid_overload_penalty_eur_kw = float(getattr(dso, "peak_penalty_rate_kw", 0.0))
        fin_cfg.dso_enable_excess_capacity_penalty = bool(getattr(dso, "enable_excess_capacity_penalty", False))
        fin_cfg.dso_adjust_capacity_on_breach = bool(getattr(dso, "adjust_capacity_on_breach", False))
        fin_cfg.dso_bill_peak_on_pico_only = bool(getattr(dso, "bill_peak_demand_on_peak_tou_only", False))
        fin_cfg.dso_regulatory_adjustments_eur_month = float(getattr(dso, "regulatory_adjustments_monthly", 0.0))

    supp = getattr(sq_cfg, "supplier", None)
    if supp is not None:
        fin_cfg.supplier_fixed_fee_eur_month = round(float(getattr(supp, "base_fee_annual", 0.0)) / 12.0, 2)
        fin_cfg.supplier_energy_price_eur_kwh = float(getattr(supp, "fixed_rate_kwh", 0.125))
        fin_cfg.supplier_pricing_mode = "dual_tou" if bool(getattr(supp, "is_dual_rate", False)) else "single"
        fin_cfg.supplier_peak_ht_eur_kwh = float(getattr(supp, "fixed_rate_peak_kwh", 0.134))
        fin_cfg.supplier_offpeak_nt_eur_kwh = float(getattr(supp, "fixed_rate_offpeak_kwh", 0.118))
        fin_cfg.supplier_gvo_surcharge_eur_kwh = float(getattr(supp, "green_certificate_surcharge_kwh", 0.0)) + float(
            getattr(supp, "procurement_fee_kwh", 0.0)
        )

    meter = getattr(sq_cfg, "metering", None)
    if meter is not None:
        fin_cfg.metering_fixed_fee_eur_month = round(float(getattr(meter, "annual_flat_fee", 0.0)) / 12.0, 2)

    levies = getattr(sq_cfg, "levies", None)
    if levies is not None:
        fin_cfg.energy_tax_eur_kwh = float(getattr(levies, "statutory_levy_rate_kwh", 0.0))
        fin_cfg.tax_surcharge_pct = float(getattr(levies, "percentage_levy_rate_pct", 0.0))
        fin_cfg.annual_tax_reduction_credit_eur = float(getattr(levies, "annual_tax_reduction", 0.0))
        fin_cfg.vat_rate_pct = float(getattr(levies, "vat_rate_pct", 21.0))
        fin_cfg.vat_applies_to_levies = bool(getattr(levies, "vat_applies_to_levies", True))

    return fin_cfg


def build_financial_summary_table_df(
    cfg: CombinedSystemConfig,
    solar_deriv: SolarDerivationInfo,
    kpis: CombinedTechnicalKPIs,
    fin_kpis: CombinedFinancialKPIs,
    simple_payback_years: Optional[float],
    solar_iso_payback: Optional[float],
    bat_iso_payback: Optional[float],
    gen_iso_payback: Optional[float],
) -> pd.DataFrame:
    """Builds the component-level financial summary DataFrame for UI & Excel export."""
    denom = max(1.0, kpis.annual_consumption_kwh)
    payback_str = f"{simple_payback_years:.1f} yrs" if simple_payback_years is not None else "N/A"
    curr_sym = "€" if fin_kpis.currency_code == "EUR" else (f"{fin_kpis.currency_code} " if fin_kpis.currency_code == "ARS" else "$")

    def _f(v: float, signed: bool = False) -> str:
        if signed:
            return f"{curr_sym}{v:+,.0f}"
        return f"{curr_sym}{v:,.0f}"

    return pd.DataFrame([
        {
            "Component": "Grid",
            "Installed Size": f"{kpis.grid_limit_kw:,.0f} kW limit",
            "Energy Supplied (kWh/year & %)": f"{kpis.grid_supplied_to_load_kwh:,.0f} kWh ({(kpis.grid_supplied_to_load_kwh / denom * 100.0):.1f}%)",
            "Investment (CAPEX)": _f(0),
            "Annual Operating Cost (OPEX)": _f(fin_kpis.combined_grid_total_eur),
            "Annual Savings vs. Current situation": _f(fin_kpis.baseline_total_opex_eur - fin_kpis.combined_grid_total_eur),
            "Payback (Years)": "—",
        },
        {
            "Component": "Solar",
            "Installed Size": f"{solar_deriv.installed_kwp:,.1f} kWp" if cfg.enable_solar else "0.0 kWp",
            "Energy Supplied (kWh/year & %)": f"{kpis.solar_direct_kwh:,.0f} kWh direct ({kpis.solar_supply_share_pct:.1f}% total)" if cfg.enable_solar else "0 kWh (0.0%)",
            "Investment (CAPEX)": _f(fin_kpis.solar_capex_eur),
            "Annual Operating Cost (OPEX)": _f(fin_kpis.solar_om_eur),
            "Annual Savings vs. Current situation": _f(fin_kpis.solar_net_value_y1_eur, signed=True) if cfg.enable_solar else "—",
            "Payback (Years)": f"{solar_iso_payback:.1f} yrs" if solar_iso_payback is not None else "—",
        },
        {
            "Component": "Battery",
            "Installed Size": f"{cfg.battery_capacity_kwh:,.0f} kWh / {cfg.battery_power_kw:,.0f} kW" if cfg.enable_battery else "0 kWh / 0 kW",
            "Energy Supplied (kWh/year & %)": f"{kpis.battery_total_discharged_kwh:,.0f} kWh ({kpis.battery_discharge_share_pct:.1f}%)" if cfg.enable_battery else "0 kWh (0.0%)",
            "Investment (CAPEX)": _f(fin_kpis.battery_capex_eur),
            "Annual Operating Cost (OPEX)": _f(fin_kpis.battery_om_eur),
            "Annual Savings vs. Current situation": _f(fin_kpis.battery_net_value_y1_eur, signed=True) if cfg.enable_battery else "—",
            "Payback (Years)": f"{bat_iso_payback:.1f} yrs" if bat_iso_payback is not None else "—",
        },
        {
            "Component": "Generator",
            "Installed Size": f"{cfg.generator_rated_kw:,.0f} kW ({cfg.fuel_type})" if cfg.enable_generator else "0 kW",
            "Energy Supplied (kWh/year & %)": f"{kpis.generator_to_load_kwh:,.0f} kWh ({kpis.generator_supply_share_pct:.1f}%)" if cfg.enable_generator else "0 kWh (0.0%)",
            "Investment (CAPEX)": _f(fin_kpis.generator_capex_eur),
            "Annual Operating Cost (OPEX)": _f(fin_kpis.generator_total_opex_eur),
            "Annual Savings vs. Current situation": _f(fin_kpis.generator_net_value_y1_eur, signed=True) if cfg.enable_generator else "—",
            "Payback (Years)": f"{gen_iso_payback:.1f} yrs" if gen_iso_payback is not None else "—",
        },
        {
            "Component": "Combined system",
            "Installed Size": (
                f"Grid {kpis.grid_limit_kw:,.0f} kW + "
                f"Solar {solar_deriv.installed_kwp if cfg.enable_solar else 0.0:,.1f} kWp + "
                f"Battery {cfg.battery_capacity_kwh if cfg.enable_battery else 0.0:,.0f} kWh + "
                f"Generator {cfg.generator_rated_kw if cfg.enable_generator else 0.0:,.0f} kW"
            ),
            "Energy Supplied (kWh/year & %)": f"{kpis.annual_consumption_kwh:,.0f} kWh (100.0%)",
            "Investment (CAPEX)": _f(fin_kpis.total_capex_eur),
            "Annual Operating Cost (OPEX)": _f(fin_kpis.total_annual_opex_eur),
            "Annual Savings vs. Current situation": _f(fin_kpis.annual_savings_eur),
            "Payback (Years)": payback_str,
        },
        {
            "Component": "Current situation",
            "Installed Size": f"Grid Limit {kpis.grid_limit_kw:,.0f} kW (Grid only)",
            "Energy Supplied (kWh/year & %)": f"{kpis.annual_consumption_kwh:,.0f} kWh (100.0%)",
            "Investment (CAPEX)": _f(0),
            "Annual Operating Cost (OPEX)": _f(fin_kpis.baseline_total_opex_eur),
            "Annual Savings vs. Current situation": f"Baseline ({_f(0)})",
            "Payback (Years)": "—",
        },
    ])
