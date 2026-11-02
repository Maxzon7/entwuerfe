"""
========================================================================================
Scenario 3 Engine: Solar PV Simulation & Hockey-Stick Auto-Sizing (ui_sandbox/Solar_sandbox/solar_sandbox_engine.py)
========================================================================================

Provides fast, vectorized 35,040-step (15-min) Solar PV yield and direct self-consumption
simulation coupled with `LoadSeries2025`, plus the interactive **Solar Sizing Hockey-Stick
(Pareto Tradeoff) Curve**:
  - `generate_normalized_solar_unit_profile_2025`: Generates a physically realistic 35,040-step
    unit PV generation curve (kW AC per 1 kWp installed DC) for a given latitude, tilt, azimuth,
    and cell technology (PERC, TOPCon, Backcontact).
  - `simulate_standalone_solar_dispatch`: Evaluates direct self-consumption, grid export,
    curtailment, and residual grid import P_Grid(t) for any PV capacity (kWp).
  - `compute_solar_hockey_stick_curve`: Sweeps PV sizing across 14 support points from 5% to 200%
    of annual demand, mapping Achieved Direct Autarky (%) vs. Required PV Nameplate Capacity (kWp)
    and Direct Self-Consumption Rate (SCR %) — revealing the classic solar hockey-stick inflection
    point where midday demand becomes saturated and additional kWp predominantly exports to the grid.
  - `create_solar_hockey_stick_figure`: Dual-axis Plotly figure matching `BESS_sandbox`'s Pareto
    hockey-stick styling.
========================================================================================
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    from models.solar import TECHNOLOGY_SPECS
except ImportError:
    from current_model.models.solar import TECHNOLOGY_SPECS

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025


SOLAR_CLIMATE_PRESETS: Dict[str, Dict[str, Any]] = {
    "Rotterdam / Netherlands (Cfb Maritime — ~980 kWh/kWp/yr)": {
        "latitude": 51.9244,
        "longitude": 4.4777,
        "specific_yield_kwh_per_kwp": 980.0,
        "default_tilt_deg": 15.0,
        "default_azimuth_deg": 180.0,
        "hemisphere": "north",
    },
    "Mendoza / Argentina (Bodegas Salentein High-Altitude — ~1,850 kWh/kWp/yr)": {
        "latitude": -33.5133,
        "longitude": -69.2561,
        "specific_yield_kwh_per_kwp": 1850.0,
        "default_tilt_deg": 28.0,
        "default_azimuth_deg": 0.0,
        "hemisphere": "south",
    },
    "Central Europe / Southern Germany (Cfb Continental — ~1,120 kWh/kWp/yr)": {
        "latitude": 48.1351,
        "longitude": 11.5820,
        "specific_yield_kwh_per_kwp": 1120.0,
        "default_tilt_deg": 20.0,
        "default_azimuth_deg": 180.0,
        "hemisphere": "north",
    },
}


def generate_normalized_solar_unit_profile_2025(
    timestamps: pd.DatetimeIndex,
    latitude: float = 51.9244,
    tilt_deg: float = 15.0,
    azimuth_deg: float = 180.0,
    technology: str = "TOPCon",
    dc_ac_ratio: float = 1.15,
    system_losses_pct: float = 14.0,
) -> Tuple[np.ndarray, float]:
    """
    Generates a deterministic, high-realism 35,040-step unit AC output profile (kW AC per 1 kWp DC)
    for reference year 2025 using solar declination, hour angle, cloud variability, and cell thermal physics.
    Returns `(unit_kw_per_kwp_array, annual_specific_yield_kwh_per_kwp)`.
    """
    n_steps = len(timestamps)
    doy = timestamps.dayofyear.to_numpy(dtype=float)
    hour_float = timestamps.hour.to_numpy(dtype=float) + timestamps.minute.to_numpy(dtype=float) / 60.0

    lat_rad = np.radians(latitude)
    # Solar declination (Cooper's equation)
    decl_rad = np.radians(23.45 * np.sin(np.radians(360.0 * (284.0 + doy) / 365.0)))
    # Solar hour angle (15 deg per hour from solar noon at 12:30 local standard time)
    omega_rad = np.radians(15.0 * (hour_float - 12.5))

    sin_elev = np.sin(lat_rad) * np.sin(decl_rad) + np.cos(lat_rad) * np.cos(decl_rad) * np.cos(omega_rad)
    sin_elev = np.clip(sin_elev, 0.0, 1.0)

    # Tilt & orientation modifier
    opt_tilt = min(40.0, abs(latitude) * 0.75)
    tilt_factor = 1.0 - 0.00012 * ((tilt_deg - opt_tilt) ** 2)
    opt_az = 180.0 if latitude >= 0 else 0.0
    az_diff = min(abs(azimuth_deg - opt_az), 360.0 - abs(azimuth_deg - opt_az))
    az_factor = max(0.65, 1.0 - 0.0018 * az_diff)

    # Deterministic weather/cloud transmittance series (seeded for exact reproducibility)
    rng = np.random.default_rng(seed=202503)
    daily_cloud = rng.beta(a=4.2 if abs(latitude) < 40 else 2.6, b=1.4, size=366)
    day_idx = np.clip(doy.astype(int), 1, 365)
    cloud_transmittance = 0.25 + 0.75 * daily_cloud[day_idx]

    # Technology efficiency modifier
    tech_mod = 1.025 if technology == "Backcontact" else (1.012 if technology == "TOPCon" else 0.99)
    loss_factor = (1.0 - system_losses_pct / 100.0) * tech_mod * tilt_factor * az_factor

    raw_unit_kw = sin_elev * cloud_transmittance * loss_factor
    # Clip at inverter AC limit (1 / dc_ac_ratio)
    inv_ac_limit_per_kwp = 1.0 / max(1.0, dc_ac_ratio)
    unit_kw = np.clip(raw_unit_kw, 0.0, inv_ac_limit_per_kwp)

    # Calibrate annual specific yield to realistic regional benchmark
    base_target_yield = 1820.0 if abs(latitude) < 38.0 else (1120.0 if abs(latitude) < 49.5 else 985.0)
    target_yield = base_target_yield * tilt_factor * az_factor * tech_mod * ((100.0 - system_losses_pct) / 86.0)
    raw_yield = float(np.sum(unit_kw) * 0.25)
    if raw_yield > 1.0:
        unit_kw = np.clip(unit_kw * (target_yield / raw_yield), 0.0, inv_ac_limit_per_kwp)

    actual_spec_yield = float(np.sum(unit_kw) * 0.25)
    return unit_kw, actual_spec_yield


def simulate_standalone_solar_dispatch(
    load: LoadSeries2025,
    unit_pv_kw: np.ndarray,
    pv_capacity_kwp: float,
    max_grid_export_kw: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Simulates 35,040-step standalone Solar PV generation, direct self-consumption,
    grid export, curtailment, and residual grid import P_Grid(t).
    """
    p_load = np.asarray(load.power_kw, dtype=float)
    p_pv = np.asarray(unit_pv_kw, dtype=float) * max(0.0, float(pv_capacity_kwp))

    p_direct = np.minimum(p_load, p_pv)
    p_surplus = np.maximum(0.0, p_pv - p_direct)

    if max_grid_export_kw is not None and max_grid_export_kw >= 0.0:
        p_export = np.minimum(p_surplus, float(max_grid_export_kw))
        p_curtailed = np.maximum(0.0, p_surplus - p_export)
    else:
        p_export = p_surplus
        p_curtailed = np.zeros_like(p_surplus)

    p_grid = np.maximum(0.0, p_load - p_direct)

    dt = 0.25
    load_kwh = float(np.sum(p_load) * dt)
    pv_kwh = float(np.sum(p_pv) * dt)
    direct_kwh = float(np.sum(p_direct) * dt)
    export_kwh = float(np.sum(p_export) * dt)
    curtailed_kwh = float(np.sum(p_curtailed) * dt)
    grid_import_kwh = float(np.sum(p_grid) * dt)

    # Daylight load (intervals where solar irradiance > 0.01 kW/kWp)
    daylight_mask = (unit_pv_kw > 0.005)
    daylight_load_kwh = float(np.sum(p_load[daylight_mask]) * dt)
    daylight_coverage_pct = (direct_kwh / daylight_load_kwh * 100.0) if daylight_load_kwh > 0 else 0.0

    autarky_pct = (direct_kwh / load_kwh * 100.0) if load_kwh > 0 else 0.0
    scr_pct = (direct_kwh / pv_kwh * 100.0) if pv_kwh > 0 else 100.0

    # TOU breakdown of direct self-consumption savings
    if load.tou_window_codes is not None:
        pico_saved_kwh = float(np.sum(p_direct[load.tou_window_codes == 1]) * dt)
        valle_saved_kwh = float(np.sum(p_direct[load.tou_window_codes == 0]) * dt)
        resto_saved_kwh = float(np.sum(p_direct[load.tou_window_codes == 2]) * dt)
    else:
        pico_saved_kwh = float(np.sum(p_direct[load.is_peak_tou]) * dt)
        valle_saved_kwh = float(np.sum(p_direct[~load.is_peak_tou]) * dt)
        resto_saved_kwh = 0.0

    return {
        "pv_capacity_kwp": float(pv_capacity_kwp),
        "p_load_kw": p_load,
        "p_pv_kw": p_pv,
        "p_direct_kw": p_direct,
        "p_export_kw": p_export,
        "p_curtailed_kw": p_curtailed,
        "p_grid_kw": p_grid,
        "load_kwh": load_kwh,
        "pv_kwh": pv_kwh,
        "direct_kwh": direct_kwh,
        "export_kwh": export_kwh,
        "curtailed_kwh": curtailed_kwh,
        "grid_import_kwh": grid_import_kwh,
        "daylight_load_kwh": daylight_load_kwh,
        "daylight_coverage_pct": daylight_coverage_pct,
        "autarky_pct": autarky_pct,
        "self_consumption_pct": scr_pct,
        "peak_before_kw": float(np.max(p_load)),
        "peak_after_kw": float(np.max(p_grid)),
        "peak_shaved_kw": float(np.max(p_load) - np.max(p_grid)),
        "pico_or_ht_saved_kwh": pico_saved_kwh,
        "valle_or_nt_saved_kwh": valle_saved_kwh,
        "resto_saved_kwh": resto_saved_kwh,
    }


def compute_solar_hockey_stick_curve(
    load: LoadSeries2025,
    unit_pv_kw: np.ndarray,
    specific_yield_kwh_per_kwp: float,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Computes the Solar Sizing Hockey-Stick / Pareto Tradeoff Curve across 15 demand-ratio support points
    (from 5% to 200% of annual facility energy demand).
    Demonstrates why sizing standalone PV for higher direct load coverage exhibits a sharp hockey-stick
    inflection point: once midday facility demand is covered, additional kWp goes almost entirely into
    grid export/curtailment while yielding diminishing autarky gains.
    """
    annual_load_kwh = load.total_energy_kwh
    kwp_100pct = annual_load_kwh / max(500.0, specific_yield_kwh_per_kwp)

    demand_ratios = [0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00, 1.20, 1.40, 1.70, 2.00]
    rows: List[Dict[str, float]] = []

    for ratio in demand_ratios:
        cand_kwp = round(kwp_100pct * ratio, 1)
        sim = simulate_standalone_solar_dispatch(load=load, unit_pv_kw=unit_pv_kw, pv_capacity_kwp=cand_kwp)
        rows.append(
            {
                "demand_ratio_pct": round(ratio * 100.0, 1),
                "pv_kwp": cand_kwp,
                "pv_kwh": sim["pv_kwh"],
                "direct_kwh": sim["direct_kwh"],
                "export_kwh": sim["export_kwh"],
                "autarky_pct": sim["autarky_pct"],
                "daylight_coverage_pct": sim["daylight_coverage_pct"],
                "self_consumption_pct": sim["self_consumption_pct"],
                "peak_after_kw": sim["peak_after_kw"],
            }
        )

    df_curve = pd.DataFrame(rows)
    presets_kwp = {
        "40_pct": round(kwp_100pct * 0.40, 1),
        "60_pct": round(kwp_100pct * 0.60, 1),
        "80_pct": round(kwp_100pct * 0.80, 1),
        "100_pct": round(kwp_100pct * 1.00, 1),
        "sweet_spot": round(kwp_100pct * 0.55, 1),
    }
    return df_curve, presets_kwp


def create_solar_hockey_stick_figure(
    df_curve: pd.DataFrame,
    selected_kwp: float,
    selected_daylight_cov_pct: float,
    selected_scr_pct: float,
) -> go.Figure:
    """
    Renders the interactive Dual-Axis Solar Auto-Sizing Hockey-Stick Curve (matching BESS_sandbox style):
      - X-Axis: Achieved Daylight Load Coverage (%) [or Direct Autarky %]
      - Left Y-Axis: Required Solar PV Nameplate Capacity (kWp) -> Hockey-Stick Curve
      - Right Y-Axis: Direct Self-Consumption Rate (SCR %) -> Diminishing Returns Curve
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Primary Y-Axis: Required PV Nameplate Capacity (kWp) vs. Daylight Load Coverage (%)
    fig.add_trace(
        go.Scatter(
            x=df_curve["daylight_coverage_pct"],
            y=df_curve["pv_kwp"],
            mode="lines+markers",
            name="Required PV Size (kWp) — Hockey-Stick Curve",
            line=dict(color="#f59e0b", width=3.5),
            marker=dict(size=7, color="#fbbf24"),
            hovertemplate=(
                "Daylight Coverage: %{x:.1f}%<br>"
                "Required PV Size: %{y:,.1f} kWp<extra></extra>"
            ),
        ),
        secondary_y=False,
    )

    # Secondary Y-Axis: Direct Self-Consumption Rate (%)
    fig.add_trace(
        go.Scatter(
            x=df_curve["daylight_coverage_pct"],
            y=df_curve["self_consumption_pct"],
            mode="lines+markers",
            name="Direct Self-Consumption Rate (SCR %)",
            line=dict(color="#38bdf8", width=2.5, dash="dot"),
            marker=dict(size=6, color="#38bdf8"),
            hovertemplate=(
                "Daylight Coverage: %{x:.1f}%<br>"
                "Self-Consumption Rate: %{y:.1f}%<extra></extra>"
            ),
        ),
        secondary_y=True,
    )

    # Highlight current selected operating point
    fig.add_trace(
        go.Scatter(
            x=[selected_daylight_cov_pct],
            y=[selected_kwp],
            mode="markers+text",
            name=f"Selected PV ({selected_kwp:,.1f} kWp)",
            marker=dict(size=14, color="#10b981", symbol="diamond", line=dict(width=2, color="#ffffff")),
            text=[f"  {selected_kwp:,.0f} kWp ({selected_scr_pct:.0f}% SCR)"],
            textposition="top left",
            textfont=dict(color="#4ade80", size=11),
        ),
        secondary_y=False,
    )

    fig.update_layout(
        title=dict(
            text="<b>Solar PV Auto-Sizing Hockey-Stick Curve: Required Capacity (kWp) vs. Daylight Load Coverage (%)</b>",
            x=0.01,
            y=0.98,
            xanchor="left",
            font=dict(size=14, color="#f8fafc"),
        ),
        template="plotly_dark",
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.55)",
        height=410,
        margin=dict(l=55, r=55, t=90, b=45),
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0.01),
        xaxis=dict(
            title="Achieved Daylight Facility Load Coverage (%)",
            gridcolor="#1e293b",
             ticksuffix="%",
        ),
    )
    fig.update_yaxes(
        title_text="<b>Required Solar PV Capacity (kWp)</b>",
        gridcolor="#1e293b",
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="<b>Direct Self-Consumption Rate (SCR %)</b>",
        range=[0, 105],
        ticksuffix="%",
        showgrid=False,
        secondary_y=True,
    )
    return fig


def compute_pure_solar_plant_economics(
    pv_kwp: float,
    annual_generation_kwh: float,
    capex_per_kwp: float = 850.0,
    annual_om_pct: float = 1.5,
    annual_om_fixed: float = 0.0,
    horizon_years: int = 20,
    discount_rate_pct: float = 5.0,
    degradation_pct_a: float = 0.40,
    first_year_degradation_pct: float = 1.50,
    inverter_replacement_cost_pct: float = 12.0,
    inverter_replacement_year: int = 11,
) -> Dict[str, Any]:
    """
    Computes pure plant financial metrics (Levelized Cost of Electricity LCOE, total CAPEX,
    annual OPEX, and lifecycle cashflow schedule) WITHOUT coupling to external electricity tariffs or bills.
    """
    total_capex = float(pv_kwp * capex_per_kwp)
    r = float(discount_rate_pct / 100.0)
    d1 = float(first_year_degradation_pct / 100.0)
    d2 = float(degradation_pct_a / 100.0)

    opex_year1 = total_capex * (annual_om_pct / 100.0) + annual_om_fixed
    inv_rep_cost = total_capex * (inverter_replacement_cost_pct / 100.0) if inverter_replacement_year > 0 else 0.0

    discounted_costs_sum = total_capex
    discounted_generation_sum = 0.0
    total_lifetime_generation = 0.0

    cashflow_rows: List[Dict[str, Any]] = [
        {
            "year": 0,
            "capex_and_rep": total_capex,
            "opex": 0.0,
            "net_outflow": total_capex,
            "generation_kwh": 0.0,
            "discounted_cost": total_capex,
            "discounted_gen_kwh": 0.0,
            "cumulative_cost": total_capex,
        }
    ]

    running_cost = total_capex
    for y in range(1, horizon_years + 1):
        # Physical degradation
        f_deg = (1.0 - d1) if y == 1 else (1.0 - d1) * ((1.0 - d2) ** (y - 1))
        y_gen = annual_generation_kwh * f_deg
        total_lifetime_generation += y_gen

        # OPEX with small inflation (2% p.a.)
        y_opex = opex_year1 * ((1.0 + 0.02) ** (y - 1))
        y_rep = inv_rep_cost if y == inverter_replacement_year else 0.0
        y_outflow = y_opex + y_rep
        running_cost += y_outflow

        disc_factor = 1.0 / ((1.0 + r) ** y)
        y_disc_cost = y_outflow * disc_factor
        y_disc_gen = y_gen * disc_factor

        discounted_costs_sum += y_disc_cost
        discounted_generation_sum += y_disc_gen

        cashflow_rows.append(
            {
                "year": y,
                "capex_and_rep": y_rep,
                "opex": y_opex,
                "net_outflow": y_outflow,
                "generation_kwh": y_gen,
                "discounted_cost": y_disc_cost,
                "discounted_gen_kwh": y_disc_gen,
                "cumulative_cost": running_cost,
            }
        )

    lcoe = (discounted_costs_sum / discounted_generation_sum) if discounted_generation_sum > 0 else 0.0

    return {
        "total_capex": total_capex,
        "capex_per_kwp": capex_per_kwp,
        "annual_om_year1": opex_year1,
        "lcoe": lcoe,
        "discounted_costs_sum": discounted_costs_sum,
        "discounted_generation_sum": discounted_generation_sum,
        "total_lifetime_generation_kwh": total_lifetime_generation,
        "cashflow_rows": cashflow_rows,
    }


def create_monthly_solar_balance_figure(
    load: LoadSeries2025,
    p_direct_kw: np.ndarray,
    p_export_kw: np.ndarray,
    p_load_kw: np.ndarray,
) -> go.Figure:
    """Creates a monthly stacked bar chart showing Direct Self-Consumption vs. Export Surplus."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    direct_m = []
    export_m = []
    load_m = []

    dt = 0.25
    for m in range(1, 13):
        mask = (load.month_indices == m)
        direct_m.append(float(np.sum(p_direct_kw[mask]) * dt / 1000.0))
        export_m.append(float(np.sum(p_export_kw[mask]) * dt / 1000.0))
        load_m.append(float(np.sum(p_load_kw[mask]) * dt / 1000.0))

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=months,
            y=direct_m,
            name="Direct On-Site Consumption (MWh)",
            marker_color="#10b981",
        )
    )
    fig.add_trace(
        go.Bar(
            x=months,
            y=export_m,
            name="Grid Export / Surplus (MWh)",
            marker_color="#f59e0b",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=months,
            y=load_m,
            mode="lines+markers",
            name="Total Facility Load (MWh)",
            line=dict(color="#38bdf8", width=2.5),
            marker=dict(size=6),
        )
    )
    fig.update_layout(
        title=dict(text="<b>Monthly Generation & Self-Consumption Balance (MWh)</b>", x=0.01, y=0.98, xanchor="left"),
        barmode="stack",
        template="plotly_dark",
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.55)",
        height=350,
        margin=dict(l=50, r=30, t=85, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0.01),
        yaxis=dict(title="Energy (MWh)", gridcolor="#1e293b"),
    )
    return fig


def create_diurnal_solar_season_figure(
    load: LoadSeries2025,
    unit_pv_kw: np.ndarray,
    pv_capacity_kwp: float,
    latitude: float,
) -> go.Figure:
    """Creates a 24-hour diurnal profile comparing average Summer vs. Winter load and solar curves."""
    p_pv = unit_pv_kw * max(0.0, float(pv_capacity_kwp))
    hour_float = load.timestamps.hour + load.timestamps.minute / 60.0

    # Summer / Winter months based on hemisphere
    is_northern = (latitude >= 0.0)
    summer_months = [6, 7, 8] if is_northern else [12, 1, 2]
    winter_months = [12, 1, 2] if is_northern else [6, 7, 8]

    mask_sum = np.isin(load.month_indices, summer_months)
    mask_win = np.isin(load.month_indices, winter_months)

    df_h = pd.DataFrame(
        {
            "hour": hour_float,
            "load_sum": np.where(mask_sum, load.power_kw, np.nan),
            "pv_sum": np.where(mask_sum, p_pv, np.nan),
            "load_win": np.where(mask_win, load.power_kw, np.nan),
            "pv_win": np.where(mask_win, p_pv, np.nan),
        }
    ).groupby("hour", as_index=False).mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_h["hour"], y=df_h["load_sum"], name="Mean Load (Summer, kW)", line=dict(color="#94a3b8", width=2, dash="dash")))
    fig.add_trace(go.Scatter(x=df_h["hour"], y=df_h["pv_sum"], name="Solar Generation (Summer, kW)", fill="tozeroy", line=dict(color="#f59e0b", width=2.5), fillcolor="rgba(245, 158, 11, 0.22)"))
    fig.add_trace(go.Scatter(x=df_h["hour"], y=df_h["load_win"], name="Mean Load (Winter, kW)", line=dict(color="#64748b", width=1.5, dash="dot")))
    fig.add_trace(go.Scatter(x=df_h["hour"], y=df_h["pv_win"], name="Solar Generation (Winter, kW)", fill="tozeroy", line=dict(color="#38bdf8", width=2), fillcolor="rgba(56, 189, 248, 0.15)"))

    fig.update_layout(
        title=dict(text="<b>24-Hour Diurnal Profile: Summer vs. Winter Generation & Facility Load</b>", x=0.01, y=0.98, xanchor="left"),
        template="plotly_dark",
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.55)",
        height=350,
        margin=dict(l=50, r=30, t=85, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0.01),
        xaxis=dict(title="Hour of Day (00:00 - 24:00)", gridcolor="#1e293b"),
        yaxis=dict(title="Power (kW)", gridcolor="#1e293b"),
    )
    return fig


def create_solar_pure_cashflow_figure(
    cashflow_rows: List[Dict[str, Any]],
    currency_code: str = "EUR",
) -> go.Figure:
    """Creates a chart showing annual lifecycle outflows and cumulative pure plant investment."""
    years = [r["year"] for r in cashflow_rows]
    cum_costs = [r["cumulative_cost"] for r in cashflow_rows]
    outflows = [r["net_outflow"] for r in cashflow_rows]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=years[1:],
            y=outflows[1:],
            name=f"Annual O&M & Replacement ({currency_code}/yr)",
            marker_color="rgba(245, 158, 11, 0.65)",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=years,
            y=cum_costs,
            mode="lines+markers",
            name=f"Cumulative Plant Expenditure ({currency_code})",
            line=dict(color="#38bdf8", width=3),
            marker=dict(size=6),
        ),
        secondary_y=True,
    )
    fig.update_layout(
        title=dict(text="<b>Pure Solar Plant Lifecycle Cashflows & Cumulative Investment</b>", x=0.01, y=0.98, xanchor="left"),
        template="plotly_dark",
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.55)",
        height=350,
        margin=dict(l=50, r=50, t=85, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0.01),
        xaxis=dict(title="Operating Year", gridcolor="#1e293b"),
    )
    fig.update_yaxes(title_text=f"Annual Outflow ({currency_code})", gridcolor="#1e293b", secondary_y=False)
    fig.update_yaxes(title_text=f"Cumulative Cost ({currency_code})", showgrid=False, secondary_y=True)
    return fig


