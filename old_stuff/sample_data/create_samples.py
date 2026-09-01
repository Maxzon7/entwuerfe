import os
import json
import zipfile
import sys

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from current_model.models.contract import Contract
from current_model.models.load_component import SimpleConsumer, TimeWindow, consumers_to_drac
import datetime

os.makedirs("sample_data/contracts", exist_ok=True)
os.makedirs("sample_data/profiles", exist_ok=True)

# 1. Five diverse contracts
contracts = [
    Contract(
        name="1. Standard Gewerbe (HT/NT)",
        currency="EUR",
        base_monthly_fee=65.0,
        contracted_capacity_kw=250.0,
        monthly_capacity_tariff=12.50,
        demand_capacity_tariff=0.0,
        max_physical_limit_kw=400.0,
        peak_penalty_rate=20.0,
        reactive_power_tariff=0.03,
        min_power_factor=0.90,
        reactive_power_allowance_pct=33.0,
        tou_rates=[
            {"name": "Hochtarif (HT)", "rate": 0.2850, "start_time": "06:00", "end_time": "22:00"},
            {"name": "Niedertarif (NT)", "rate": 0.1780, "start_time": "22:00", "end_time": "06:00"}
        ],
        default_energy_rate=0.2850,
        weekend_is_off_peak=True,
        taxes_and_fees=[
            {"name": "Stromsteuer", "type": "per_kwh", "value": 0.0205, "description": "Gesetzliche Stromsteuer"},
            {"name": "Umsatzsteuer (MwSt)", "type": "percentage", "value": 19.0, "description": "19% MwSt"}
        ]
    ),
    Contract(
        name="2. KMU Flattarif 24/7",
        currency="EUR",
        base_monthly_fee=45.0,
        contracted_capacity_kw=150.0,
        monthly_capacity_tariff=8.00,
        demand_capacity_tariff=0.0,
        max_physical_limit_kw=250.0,
        peak_penalty_rate=15.0,
        tou_rates=[
            {"name": "Flattarif 24/7", "rate": 0.2280, "start_time": "00:00", "end_time": "24:00"}
        ],
        default_energy_rate=0.2280,
        weekend_is_off_peak=False,
        taxes_and_fees=[
            {"name": "MwSt", "type": "percentage", "value": 19.0, "description": "Mehrwertsteuer"}
        ]
    ),
    Contract(
        name="3. Industrie 3-Stufen Tarif",
        currency="EUR",
        base_monthly_fee=120.0,
        contracted_capacity_kw=600.0,
        monthly_capacity_tariff=16.50,
        demand_capacity_tariff=2.50,
        max_physical_limit_kw=1000.0,
        peak_penalty_rate=35.0,
        tou_rates=[
            {"name": "Spitzenlast (Peak)", "rate": 0.3650, "start_time": "08:00", "end_time": "12:00"},
            {"name": "Tageslast (Standard)", "rate": 0.2450, "start_time": "12:00", "end_time": "20:00"},
            {"name": "Schwachlast (Night)", "rate": 0.1490, "start_time": "20:00", "end_time": "08:00"}
        ],
        default_energy_rate=0.2450,
        weekend_is_off_peak=True,
        taxes_and_fees=[
            {"name": "Konzessionsabgabe", "type": "per_kwh", "value": 0.0150, "description": "Kommunale Abgabe"},
            {"name": "MwSt", "type": "percentage", "value": 19.0, "description": "19% MwSt"}
        ]
    ),
    Contract(
        name="4. Dynamischer Grünstrom Eco",
        currency="EUR",
        base_monthly_fee=50.0,
        contracted_capacity_kw=200.0,
        monthly_capacity_tariff=9.50,
        tou_rates=[
            {"name": "Solar-Mittagsbonus", "rate": 0.1150, "start_time": "11:00", "end_time": "16:00"},
            {"name": "Abendspitze", "rate": 0.3200, "start_time": "17:00", "end_time": "21:00"},
            {"name": "Basiszeit", "rate": 0.2050, "start_time": "00:00", "end_time": "11:00"}
        ],
        default_energy_rate=0.2050,
        weekend_is_off_peak=True,
        taxes_and_fees=[
            {"name": "Ökostrom-Zertifikate", "type": "percentage", "value": 3.5, "description": "Herkunftsnachweise"},
            {"name": "MwSt", "type": "percentage", "value": 19.0, "description": "19% MwSt"}
        ]
    ),
    Contract(
        name="5. Großverbraucher Hochspannung (USD)",
        currency="USD",
        base_monthly_fee=250.0,
        contracted_capacity_kw=1200.0,
        monthly_capacity_tariff=18.00,
        demand_capacity_tariff=4.00,
        max_physical_limit_kw=2000.0,
        peak_penalty_rate=45.0,
        tou_rates=[
            {"name": "On-Peak Day", "rate": 0.1850, "start_time": "09:00", "end_time": "19:00"},
            {"name": "Off-Peak Night", "rate": 0.0980, "start_time": "19:00", "end_time": "09:00"}
        ],
        default_energy_rate=0.1850,
        weekend_is_off_peak=True,
        taxes_and_fees=[
            {"name": "State Energy Surcharge", "type": "percentage", "value": 6.5, "description": "State Grid Fee"}
        ]
    )
]

# Write individual contract files
contract_filenames = [
    "sample_data/contracts/1_Standard_Gewerbe_HT_NT.drac",
    "sample_data/contracts/2_KMU_Flattarif.drac",
    "sample_data/contracts/3_Industrie_3_Stufen.drac",
    "sample_data/contracts/4_Gruenstrom_Eco_Dynamisch.drac",
    "sample_data/contracts/5_Grossverbraucher_USD.drac"
]

for c, fname in zip(contracts, contract_filenames):
    with open(fname, "w", encoding="utf-8") as f:
        f.write(c.to_json(indent=2))

# Create a single ZIP containing all 5 contracts
zip_path = "sample_data/contracts/Mustervertraege_Paket.zip"
with zipfile.ZipFile(zip_path, "w") as z:
    for fname in contract_filenames:
        z.write(fname, arcname=os.path.basename(fname))

# 2. Also create 2 sample .drac load profiles
prof1 = [
    SimpleConsumer(
        name="Produktionslinie A",
        power_kw=120.0,
        time_windows=[TimeWindow(start_time=datetime.time(6, 0), end_time=datetime.time(18, 0))],
        category="Machinery",
        count=1
    ),
    SimpleConsumer(
        name="Büro & Beleuchtung",
        power_kw=18.0,
        time_windows=[TimeWindow(start_time=datetime.time(7, 30), end_time=datetime.time(19, 0))],
        category="Lighting",
        count=1
    )
]

prof2 = [
    SimpleConsumer(
        name="Kühlanlage Gewerbe",
        power_kw=45.0,
        time_windows=[TimeWindow(start_time=datetime.time(0, 0), end_time=datetime.time(23, 59))],
        category="Cooling",
        count=2
    ),
    SimpleConsumer(
        name="EV Ladesäulen Fuhrpark",
        power_kw=22.0,
        time_windows=[TimeWindow(start_time=datetime.time(8, 0), end_time=datetime.time(16, 0))],
        category="EV Charging",
        count=4
    )
]

with open("sample_data/profiles/Profil_Produktion_Gewerbe.drac", "w", encoding="utf-8") as f:
    f.write(consumers_to_drac(prof1, profile_name="Produktion & Büro"))

with open("sample_data/profiles/Profil_Kuehlung_EV_Hub.drac", "w", encoding="utf-8") as f:
    f.write(consumers_to_drac(prof2, profile_name="Gewerbekühlung + EV"))

print("Sample files created successfully!")
