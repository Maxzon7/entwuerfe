"""
========================================================================================
Calendar & System-Wide Holiday Configuration (current_model/models/calendar_config.py)
========================================================================================

Description:
------------
Defines the `CalendarConfig` dataclass for managing simulation years, system-wide
custom public holidays, and factory shutdown periods.
"""

from dataclasses import dataclass, field
from typing import List, Set, Union
import datetime
import pandas as pd


@dataclass
class CalendarConfig:
    """Configuration for calendar year and system-wide holidays."""
    year: int = 2025
    # List of ISO date strings 'YYYY-MM-DD' or 'DD.MM.YYYY'
    holidays: List[str] = field(default_factory=list)

    def get_holiday_dates(self) -> Set[datetime.date]:
        """Returns a normalized set of datetime.date objects for fast lookup."""
        dates_set: Set[datetime.date] = set()
        for h_str in self.holidays:
            try:
                parsed = pd.to_datetime(h_str, dayfirst=True)
                if pd.notnull(parsed):
                    dates_set.add(parsed.date())
            except Exception:
                continue
        return dates_set

    def is_holiday(self, dt: Union[datetime.date, datetime.datetime, pd.Timestamp]) -> bool:
        """Returns True if the given date is configured as a system holiday."""
        if isinstance(dt, (datetime.datetime, pd.Timestamp)):
            d = dt.date()
        else:
            d = dt
        return d in self.get_holiday_dates()
