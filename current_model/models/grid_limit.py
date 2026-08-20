"""
========================================================================================
Grid Limit & Overload Analysis Models (current_model/models/grid_limit.py)
========================================================================================

Description:
------------
Dataclasses and helper structures for grid capacity constraints, target peak shaving caps,
and calculated violation statistics.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass
class GridLimitConfig:
    """Configuration for grid connection capacity monitoring and peak-shaving targets."""
    enabled: bool = False
    max_grid_limit_kw: Optional[float] = 100.0
    target_shaving_cap_kw: Optional[float] = 80.0


@dataclass
class OverloadAnalysisResult:
    """Results from evaluating a load curve against grid and shaving thresholds."""
    has_violation: bool
    overload_peak_kw: float
    overload_duration_hours: float
    overload_intervals_count: int
    overload_energy_kwh: float
    target_shave_peak_kw: float = 0.0
    target_shave_energy_kwh: float = 0.0

    @classmethod
    def from_curve(
        cls,
        total_curve_kw: np.ndarray,
        grid_limit_kw: Optional[float] = None,
        target_cap_kw: Optional[float] = None,
        step_hours: float = 0.25
    ) -> "OverloadAnalysisResult":
        """Calculates overload and shaving metrics from a power array."""
        if grid_limit_kw is None or grid_limit_kw <= 0:
            return cls(
                has_violation=False,
                overload_peak_kw=0.0,
                overload_duration_hours=0.0,
                overload_intervals_count=0,
                overload_energy_kwh=0.0,
                target_shave_peak_kw=0.0,
                target_shave_energy_kwh=0.0
            )

        overload_diff = np.maximum(0.0, total_curve_kw - grid_limit_kw)
        overload_peak = float(overload_diff.max()) if len(overload_diff) > 0 else 0.0
        intervals_over = int((total_curve_kw > grid_limit_kw).sum())
        overload_hours = float(intervals_over * step_hours)
        overload_kwh = float(overload_diff.sum() * step_hours)
        has_violation = overload_peak > 0.0

        shave_peak = 0.0
        shave_kwh = 0.0
        if target_cap_kw is not None and target_cap_kw > 0:
            shave_diff = np.maximum(0.0, total_curve_kw - target_cap_kw)
            shave_peak = float(shave_diff.max()) if len(shave_diff) > 0 else 0.0
            shave_kwh = float(shave_diff.sum() * step_hours)

        return cls(
            has_violation=has_violation,
            overload_peak_kw=overload_peak,
            overload_duration_hours=overload_hours,
            overload_intervals_count=intervals_over,
            overload_energy_kwh=overload_kwh,
            target_shave_peak_kw=shave_peak,
            target_shave_energy_kwh=shave_kwh
        )
