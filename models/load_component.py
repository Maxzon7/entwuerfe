"""
========================================================================================
Load Component Model & Time Window Definition (models/load_component.py)
========================================================================================

Description:
------------
Defines the fundamental building blocks of electrical load simulation:
  - `TimeWindow`: Encapsulates an operating time interval, startup peak power, and duration.
  - `LoadComponent`: Represents an individual physical asset (machine, HVAC system, EV charger, etc.),
    supporting multi-window operations, weekly schedule filtering, scaling counts, and 15-minute
    discretization arrays (96 steps/day).

Discretization Logic:
---------------------
A 24-hour day is divided into 96 fifteen-minute slots:
  - Slot 0:  00:00 - 00:15
  - Slot 1:  00:15 - 00:30
  - ...
  - Slot 95: 23:45 - 24:00

Special Handling:
-----------------
1. Overnight shifts (e.g., 22:00 -> 06:00) where start_time > end_time.
2. Continuous 24/7 operations (00:00 -> 00:00 / 24:00).
3. Temporary inrush startup peaks (e.g., initial 30 min at higher kW before settling to nominal).
4. Machine scaling (multiplier count: e.g., 6 charging stations with identical profiles).
"""

import datetime
import uuid
from typing import List, Optional, Dict, Any
import numpy as np
import pandas as pd


class TimeWindow:
    """
    Represents an operating time window for an electrical load component.

    Attributes:
        start_time (datetime.time): Time when the component turns on.
        end_time (datetime.time): Time when the component turns off.
        has_peak (bool): Whether this window experiences a startup or peak power spike.
        peak_power_kw (Optional[float]): Peak power level in kW (must be >= nominal).
        peak_duration_min (int): Duration of the peak spike in minutes (e.g., 15, 30, 45, 60).
    """

    def __init__(
        self,
        start_time: datetime.time = datetime.time(8, 0),
        end_time: datetime.time = datetime.time(16, 0),
        has_peak: bool = False,
        peak_power_kw: Optional[float] = None,
        peak_duration_min: int = 30
    ):
        self.start_time = start_time
        self.end_time = end_time
        self.has_peak = has_peak
        self.peak_power_kw = peak_power_kw
        self.peak_duration_min = peak_duration_min

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
            peak_power_kw=data.get("peak_power_kw"),
            peak_duration_min=data.get("peak_duration_min", 30)
        )


class LoadComponent:
    """
    Represents an individual electrical load component or group of identical machines.

    Attributes:
        id (str): Unique UUID string identifying this component.
        name (str): Human-readable name (e.g. 'CNC Machine 1', 'HVAC Chiller').
        category (str): Classification category (e.g. 'Produktion', 'HLK', 'IT & Büro', 'Mobilität').
        nominal_power_kw (float): Base active electrical power consumption per unit during operation (kW).
        peak_power_kw (Optional[float]): Maximum peak power per unit during inrush spikes (kW).
        count (int): Multiplier count of identical units operating in parallel.
        time_windows (List[TimeWindow]): List of active time windows during operational days.
        active_days (List[int]): Days of the week the component runs (0=Monday, 1=Tuesday, ..., 6=Sunday).
        is_active (bool): Master toggle to include/exclude this component from the simulation.
    """

    def __init__(
        self,
        id: Optional[str] = None,
        name: str = "Machine 1",
        category: str = "Production",
        nominal_power_kw: float = 10.0,
        peak_power_kw: Optional[float] = None,
        count: int = 1,
        time_windows: Optional[List[TimeWindow]] = None,
        active_days: Optional[List[int]] = None,
        is_active: bool = True
    ):
        self.id = id if id else str(uuid.uuid4())
        self.name = name
        self.category = category
        self.nominal_power_kw = max(0.0, float(nominal_power_kw))
        self.peak_power_kw = float(peak_power_kw) if peak_power_kw is not None else self.nominal_power_kw
        self.count = max(1, int(count))
        self.time_windows = time_windows if time_windows is not None else [TimeWindow()]
        # Default active days: Monday through Friday (0, 1, 2, 3, 4)
        self.active_days = active_days if active_days is not None else [0, 1, 2, 3, 4]
        self.is_active = is_active

    def add_time_window(
        self,
        start_time: datetime.time,
        end_time: datetime.time,
        has_peak: bool = False,
        peak_power_kw: Optional[float] = None,
        peak_duration_min: int = 30
    ) -> None:
        """Appends a new operating time window to this component."""
        self.time_windows.append(
            TimeWindow(
                start_time=start_time,
                end_time=end_time,
                has_peak=has_peak,
                peak_power_kw=peak_power_kw if peak_power_kw is not None else self.nominal_power_kw,
                peak_duration_min=peak_duration_min
            )
        )

    def remove_time_window(self, index: int) -> None:
        """Removes the time window at the specified index."""
        if 0 <= index < len(self.time_windows):
            self.time_windows.pop(index)

    def get_daily_array_15min(self, day_of_week: int = 0) -> np.ndarray:
        """
        Synthesizes a 96-element NumPy array representing 15-minute average power (kW)
        for a 24-hour cycle on the given day of the week.

        Algorithm Details:
        ------------------
        1. Checks if the component is active and if `day_of_week` is included in `self.active_days`.
           If not, returns an array of zeros (0.0 kW).
        2. For each configured `TimeWindow`:
           a. Converts start and end times to minute-of-day [0, 1440).
           b. Determines whether the window is standard (start < end), overnight (start > end),
              or full 24-hour (start == end == 00:00).
           c. Evaluates each of the 96 fifteen-minute slots (slot_start = step * 15, slot_end = slot_start + 15).
           d. Applies peak power during the inrush window [start_m, start_m + peak_dur).
           e. Multiplies power by `self.count` and records the maximum demand in `daily_power`.

        Args:
            day_of_week (int): Day index from 0 (Monday) to 6 (Sunday).

        Returns:
            np.ndarray: 96-element float array of electrical power in kW.
        """
        daily_power = np.zeros(96, dtype=float)

        # Early exit if disabled or non-operational day
        if not self.is_active or day_of_week not in self.active_days:
            return daily_power

        unit_nominal = self.nominal_power_kw
        unit_peak = self.peak_power_kw if self.peak_power_kw is not None else unit_nominal

        for window in self.time_windows:
            start_m = window.start_time.hour * 60 + window.start_time.minute
            end_m = window.end_time.hour * 60 + window.end_time.minute

            peak_power = window.peak_power_kw if window.peak_power_kw is not None else unit_peak
            has_peak = window.has_peak and (peak_power > unit_nominal)
            peak_dur = window.peak_duration_min if has_peak else 0

            # Full 24-hour continuous operation flag
            is_full_24h = (start_m == 0 and end_m == 0 and len(self.time_windows) == 1)

            for step in range(96):
                slot_start_m = step * 15
                slot_end_m = slot_start_m + 15

                # Determine if current 15-minute slot falls inside the operational window
                slot_active = False
                if is_full_24h:
                    slot_active = True
                elif start_m < end_m:
                    # Standard same-day window (e.g. 08:00 to 16:00)
                    if slot_start_m >= start_m and slot_end_m <= end_m:
                        slot_active = True
                    elif slot_start_m < end_m and slot_end_m > start_m:
                        slot_active = True
                elif start_m > end_m:
                    # Overnight shift wrapping around midnight (e.g. 22:00 to 06:00)
                    if slot_start_m >= start_m or slot_end_m <= end_m:
                        slot_active = True
                    elif slot_start_m < end_m or slot_end_m > start_m:
                        slot_active = True

                if slot_active:
                    power = unit_nominal
                    if has_peak:
                        # Check if within the initial inrush duration window
                        if start_m < end_m:
                            if slot_start_m < start_m + peak_dur:
                                power = peak_power
                        else:
                            # Overnight inrush logic
                            if slot_start_m >= start_m and slot_start_m < (start_m + peak_dur):
                                power = peak_power
                            elif (start_m + peak_dur >= 1440) and (slot_start_m < (start_m + peak_dur - 1440)):
                                power = peak_power

                    # Aggregate power considering unit multiplier
                    daily_power[step] = max(daily_power[step], power * self.count)

        return daily_power

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the LoadComponent to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "nominal_power_kw": self.nominal_power_kw,
            "peak_power_kw": self.peak_power_kw,
            "count": self.count,
            "time_windows": [w.to_dict() for w in self.time_windows],
            "active_days": list(self.active_days),
            "is_active": self.is_active
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LoadComponent":
        """Reconstructs a LoadComponent instance from a serialized dictionary."""
        windows = [TimeWindow.from_dict(w) for w in data.get("time_windows", [])]
        return cls(
            id=data.get("id"),
            name=data.get("name", "Component"),
            category=data.get("category", "Production"),
            nominal_power_kw=data.get("nominal_power_kw", 10.0),
            peak_power_kw=data.get("peak_power_kw"),
            count=data.get("count", 1),
            time_windows=windows if windows else [TimeWindow()],
            active_days=data.get("active_days", [0, 1, 2, 3, 4]),
            is_active=data.get("is_active", True)
        )
