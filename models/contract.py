from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional
import datetime


@dataclass
class Contract:
    currency: str = "EUR"
    base_monthly_fee: float = 50.0

    contracted_capacity_kw: float = 400.0          # Guaranteed capacity (kW)
    monthly_capacity_tariff: float = 0.15          # Tariff for contracted capacity (€/kW/month)
    max_physical_limit_kw: float = 1000.0          # Absolute physical limit (kW)
    peak_penalty_rate: float = 0.25                # Penalty rate for exceeding contracted capacity (€/kW)

    # Simple Time-of-Use (TOU) Energy Rates (€/kWh)
    default_energy_rate: float = 0.20              # Fallback/standard rate (€/kWh)
    peak_energy_rate: float = 0.30                 # Peak rate (€/kWh)
    off_peak_energy_rate: float = 0.15             # Off-peak rate (€/kWh)
    
    # Peak hours definition as (start_hour, end_hour) - e.g. (8, 20) means 08:00 to 20:00
    peak_hours: Tuple[int, int] = (8, 20)
    weekend_is_off_peak: bool = True

    def get_energy_rate(self, dt_or_hour) -> float:
        """
        Returns the energy price (€/kWh) for a given hour (int) or datetime object.
        """
        if isinstance(dt_or_hour, (datetime.datetime, datetime.time)):
            if isinstance(dt_or_hour, datetime.datetime):
                if self.weekend_is_off_peak and dt_or_hour.weekday() >= 5:
                    return self.off_peak_energy_rate
            hour = dt_or_hour.hour
        else:
            hour = int(dt_or_hour)

        start_h, end_h = self.peak_hours
        if start_h <= end_h:
            is_peak = (start_h <= hour < end_h)
        else:
            is_peak = (hour >= start_h or hour < end_h)

        return self.peak_energy_rate if is_peak else self.off_peak_energy_rate

    


