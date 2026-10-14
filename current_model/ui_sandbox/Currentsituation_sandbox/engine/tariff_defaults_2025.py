"""
========================================================================================
Stage 1 Benchmark Defaults: Dutch Grootverbruik (engine/tariff_defaults_2025.py)
Current Situation (Status Quo) Sandbox Engine
========================================================================================
Supplies official 2025/2026 Dutch DSO rate catalogs, 4 commercial supplier segments,
transformer station rental catalog, and certified metering defaults:
  - Liander N.V. (Official AC2 to AC6 categories with PAV and GTV)
  - Enexis Netbeheer & Stedin Netbeheer
  - Commercial suppliers (4 categories: Major Utilities, B2B Portfolio, Dynamic Spot, Green)
  - Transformer Rental (Fudura, Kenter, Joulz, Alfen, Batenburg)
  - Certified Metering EMV (Fudura, Joulz, Kenter, Anexo, INNAX)
  - Statutory 2025 & 2026 Energiebelasting brackets and Vermindering rebates
========================================================================================
"""

from typing import Dict, Any, List, Optional
try:
    from .config_and_models import (
        TariffStage,
        PricingMode,
        SupplierCategory,
        DSOTariff,
        SupplierTariff,
        TrancheBlock,
        MeteringTariff,
        TrafoRentalTariff,
        TaxBracket,
        LevyConfig,
        StatusQuoConfig2025,
    )
    from .tax_accounting import TAX_SCHEDULE_2025, TAX_SCHEDULE_2026, VERMINDERING_2025, VERMINDERING_2026
except (ImportError, ValueError):
    from config_and_models import (
        TariffStage,
        PricingMode,
        SupplierCategory,
        DSOTariff,
        SupplierTariff,
        TrancheBlock,
        MeteringTariff,
        TrafoRentalTariff,
        TaxBracket,
        LevyConfig,
        StatusQuoConfig2025,
    )
    from tax_accounting import TAX_SCHEDULE_2025, TAX_SCHEDULE_2026, VERMINDERING_2025, VERMINDERING_2026


# ======================================================================================
# 1. Regulated DSO Tariff Catalogs (ACM Regulated)
# ======================================================================================

LIANDER_2025_GRID_TIERS: Dict[str, Dict[str, Any]] = {
    "AC4b: MS/LS (Trafo DSO > 50 bis 147 kW)": {
        "ac_code": "AC4b",
        "description": "Transformator MS naar LS DSO (>50 bis 147 kW gecontracteerd vermogen)",
        "aansluitdienst_annual": 283.68,        # PAV: 12 x € 23.64 / maand
        "vastrecht_annual": 441.00,             # Vastrecht: 12 x € 36.75 / maand
        "rate_contracted_monthly": 3.6567,      # GTV: € 43.881 / kW / jaar -> € 3.6567 / kW / maand
        "rate_peak_monthly": 3.4600,            # Maandpiek: € 3.46 / kW / maand
        "rate_peak_kwh": 0.0220,
        "rate_offpeak_kwh": 0.0220,
        "max_physical_limit_kw": 160.0,
        "typical_contracted_kw": 147.0,
    },
    "AC4a: MS/LS (Trafo DSO > 50 bis 100 kW)": {
        "ac_code": "AC4a",
        "description": "Transformator MS naar LS DSO (>50 bis 100 kW gecontracteerd vermogen)",
        "aansluitdienst_annual": 254.16,        # PAV: 12 x € 21.18 / maand
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 3.6567,
        "rate_peak_monthly": 3.4600,
        "rate_peak_kwh": 0.0220,
        "rate_offpeak_kwh": 0.0220,
        "max_physical_limit_kw": 100.0,
        "typical_contracted_kw": 80.0,
    },
    "AC5a: MS eigene Station (> 136 bis 536 kW)": {
        "ac_code": "AC5a",
        "description": "Middenspanning eigene Trafostation (>136 bis 536 kW, 160–630 kVA Trafo, LS-Messung)",
        "aansluitdienst_annual": 1013.88,       # PAV: 12 x € 84.49 / maand
        "vastrecht_annual": 441.00,             # Vastrecht: 12 x € 36.75 / maand
        "rate_contracted_monthly": 2.2233,      # GTV: € 26.680 / kW / jaar -> € 2.2233 / kW / maand
        "rate_peak_monthly": 3.4600,            # Maandpiek: € 3.46 / kW / maand
        "rate_peak_kwh": 0.0220,
        "rate_offpeak_kwh": 0.0220,
        "max_physical_limit_kw": 630.0,
        "typical_contracted_kw": 536.0,
    },
    "AC5b: MS eigene Station (> 136 bis 850 kW)": {
        "ac_code": "AC5b",
        "description": "Middenspanning eigene Trafostation (>136 bis 850 kW, 630–1.000 kVA, LS-Messung)",
        "aansluitdienst_annual": 1013.88,       # PAV: 12 x € 84.49 / maand
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 2.2233,
        "rate_peak_monthly": 3.4600,
        "rate_peak_kwh": 0.0220,
        "rate_offpeak_kwh": 0.0220,
        "max_physical_limit_kw": 1000.0,
        "typical_contracted_kw": 750.0,
    },
    "AC5: MS eigene Station MS-Messung (> 136 bis 1.850 kW)": {
        "ac_code": "AC5",
        "description": "Middenspanning eigene Trafostation (>136 bis 1.850 kW, 1–2 MVA Trafo, MS-Messung)",
        "aansluitdienst_annual": 1926.84,       # PAV: 12 x € 160.57 / maand
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 2.2233,
        "rate_peak_monthly": 3.4600,
        "rate_peak_kwh": 0.0220,
        "rate_offpeak_kwh": 0.0220,
        "max_physical_limit_kw": 2000.0,
        "typical_contracted_kw": 1200.0,
    },
    "AC2: Niederspannung LS (bis 50 kW)": {
        "ac_code": "AC2",
        "description": "Niederspannung Klein-Grootverbruik (3x80A bis 100 kVA, ≤ 50 kW)",
        "aansluitdienst_annual": 61.20,         # PAV: 12 x € 5.10 / maand
        "vastrecht_annual": 18.00,              # Vastrecht: 12 x € 1.50 / maand
        "rate_contracted_monthly": 1.4100,
        "rate_peak_monthly": 0.0000,
        "rate_peak_kwh": 0.0758,
        "rate_offpeak_kwh": 0.0403,
        "max_physical_limit_kw": 50.0,
        "typical_contracted_kw": 45.0,
    },
    "AC6: Zwischen-/Hochspannung TS/MS (> 2.000 kW)": {
        "ac_code": "AC6",
        "description": "Zwischen- und Hochspannung (> 2.000 kW, 2 bis 10 MVA)",
        "aansluitdienst_annual": 13902.00,      # PAV: 12 x € 1.158.50 / maand
        "vastrecht_annual": 2760.00,            # Vastrecht: 12 x € 230.00 / maand
        "rate_contracted_monthly": 3.8000,
        "rate_peak_monthly": 5.5800,
        "rate_peak_kwh": 0.0000,
        "rate_offpeak_kwh": 0.0000,
        "max_physical_limit_kw": 10000.0,
        "typical_contracted_kw": 3500.0,
    },
}

ENEXIS_2025_GRID_TIERS: Dict[str, Dict[str, Any]] = {
    "MS-D (125 t/m 1.500 kW)": {
        "ac_code": "AC5a",
        "description": "Enexis Middenspanning Distributienet (125 bis 1500 kW)",
        "aansluitdienst_annual": 1013.88,
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 2.4400,
        "rate_peak_monthly": 3.7100,
        "rate_peak_kwh": 0.0250,
        "rate_offpeak_kwh": 0.0250,
        "max_physical_limit_kw": 1500.0,
        "typical_contracted_kw": 500.0,
    },
    "MS/LS (> 50 t/m 125 kW)": {
        "ac_code": "AC4b",
        "description": "Enexis Transformator MS naar LS (50 bis 125 kW)",
        "aansluitdienst_annual": 283.68,
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 4.2000,
        "rate_peak_monthly": 3.7100,
        "rate_peak_kwh": 0.0250,
        "rate_offpeak_kwh": 0.0250,
        "max_physical_limit_kw": 160.0,
        "typical_contracted_kw": 100.0,
    },
}

STEDIN_2025_GRID_TIERS: Dict[str, Dict[str, Any]] = {
    "MS Randstad (> 125 bis 2.000 kW)": {
        "ac_code": "AC5a",
        "description": "Stedin Middenspanning Randstad / Rotterdam Haven (125–2.000 kW)",
        "aansluitdienst_annual": 1013.88,
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 2.3800,
        "rate_peak_monthly": 3.6200,
        "rate_peak_kwh": 0.0240,
        "rate_offpeak_kwh": 0.0240,
        "max_physical_limit_kw": 2000.0,
        "typical_contracted_kw": 600.0,
    },
    "MS/LS Trafo Stedin (50 bis 125 kW)": {
        "ac_code": "AC4b",
        "description": "Stedin Transformator MS naar LS",
        "aansluitdienst_annual": 283.68,
        "vastrecht_annual": 441.00,
        "rate_contracted_monthly": 3.9500,
        "rate_peak_monthly": 3.6200,
        "rate_peak_kwh": 0.0240,
        "rate_offpeak_kwh": 0.0240,
        "max_physical_limit_kw": 160.0,
        "typical_contracted_kw": 120.0,
    },
}

DSO_CATALOGS_2025: Dict[str, Dict[str, Dict[str, Any]]] = {
    "Liander N.V.": LIANDER_2025_GRID_TIERS,
    "Enexis Netbeheer B.V.": ENEXIS_2025_GRID_TIERS,
    "Stedin Netbeheer B.V.": STEDIN_2025_GRID_TIERS,
}


# ======================================================================================
# 2. Commercial Suppliers (4 Segments + Shell Energy)
# ======================================================================================

SUPPLIER_CATALOG_2025: Dict[str, Dict[str, Dict[str, Any]]] = {
    # ----------------------------------------------------------------------------------
    # Category 1: Major Integrated Utilities
    # ----------------------------------------------------------------------------------
    "Essent Zakelijk (E.ON)": {
        "Vast 1 Jaar (Dubbeltarief)": {
            "category": SupplierCategory.MAJOR_UTILITY.value,
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 360.00,          # €30/mo
            "rate_peak_kwh": 0.1220,
            "rate_offpeak_kwh": 0.1080,
            "fixed_rate_kwh": 0.1150,
            "supplier_margin_kwh": 0.0080,
            "balancing_fee_kwh": 0.0018,
            "green_surcharge_kwh": 0.0035,
            "description": "Essent Zekerheidscontract met HT/NT uren en balansbeheer",
        },
        "Tranchen-Portfolio Essent": {
            "category": SupplierCategory.MAJOR_UTILITY.value,
            "pricing_mode": PricingMode.TRANCHE,
            "is_dual_rate": False,
            "base_fee_annual": 480.00,          # €40/mo
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0075,
            "balancing_fee_kwh": 0.0018,
            "green_surcharge_kwh": 0.0035,
            "description": "Gefaseerde kwartaalinkoop gekoppeld aan ICE Endex futures",
        },
    },
    "Vattenfall Zakelijk": {
        "Vast 1 Jaar (Dubbeltarief HT/NT)": {
            "category": SupplierCategory.MAJOR_UTILITY.value,
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 360.00,
            "rate_peak_kwh": 0.1240,
            "rate_offpeak_kwh": 0.1090,
            "fixed_rate_kwh": 0.1160,
            "supplier_margin_kwh": 0.0075,
            "balancing_fee_kwh": 0.0015,
            "green_surcharge_kwh": 0.0030,
            "description": "Fossil-free stroom met vaste prijszekerheid",
        },
        "Dynamisch EPEX Spot Zakelijk": {
            "category": SupplierCategory.MAJOR_UTILITY.value,
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 360.00,
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0075,
            "balancing_fee_kwh": 0.0015,
            "green_surcharge_kwh": 0.0030,
            "description": "EPEX Spot NL Day-Ahead inkoop met Vattenfall opslag",
        },
    },
    "Eneco Zakelijk": {
        "Klik-Contract (Eneco Portfolio)": {
            "category": SupplierCategory.MAJOR_UTILITY.value,
            "pricing_mode": PricingMode.TRANCHE,
            "is_dual_rate": False,
            "base_fee_annual": 420.00,          # €35/mo
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0080,
            "balancing_fee_kwh": 0.0016,
            "green_surcharge_kwh": 0.0040,
            "description": "Gestaffelde trancheninkoop gecombineerd met Hollandse Wind",
        },
        "Dynamisch Spot Zakelijk": {
            "category": SupplierCategory.MAJOR_UTILITY.value,
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 360.00,
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0080,
            "balancing_fee_kwh": 0.0016,
            "green_surcharge_kwh": 0.0040,
            "description": "EPEX Day-Ahead inkoop voor flexibele verbruikers",
        },
    },
    # ----------------------------------------------------------------------------------
    # Category 2: B2B Portfolio Specialists
    # ----------------------------------------------------------------------------------
    "Scholt Energy": {
        "Klik-Contract (Quartale Tranchen)": {
            "category": SupplierCategory.B2B_PORTFOLIO.value,
            "pricing_mode": PricingMode.TRANCHE,
            "is_dual_rate": False,
            "base_fee_annual": 600.00,          # €50/mo
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0065,
            "balancing_fee_kwh": 0.0014,
            "green_surcharge_kwh": 0.0025,
            "description": "Benelux marktleider voor klik-contracten en geautomatiseerde triggers",
        },
        "Scholt Dynamic + Flex Control": {
            "category": SupplierCategory.B2B_PORTFOLIO.value,
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 600.00,
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0060,
            "balancing_fee_kwh": 0.0012,
            "green_surcharge_kwh": 0.0025,
            "description": "Spotmarktinkoop met algoritmen voor BESS en load-shifting",
        },
    },
    "ENGIE Nederland": {
        "Industrial Tranche Portfolio": {
            "category": SupplierCategory.B2B_PORTFOLIO.value,
            "pricing_mode": PricingMode.TRANCHE,
            "is_dual_rate": False,
            "base_fee_annual": 600.00,
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0068,
            "balancing_fee_kwh": 0.0015,
            "green_surcharge_kwh": 0.0030,
            "description": "Grootzakelijke tranchen voor industrie, chemie en datacenters",
        },
    },
    "SEFE Energy": {
        "Structured Monthly Tranches": {
            "category": SupplierCategory.B2B_PORTFOLIO.value,
            "pricing_mode": PricingMode.TRANCHE,
            "is_dual_rate": False,
            "base_fee_annual": 540.00,          # €45/mo
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0070,
            "balancing_fee_kwh": 0.0016,
            "green_surcharge_kwh": 0.0025,
            "description": "OTC-terminmarktlevering en gestructureerde bandlevering",
        },
    },
    # ----------------------------------------------------------------------------------
    # Category 3: Pure Dynamic & Spot Providers
    # ----------------------------------------------------------------------------------
    "NieuweStroom": {
        "Pure EPEX Spot (Geen Risicopremie)": {
            "category": SupplierCategory.DYNAMIC_SPOT.value,
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 360.00,          # €30/mo
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0055,
            "balancing_fee_kwh": 0.0012,
            "green_surcharge_kwh": 0.0025,
            "description": "Pionier van dynamische B2B uurprijzen zonder ingebouwde risico-opslag",
        },
    },
    "Energyhouse": {
        "15-Minuten Spot Levering": {
            "category": SupplierCategory.DYNAMIC_SPOT.value,
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 360.00,
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0050,
            "balancing_fee_kwh": 0.0010,
            "green_surcharge_kwh": 0.0025,
            "description": "Softwarematige kwartierinkoop met minimale handlingmarge",
        },
    },
    "Tibber Zakelijk": {
        "Tibber Dynamic Spot": {
            "category": SupplierCategory.DYNAMIC_SPOT.value,
            "pricing_mode": PricingMode.DYNAMIC,
            "is_dual_rate": False,
            "base_fee_annual": 240.00,          # €20/mo
            "fixed_rate_kwh": 0.1100,
            "rate_peak_kwh": 0.1100,
            "rate_offpeak_kwh": 0.1100,
            "supplier_margin_kwh": 0.0045,
            "balancing_fee_kwh": 0.0010,
            "green_surcharge_kwh": 0.0020,
            "description": "Digitale spotmarktlevering voor commerciële vloten en laadpleinen",
        },
    },
    # ----------------------------------------------------------------------------------
    # Category 4: Green Sourcing Specialists
    # ----------------------------------------------------------------------------------
    "Greenchoice Zakelijk": {
        "100% Nederlandse Wind & Zon Vast": {
            "category": SupplierCategory.GREEN_SOURCING.value,
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 360.00,
            "rate_peak_kwh": 0.1260,
            "rate_offpeak_kwh": 0.1120,
            "fixed_rate_kwh": 0.1190,
            "supplier_margin_kwh": 0.0075,
            "balancing_fee_kwh": 0.0015,
            "green_surcharge_kwh": 0.0050,
            "description": "100% geverifieerde Nederlandse GvO's uit lokale projecten",
        },
    },
    "Audax Renewables": {
        "Audax Zakelijk Vast 1 Jaar": {
            "category": SupplierCategory.GREEN_SOURCING.value,
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 360.00,
            "rate_peak_kwh": 0.1250,
            "rate_offpeak_kwh": 0.1110,
            "fixed_rate_kwh": 0.1180,
            "supplier_margin_kwh": 0.0075,
            "balancing_fee_kwh": 0.0015,
            "green_surcharge_kwh": 0.0040,
            "description": "Vaste tarieven voor het MKB en vastgoedportefeuilles",
        },
    },
    # ----------------------------------------------------------------------------------
    # Additional: Shell Energy
    # ----------------------------------------------------------------------------------
    "Shell Energy": {
        "Direct Fixed 1-Year": {
            "category": SupplierCategory.MAJOR_UTILITY.value,
            "pricing_mode": PricingMode.FIXED,
            "is_dual_rate": True,
            "base_fee_annual": 360.00,
            "rate_peak_kwh": 0.1250,
            "rate_offpeak_kwh": 0.1100,
            "fixed_rate_kwh": 0.1170,
            "supplier_margin_kwh": 0.0075,
            "balancing_fee_kwh": 0.0015,
            "green_surcharge_kwh": 0.0030,
            "description": "Shell Energy zakelijke levering vast tarief",
        },
    },
}


# ======================================================================================
# 3. Transformer Station Rental Catalog
# ======================================================================================

TRAFO_RENTAL_CATALOG_2025: Dict[str, Dict[str, Dict[str, Any]]] = {
    "Fudura B.V.": {
        "Kompaktstation 400 bis 630 kVA": {
            "monthly_rental_fee": 354.00,
            "capex_equivalent": 65000.0,
            "description": "Betonstation 630 kVA, inkl. Wartung und Betreiberhaftung NEN 3840",
        },
        "Kompaktstation 1.000 kVA": {
            "monthly_rental_fee": 450.00,
            "capex_equivalent": 100000.0,
            "description": "1.000 kVA Öltransformator mit MS-Schaltanlage und NEN 3840",
        },
        "Industriestation 1.600 bis 2.000 kVA": {
            "monthly_rental_fee": 700.00,
            "capex_equivalent": 140000.0,
            "description": "Industriestation bis 2 MVA mit Vakuum-Schalter und Schutzprüfung",
        },
        "Großstation bis 5 MVA": {
            "monthly_rental_fee": 1750.00,
            "capex_equivalent": 300000.0,
            "description": "Doppel-Transformatorstation für Industriecluster",
        },
    },
    "Kenter B.V.": {
        "Kenter Trafostation 630 kVA": {
            "monthly_rental_fee": 354.00,
            "capex_equivalent": 65000.0,
            "description": "Fertigstation 630 kVA mit 24/7-Störungsdienst und Isolierölprüfung",
        },
        "Kenter Trafostation 1.000 kVA": {
            "monthly_rental_fee": 440.00,
            "capex_equivalent": 95000.0,
            "description": "1.000 kVA Station mit Lasttrennschalter und periodischer Wartung",
        },
    },
    "Joulz": {
        "Joulz Turnkey Station 630 kVA": {
            "monthly_rental_fee": 354.00,
            "capex_equivalent": 65000.0,
            "description": "Turnkey-Mietstation inkl. NEN 3840 Compliance",
        },
    },
    "None / Customer Owned": {
        "Customer Owned (CAPEX purchase)": {
            "monthly_rental_fee": 0.0,
            "capex_equivalent": 65000.0,
            "description": "Eigene Station des Kunden (0 €/Monat Mietgebühr, Eigenverantwortung)",
        },
    },
}


# ======================================================================================
# 4. Certified Metering EMV Catalog
# ======================================================================================

METERING_CATALOG_2025: Dict[str, Dict[str, Dict[str, Any]]] = {
    "Fudura B.V.": {
        "MS <= 1 MW Telemetrie": {
            "annual_flat_fee": 840.00,         # €70/mo
            "voltage_level": "MS",
            "description": "Grootverbruik MS kwartierdata telemetrie (RLM) und Datenportal",
        },
        "LS Telemetrie Wandlermessung": {
            "annual_flat_fee": 600.00,         # €50/mo
            "voltage_level": "LS",
            "description": "Grootverbruik Niederspannung Wandlermessung (> 3x80A bis 100 kW)",
        },
        "MS <= 2 MW Telemetrie": {
            "annual_flat_fee": 1020.00,        # €85/mo
            "voltage_level": "MS",
            "description": "MS Wandlersatz bis 2.000 kVA mit täglicher Validierung",
        },
    },
    "Kenter B.V.": {
        "Kenter MS RLM Telemetrie": {
            "annual_flat_fee": 840.00,
            "voltage_level": "MS",
            "description": "Kwartierdata uitlezing en online energiemonitoring portaal",
        },
        "Kenter LS Grootverbruik": {
            "annual_flat_fee": 600.00,
            "voltage_level": "LS",
            "description": "Standard Großverbrauchsmessung Niederspannung",
        },
    },
    "Joulz Meetbedrijf": {
        "Joulz MS Telemetrie": {
            "annual_flat_fee": 840.00,
            "voltage_level": "MS",
            "description": "Erkend meetverantwoordelijke kwartierdata grootverbruik",
        },
    },
}


# ======================================================================================
# 5. Helper Factory Functions
# ======================================================================================

def get_dso_tariff_from_catalog(
    dso_company: str = "Liander N.V.",
    tier_name: str = "AC5a: MS eigene Station (> 136 bis 536 kW)",
    contracted_capacity_kw: float = 536.0,
    cable_surcharge_annual: float = 0.0,
    ratchet_12_months: bool = True
) -> DSOTariff:
    """Instantiates a DSOTariff model from catalog."""
    company_data = DSO_CATALOGS_2025.get(dso_company, LIANDER_2025_GRID_TIERS)
    tier = company_data.get(tier_name, list(company_data.values())[0])

    return DSOTariff(
        dso_name=dso_company,
        grid_tier=tier_name,
        connection_category=tier.get("ac_code", "AC5a"),
        fixed_connection_annual=float(tier.get("aansluitdienst_annual", 1013.88)),
        fixed_transport_annual=float(tier.get("vastrecht_annual", 441.00)),
        cable_surcharge_annual=float(cable_surcharge_annual),
        contracted_capacity_kw=float(contracted_capacity_kw),
        rate_contracted_capacity=float(tier.get("rate_contracted_monthly", 2.2233)),
        rate_peak_demand=float(tier.get("rate_peak_monthly", 3.4600)),
        rate_transport_peak_kwh=float(tier.get("rate_peak_kwh", 0.0220)),
        rate_transport_offpeak_kwh=float(tier.get("rate_offpeak_kwh", 0.0220)),
        adjust_capacity_on_breach=True,
        ratchet_12_months=ratchet_12_months,
        max_physical_limit_kw=float(tier.get("max_physical_limit_kw", 1000.0)),
        peak_penalty_rate_kw=0.2500,
        reactive_power_tariff=0.0188,
        min_power_factor=0.85,
        reactive_allowance_pct=33.0
    )


def get_supplier_tariff_from_catalog(
    supplier_name: str = "Scholt Energy",
    product_name: str = "Klik-Contract (Quartale Tranchen)",
    pricing_mode: Optional[PricingMode] = None
) -> SupplierTariff:
    """Instantiates a SupplierTariff model from catalog."""
    company_products = SUPPLIER_CATALOG_2025.get(supplier_name, SUPPLIER_CATALOG_2025["Scholt Energy"])
    prod = company_products.get(product_name, list(company_products.values())[0])

    mode = pricing_mode or prod.get("pricing_mode", PricingMode.TRANCHE)
    return SupplierTariff(
        supplier_name=supplier_name,
        supplier_category=prod.get("category", SupplierCategory.B2B_PORTFOLIO.value),
        pricing_mode=mode,
        tariff_product_name=product_name,
        base_fee_annual=float(prod.get("base_fee_annual", 600.00)),
        fixed_rate_kwh=float(prod.get("fixed_rate_kwh", 0.1100)),
        is_dual_rate=bool(prod.get("is_dual_rate", False)),
        fixed_rate_peak_kwh=float(prod.get("rate_peak_kwh", 0.1180)),
        fixed_rate_offpeak_kwh=float(prod.get("rate_offpeak_kwh", 0.1040)),
        supplier_margin_kwh=float(prod.get("supplier_margin_kwh", 0.0065)),
        balancing_fee_kwh=float(prod.get("balancing_fee_kwh", 0.0014)),
        green_certificate_surcharge_kwh=float(prod.get("green_surcharge_kwh", 0.0)),
        procurement_fee_kwh=0.0,
        monthly_variable_rates=prod.get("monthly_variable_rates", [0.110] * 12),
        market_price_profile_id="epex_nl_2025",
        spot_default_fallback_rate=0.1100
    )


def get_trafo_tariff_from_catalog(
    provider_name: str = "Fudura B.V.",
    station_type: str = "Kompaktstation 400 bis 630 kVA",
    is_rented: bool = True
) -> TrafoRentalTariff:
    """Instantiates a TrafoRentalTariff model from catalog."""
    prov_dict = TRAFO_RENTAL_CATALOG_2025.get(provider_name, TRAFO_RENTAL_CATALOG_2025["Fudura B.V."])
    pkg = prov_dict.get(station_type, list(prov_dict.values())[0])

    return TrafoRentalTariff(
        provider_name=provider_name,
        station_type=station_type,
        is_rented=is_rented,
        monthly_rental_fee=float(pkg.get("monthly_rental_fee", 354.00)),
        capex_equivalent=float(pkg.get("capex_equivalent", 65000.0)),
        includes_nen3840=True,
        description=str(pkg.get("description", ""))
    )


def get_metering_tariff_from_catalog(
    meter_company_name: str = "Fudura B.V.",
    package_name: str = "MS <= 1 MW Telemetrie"
) -> MeteringTariff:
    """Instantiates a MeteringTariff model from catalog."""
    company_packages = METERING_CATALOG_2025.get(meter_company_name, METERING_CATALOG_2025["Fudura B.V."])
    pkg = company_packages.get(package_name, list(company_packages.values())[0])

    return MeteringTariff(
        meter_company_name=meter_company_name,
        service_package_name=package_name,
        annual_flat_fee=float(pkg.get("annual_flat_fee", 840.00)),
        voltage_level=str(pkg.get("voltage_level", "MS")),
        description=str(pkg.get("description", ""))
    )


def get_default_levy_config(tax_year: int = 2026, has_verblijfsfunctie: bool = True) -> LevyConfig:
    """Instantiates LevyConfig with statutory brackets and rebate."""
    brackets = TAX_SCHEDULE_2026 if tax_year == 2026 else TAX_SCHEDULE_2025
    rebate = VERMINDERING_2026 if tax_year == 2026 else VERMINDERING_2025

    return LevyConfig(
        tax_year=tax_year,
        use_tiered_energy_tax=True,
        has_verblijfsfunctie=has_verblijfsfunctie,
        annual_tax_reduction=rebate,
        vat_rate_pct=21.0,
        statutory_levy_rate_kwh=0.03735 if tax_year == 2026 else 0.03868,
        tax_brackets=list(brackets)
    )
