"""
========================================================================================
Stage 1 Benchmark Defaults: Reference Year 2025 (tariff_defaults_2025.py)
========================================================================================
Supplies official 2025 Dutch DSO rate catalogs and commercial benchmarks:
  - Enexis Netbeheer (LS, MS/LS, MS-D, MS-T, HS/MS, TS) - From Official 2025 Tarievenblad
  - Liander Netbeheer (LS, MS/LS, MS, TS/MS, TS, HS) - From Official 2025 Tarievenblad
  - Stedin Netbeheer (LS, Trafo MS/LS, MS, Trafo HS+TS/MS, TS) - From Official 2025 Tarievenblad
  - Commercial energy suppliers: Vattenfall, Eneco, Essent, Shell Energy
  - Certified metering companies: Fudura, Joulz, Kenter
========================================================================================
"""

from typing import Dict, Any, Optional

try:
    from .config_and_models import (
        TariffStage,
        PricingMode,
        DSOTariff,
        SupplierTariff,
        MeteringTariff,
        LevyConfig,
        StatusQuoConfig2025,
    )
except (ImportError, ValueError):
    from config_and_models import (
        TariffStage,
        PricingMode,
        DSOTariff,
        SupplierTariff,
        MeteringTariff,
        LevyConfig,
        StatusQuoConfig2025,
    )


# ======================================================================================
# 1. Official Dutch 2025 DSO Tariff Catalogs
# ======================================================================================

ENEXIS_2025_GRID_TIERS: Dict[str, Dict[str, Any]] = {
    "MS-D (125 t/m 1.500 kW)": {
        "description": "Middenspanning Distributienet (1-20 kV, 125 bis 1500 kW gecontracteerd vermogen)",
        "aansluitdienst_annual": 1653.00,
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 2.4400,     # € 29.28 / kW / jaar -> € 2.44 / kW / maand
        "rate_peak_monthly": 3.7100,           # € 3.71 / kW / maand
        "rate_peak_kwh": 0.0250,               # kWh normaal
        "rate_offpeak_kwh": 0.0250,            # kWh laag
        "reactive_tariff": 0.0188,             # € 0.0188 / kVArh blind-verbruik
        "typical_contracted_kw": 400.0,
    },
    "MS/LS (> 50 t/m 125 kW)": {
        "description": "Transformator MS naar LS (50 bis 125 kW gecontracteerd vermogen)",
        "aansluitdienst_annual": 381.00,
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 4.2000,     # € 50.40 / kW / jaar -> € 4.20 / kW / maand
        "rate_peak_monthly": 3.7100,           # € 3.71 / kW / maand
        "rate_peak_kwh": 0.0250,
        "rate_offpeak_kwh": 0.0250,
        "reactive_tariff": 0.0188,
        "typical_contracted_kw": 100.0,
    },
    "LS (t/m 50 kW)": {
        "description": "Laagspanning tot en met 50 kW",
        "aansluitdienst_annual": 381.00,
        "vastrecht_annual": 18.00,
        "rate_contracted_monthly": 1.3375,     # € 16.05 / kW / jaar -> € 1.3375 / kW / maand
        "rate_peak_monthly": 0.0000,
        "rate_peak_kwh": 0.0804,
        "rate_offpeak_kwh": 0.0421,
        "reactive_tariff": 0.0188,
        "typical_contracted_kw": 40.0,
    },
    "MS-T (> 1.500 kW)": {
        "description": "Middenspanning Transportnet (> 1.500 kW gecontracteerd)",
        "aansluitdienst_annual": 1653.00,
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 2.3092,     # € 27.71 / kW / jaar -> € 2.3092 / kW / maand
        "rate_peak_monthly": 3.1000,
        "rate_peak_kwh": 0.0152,
        "rate_offpeak_kwh": 0.0152,
        "reactive_tariff": 0.0188,
        "typical_contracted_kw": 2000.0,
    },
    "HS/MS (> 1.500 kW)": {
        "description": "Hoogspanning naar Middenspanning (> 1.500 kW)",
        "aansluitdienst_annual": 4560.00,
        "vastrecht_annual": 2760.00,
        "rate_contracted_monthly": 3.5083,     # € 42.10 / kW / jaar -> € 3.5083 / kW / maand
        "rate_peak_monthly": 4.4800,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_tariff": 0.0188,
        "typical_contracted_kw": 3000.0,
    },
    "TS (> 1.500 kW)": {
        "description": "Tussenspanning (30-50 kV, > 1.500 kW)",
        "aansluitdienst_annual": 4560.00,
        "vastrecht_annual": 2760.00,
        "rate_contracted_monthly": 2.6142,     # € 31.37 / kW / jaar -> € 2.6142 / kW / maand
        "rate_peak_monthly": 3.6700,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_tariff": 0.0188,
        "typical_contracted_kw": 3000.0,
    },
}

LIANDER_2025_GRID_TIERS: Dict[str, Dict[str, Any]] = {
    "MS (> 136 t/m 2.000 kW)": {
        "description": "Middenspanning (1-20 kV, 136 bis 2.000 kW gecontracteerd)",
        "aansluitdienst_annual": 1013.88,
        "vastrecht_annual": 441.00,             # 12 x € 36.75
        "rate_contracted_monthly": 2.2233,
        "rate_peak_monthly": 3.4600,
        "rate_peak_kwh": 0.2200,               # kWh hoog (Table 2.1)
        "rate_offpeak_kwh": 0.2200,            # kWh laag (Table 2.1)
        "reactive_tariff": 0.0000,
        "typical_contracted_kw": 400.0,
    },
    "MS/LS (> 50 t/m 136 kW)": {
        "description": "Transformator MS naar LS (50 bis 136 kW)",
        "aansluitdienst_annual": 381.00,
        "vastrecht_annual": 441.00,             # 12 x € 36.75
        "rate_contracted_monthly": 3.6567,
        "rate_peak_monthly": 3.4600,
        "rate_peak_kwh": 0.2200,               # kWh hoog (Table 2.1)
        "rate_offpeak_kwh": 0.2200,            # kWh laag (Table 2.1)
        "reactive_tariff": 0.0000,
        "typical_contracted_kw": 100.0,
    },
    "LS (t/m 50 kW)": {
        "description": "Laagspanning tot en met 50 kW",
        "aansluitdienst_annual": 381.00,
        "vastrecht_annual": 18.00,              # 12 x € 1.50
        "rate_contracted_monthly": 1.4100,
        "rate_peak_monthly": 0.0000,
        "rate_peak_kwh": 0.0758,
        "rate_offpeak_kwh": 0.0403,
        "reactive_tariff": 0.0000,
        "typical_contracted_kw": 40.0,
    },
    "TS/MS of HS/MS (> 2.000 kW)": {
        "description": "Tussen-/Hoogspanning naar MS (> 2.000 kW)",
        "aansluitdienst_annual": 4560.00,
        "vastrecht_annual": 2760.00,            # 12 x € 230.00
        "rate_contracted_monthly": 3.8000,
        "rate_peak_monthly": 5.9400,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_tariff": 0.0000,
        "typical_contracted_kw": 3000.0,
    },
    "TS (> 2.000 kW)": {
        "description": "Tussenspanning 50 kV (> 2.000 kW)",
        "aansluitdienst_annual": 4560.00,
        "vastrecht_annual": 2760.00,
        "rate_contracted_monthly": 3.8000,
        "rate_peak_monthly": 5.2300,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_tariff": 0.0000,
        "typical_contracted_kw": 3000.0,
    },
    "HS (> 2.000 kW)": {
        "description": "Hoogspanning boven 50 kV (> 2.000 kW)",
        "aansluitdienst_annual": 5351.00,
        "vastrecht_annual": 2760.00,
        "rate_contracted_monthly": 1.8400,
        "rate_peak_monthly": 2.2800,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_tariff": 0.0000,
        "typical_contracted_kw": 4000.0,
    },
}

STEDIN_2025_GRID_TIERS: Dict[str, Dict[str, Any]] = {
    "MS (151 t/m 1.500 kW)": {
        "description": "Middenspanning Distributienet (151 bis 1.500 kW gecontracteerd)",
        "aansluitdienst_annual": 1455.50,
        "vastrecht_annual": 441.00,             # 12 x € 36.75
        "rate_contracted_monthly": 2.0250,
        "rate_peak_monthly": 3.1000,
        "rate_peak_kwh": 0.0198,               # dubbel normaal
        "rate_offpeak_kwh": 0.0198,            # dubbel laag
        "reactive_tariff": 0.0170,             # € 0.0170 / kVArh
        "typical_contracted_kw": 400.0,
    },
    "Trafo MS/LS (51 t/m 150 kW)": {
        "description": "Transformator MS/LS (51 bis 150 kW gecontracteerd)",
        "aansluitdienst_annual": 164.30,
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 3.9350,
        "rate_peak_monthly": 3.1000,
        "rate_peak_kwh": 0.0198,
        "rate_offpeak_kwh": 0.0198,
        "reactive_tariff": 0.0170,
        "typical_contracted_kw": 100.0,
    },
    "LS (t/m 50 kW)": {
        "description": "Laagspanning tot en met 50 kW",
        "aansluitdienst_annual": 74.44,
        "vastrecht_annual": 18.00,              # 12 x € 1.50
        "rate_contracted_monthly": 1.5500,
        "rate_peak_monthly": 0.0000,
        "rate_peak_kwh": 0.0750,
        "rate_offpeak_kwh": 0.0460,
        "reactive_tariff": 0.0170,
        "typical_contracted_kw": 40.0,
    },
    "Trafo HS+TS/MS (> 1.500 kW)": {
        "description": "Transformator HS+TS naar MS (> 1.500 kW)",
        "aansluitdienst_annual": 3642.00,
        "vastrecht_annual": 2760.00,            # 12 x € 230.00
        "rate_contracted_monthly": 3.7917,
        "rate_peak_monthly": 5.3000,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_tariff": 0.0170,
        "typical_contracted_kw": 3000.0,
    },
    "TS (> 1.500 kW)": {
        "description": "Tussenspanning (> 1.500 kW)",
        "aansluitdienst_annual": 3642.00,
        "vastrecht_annual": 2760.00,
        "rate_contracted_monthly": 3.1283,
        "rate_peak_monthly": 4.1500,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "reactive_tariff": 0.0170,
        "typical_contracted_kw": 3000.0,
    },
}

DSO_CATALOGS_2025: Dict[str, Dict[str, Dict[str, Any]]] = {
    "Enexis Netbeheer B.V.": ENEXIS_2025_GRID_TIERS,
    "Liander Netbeheer B.V.": LIANDER_2025_GRID_TIERS,
    "Stedin Netbeheer B.V.": STEDIN_2025_GRID_TIERS,
}


# ======================================================================================
# 2. Commercial Suppliers & Metering Providers (Multi-Tier Catalogs 2025)
# ======================================================================================

SUPPLIER_CATALOG_2025: Dict[str, Dict[str, Dict[str, Any]]] = {
    "Vattenfall Zakelijk": {
        "Vast 1 Jaar (Dubbeltarief HT/NT)": {
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 180.00,
            "rate_peak_kwh": 0.1340,
            "rate_offpeak_kwh": 0.1180,
            "fixed_rate_kwh": 0.1250,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0030,
            "description": "1 jaar vaste prijszekerheid met afzonderlijke piek- en daltarieven",
        },
        "Vast 1 Jaar (Enkeltarief)": {
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": False,
            "base_fee_annual": 180.00,
            "fixed_rate_kwh": 0.1250,
            "rate_peak_kwh": 0.1250,
            "rate_offpeak_kwh": 0.1250,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0030,
            "description": "1 jaar vast met één uniform tarief per kWh over alle uren",
        },
        "Vast 3 Jaar (Zekerheid)": {
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 195.00,
            "rate_peak_kwh": 0.1290,
            "rate_offpeak_kwh": 0.1140,
            "fixed_rate_kwh": 0.1210,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0030,
            "description": "3 jaar langjarige prijsgarantie voor stabiele energiekosten",
        },
        "Dynamisch EPEX Spot Zakelijk": {
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 180.00,
            "fixed_rate_kwh": 0.1200,
            "rate_peak_kwh": 0.1200,
            "rate_offpeak_kwh": 0.1200,
            "supplier_margin_kwh": 0.0075,
            "procurement_fee_kwh": 0.0015,
            "green_surcharge_kwh": 0.0030,
            "description": "Uurlijkse EPEX Spot Day-Ahead inkoop + transparante leveranciersopslag",
        },
        "Flexibel Maandelijks Variabel": {
            "pricing_mode": PricingMode.VARIABLE,
            "is_dual_rate": False,
            "base_fee_annual": 180.00,
            "fixed_rate_kwh": 0.1250,
            "rate_peak_kwh": 0.1250,
            "rate_offpeak_kwh": 0.1250,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0030,
            "monthly_variable_rates": [
                0.130, 0.125, 0.120, 0.115, 0.110, 0.105,
                0.105, 0.110, 0.115, 0.120, 0.125, 0.130
            ],
            "description": "Maandelijks aanpasbare marktconforme energieprijzen",
        },
    },
    "Eneco Zakelijk": {
        "Vast 1 Jaar (Dubbeltarief HT/NT)": {
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 160.00,
            "rate_peak_kwh": 0.1360,
            "rate_offpeak_kwh": 0.1190,
            "fixed_rate_kwh": 0.1270,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0040,
            "description": "100% Hollandse Wind met dubbeltarief dag/nacht",
        },
        "Vast 3 Jaar (Zekerheid)": {
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 175.00,
            "rate_peak_kwh": 0.1310,
            "rate_offpeak_kwh": 0.1150,
            "fixed_rate_kwh": 0.1230,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0040,
            "description": "3 jaar lang vaste tarieven voor actieve energie",
        },
        "Eneco Dynamisch Zakelijk": {
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 160.00,
            "fixed_rate_kwh": 0.1200,
            "rate_peak_kwh": 0.1200,
            "rate_offpeak_kwh": 0.1200,
            "supplier_margin_kwh": 0.0080,
            "procurement_fee_kwh": 0.0018,
            "green_surcharge_kwh": 0.0040,
            "description": "Flexibele inkoop op EPEX Spot groothandelsmarkt",
        },
        "Eneco Flexibel Variabel": {
            "pricing_mode": PricingMode.VARIABLE,
            "is_dual_rate": False,
            "base_fee_annual": 160.00,
            "fixed_rate_kwh": 0.1270,
            "rate_peak_kwh": 0.1270,
            "rate_offpeak_kwh": 0.1270,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0040,
            "monthly_variable_rates": [
                0.132, 0.127, 0.122, 0.117, 0.112, 0.107,
                0.107, 0.112, 0.117, 0.122, 0.127, 0.132
            ],
            "description": "Maandelijks variabele tariefstructuur",
        },
    },
    "Essent Zakelijk": {
        "Vast 1 Jaar (Dubbeltarief HT/NT)": {
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 190.00,
            "rate_peak_kwh": 0.1320,
            "rate_offpeak_kwh": 0.1160,
            "fixed_rate_kwh": 0.1230,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0035,
            "description": "Essent Zekerheidscontract met HT/NT uren",
        },
        "Vast 3 Jaar (Zekerheid)": {
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 205.00,
            "rate_peak_kwh": 0.1280,
            "rate_offpeak_kwh": 0.1120,
            "fixed_rate_kwh": 0.1200,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0035,
            "description": "Langjarige stabiliteit tegen scherpe vaste prijzen",
        },
        "Essent Dynamisch Zakelijk": {
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 190.00,
            "fixed_rate_kwh": 0.1200,
            "rate_peak_kwh": 0.1200,
            "rate_offpeak_kwh": 0.1200,
            "supplier_margin_kwh": 0.0070,
            "procurement_fee_kwh": 0.0015,
            "green_surcharge_kwh": 0.0035,
            "description": "EPEX Spot indexering met transparante Essent opslag",
        },
    },
    "Shell Energy": {
        "Direct Fixed 1-Year (Dubbeltarief)": {
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 200.00,
            "rate_peak_kwh": 0.1350,
            "rate_offpeak_kwh": 0.1170,
            "fixed_rate_kwh": 0.1260,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0025,
            "description": "Shell Energy zakelijke levering vast tarief",
        },
        "Direct Dynamic Spot": {
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 200.00,
            "fixed_rate_kwh": 0.1200,
            "rate_peak_kwh": 0.1200,
            "rate_offpeak_kwh": 0.1200,
            "supplier_margin_kwh": 0.0065,
            "procurement_fee_kwh": 0.0012,
            "green_surcharge_kwh": 0.0025,
            "description": "Directe koppeling aan EPEX Spot groothandelsprijzen",
        },
    },
    "TotalEnergies Gas & Power": {
        "TotalEnergies Vast 1 Jaar": {
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 185.00,
            "rate_peak_kwh": 0.1330,
            "rate_offpeak_kwh": 0.1165,
            "fixed_rate_kwh": 0.1240,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0030,
            "description": "Vaste zakelijke stroomtarieven voor het MKB en industrie",
        },
        "TotalEnergies Dynamisch": {
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 185.00,
            "fixed_rate_kwh": 0.1200,
            "rate_peak_kwh": 0.1200,
            "rate_offpeak_kwh": 0.1200,
            "supplier_margin_kwh": 0.0068,
            "procurement_fee_kwh": 0.0014,
            "green_surcharge_kwh": 0.0030,
            "description": "Dynamische uurprijzen EPEX Day-Ahead",
        },
    },
    "Greenchoice Zakelijk": {
        "100% Groene Stroom Vast 1 Jaar": {
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 175.00,
            "rate_peak_kwh": 0.1380,
            "rate_offpeak_kwh": 0.1210,
            "fixed_rate_kwh": 0.1290,
            "supplier_margin_kwh": 0.0,
            "procurement_fee_kwh": 0.0,
            "green_surcharge_kwh": 0.0050,
            "description": "100% Nederlandse wind- en zonne-energie met GvO's",
        },
        "Greenchoice Dynamisch": {
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 175.00,
            "fixed_rate_kwh": 0.1200,
            "rate_peak_kwh": 0.1200,
            "rate_offpeak_kwh": 0.1200,
            "supplier_margin_kwh": 0.0078,
            "procurement_fee_kwh": 0.0015,
            "green_surcharge_kwh": 0.0050,
            "description": "Dynamisch spotcontract met uitsluitend duurzame garanties",
        },
    },
    "Tibber Zakelijk (Dynamisch)": {
        "Tibber Pure Dynamic Spot": {
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 71.88,
            "fixed_rate_kwh": 0.1200,
            "rate_peak_kwh": 0.1200,
            "rate_offpeak_kwh": 0.1200,
            "supplier_margin_kwh": 0.0020,
            "procurement_fee_kwh": 0.0010,
            "green_surcharge_kwh": 0.0025,
            "description": "Transparant inkoopstarief (€ 5,99/mo + minimale opslag)",
        },
    },
}

METERING_CATALOG_2025: Dict[str, Dict[str, Dict[str, Any]]] = {
    "Fudura B.V.": {
        "Kwartierdata Telemetrie MS (Grootverbruik RLM)": {
            "annual_flat_fee": 900.00,
            "description": "Grootverbruik kwartierdata telemetrie (MS/RLM) via GPRS/Ethernet",
        },
        "Meettransformatoren MS (Trafo CT/VT)": {
            "annual_flat_fee": 1550.00,
            "description": "Inclusief huur en kalibratie van stroom- & spanningstransformatoren",
        },
        "Kleinverbruik / Tussenmeting (Submetering)": {
            "annual_flat_fee": 420.00,
            "description": "Secundaire tussenbemeting voor proces- of huurdersbewaking",
        },
        "Hoogspanning Telemetrie (HS/TS > 2 MW)": {
            "annual_flat_fee": 2600.00,
            "description": "Redundante hoogspannings-telemetrie met optische meetkoppeling",
        },
    },
    "Joulz Meetbedrijf": {
        "Grootverbruik Telemetrie MS": {
            "annual_flat_fee": 850.00,
            "description": "Erkend meetverantwoordelijke kwartierdata grootverbruik",
        },
        "Meettransformatoren MS": {
            "annual_flat_fee": 1480.00,
            "description": "Inclusief geijkte stroom- en spanningstransformatoren",
        },
        "Kleinverbruik / Tussenmeting": {
            "annual_flat_fee": 390.00,
            "description": "Submetering meetdienst kleinverbruik",
        },
        "Hoogspanning HS Telemetrie": {
            "annual_flat_fee": 2450.00,
            "description": "Hoogspanningsmeting en dagelijkse datavalidatie",
        },
    },
    "Kenter B.V.": {
        "Kenter Meetdiensten MS RLM": {
            "annual_flat_fee": 950.00,
            "description": "Kwartierdata uitlezing en online energiemonitoring portaal",
        },
        "Kenter Trafo Meetset": {
            "annual_flat_fee": 1620.00,
            "description": "Complete meetset inclusief transformatoren",
        },
        "Kenter Tussenbemeting": {
            "annual_flat_fee": 450.00,
            "description": "Tussenbemeting voor energiemanagement (ISO 50001)",
        },
        "Kenter Hoogspanning HS": {
            "annual_flat_fee": 2750.00,
            "description": "Inkoopstation hoogspanningsbemeting",
        },
    },
}


# ======================================================================================
# 3. Helper Functions
# ======================================================================================

def get_dso_tariff_from_catalog(
    dso_company: str,
    tier_name: str,
    contracted_capacity_kw: float = 250.0,
    cable_surcharge_annual: float = 0.0,
) -> DSOTariff:
    """Instantiates a DSOTariff model from the selected company and tier."""
    company_data = DSO_CATALOGS_2025.get(dso_company, ENEXIS_2025_GRID_TIERS)
    tier = company_data.get(tier_name, list(company_data.values())[0])

    return DSOTariff(
        dso_name=dso_company,
        grid_tier=tier_name,
        connection_category="standard",
        fixed_connection_annual=float(tier.get("aansluitdienst_annual", 1653.00)),
        fixed_transport_annual=float(tier.get("vastrecht_annual", 441.00)),
        cable_surcharge_annual=float(cable_surcharge_annual),
        contracted_capacity_kw=float(contracted_capacity_kw),
        rate_contracted_capacity=float(tier.get("rate_contracted_monthly", 2.4400)),
        rate_peak_demand=float(tier.get("rate_peak_monthly", 3.7100)),
        rate_transport_peak_kwh=float(tier.get("rate_peak_kwh", 0.0250)),
        rate_transport_offpeak_kwh=float(tier.get("rate_offpeak_kwh", 0.0250)),
        adjust_capacity_on_breach=True,
    )


def get_liander_2025_dso_defaults(contracted_capacity_kw: float = 250.0) -> DSOTariff:
    """Default fallback matching Liander MS."""
    return get_dso_tariff_from_catalog(
        dso_company="Liander Netbeheer B.V.",
        tier_name="MS (> 136 t/m 2.000 kW)",
        contracted_capacity_kw=contracted_capacity_kw,
    )


def get_supplier_tariff_from_catalog(
    supplier_name: str,
    product_name: str,
) -> SupplierTariff:
    """Instantiates a SupplierTariff model from selected supplier and product."""
    company_products = SUPPLIER_CATALOG_2025.get(supplier_name, SUPPLIER_CATALOG_2025["Vattenfall Zakelijk"])
    prod = company_products.get(product_name, list(company_products.values())[0])

    mode = prod.get("pricing_mode", PricingMode.FIXED)
    return SupplierTariff(
        supplier_name=supplier_name,
        pricing_mode=mode,
        tariff_product_name=product_name,
        base_fee_annual=float(prod.get("base_fee_annual", 180.00)),
        fixed_rate_kwh=float(prod.get("fixed_rate_kwh", 0.1250)),
        is_dual_rate=bool(prod.get("is_dual_rate", False)),
        fixed_rate_peak_kwh=float(prod.get("rate_peak_kwh", 0.1340)),
        fixed_rate_offpeak_kwh=float(prod.get("rate_offpeak_kwh", 0.1180)),
        procurement_fee_kwh=float(prod.get("procurement_fee_kwh", 0.0)),
        green_certificate_surcharge_kwh=float(prod.get("green_surcharge_kwh", 0.0)),
        monthly_variable_rates=prod.get("monthly_variable_rates", [0.125] * 12),
        market_price_profile_id="epex_nl_2025",
        supplier_margin_kwh=float(prod.get("supplier_margin_kwh", 0.0075)),
        spot_default_fallback_rate=0.1200,
    )


def get_default_supplier_tariff_2025(
    supplier_name: str = "Vattenfall Zakelijk",
    pricing_mode: PricingMode = PricingMode.DYNAMIC,
) -> SupplierTariff:
    """Backward-compatible helper returning default supplier contract."""
    prod_name = "Dynamisch EPEX Spot Zakelijk" if pricing_mode == PricingMode.DYNAMIC else (
        "Flexibel Maandelijks Variabel" if pricing_mode == PricingMode.VARIABLE else "Vast 1 Jaar (Dubbeltarief HT/NT)"
    )
    t = get_supplier_tariff_from_catalog(supplier_name=supplier_name, product_name=prod_name)
    t.pricing_mode = pricing_mode
    return t


def get_metering_tariff_from_catalog(
    meter_company_name: str,
    package_name: str,
) -> MeteringTariff:
    """Instantiates a MeteringTariff model from selected company and service package."""
    company_packages = METERING_CATALOG_2025.get(meter_company_name, METERING_CATALOG_2025["Fudura B.V."])
    pkg = company_packages.get(package_name, list(company_packages.values())[0])

    return MeteringTariff(
        meter_company_name=meter_company_name,
        service_package_name=package_name,
        annual_flat_fee=float(pkg.get("annual_flat_fee", 900.00)),
        description=str(pkg.get("description", "")),
    )


def get_default_metering_tariff_2025(meter_company_name: str = "Fudura B.V.") -> MeteringTariff:
    """Backward-compatible helper returning default metering contract."""
    return get_metering_tariff_from_catalog(
        meter_company_name=meter_company_name,
        package_name="Kwartierdata Telemetrie MS (Grootverbruik RLM)",
    )


def get_default_levy_config_2025() -> LevyConfig:
    return LevyConfig(
        statutory_levy_rate_kwh=0.0125,
        annual_tax_reduction=0.0,
        vat_rate_pct=21.0,
    )


def get_stage_1_default_config_2025(
    pricing_mode: PricingMode = PricingMode.DYNAMIC,
    contracted_capacity_kw: float = 250.0,
) -> StatusQuoConfig2025:
    return StatusQuoConfig2025(
        stage=TariffStage.STAGE_1_DEFAULT,
        dso=get_dso_tariff_from_catalog(
            dso_company="Enexis Netbeheer B.V.",
            tier_name="MS-D (125 t/m 1.500 kW)",
            contracted_capacity_kw=contracted_capacity_kw,
        ),
        supplier=get_default_supplier_tariff_2025(pricing_mode=pricing_mode),
        metering=get_default_metering_tariff_2025(),
        levies=get_default_levy_config_2025(),
        discount_rate_pct=5.0,
        energy_escalation_pct=3.0,
        evaluation_horizon_years=15,
    )

