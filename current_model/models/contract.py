"""
========================================================================================
Electricity Supply Contract & Tariff Model (current_model/models/contract.py)
========================================================================================

Description:
------------
Defines the `Contract` dataclass encapsulating all billing, capacity limits,
dynamic Time-of-Use (TOU) energy rates, reactive power penalties, and custom tax structures.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional
import datetime


@dataclass
class Contract:
    """
    Represents an electricity supply contract with dynamic Time-of-Use (TOU) rate windows,
    capacity tariffs, reactive energy thresholds, and taxes.
    """
    currency: str = "EUR"
    base_monthly_fee: float = 50.0

    # Active Power & Capacity Parameters
    contracted_capacity_kw: float = 400.0          # Contracted active capacity limit (kW)
    monthly_capacity_tariff: float = 0.15          # Capacity charge (€/kW/month)
    max_physical_limit_kw: float = 1000.0          # Absolute physical grid fuse limit (kW)
    peak_penalty_rate: float = 0.25                # Penalty rate for exceeding contracted capacity (€/kW)

    # Reactive Power Parameters
    reactive_power_tariff: float = 0.03            # Tariff for excess reactive energy (€/kVARh)
    min_power_factor: float = 0.90                 # Minimum allowed power factor (cos phi)
    reactive_power_allowance_pct: float = 33.0     # Free reactive allowance as % of active kWh

    # Dynamic Time-of-Use (TOU) Energy Rates Table
    # By default: 1 standard entry covering 24 hours
    tou_rates: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "Standard Rate", "rate": 0.20, "start_time": "00:00", "end_time": "24:00"}
    ])
    default_energy_rate: float = 0.20              # Fallback rate (€/kWh)
    weekend_is_off_peak: bool = False

    # Taxes & Additional Fees (Dynamic Table)
    taxes_and_fees: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "VAT", "type": "percentage", "value": 20.0, "description": "Standard Value Added Tax"}
    ])

    def _parse_time_to_minutes(self, t_val: Any) -> int:
        """Helper to convert time string, int hour, or datetime.time to minutes of day [0, 1440]."""
        if isinstance(t_val, (datetime.time, datetime.datetime)):
            return t_val.hour * 60 + t_val.minute
        s = str(t_val).strip()
        if ":" in s:
            parts = s.split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return h * 60 + m
        try:
            return int(float(s)) * 60
        except ValueError:
            return 0

    def get_energy_rate(self, dt_or_hour: Any) -> float:
        """
        Returns the active energy price (€/kWh) for a given hour (int), time, or datetime object
        by matching against the configured dynamic TOU rate windows.
        """
        if isinstance(dt_or_hour, datetime.datetime):
            if self.weekend_is_off_peak and dt_or_hour.weekday() >= 5:
                # Return minimum available rate for weekend off-peak
                rates = [float(r.get("rate", self.default_energy_rate)) for r in self.tou_rates if "rate" in r]
                return min(rates) if rates else self.default_energy_rate
            current_m = dt_or_hour.hour * 60 + dt_or_hour.minute
        elif isinstance(dt_or_hour, datetime.time):
            current_m = dt_or_hour.hour * 60 + dt_or_hour.minute
        else:
            try:
                current_m = int(dt_or_hour) * 60
            except (ValueError, TypeError):
                current_m = 0

        if not self.tou_rates:
            return self.default_energy_rate

        # Iterate through dynamic TOU windows (last matching or first matching)
        for tou in self.tou_rates:
            start_m = self._parse_time_to_minutes(tou.get("start_time", "00:00"))
            end_m = self._parse_time_to_minutes(tou.get("end_time", "24:00"))
            rate = float(tou.get("rate", self.default_energy_rate))

            # Full 24-hour window
            if (start_m == 0 and end_m >= 1440) or (start_m == 0 and end_m == 0 and len(self.tou_rates) == 1):
                return rate

            # Standard window (e.g. 08:00 to 20:00 -> 480 to 1200)
            if start_m < end_m:
                if start_m <= current_m < end_m:
                    return rate
            # Overnight window (e.g. 22:00 to 06:00 -> 1320 to 360)
            elif start_m > end_m:
                if current_m >= start_m or current_m < end_m:
                    return rate

        # Fallback to default or first rate
        return float(self.tou_rates[0].get("rate", self.default_energy_rate))
