import datetime
import numpy as np
import pandas as pd


class Baseline:
    def __init__(
        self,
        monthly_consumption: float = 25000.0,
        days_per_week: int = 5,
        start_time: datetime.time = datetime.time(8, 0),
        end_time: datetime.time = datetime.time(16, 0),
        base_load_pct: float = 15.0,
        year: int = 2026
    ):
        self.monthly_consumption = monthly_consumption
        self.days_per_week = days_per_week
        self.start_time = start_time
        self.end_time = end_time
        self.base_load_pct = base_load_pct
        self.year = year
        self.df = None

    def generate(self) -> pd.DataFrame:
        """Generates a 15-minute resolution load profile for the entire year."""
        # 1. Create a 15-minute time series for the year
        start_date = pd.Timestamp(self.year, 1, 1, 0, 0)
        end_date = pd.Timestamp(self.year + 1, 1, 1, 0, 0) - pd.Timedelta(minutes=15)
        timestamps = pd.date_range(start=start_date, end=end_date, freq='15min')

        df = pd.DataFrame({'timestamp': timestamps})
        df['time'] = df['timestamp'].dt.time
        df['dayofweek'] = df['timestamp'].dt.dayofweek

        # 2. Define base load vs. operational hours
        base_factor = self.base_load_pct / 100.0
        profile = np.full(len(df), base_factor)

        # Operational time window (supports overnight shifts as well)
        if self.start_time <= self.end_time:
            time_mask = (df['time'] >= self.start_time) & (df['time'] < self.end_time)
        else:
            time_mask = (df['time'] >= self.start_time) | (df['time'] < self.end_time)

        work_days = df['dayofweek'] < self.days_per_week
        profile[time_mask & work_days] = 1.0

        # 3. Scale strictly to target annual consumption (12 * monthly_consumption)
        annual_target_kwh = self.monthly_consumption * 12
        raw_energy_kwh = np.sum(profile) * 0.25  # 15min intervals = 0.25h
        scaling_factor = annual_target_kwh / raw_energy_kwh if raw_energy_kwh > 0 else 0.0

        df['consumption_kw'] = profile * scaling_factor

        self.df = df[['timestamp', 'consumption_kw']]
        return self.df
