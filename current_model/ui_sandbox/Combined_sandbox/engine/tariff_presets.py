"""
Utility tariff preset catalogs (DSO, Energy Supplier, Metering) and 1-click preset loader.
"""

from typing import Dict, List, Any

from .models_and_presets import CombinedFinancialConfig

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
            "capacity_fee_kw_mo": 32.50,
            "peak_fee_kw_mo": 6.80,
            "connection_fee_mo": 0.0,
            "fixed_fee_mo": 411.00,
            "transport_eur_kwh": 0.054,
            "penalty_kw": 32.50,
            "adjust_capacity_on_breach": False,
            "tax_credit_yr": 0.0,
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

    # DSO
    dso_tiers = UTILITY_DSO_PRESETS.get(dso_choice_clean, {})
    dso_data = dso_tiers.get(tier_choice_clean)
    if not dso_data and dso_tiers:
        dso_data = next(iter(dso_tiers.values()))
    if dso_data:
        fin_cfg.dso_capacity_fee_eur_kw_month = float(dso_data.get("capacity_fee_kw_mo", fin_cfg.dso_capacity_fee_eur_kw_month))
        fin_cfg.dso_peak_demand_fee_eur_kw_month = float(dso_data.get("peak_fee_kw_mo", fin_cfg.dso_peak_demand_fee_eur_kw_month))
        fin_cfg.dso_connection_fee_eur_month = float(dso_data.get("connection_fee_mo", fin_cfg.dso_connection_fee_eur_month))
        fin_cfg.dso_fixed_fee_eur_month = float(dso_data.get("fixed_fee_mo", fin_cfg.dso_fixed_fee_eur_month))
        fin_cfg.dso_transport_eur_kwh = float(dso_data.get("transport_eur_kwh", fin_cfg.dso_transport_eur_kwh))
        fin_cfg.grid_overload_penalty_eur_kw = float(dso_data.get("penalty_kw", fin_cfg.grid_overload_penalty_eur_kw))
        fin_cfg.dso_adjust_capacity_on_breach = bool(dso_data.get("adjust_capacity_on_breach", fin_cfg.dso_adjust_capacity_on_breach))
        fin_cfg.annual_tax_reduction_credit_eur = float(dso_data.get("tax_credit_yr", fin_cfg.annual_tax_reduction_credit_eur))

    # Supplier
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

    # Metering
    meter_tiers = UTILITY_METERING_PRESETS.get(meter_choice_clean, {})
    meter_data = meter_tiers.get(meter_tier_clean)
    if not meter_data and meter_tiers:
        meter_data = next(iter(meter_tiers.values()))
    if meter_data:
        fin_cfg.metering_fixed_fee_eur_month = float(meter_data.get("fixed_fee_mo", fin_cfg.metering_fixed_fee_eur_month))

    return fin_cfg
