"""
========================================================================================
Load Profile Presets & Factory Configuration (current_model/models/presets.py)
========================================================================================

Description:
------------
Provides pre-configured industry presets representing typical commercial,
industrial, and mobility load profiles.
"""

import datetime
from typing import List, Dict, Any, Callable
from current_model.models.load_component import SimpleConsumer, TimeWindow


def get_industry_preset_consumers() -> List[SimpleConsumer]:
    """Generates standard industrial manufacturing consumer profile."""
    return [
        SimpleConsumer(
            name="Machine 1 (Main Production)",
            power_kw=100.0,
            category="Production",
            time_windows=[
                TimeWindow(
                    start_time=datetime.time(5, 0),
                    end_time=datetime.time(14, 0),
                    has_peak=True,
                    peak_power_kw=130.0,
                    peak_duration_min=30
                )
            ]
        ),
        SimpleConsumer(
            name="Machine 2 (CNC Machining)",
            power_kw=20.0,
            category="Production",
            time_windows=[
                TimeWindow(start_time=datetime.time(2, 0), end_time=datetime.time(13, 0)),
                TimeWindow(start_time=datetime.time(14, 0), end_time=datetime.time(17, 0))
            ]
        ),
        SimpleConsumer(
            name="Air Compressor Station",
            power_kw=30.0,
            category="Production Support",
            time_windows=[
                TimeWindow(start_time=datetime.time(6, 0), end_time=datetime.time(18, 0))
            ]
        ),
        SimpleConsumer(
            name="Lighting & Facility Ventilation",
            power_kw=8.0,
            category="Facility",
            time_windows=[
                TimeWindow(start_time=datetime.time(5, 0), end_time=datetime.time(22, 0))
            ]
        )
    ]


def get_office_preset_consumers() -> List[SimpleConsumer]:
    """Generates typical commercial office building consumer profile."""
    return [
        SimpleConsumer(
            name="IT Server & Network Infrastructure",
            power_kw=15.0,
            category="IT Infrastructure",
            time_windows=[
                TimeWindow(start_time=datetime.time(0, 0), end_time=datetime.time(0, 0))
            ]
        ),
        SimpleConsumer(
            name="Workstations & Office Lighting",
            power_kw=45.0,
            category="Workspaces",
            time_windows=[
                TimeWindow(start_time=datetime.time(7, 30), end_time=datetime.time(17, 30))
            ]
        ),
        SimpleConsumer(
            name="HVAC & Climate Control",
            power_kw=25.0,
            category="HVAC",
            time_windows=[
                TimeWindow(
                    start_time=datetime.time(8, 0),
                    end_time=datetime.time(18, 0),
                    has_peak=True,
                    peak_power_kw=35.0,
                    peak_duration_min=45
                )
            ]
        )
    ]


def get_ev_hub_preset_consumers() -> List[SimpleConsumer]:
    """Generates mobility and EV charging station profile."""
    return [
        SimpleConsumer(
            name="DC Fast Charger (150 kW)",
            power_kw=150.0,
            category="EV Charging",
            time_windows=[
                TimeWindow(start_time=datetime.time(7, 0), end_time=datetime.time(9, 30)),
                TimeWindow(start_time=datetime.time(16, 30), end_time=datetime.time(19, 30))
            ]
        ),
        SimpleConsumer(
            name="AC Wallbox Charging Array (6x11kW)",
            power_kw=66.0,
            category="EV Charging",
            time_windows=[
                TimeWindow(start_time=datetime.time(8, 0), end_time=datetime.time(17, 0))
            ]
        )
    ]


def get_preset_factory(key: str) -> Callable[[], List[SimpleConsumer]]:
    """Safe lookup for preset factory with alias and partial match support."""
    if key in PRESET_FACTORIES:
        return PRESET_FACTORIES[key]
    key_clean = key.lower().strip()
    if "manufactur" in key_clean or "industr" in key_clean:
        return get_industry_preset_consumers
    if "office" in key_clean or "commercial" in key_clean:
        return get_office_preset_consumers
    if "ev" in key_clean or "mobility" in key_clean or "charg" in key_clean:
        return get_ev_hub_preset_consumers
    return get_industry_preset_consumers


PRESET_TEMPLATES: Dict[str, Callable[[], List[SimpleConsumer]]] = {
    "🏭 Industry & Manufacturing": get_industry_preset_consumers,
    "🏢 Commercial Office Building": get_office_preset_consumers,
    "⚡ Mobility & EV Hub": get_ev_hub_preset_consumers,
}

PRESET_FACTORIES: Dict[str, Any] = {
    **PRESET_TEMPLATES,
    # Standard alias keys for programmatic access
    "manufacturing": get_industry_preset_consumers,
    "industry": get_industry_preset_consumers,
    "office": get_office_preset_consumers,
    "ev_hub": get_ev_hub_preset_consumers,
}


