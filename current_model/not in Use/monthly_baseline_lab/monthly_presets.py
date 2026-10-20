"""
========================================================================================
Monthly Baseline & Commercial Electricity Tariff Presets & Catalogs
(current_model/ui_sandbox/monthly_presets.py)
========================================================================================

Description:
------------
Decoupled tariff catalogs, standard industry presets, and grid operator rate builders
for the autarkic 12-Month Baseline & Commercial Electricity Tariff Lab.

Contains:
1. Bodegas Salentein Pozo 600 reference contract (Excel Sheet 1.1 & 1.3)
2. Argentine 3-Tier Industrial Contract (Pico, Resto, Valle)
3. Official Dutch Grid Operator Catalogs 2025:
   - Enexis Netbeheer (LS, MS/LS, MS-D, MS-T, HS/MS, TS, Reserve)
   - Liander (LS, MS/LS, MS, TS/MS, TS, HS3)
4. Dynamic 12-month tariff table builders (monthly accrual vs. annual December settlement)
5. Robust preset reload and restoration engine
========================================================================================
"""

from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from dataclasses import dataclass


@dataclass
class TOUTierConfig:
    """Represents a single Time-of-Use energy pricing window."""
    id: str
    name: str
    time_window: str = "Standard Hours"
    color: str = "#EF4444"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "time_window": self.time_window,
            "color": self.color
        }


MONTHS_LIST = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


# ========================================================================================
# 1. Bodegas Salentein Pozo 600 Reference Preset (Cent-precise 36,234.97 EUR Verification)
# ========================================================================================

def get_salentein_pozo600_preset() -> Tuple[pd.DataFrame, pd.DataFrame, List[TOUTierConfig], str, float, str]:
    """Bodegas Salentein Pozo 600 reference dataset (Excel Blatt 1.1 & 1.3)."""
    consumption_data = [
        {"month_index": 1, "Month": "January", "P_contract_kW": 104.0, "P_max_kW": 103.0, "kWh_peak": 11190.0, "kWh_offpeak": 17730.0},
        {"month_index": 2, "Month": "February", "P_contract_kW": 104.0, "P_max_kW": 103.0, "kWh_peak": 14130.0, "kWh_offpeak": 23820.0},
        {"month_index": 3, "Month": "March", "P_contract_kW": 104.0, "P_max_kW": 102.0, "kWh_peak": 16032.0, "kWh_offpeak": 23328.0},
        {"month_index": 4, "Month": "April", "P_contract_kW": 104.0, "P_max_kW": 104.0, "kWh_peak": 11322.0, "kWh_offpeak": 18318.0},
        {"month_index": 5, "Month": "May", "P_contract_kW": 104.0, "P_max_kW": 103.0, "kWh_peak": 3582.0, "kWh_offpeak": 6396.0},
        {"month_index": 6, "Month": "June", "P_contract_kW": 104.0, "P_max_kW": 0.0, "kWh_peak": 12.0, "kWh_offpeak": 30.0},
        {"month_index": 7, "Month": "July", "P_contract_kW": 104.0, "P_max_kW": 0.0, "kWh_peak": 12.0, "kWh_offpeak": 30.0},
        {"month_index": 8, "Month": "August", "P_contract_kW": 104.0, "P_max_kW": 101.0, "kWh_peak": 2898.0, "kWh_offpeak": 3444.0},
        {"month_index": 9, "Month": "September", "P_contract_kW": 104.0, "P_max_kW": 105.0, "kWh_peak": 4056.0, "kWh_offpeak": 5220.0},
        {"month_index": 10, "Month": "October", "P_contract_kW": 104.0, "P_max_kW": 103.0, "kWh_peak": 7038.0, "kWh_offpeak": 8748.0},
        {"month_index": 11, "Month": "November", "P_contract_kW": 104.0, "P_max_kW": 104.0, "kWh_peak": 6906.0, "kWh_offpeak": 10434.0},
        {"month_index": 12, "Month": "December", "P_contract_kW": 104.0, "P_max_kW": 103.0, "kWh_peak": 10824.0, "kWh_offpeak": 16350.0},
    ]
    c_df = pd.DataFrame(consumption_data)

    tou_tiers = [
        TOUTierConfig(id="peak", name="High Energy (Pico)", time_window="14:00 - 23:00", color="#EF4444"),
        TOUTierConfig(id="offpeak", name="Low Energy (Valle/Resto)", time_window="23:00 - 14:00", color="#3B82F6")
    ]

    tariff_data = []
    for idx, m in enumerate(MONTHS_LIST, 1):
        tariff_data.append({
            "month_index": idx,
            "Month": m,
            "base_fee": 28929.64,
            "metering_fee": 0.0,
            "rate_contracted_kw": 3589.886,
            "rate_excess_kw": 0.0,
            "rate_peak_demand_kw": 0.0,
            "rate_peak": 172.46,
            "rate_offpeak": 106.97,
            "tax_rate_pct": 37.59,
            "tax_rate_fixed_pct": 30.996984,
            "exempt_surcharge": 16688.00
        })
    t_df = pd.DataFrame(tariff_data)

    return c_df, t_df, tou_tiers, "ARS", 1300.0, "Bodegas Salentein (Pozo 600 - EDEMSA T2 R MT)"


# ========================================================================================
# 2. Argentine 3-Tier Industrial Contract (Pico, Resto, Valle)
# ========================================================================================

def get_3tier_argentine_preset() -> Tuple[pd.DataFrame, pd.DataFrame, List[TOUTierConfig], str, float, str]:
    """3-Tier Argentine Industrial Supply Contract (Pico, Resto, Valle) with peak penalties."""
    consumption_data = [
        {"month_index": 1, "Month": "January", "P_contract_kW": 250.0, "P_max_kW": 240.0, "kWh_peak": 12500.0, "kWh_resto": 22000.0, "kWh_valle": 14500.0},
        {"month_index": 2, "Month": "February", "P_contract_kW": 250.0, "P_max_kW": 245.0, "kWh_peak": 13100.0, "kWh_resto": 23500.0, "kWh_valle": 15200.0},
        {"month_index": 3, "Month": "March", "P_contract_kW": 250.0, "P_max_kW": 252.0, "kWh_peak": 14200.0, "kWh_resto": 24800.0, "kWh_valle": 16000.0},
        {"month_index": 4, "Month": "April", "P_contract_kW": 250.0, "P_max_kW": 238.0, "kWh_peak": 11800.0, "kWh_resto": 21000.0, "kWh_valle": 13900.0},
        {"month_index": 5, "Month": "May", "P_contract_kW": 250.0, "P_max_kW": 220.0, "kWh_peak": 9500.0, "kWh_resto": 18200.0, "kWh_valle": 11400.0},
        {"month_index": 6, "Month": "June", "P_contract_kW": 250.0, "P_max_kW": 210.0, "kWh_peak": 8200.0, "kWh_resto": 16500.0, "kWh_valle": 10200.0},
        {"month_index": 7, "Month": "July", "P_contract_kW": 250.0, "P_max_kW": 215.0, "kWh_peak": 8400.0, "kWh_resto": 16800.0, "kWh_valle": 10500.0},
        {"month_index": 8, "Month": "August", "P_contract_kW": 250.0, "P_max_kW": 230.0, "kWh_peak": 10100.0, "kWh_resto": 19200.0, "kWh_valle": 12300.0},
        {"month_index": 9, "Month": "September", "P_contract_kW": 250.0, "P_max_kW": 258.0, "kWh_peak": 13800.0, "kWh_resto": 24000.0, "kWh_valle": 15800.0},
        {"month_index": 10, "Month": "October", "P_contract_kW": 250.0, "P_max_kW": 248.0, "kWh_peak": 12900.0, "kWh_resto": 22800.0, "kWh_valle": 14900.0},
        {"month_index": 11, "Month": "November", "P_contract_kW": 250.0, "P_max_kW": 250.0, "kWh_peak": 13400.0, "kWh_resto": 23600.0, "kWh_valle": 15400.0},
        {"month_index": 12, "Month": "December", "P_contract_kW": 250.0, "P_max_kW": 255.0, "kWh_peak": 14500.0, "kWh_resto": 25400.0, "kWh_valle": 16800.0},
    ]
    c_df = pd.DataFrame(consumption_data)

    tou_tiers = [
        TOUTierConfig(id="peak", name="Pico (On-Peak)", time_window="18:00 - 23:00", color="#EF4444"),
        TOUTierConfig(id="resto", name="Resto (Mid-Peak)", time_window="05:00 - 18:00", color="#F59E0B"),
        TOUTierConfig(id="valle", name="Valle (Off-Peak)", time_window="23:00 - 05:00", color="#3B82F6")
    ]

    tariff_data = []
    for idx, m in enumerate(MONTHS_LIST, 1):
        tariff_data.append({
            "month_index": idx,
            "Month": m,
            "base_fee": 45000.00,
            "metering_fee": 0.0,
            "rate_contracted_kw": 3589.886,
            "rate_excess_kw": 4500.00,
            "rate_peak_demand_kw": 450.00,
            "rate_peak": 172.46,
            "rate_resto": 135.20,
            "rate_valle": 106.97,
            "tax_rate_pct": 37.59,
            "tax_rate_fixed_pct": 37.59,
            "exempt_surcharge": 22500.00
        })
    t_df = pd.DataFrame(tariff_data)

    return c_df, t_df, tou_tiers, "ARS", 1300.0, "Argentine 3-Tier Industrial (Pico / Resto / Valle)"


# ========================================================================================
# 3. Enexis Netbeheer 2025 Catalog & Builder
# ========================================================================================

ENEXIS_2025_GRID_TIERS: Dict[str, Dict[str, Any]] = {
    "LS": {
        "label": "LS — Low Voltage (<= 1 kV, Capacity <= 50 kW)",
        "voltage_level": "Low Voltage (<= 1 kV)",
        "fixed_transport_annual": 18.00,
        "rate_contracted_annual": 16.05,
        "rate_peak_demand_monthly": 0.00,
        "rate_peak_kwh": 0.0804,
        "rate_offpeak_kwh": 0.0421,
        "reactive_kvarh": 0.0188,
        "default_capacity_key": "cap_173",
        "description": "Niederspannung für kleinere Gewerbeanschlüsse bis 50 kW"
    },
    "MS_LS": {
        "label": "MS/LS — Medium/Low Voltage (> 50 kW to 125 kW)",
        "voltage_level": "Medium/Low Voltage Transformator",
        "fixed_transport_annual": 441.00,
        "rate_contracted_annual": 50.40,
        "rate_peak_demand_monthly": 3.71,
        "rate_peak_kwh": 0.0250,
        "rate_offpeak_kwh": 0.0250,
        "reactive_kvarh": 0.0188,
        "default_capacity_key": "cap_173",
        "description": "Transformator-Ebene MS/LS bis 125 kW"
    },
    "MS_D": {
        "label": "MS-D — Medium Voltage Distribution (1-20 kV, 125 to 1,500 kW & > 1,500 kW)",
        "voltage_level": "Medium Voltage Distribution (1-20 kV)",
        "fixed_transport_annual": 441.00,
        "rate_contracted_annual": 29.28,
        "rate_peak_demand_monthly": 3.71,
        "rate_peak_kwh": 0.0250,
        "rate_offpeak_kwh": 0.0250,
        "reactive_kvarh": 0.0188,
        "default_capacity_key": "cap_1750",
        "description": "Standard Mittelspannungs-Verteilnetz für Industrie & Gewerbe"
    },
    "MS_T": {
        "label": "MS-T — Medium Voltage Transmission (1-20 kV, > 1,500 kW)",
        "voltage_level": "Medium Voltage Transmission (1-20 kV)",
        "fixed_transport_annual": 441.00,
        "rate_contracted_annual": 27.71,
        "rate_peak_demand_monthly": 3.10,
        "rate_peak_kwh": 0.0152,
        "rate_offpeak_kwh": 0.0152,
        "reactive_kvarh": 0.0188,
        "default_capacity_key": "cap_3000",
        "description": "Mittelspannungs-Transportnetz für Großverbraucher > 1.500 kW"
    },
    "HS_MS": {
        "label": "HS/MS — High/Medium Voltage (> 1,500 kW)",
        "voltage_level": "High/Medium Voltage",
        "fixed_transport_annual": 2760.00,
        "rate_contracted_annual": 42.10,
        "rate_peak_demand_monthly": 4.48,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_kvarh": 0.0188,
        "default_capacity_key": "cap_6000",
        "description": "Hoch-/Mittelspannungsumspannung (keine variablen kWh-Entgelte auf Verteilnetzebene)"
    },
    "TS": {
        "label": "TS — Intermediate Voltage (30-50 kV, > 1,500 kW)",
        "voltage_level": "Intermediate Voltage (30-50 kV)",
        "fixed_transport_annual": 2760.00,
        "rate_contracted_annual": 31.37,
        "rate_peak_demand_monthly": 3.67,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_kvarh": 0.0188,
        "default_capacity_key": "cap_6000",
        "description": "Zwischenspannungsnetz 30-50 kV"
    },
    "HS_MS_RES": {
        "label": "HS/MS Reserve — Max 600h Reserve Capacity (> 1,500 kW)",
        "voltage_level": "High/Medium Voltage (Reserve)",
        "fixed_transport_annual": 2760.00,
        "rate_contracted_annual": 21.05,
        "rate_peak_demand_monthly": 1.55 * (52.0 / 12.0),
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_kvarh": 0.0188,
        "default_capacity_key": "cap_6000",
        "description": "Reservetarif HS/MS max. 600h Betriebszeit"
    },
    "TS_RES": {
        "label": "TS Reserve — Max 600h Reserve Capacity (> 1,500 kW)",
        "voltage_level": "Intermediate Voltage (Reserve)",
        "fixed_transport_annual": 2760.00,
        "rate_contracted_annual": 15.69,
        "rate_peak_demand_monthly": 1.27 * (52.0 / 12.0),
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_kvarh": 0.0188,
        "default_capacity_key": "cap_6000",
        "description": "Reservetarif TS max. 600h Betriebszeit"
    },
}

ENEXIS_2025_CONNECTION_CAPACITIES: Dict[str, Dict[str, Any]] = {
    "cap_173": {
        "label": "> 3 x 80 A to 3 x 250 A (173 kVA) — € 381.00 / yr",
        "annual_fee": 381.00
    },
    "cap_1750": {
        "label": "> 173 kVA to 1,750 kVA — € 1,653.00 / yr (Standard Commercial MS)",
        "annual_fee": 1653.00
    },
    "cap_3000": {
        "label": "> 1,750 kVA to 3,000 kVA (3 MVA) — € 4,560.00 / yr",
        "annual_fee": 4560.00
    },
    "cap_6000": {
        "label": "> 3 MVA to 6 MVA — € 4,560.00 / yr",
        "annual_fee": 4560.00
    },
    "cap_10000": {
        "label": "> 6 MVA to 10 MVA — € 5,351.00 / yr",
        "annual_fee": 5351.00
    }
}


def build_enexis_2025_tariff_dataframe(
    grid_tier_key: str = "MS_D",
    capacity_key: str = "cap_1750",
    billing_schedule: str = "monthly",
    supply_markup_peak: float = 0.0,
    supply_markup_offpeak: float = 0.0,
    metering_fee: float = 85.0,
    tax_rate_pct: float = 21.0
) -> pd.DataFrame:
    """Constructs a 12-month Table B tariff DataFrame according to Enexis 2025 tariffs."""
    tier = ENEXIS_2025_GRID_TIERS.get(grid_tier_key, ENEXIS_2025_GRID_TIERS["MS_D"])
    conn = ENEXIS_2025_CONNECTION_CAPACITIES.get(capacity_key, ENEXIS_2025_CONNECTION_CAPACITIES["cap_1750"])

    total_fixed_annual = float(tier["fixed_transport_annual"]) + float(conn["annual_fee"])
    annual_contracted_rate = float(tier["rate_contracted_annual"])
    monthly_peak_rate = float(tier["rate_peak_demand_monthly"])

    rate_peak_allin = float(tier["rate_peak_kwh"]) + float(supply_markup_peak)
    rate_offpeak_allin = float(tier["rate_offpeak_kwh"]) + float(supply_markup_offpeak)

    tariff_rows = []
    for idx, m in enumerate(MONTHS_LIST, 1):
        if billing_schedule == "annual_settlement":
            if idx < 12:
                base_fee_val = 0.0
                rate_cap_val = 0.0
            else:
                base_fee_val = total_fixed_annual
                rate_cap_val = annual_contracted_rate
        else:
            base_fee_val = round(total_fixed_annual / 12.0, 4)
            rate_cap_val = round(annual_contracted_rate / 12.0, 4)

        tariff_rows.append({
            "month_index": idx,
            "Month": m,
            "base_fee": base_fee_val,
            "metering_fee": metering_fee,
            "rate_contracted_kw": rate_cap_val,
            "rate_excess_kw": 0.0,
            "rate_peak_demand_kw": round(monthly_peak_rate, 4),
            "rate_peak": round(rate_peak_allin, 4),
            "rate_offpeak": round(rate_offpeak_allin, 4),
            "tax_rate_pct": tax_rate_pct,
            "tax_rate_fixed_pct": tax_rate_pct,
            "exempt_surcharge": 0.0
        })

    return pd.DataFrame(tariff_rows)


# ========================================================================================
# 4. Liander 2025 Catalog & Builder
# ========================================================================================

LIANDER_2025_GRID_TIERS: Dict[str, Dict[str, Any]] = {
    "LS": {
        "label": "LS — Low Voltage (<= 1 kV, Capacity <= 50 kW)",
        "voltage_level": "Low Voltage (<= 1 kV)",
        "fixed_transport_monthly": 1.50,
        "rate_contracted_monthly": 1.4100,
        "rate_peak_demand_monthly": 0.00,
        "rate_peak_kwh": 0.0758,
        "rate_offpeak_kwh": 0.0403,
        "reactive_kvarh": 0.0,
        "default_capacity_key": "cap_100",
        "description": "Low voltage for small commercial connections up to 50 kW"
    },
    "MS_LS": {
        "label": "MS/LS — Medium/Low Voltage Transformer (> 50 to 136 kW)",
        "voltage_level": "Medium/Low Voltage Transformer",
        "fixed_transport_monthly": 36.75,
        "rate_contracted_monthly": 3.6567,
        "rate_peak_demand_monthly": 3.4600,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_kvarh": 0.0,
        "default_capacity_key": "cap_160",
        "description": "Transformer level MS/LS connection up to 136 kW"
    },
    "MS": {
        "label": "MS — Medium Voltage Distribution (> 136 to 2,000 kW)",
        "voltage_level": "Medium Voltage Distribution (1-20 kV)",
        "fixed_transport_monthly": 36.75,
        "rate_contracted_monthly": 2.2233,
        "rate_peak_demand_monthly": 3.4600,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_kvarh": 0.0,
        "default_capacity_key": "cap_630",
        "description": "Standard medium voltage commercial & industrial grid connection"
    },
    "TS_MS": {
        "label": "TS/MS — Intermediate/Medium Voltage (> 2,000 kW)",
        "voltage_level": "Intermediate/Medium Voltage Substation",
        "fixed_transport_monthly": 230.00,
        "rate_contracted_monthly": 3.8000,
        "rate_peak_demand_monthly": 5.9400,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_kvarh": 0.0,
        "default_capacity_key": "cap_2000",
        "description": "Substation transformation level for large customers > 2,000 kW"
    },
    "TS": {
        "label": "TS — Intermediate Voltage (50 kV, > 2,000 kW)",
        "voltage_level": "Intermediate Voltage (50 kV)",
        "fixed_transport_monthly": 230.00,
        "rate_contracted_monthly": 3.8000,
        "rate_peak_demand_monthly": 5.2300,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_kvarh": 0.0,
        "default_capacity_key": "cap_5000",
        "description": "Direct intermediate voltage grid connection (50 kV)"
    },
    "HS3": {
        "label": "HS3 — High Voltage (> 50 kV, > 2,000 kW)",
        "voltage_level": "High Voltage (> 50 kV)",
        "fixed_transport_monthly": 230.00,
        "rate_contracted_monthly": 1.8400,
        "rate_peak_demand_monthly": 2.2800,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_kvarh": 0.0,
        "default_capacity_key": "cap_10000",
        "description": "High voltage grid connection"
    },
}

LIANDER_2025_CONNECTION_CAPACITIES: Dict[str, Dict[str, Any]] = {
    "cap_lv": {
        "label": "> 3x80A connected to Low Voltage Grid — € 5.11 / mo",
        "monthly_fee": 5.1069
    },
    "cap_100": {
        "label": "> 3x80A to 100 kVA (Standard Supply Point) — € 21.18 / mo",
        "monthly_fee": 21.180
    },
    "cap_160": {
        "label": "> 100 kVA to 160 kVA — € 23.64 / mo",
        "monthly_fee": 23.640
    },
    "cap_630": {
        "label": "> 160 kVA to 630 kVA with Transformer & LV Metering — € 84.49 / mo (Standard MS)",
        "monthly_fee": 84.490
    },
    "cap_1000": {
        "label": "> 630 kVA to 1,000 kVA (1 MVA) with Transformer — € 84.49 / mo",
        "monthly_fee": 84.490
    },
    "cap_2000": {
        "label": "> 1 MVA to 2 MVA — € 160.57 / mo",
        "monthly_fee": 160.570
    },
    "cap_5000": {
        "label": "> 2 MVA to 5 MVA — € 1,056.00 / mo",
        "monthly_fee": 1056.000
    },
    "cap_10000": {
        "label": "> 5 MVA to 10 MVA — € 1,261.00 / mo",
        "monthly_fee": 1261.000
    }
}


def build_liander_2025_tariff_dataframe(
    grid_tier_key: str = "MS",
    capacity_key: str = "cap_630",
    billing_schedule: str = "monthly",
    supply_markup_peak: float = 0.0,
    supply_markup_offpeak: float = 0.0,
    metering_fee: float = 75.0,
    tax_rate_pct: float = 21.0
) -> pd.DataFrame:
    """Constructs a 12-month Table B tariff DataFrame according to Liander 2025 network tariffs."""
    tier = LIANDER_2025_GRID_TIERS.get(grid_tier_key, LIANDER_2025_GRID_TIERS["MS"])
    conn = LIANDER_2025_CONNECTION_CAPACITIES.get(capacity_key, LIANDER_2025_CONNECTION_CAPACITIES["cap_630"])

    monthly_fixed = float(tier["fixed_transport_monthly"]) + float(conn["monthly_fee"])
    monthly_contracted_rate = float(tier["rate_contracted_monthly"])
    monthly_peak_rate = float(tier["rate_peak_demand_monthly"])

    rate_peak_allin = float(tier["rate_peak_kwh"]) + float(supply_markup_peak)
    rate_offpeak_allin = float(tier["rate_offpeak_kwh"]) + float(supply_markup_offpeak)

    tariff_rows = []
    for idx, m in enumerate(MONTHS_LIST, 1):
        if billing_schedule == "annual_settlement":
            if idx < 12:
                base_fee_val = 0.0
                rate_cap_val = 0.0
            else:
                base_fee_val = round(monthly_fixed * 12.0, 4)
                rate_cap_val = round(monthly_contracted_rate * 12.0, 4)
        else:
            base_fee_val = round(monthly_fixed, 4)
            rate_cap_val = round(monthly_contracted_rate, 4)

        tariff_rows.append({
            "month_index": idx,
            "Month": m,
            "base_fee": base_fee_val,
            "metering_fee": metering_fee,
            "rate_contracted_kw": rate_cap_val,
            "rate_excess_kw": 0.0,
            "rate_peak_demand_kw": round(monthly_peak_rate, 4),
            "rate_peak": round(rate_peak_allin, 4),
            "rate_offpeak": round(rate_offpeak_allin, 4),
            "tax_rate_pct": tax_rate_pct,
            "tax_rate_fixed_pct": tax_rate_pct,
            "exempt_surcharge": 0.0
        })

    return pd.DataFrame(tariff_rows)


# ========================================================================================
# 5. Combined Netherlands Preset & Universal Reload Helper
# ========================================================================================

def get_netherlands_commercial_preset(
    provider: str = "enexis",
    grid_tier_key: Optional[str] = None,
    capacity_key: Optional[str] = None,
    billing_schedule: str = "monthly"
) -> Tuple[pd.DataFrame, pd.DataFrame, List[TOUTierConfig], str, float, str]:
    """Dutch commercial customer under Enexis Netbeheer or Liander 2025 network tariffs."""
    consumption_data = [
        {"month_index": 1, "Month": "January", "P_contract_kW": 250.0, "P_max_kW": 210.0, "kWh_peak": 18500.0, "kWh_offpeak": 14200.0},
        {"month_index": 2, "Month": "February", "P_contract_kW": 250.0, "P_max_kW": 215.0, "kWh_peak": 17200.0, "kWh_offpeak": 13800.0},
        {"month_index": 3, "Month": "March", "P_contract_kW": 250.0, "P_max_kW": 195.0, "kWh_peak": 16400.0, "kWh_offpeak": 12900.0},
        {"month_index": 4, "Month": "April", "P_contract_kW": 250.0, "P_max_kW": 180.0, "kWh_peak": 14800.0, "kWh_offpeak": 11500.0},
        {"month_index": 5, "Month": "May", "P_contract_kW": 250.0, "P_max_kW": 170.0, "kWh_peak": 13900.0, "kWh_offpeak": 10800.0},
        {"month_index": 6, "Month": "June", "P_contract_kW": 250.0, "P_max_kW": 165.0, "kWh_peak": 13200.0, "kWh_offpeak": 10400.0},
        {"month_index": 7, "Month": "July", "P_contract_kW": 250.0, "P_max_kW": 160.0, "kWh_peak": 12800.0, "kWh_offpeak": 9900.0},
        {"month_index": 8, "Month": "August", "P_contract_kW": 250.0, "P_max_kW": 168.0, "kWh_peak": 13500.0, "kWh_offpeak": 10200.0},
        {"month_index": 9, "Month": "September", "P_contract_kW": 250.0, "P_max_kW": 260.0, "kWh_peak": 15100.0, "kWh_offpeak": 11800.0},
        {"month_index": 10, "Month": "October", "P_contract_kW": 250.0, "P_max_kW": 200.0, "kWh_peak": 16800.0, "kWh_offpeak": 13100.0},
        {"month_index": 11, "Month": "November", "P_contract_kW": 250.0, "P_max_kW": 220.0, "kWh_peak": 18100.0, "kWh_offpeak": 14500.0},
        {"month_index": 12, "Month": "December", "P_contract_kW": 250.0, "P_max_kW": 230.0, "kWh_peak": 19600.0, "kWh_offpeak": 15400.0},
    ]
    c_df = pd.DataFrame(consumption_data)

    tou_tiers = [
        TOUTierConfig(id="peak", name="Piek (07:00 - 23:00)", time_window="07:00 - 23:00", color="#EF4444"),
        TOUTierConfig(id="offpeak", name="Dal (23:00 - 07:00)", time_window="23:00 - 07:00", color="#3B82F6")
    ]

    is_liander = (provider.strip().lower() == "liander")
    if is_liander:
        tier_key = grid_tier_key or "MS"
        cap_key = capacity_key or "cap_630"
        t_df = build_liander_2025_tariff_dataframe(
            grid_tier_key=tier_key,
            capacity_key=cap_key,
            billing_schedule=billing_schedule,
            supply_markup_peak=0.0,
            supply_markup_offpeak=0.0,
            tax_rate_pct=21.0
        )
        tier_label = LIANDER_2025_GRID_TIERS.get(tier_key, {}).get("label", "MS")
        preset_title = f"Netherlands Liander 2025 ({tier_label})"
    else:
        tier_key = grid_tier_key or "MS_D"
        cap_key = capacity_key or "cap_1750"
        t_df = build_enexis_2025_tariff_dataframe(
            grid_tier_key=tier_key,
            capacity_key=cap_key,
            billing_schedule=billing_schedule,
            supply_markup_peak=0.0,
            supply_markup_offpeak=0.0,
            tax_rate_pct=21.0
        )
        tier_label = ENEXIS_2025_GRID_TIERS.get(tier_key, {}).get("label", "MS-D")
        preset_title = f"Netherlands Enexis 2025 ({tier_label})"

    return c_df, t_df, tou_tiers, "EUR", 1.0, preset_title


def reload_preset_data(preset_name: str) -> Tuple[pd.DataFrame, pd.DataFrame, List[TOUTierConfig], str, float, str]:
    """Reloads clean initial preset data matching the given preset title or identifier."""
    name_clean = str(preset_name).strip().lower()
    if "liander" in name_clean:
        return get_netherlands_commercial_preset(provider="liander")
    elif "enexis" in name_clean or "netherlands" in name_clean:
        return get_netherlands_commercial_preset(provider="enexis")
    elif "argentine" in name_clean or "pico" in name_clean or "3-tier" in name_clean:
        return get_3tier_argentine_preset()
    else:
        return get_salentein_pozo600_preset()


def get_preset_three_party_entities(preset_name: str) -> Tuple[str, str, str, float]:
    """
    Returns (dso_name, supplier_name, meter_company_name, default_monthly_meter_fee)
    for a given preset to explicitly populate the 3-Party Market Entities in the UI.
    """
    p_lower = (preset_name or "").lower()
    if "liander" in p_lower:
        return ("Liander Netbeheer B.V.", "Eneco Zakelijk", "Fudura B.V.", 75.00)
    elif "enexis" in p_lower:
        return ("Enexis Netbeheer B.V.", "Vattenfall Zakelijk", "Kenter B.V.", 85.00)
    elif "salentein" in p_lower:
        return ("EDEMSA (Distribuidora de Electricidad de Mendoza S.A.)", "EDEMSA Suministro", "EDEMSA Medición RLM", 0.0)
    elif "3-tier" in p_lower or "argentine" in p_lower:
        return ("EDEMSA Mendoza", "CAMMESA / Distribuidora", "EDEMSA Medición", 0.0)
    else:
        return ("Regional Distribution Network Operator (DSO)", "Commercial Energy Supplier", "Certified Metering Company", 50.00)

