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
    filtering, scaling counts, startup peaks, and 15-minute discretization arrays (96 steps/day).

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
    Represents an electrical consumer load supporting multiple 24-hour time windows.
    Fully compatible with Streamlit session state and 96-slot 15-minute daily arrays.
    """

    def __init__(
        self,
        name: str,
        power_kw: float,
        time_windows: Optional[List[TimeWindow]] = None,
        category: str = "General",
        count: int = 1,
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

    def get_daily_array_15min(self, day_of_week: int = 0) -> np.ndarray:
        """Alias for get_24h_array for compatibility with multi-day aggregators."""
        return self.get_24h_array()

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the Consumer to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "power_kw": self.power_kw,
            "category": self.category,
            "count": self.count,
            "time_windows": [w.to_dict() for w in self.time_windows],
            "is_active": self.is_active
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimpleConsumer":
        """Reconstructs a SimpleConsumer from a dictionary."""
        windows = [TimeWindow.from_dict(w) for w in data.get("time_windows", [])]
        return cls(
            id=data.get("id"),
            name=data.get("name", "Consumer"),
            power_kw=data.get("power_kw", data.get("nominal_power_kw", 10.0)),
            category=data.get("category", "General"),
            count=data.get("count", 1),
            time_windows=windows
        )


# Aliases for unified naming
LoadComponent = SimpleConsumer
Consumer = SimpleConsumer
