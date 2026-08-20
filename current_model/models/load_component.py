"""
========================================================================================
Load Component Model & Time Window Definition (current_model/models/load_component.py)
========================================================================================

Description:
------------
Defines the fundamental building blocks of electrical load simulation:
  - `TimeWindow`: Encapsulates an operating time interval, startup peak power, and duration.
  - `LoadComponent` / `SimpleConsumer`: Represents an individual physical asset (machine,
    HVAC system, EV charger, etc.), supporting multi-window operations, weekly schedule
    filtering (Monday to Sunday), seasonal variations, scaling counts, and 15-minute
    discretization arrays (96 steps/day and 35,040 steps/year).

Discretization Logic:
---------------------
A 24-hour day is divided into 96 fifteen-minute slots:
  - Slot 0:  00:00 - 00:15
  - Slot 1:  00:15 - 00:30
  - ...
  - Slot 95: 23:45 - 24:00
"""

import datetime
import uuid
from typing import List, Optional, Dict, Any
import numpy as np


class TimeWindow:
    """
    Represents an operating time window for an electrical load component.

    Attributes:
        start_time (datetime.time): Time when the component turns on.
        end_time (datetime.time): Time when the component turns off.
        has_peak (bool): Whether this window experiences a startup or peak power spike.
        peak_power_kw (float): Peak power level in kW (defaults to nominal if not specified).
        peak_duration_min (int): Duration of the peak spike in minutes (15, 30, 45, 60).
    """

    def __init__(
        self,
        start_time: datetime.time = datetime.time(8, 0),
        end_time: datetime.time = datetime.time(16, 0),
        has_peak: bool = False,
        peak_power_kw: float = 0.0,
        peak_duration_min: int = 30
    ):
        self.start_time = start_time
        self.end_time = end_time
        self.has_peak = bool(has_peak)
        self.peak_power_kw = float(peak_power_kw)
        self.peak_duration_min = int(peak_duration_min)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the TimeWindow instance to a dictionary for JSON/State storage."""
        return {
            "start_time": self.start_time.strftime("%H:%M"),
            "end_time": self.end_time.strftime("%H:%M"),
            "has_peak": self.has_peak,
            "peak_power_kw": self.peak_power_kw,
            "peak_duration_min": self.peak_duration_min
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeWindow":
        """Deserializes a dictionary back into a TimeWindow object."""
        start_parts = [int(x) for x in data["start_time"].split(":")]
        end_parts = [int(x) for x in data["end_time"].split(":")]
        return cls(
            start_time=datetime.time(start_parts[0], start_parts[1]),
            end_time=datetime.time(end_parts[0], end_parts[1]),
            has_peak=data.get("has_peak", False),
            peak_power_kw=data.get("peak_power_kw", 0.0),
            peak_duration_min=data.get("peak_duration_min", 30)
        )


class SimpleConsumer:
    """
    Represents an electrical consumer load supporting multiple 24-hour time windows,
    individual weekday schedules (Monday..Sunday), and seasonal variation.
    Fully compatible with Streamlit session state, 96-slot daily arrays, and 365-day annual arrays.
    """

    def __init__(
        self,
        name: str,
        power_kw: float,
        time_windows: Optional[List[TimeWindow]] = None,
        category: str = "General",
        count: int = 1,
        active_days: Optional[List[int]] = None,
        seasonal_pattern: str = "flat",
        monthly_factors: Optional[List[float]] = None,
        id: Optional[str] = None
    ):
        self.id = id if id else str(uuid.uuid4())[:8]
        self.name = name
        self.power_kw = max(0.0, float(power_kw))
        self.nominal_power_kw = self.power_kw
        self.category = category
        self.count = max(1, int(count))
        self.time_windows = time_windows if time_windows is not None else []
        self.is_active = True

        # Weekdays: 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday
        # Default: Monday to Friday [0, 1, 2, 3, 4]
        self.active_days = active_days if active_days is not None else [0, 1, 2, 3, 4]

        # Seasonal variation: 'flat', 'winter_heavy', 'summer_heavy', 'custom'
        self.seasonal_pattern = seasonal_pattern if seasonal_pattern in ["flat", "winter_heavy", "summer_heavy", "custom"] else "flat"
        self.monthly_factors = monthly_factors if monthly_factors and len(monthly_factors) == 12 else [1.0] * 12

    def get_seasonal_factor(self, month: int) -> float:
        """Returns the monthly scaling factor (1=Jan .. 12=Dec)."""
        m_idx = max(0, min(11, month - 1))
        if self.seasonal_pattern == "winter_heavy":
            # Higher in Nov, Dec, Jan, Feb (+25%), lower in Summer (-15%)
            factors = [1.25, 1.20, 1.10, 1.00, 0.90, 0.85, 0.85, 0.85, 0.90, 1.05, 1.20, 1.25]
            return factors[m_idx]
        elif self.seasonal_pattern == "summer_heavy":
            # Higher in Jun, Jul, Aug (+30%), lower in Winter (-20%)
            factors = [0.80, 0.80, 0.85, 0.95, 1.15, 1.30, 1.30, 1.30, 1.10, 0.95, 0.80, 0.80]
            return factors[m_idx]
        elif self.seasonal_pattern == "custom":
            return self.monthly_factors[m_idx]
        return 1.0

    def get_24h_array(self) -> np.ndarray:
        """
        Computes a 96-element array of power (kW) for 15-minute intervals across all windows.
        Includes overnight shifts and startup peak calculations.
        """
        curve = np.zeros(96, dtype=float)
        if not self.is_active or not self.time_windows:
            return curve

        for window in self.time_windows:
            start_m = window.start_time.hour * 60 + window.start_time.minute
            end_m = window.end_time.hour * 60 + window.end_time.minute
            is_24h = (start_m == 0 and end_m == 0 and window.start_time == window.end_time)

            for step in range(96):
                slot_start = step * 15
                active = False

                if is_24h:
                    active = True
                elif start_m < end_m:
                    if start_m <= slot_start < end_m:
                        active = True
                elif start_m > end_m:
                    if slot_start >= start_m or slot_start < end_m:
                        active = True

                if active:
                    val = self.power_kw
                    if window.has_peak and window.peak_power_kw > self.power_kw:
                        peak_dur = window.peak_duration_min
                        if start_m < end_m:
                            if slot_start < (start_m + peak_dur):
                                val = window.peak_power_kw
                        else:
                            if slot_start >= start_m and slot_start < (start_m + peak_dur):
                                val = window.peak_power_kw
                            elif slot_start < end_m and (slot_start + 1440) < (start_m + peak_dur):
                                val = window.peak_power_kw
                    curve[step] = max(curve[step], val * self.count)

        return curve

    def get_daily_array_for_weekday(self, day_of_week: int = 0, month: int = 1) -> np.ndarray:
        """
        Calculates the 96-slot array for a specific day of week (0=Mon .. 6=Sun) and month (1..12).
        If the day of week is not in active_days, returns an all-zero array.
        """
        if not self.is_active or day_of_week not in self.active_days:
            return np.zeros(96, dtype=float)

        base_curve = self.get_24h_array()
        season_factor = self.get_seasonal_factor(month)
        if season_factor != 1.0:
            return base_curve * season_factor
        return base_curve

    def get_daily_array_15min(self, day_of_week: int = 0) -> np.ndarray:
        """Alias for compatibility with multi-day aggregators."""
        return self.get_daily_array_for_weekday(day_of_week=day_of_week, month=1)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the Consumer to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "power_kw": self.power_kw,
            "category": self.category,
            "count": self.count,
            "time_windows": [w.to_dict() for w in self.time_windows],
            "active_days": self.active_days,
            "seasonal_pattern": self.seasonal_pattern,
            "monthly_factors": self.monthly_factors,
            "is_active": self.is_active
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimpleConsumer":
        """Reconstructs a SimpleConsumer from a dictionary with backward compatibility."""
        windows = [TimeWindow.from_dict(w) for w in data.get("time_windows", [])]
        return cls(
            id=data.get("id"),
            name=data.get("name", "Consumer"),
            power_kw=data.get("power_kw", data.get("nominal_power_kw", 10.0)),
            category=data.get("category", "General"),
            count=data.get("count", 1),
            active_days=data.get("active_days", [0, 1, 2, 3, 4]),
            seasonal_pattern=data.get("seasonal_pattern", "flat"),
            monthly_factors=data.get("monthly_factors", [1.0] * 12),
            time_windows=windows
        )


# Aliases for unified naming
LoadComponent = SimpleConsumer
Consumer = SimpleConsumer
