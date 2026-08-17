import numpy as np
import pandas as pd


class Baseline:
    def __init__(
        self,
        monthly_consumption: float = 25000.0,
        days_per_week: int = 5,
        hours_per_day: int = 8,
        start_hour: int = 8,
        base_load_pct: float = 15.0,
        year: int = 2026
    ):
        self.monthly_consumption = monthly_consumption
        self.days_per_week = days_per_week
        self.hours_per_day = hours_per_day
        self.start_hour = start_hour
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
        df['hour'] = df['timestamp'].dt.hour
        df['dayofweek'] = df['timestamp'].dt.dayofweek

        # 2. Define base load vs. operational hours
        base_factor = self.base_load_pct / 100.0
        profile = np.full(len(df), base_factor)

        # Operational hours (working days & shift hours)
        end_hour = self.start_hour + self.hours_per_day
        if self.hours_per_day >= 24:
            work_hours = pd.Series(True, index=df.index)
        else:
            work_hours = (df['hour'] >= self.start_hour) & (df['hour'] < end_hour)

        work_days = df['dayofweek'] < self.days_per_week
        profile[work_hours & work_days] = 1.0

        # 3. Scale strictly to target annual consumption (12 * monthly_consumption)
        annual_target_kwh = self.monthly_consumption * 12
        raw_energy_kwh = np.sum(profile) * 0.25  # 15min intervals = 0.25h
        scaling_factor = annual_target_kwh / raw_energy_kwh if raw_energy_kwh > 0 else 0.0

        df['consumption_kw'] = profile * scaling_factor
        
        self.df = df[['timestamp', 'consumption_kw']]
        return self.df
