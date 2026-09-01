"""
========================================================================================
Load Aggregator & Energy KPI Engine (models/load_aggregator.py)
========================================================================================

Description:
------------
The `LoadAggregator` class coordinates multiple `LoadComponent` building blocks
and an optional 24/7 continuous baseline/standby load. It performs:
  1. 24-Hour Daily Profile Assembly: 96 intervals per day (15-min resolution) with individual component breakdowns.
  2. Full-Year Simulation: 35,040 intervals per year (8,760 hours * 4 slots/hour) with weekday/weekend scheduling.
  3. Energy Key Performance Indicators (KPIs):
     - Peak Demand P_max (kW) and exact time of occurrence.
     - Annual electricity consumption in kWh/a and MWh/a.
     - Workday vs. Weekend consumption.
     - Average continuous load P_avg (kW).
     - Full Load Hours (Vollbenutzungsstunden) T_voll = Annual_kWh / P_max.
     - Percentage energy breakdown and MWh per component.

Energy Calculation Formulas:
----------------------------
- Interval Energy: E_step [kWh] = P [kW] * 0.25 h
- Annual Energy: E_annual [kWh] = Sum(P_step * 0.25 h) for step = 0 to 35,039
- Average Power: P_avg [kW] = E_annual [kWh] / 8,760 h
- Full Load Hours: T_voll [h/a] = E_annual [kWh] / P_max [kW]
"""

import datetime
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from models.load_component import LoadComponent, TimeWindow


class LoadAggregator:
    """
    Coordinates modular load components, baseline loads, and annual time series synthesis.

    Attributes:
        components (List[LoadComponent]): List of active/inactive electrical load components.
        baseline_enabled (bool): Whether continuous 24/7 standby baseline is active.
        baseline_power_kw (float): Power drawn continuously by the baseline (kW).
        year (int): Calendar year for datetime index generation (default: 2026).
    """

    def __init__(
        self,
        components: Optional[List[LoadComponent]] = None,
        baseline_enabled: bool = False,
        baseline_power_kw: float = 0.0,
        year: int = 2026
    ):
        self.components = components if components is not None else []
        self.baseline_enabled = baseline_enabled
        self.baseline_power_kw = max(0.0, float(baseline_power_kw))
        self.year = year

    def add_component(self, component: LoadComponent) -> None:
        """Adds a new LoadComponent to the aggregator collection."""
        self.components.append(component)

    def remove_component(self, component_id: str) -> None:
        """Removes a component by its unique UUID string."""
        self.components = [c for c in self.components if c.id != component_id]

    def get_component(self, component_id: str) -> Optional[LoadComponent]:
        """Finds and returns a component by ID, or None if not found."""
        for c in self.components:
            if c.id == component_id:
                return c
        return None

    def get_daily_dataframe(self, day_of_week: int = 0) -> pd.DataFrame:
        """
        Generates a 96-row pandas DataFrame representing a 24-hour day in 15-minute intervals.

        Structure of the resulting DataFrame:
          - 'time': String timestamps ('00:00', '00:15', ..., '23:45')
          - 'Baseload (Standby)': Continuous baseline curve (if enabled)
          - '<Component Name>': Power curve for each active component (kW)
          - 'Total_kW': Sum of all individual loads and baseline for that 15-min slot

        Args:
            day_of_week (int): Day index (0=Monday, 1=Tuesday, ..., 6=Sunday).

        Returns:
            pd.DataFrame: 96-row DataFrame with individual component columns and Total_kW.
        """
        time_strings = [
            f"{h:02d}:{m:02d}"
            for h in range(24)
            for m in (0, 15, 30, 45)
        ]

        data = {"time": time_strings}
        total_kw = np.zeros(96, dtype=float)

        # 1. Add Optional Continuous Baseline / Standby Load
        if self.baseline_enabled and self.baseline_power_kw > 0:
            base_curve = np.full(96, self.baseline_power_kw, dtype=float)
            data["Baseload (Standby)"] = base_curve
            total_kw += base_curve

        # 2. Add Each Active Component Curve
        # Maintain a counter to prevent column name collisions for duplicate names
        used_names: Dict[str, int] = {}
        for comp in self.components:
            if not comp.is_active:
                continue

            col_name = comp.name
            if col_name in used_names:
                used_names[col_name] += 1
                col_name = f"{col_name} ({used_names[col_name]})"
            else:
                used_names[col_name] = 1

            comp_curve = comp.get_daily_array_15min(day_of_week=day_of_week)
            data[col_name] = comp_curve
            total_kw += comp_curve

        data["Total_kW"] = total_kw
        return pd.DataFrame(data)

    def get_yearly_dataframe(self) -> pd.DataFrame:
        """
        Synthesizes a full 1-year time series with 35,040 fifteen-minute resolution timestamps.

        Why 35,040 rows:
        ----------------
        365 days * 24 hours/day * 4 intervals/hour = 35,040 intervals.
        Each day of the week (Monday through Sunday) is correctly mapped to each component's
        operational schedule.

        Returns:
            pd.DataFrame: 35,040-row DataFrame containing timestamp, individual loads, and 'consumption_kw'.
        """
        start_date = pd.Timestamp(self.year, 1, 1, 0, 0)
        end_date = pd.Timestamp(self.year + 1, 1, 1, 0, 0) - pd.Timedelta(minutes=15)
        timestamps = pd.date_range(start=start_date, end=end_date, freq="15min")

        df = pd.DataFrame({"timestamp": timestamps})
        df["dayofweek"] = df["timestamp"].dt.dayofweek

        total_kw = np.zeros(len(df), dtype=float)

        # Baseline addition
        if self.baseline_enabled and self.baseline_power_kw > 0:
            base_val = self.baseline_power_kw
            df["Baseload (Standby)"] = base_val
            total_kw += base_val

        # Vectorized Day-of-Week mapping for each component
        for comp in self.components:
            if not comp.is_active:
                continue

            comp_total = np.zeros(len(df), dtype=float)
            for dow in range(7):
                dow_mask = (df["dayofweek"] == dow)
                dow_curve = comp.get_daily_array_15min(day_of_week=dow)
                matching_count = np.sum(dow_mask) // 96
                if matching_count > 0:
                    comp_total[dow_mask] = np.tile(dow_curve, matching_count)[:np.sum(dow_mask)]

            df[comp.name] = comp_total
            total_kw += comp_total

        df["consumption_kw"] = total_kw
        return df

    def calculate_kpis(self) -> Dict[str, Any]:
        """
        Computes comprehensive Energy Key Performance Indicators (KPIs).

        Returns:
            dict containing:
              - 'p_max_kw': Maximum annual peak demand (kW)
              - 'p_avg_kw': Average annual electrical power (kW)
              - 'workday_pmax_kw': Peak demand on a standard workday (kW)
              - 'peak_time_workday': Clock time (HH:MM) when workday peak occurs
              - 'workday_kwh': Total daily energy requirement on workdays (kWh/day)
              - 'saturday_kwh': Total daily energy on Saturdays (kWh/day)
              - 'sunday_kwh': Total daily energy on Sundays (kWh/day)
              - 'annual_kwh': Total annual electricity consumption (kWh/a)
              - 'annual_mwh': Total annual electricity in megawatt-hours (MWh/a)
              - 'full_load_hours': Full load utilization hours (h/a)
              - 'active_components_count': Number of enabled components
              - 'component_shares': Detailed breakdown of MWh and % share per machine
        """
        # Workday profile analysis (Monday = 0)
        df_workday = self.get_daily_dataframe(day_of_week=0)
        workday_kwh = float(df_workday["Total_kW"].sum() * 0.25)
        workday_pmax = float(df_workday["Total_kW"].max())

        # Weekend profiles analysis (Saturday = 5, Sunday = 6)
        df_sat = self.get_daily_dataframe(day_of_week=5)
        sat_kwh = float(df_sat["Total_kW"].sum() * 0.25)
        df_sun = self.get_daily_dataframe(day_of_week=6)
        sun_kwh = float(df_sun["Total_kW"].sum() * 0.25)

        # Full Year Simulation
        df_year = self.get_yearly_dataframe()
        annual_kwh = float(df_year["consumption_kw"].sum() * 0.25)
        annual_mwh = annual_kwh / 1000.0
        annual_pmax = float(df_year["consumption_kw"].max())
        avg_power_kw = annual_kwh / 8760.0 if annual_kwh > 0 else 0.0
        full_load_hours = (annual_kwh / annual_pmax) if annual_pmax > 0 else 0.0

        # Component Energy Breakdown Calculation
        component_energy: Dict[str, float] = {}
        total_comp_energy = 0.0

        if self.baseline_enabled and self.baseline_power_kw > 0:
            base_energy = self.baseline_power_kw * 8760.0
            component_energy["Baseload (Standby)"] = base_energy
            total_comp_energy += base_energy

        for comp in self.components:
            if not comp.is_active:
                continue
            if comp.name in df_year.columns:
                comp_kwh = float(df_year[comp.name].sum() * 0.25)
                component_energy[comp.name] = comp_kwh
                total_comp_energy += comp_kwh

        component_shares: Dict[str, Dict[str, float]] = {}
        if total_comp_energy > 0:
            for name, kwh in component_energy.items():
                component_shares[name] = {
                    "kwh": round(kwh, 1),
                    "mwh": round(kwh / 1000.0, 2),
                    "share_pct": round((kwh / total_comp_energy) * 100.0, 1)
                }

        # Workday peak time identification
        max_idx = df_workday["Total_kW"].idxmax()
        peak_time_str = df_workday.loc[max_idx, "time"] if len(df_workday) > 0 else "00:00"

        return {
            "p_max_kw": round(annual_pmax, 2),
            "p_avg_kw": round(avg_power_kw, 2),
            "workday_pmax_kw": round(workday_pmax, 2),
            "peak_time_workday": peak_time_str,
            "workday_kwh": round(workday_kwh, 1),
            "saturday_kwh": round(sat_kwh, 1),
            "sunday_kwh": round(sun_kwh, 1),
            "annual_kwh": round(annual_kwh, 1),
            "annual_mwh": round(annual_mwh, 2),
            "full_load_hours": round(full_load_hours, 1),
            "active_components_count": len([c for c in self.components if c.is_active]),
            "component_shares": component_shares
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the complete LoadAggregator state to a JSON-compatible dictionary."""
        return {
            "baseline_enabled": self.baseline_enabled,
            "baseline_power_kw": self.baseline_power_kw,
            "year": self.year,
            "components": [c.to_dict() for c in self.components]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LoadAggregator":
        """Deserializes a dictionary into a LoadAggregator instance."""
        comps = [LoadComponent.from_dict(c) for c in data.get("components", [])]
        return cls(
            components=comps,
            baseline_enabled=data.get("baseline_enabled", False),
            baseline_power_kw=data.get("baseline_power_kw", 0.0),
            year=data.get("year", 2026)
        )
