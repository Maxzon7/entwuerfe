import datetime
import numpy as np
import pandas as pd


class LoadProfile:
    def __init__(self, name: str = "", power: float = 0.0, days_per_week: int = 5):
        self.name = name
        self.power = power  # Power in kW
        self.days_per_week = days_per_week
        self.operation_hours = []  # List of time window dicts

    def add_time_window(self, start_time: datetime.time, end_time: datetime.time):
        """Adds a specific minute-precise operating window."""
        self.operation_hours.append({
            'start': start_time,
            'end': end_time
        })

    def clear_time_windows(self):
        """Clears all configured time windows."""
        self.operation_hours = []

    def generate(self, year: int = 2026) -> pd.DataFrame:
        """Generates a 15-minute load profile for the entire year."""
        start_date = pd.Timestamp(year, 1, 1, 0, 0)
        end_date = pd.Timestamp(year + 1, 1, 1, 0, 0) - pd.Timedelta(minutes=15)
        timestamps = pd.date_range(start=start_date, end=end_date, freq='15min')

        df = pd.DataFrame({'timestamp': timestamps})
        df['time'] = df['timestamp'].dt.time
        df['dayofweek'] = df['timestamp'].dt.dayofweek

        profile = np.zeros(len(df))
        work_days_mask = df['dayofweek'] < self.days_per_week

        for window in self.operation_hours:
            s = window['start']
            e = window['end']
            if s <= e:
                time_mask = (df['time'] >= s) & (df['time'] < e)
            else:
                time_mask = (df['time'] >= s) | (df['time'] < e)

            active_mask = work_days_mask & time_mask
            profile[active_mask] = self.power

        df['consumption_kw'] = profile
        return df[['timestamp', 'consumption_kw']]
