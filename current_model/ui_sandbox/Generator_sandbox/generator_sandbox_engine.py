"""
========================================================================================
Generator Sandbox Engine (ui_sandbox/Generator_sandbox/generator_sandbox_engine.py)
========================================================================================

Provides:
  1. Fast 35,040-step 15-minute peaking generator dispatch simulation with Willans fuel model
     and wet-stacking minimum load enforcement.
  2. Generator Capacity Sweep Engine for optimal grid breach elimination.
  3. Interactive Plotly Visualizations:
     - 15-Minute Dispatch Timeseries with 7D/1M/3M/All range selector buttons and range slider
     - 12-Month Generation & Fuel Consumption Balance
     - Energy Flow Sankey Diagram (Grid + Fuel/Genset -> Facility Demand)
     - Sizing Sweep Curve (Avoided Overload % vs. Rated kW vs. Fuel Burn)
========================================================================================
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from current_model.models.generator import GeneratorConfig, GeneratorKPIs


@dataclass
class IdealGeneratorSizingResult:
    """Diagnostic dimensioning outputs for 'The Perfect Generator' (Ideal Peaker)."""
    peak_overload_kw: float                     # Max kW exceeding contracted grid limit
    recommended_rated_kw_100: float             # 100% zero-breach continuous rated power (kW)
    recommended_rated_kw_80: float              # 80% peak capping economic sweet spot (kW)
    recommended_rated_kw_50: float              # 50% peak assist (kW)
    annual_overload_energy_kwh: float           # Total kWh exceeding grid limit
    annual_overload_energy_mwh: float           # Total MWh exceeding grid limit
    overload_hours_count: float                 # Total hours above grid limit
    overload_intervals_count: int               # Number of 15-minute breach intervals
    engine_starts_count: int                    # Cold engine starts required per year
    max_continuous_breach_hours: float          # Longest continuous overload run duration
    recommended_fuel_tank_liters: float         # Recommended on-site fuel tank capacity (Liters or m³)
    wet_stacking_risk_pct: float                # % of active run intervals where load is below 25% min load
    annual_estimated_fuel_liters: float         # Projected fuel consumption at 100% zero-breach
    annual_fuel_cost_est: float                 # Estimated annual fuel expenditure


def compute_ideal_generator_dimensioning(
    load_kw: np.ndarray,
    grid_limit_kw: float,
    step_hours: float = 0.25,
    fuel_type: str = "Diesel",
    fuel_price_per_unit: float = 1.45,
    min_load_pct: float = 25.0,
) -> IdealGeneratorSizingResult:
    """
    Computes mathematically perfect unconstrained generator dimensioning:
      - Evaluates peak breach, annual overload energy, longest continuous run,
        and safe fuel storage capacity.
    """
    arr = np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0)
    overload_arr = np.maximum(0.0, arr - grid_limit_kw)
    peak_overload = float(np.max(overload_arr)) if len(arr) > 0 else 0.0

    # Sizing recommendations rounded to standard 25 kW commercial frame increments
    if peak_overload > 0:
        rated_100 = float(max(25.0, np.ceil((peak_overload * 1.10) / 25.0) * 25.0))
        rated_80 = float(max(25.0, np.ceil((peak_overload * 0.80) / 25.0) * 25.0))
        rated_50 = float(max(25.0, np.ceil((peak_overload * 0.50) / 25.0) * 25.0))
    else:
        rated_100 = 50.0
        rated_80 = 50.0
        rated_50 = 25.0

    overload_kwh = float(np.sum(overload_arr) * step_hours)
    overload_mwh = overload_kwh / 1000.0
    is_overloaded = overload_arr > 0.05
    overload_intervals = int(np.sum(is_overloaded))
    overload_hours = float(overload_intervals * step_hours)

    # Engine cold starts & longest continuous run
    starts_count = 0
    cur_run_steps = 0
    max_run_steps = 0
    for val in is_overloaded:
        if val:
            cur_run_steps += 1
            if cur_run_steps > max_run_steps:
                max_run_steps = cur_run_steps
        else:
            cur_run_steps = 0

    if len(is_overloaded) > 0:
        starts_count = int(np.sum((is_overloaded[1:] == True) & (is_overloaded[:-1] == False))) + (1 if is_overloaded[0] else 0)

    max_continuous_hours = float(max_run_steps * step_hours)

    # Willans fuel model parameters
    slope = 0.28 if fuel_type == "Natural Gas" else 0.24
    intercept = 0.045 if fuel_type == "Natural Gas" else 0.04

    # Max event fuel burn + 48h emergency reserve
    max_event_fuel = (slope * peak_overload + intercept * rated_100) * max_continuous_hours
    avg_overload_kw = (overload_kwh / max(0.1, overload_hours)) if overload_hours > 0 else (rated_100 * 0.5)
    reserve_48h_fuel = (slope * avg_overload_kw + intercept * rated_100) * 48.0
    recommended_tank = round(max(500.0, max_event_fuel + reserve_48h_fuel), 0)

    # Annual fuel estimation
    annual_fuel = float(np.sum([
        (slope * p + intercept * rated_100) * step_hours if p > 0 else 0.0
        for p in overload_arr
    ]))
    annual_fuel_cost = annual_fuel * fuel_price_per_unit

    # Wet-stacking risk: intervals where overload is below 25% minimum generator loading
    min_load_kw = rated_100 * (min_load_pct / 100.0)
    low_load_intervals = int(np.sum((overload_arr > 0.05) & (overload_arr < min_load_kw)))
    wet_stacking_pct = (low_load_intervals / max(1, overload_intervals) * 100.0) if overload_intervals > 0 else 0.0

    return IdealGeneratorSizingResult(
        peak_overload_kw=round(peak_overload, 1),
        recommended_rated_kw_100=rated_100,
        recommended_rated_kw_80=rated_80,
        recommended_rated_kw_50=rated_50,
        annual_overload_energy_kwh=round(overload_kwh, 1),
        annual_overload_energy_mwh=round(overload_mwh, 2),
        overload_hours_count=round(overload_hours, 1),
        overload_intervals_count=overload_intervals,
        engine_starts_count=starts_count,
        max_continuous_breach_hours=round(max_continuous_hours, 1),
        recommended_fuel_tank_liters=round(recommended_tank, 0),
        wet_stacking_risk_pct=round(wet_stacking_pct, 1),
        annual_estimated_fuel_liters=round(annual_fuel, 0),
        annual_fuel_cost_est=round(annual_fuel_cost, 0),
    )


MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]


def simulate_generator_dispatch_2025(
    load_kw: np.ndarray,
    timestamps: pd.DatetimeIndex,
    grid_limit_kw: float,
    gen_config: GeneratorConfig,
    step_hours: float = 0.25,
) -> Dict[str, Any]:
    """
    Executes a high-precision 35,040-step (15-min) generator dispatch simulation:
      - Trigger: whenever load exceeds `peak_shaving_trigger_kw` (or `grid_limit_kw`).
      - Minimum loading: enforces `P_min = rated_power_kw * (min_load_ratio_pct / 100)` when active.
      - Linear Willans fuel curve: F(P) = a * P_gen + b * P_rated (when P_gen > 0).
    """
    n_steps = len(load_kw)
    dt = step_hours

    trigger_kw = float(gen_config.peak_shaving_trigger_kw)
    if trigger_kw <= 0:
        trigger_kw = float(grid_limit_kw) if grid_limit_kw > 0 else 300.0

    rated_kw = float(gen_config.rated_power_kw)
    min_gen_kw = float(gen_config.min_power_kw)
    is_backup = getattr(gen_config, "is_backup_mode", False) or gen_config.dispatch_mode in [
        "emergency_baseload", "residual_load_follow"
    ]
    cov_ratio = max(0.0, min(1.0, float(getattr(gen_config, "backup_coverage_pct", 100.0)) / 100.0))

    p_gen = np.zeros(n_steps, dtype=float)
    fuel_step = np.zeros(n_steps, dtype=float)
    is_running = np.zeros(n_steps, dtype=bool)

    for i in range(n_steps):
        p_act = load_kw[i]
        if is_backup:
            if p_act > 0.1:
                target_req = p_act * cov_ratio
                p_run = min(target_req, rated_kw)
                if p_run > 0 and min_gen_kw > 0:
                    p_run = max(p_run, min(rated_kw, min_gen_kw))
                p_gen[i] = p_run
                is_running[i] = True
                fuel_step[i] = gen_config.calc_fuel_consumption(p_run, duration_hours=dt)
        else:
            if p_act > trigger_kw:
                excess_kw = p_act - trigger_kw
                p_run = min(excess_kw, rated_kw)
                if p_run > 0 and min_gen_kw > 0:
                    p_run = max(p_run, min(rated_kw, min_gen_kw))
                # Do not exceed active load
                p_run = min(p_run, p_act)
                p_gen[i] = p_run
                is_running[i] = True
                fuel_step[i] = gen_config.calc_fuel_consumption(p_run, duration_hours=dt)

    p_grid_new = np.maximum(0.0, load_kw - p_gen)

    # Runtime & starts
    running_int = is_running.astype(int)
    starts_count = int(np.sum(np.diff(np.concatenate(([0], running_int))) == 1))
    operating_hours = float(np.sum(is_running) * dt)
    gen_energy_kwh = float(np.sum(p_gen) * dt)
    total_fuel_units = float(np.sum(fuel_step))

    fuel_cost_total = total_fuel_units * float(gen_config.fuel_price_per_unit)
    om_cost_total = operating_hours * float(gen_config.maintenance_cost_per_op_hour)
    total_operating_cost = fuel_cost_total + om_cost_total

    orig_peak_kw = float(np.max(load_kw)) if n_steps > 0 else 0.0
    new_peak_kw = float(np.max(p_grid_new)) if n_steps > 0 else 0.0
    peak_shaved_kw = max(0.0, orig_peak_kw - new_peak_kw)

    # Overload diagnostics against grid limit
    overload_before_mask = load_kw > grid_limit_kw
    overload_after_mask = p_grid_new > grid_limit_kw

    overload_hours_before = float(np.sum(overload_before_mask) * dt)
    overload_hours_after = float(np.sum(overload_after_mask) * dt)
    overload_energy_before_kwh = float(np.sum(np.maximum(0.0, load_kw - grid_limit_kw)) * dt)
    overload_energy_after_kwh = float(np.sum(np.maximum(0.0, p_grid_new - grid_limit_kw)) * dt)

    df_dispatch = pd.DataFrame({
        "timestamp": timestamps,
        "P_Load_kW": np.round(load_kw, 2),
        "P_Gen_kW": np.round(p_gen, 2),
        "P_Grid_kW": np.round(p_grid_new, 2),
        "Fuel_Units": np.round(fuel_step, 3),
        "Is_Running": is_running,
    })

    kpis = GeneratorKPIs(
        total_generation_kwh=gen_energy_kwh,
        total_fuel_units=total_fuel_units,
        operating_hours=operating_hours,
        starts_count=starts_count,
        fuel_cost_total=fuel_cost_total,
        om_cost_total=om_cost_total,
        total_operating_cost=total_operating_cost,
        levelized_cost_per_kwh=(total_operating_cost / max(1.0, gen_energy_kwh)),
        residual_demand_before_kwh=float(np.sum(load_kw) * dt),
        residual_demand_after_kwh=float(np.sum(p_grid_new) * dt),
        peak_shaved_kw=peak_shaved_kw,
        orig_peak_kw=orig_peak_kw,
        new_peak_kw=new_peak_kw,
    )

    return {
        "df_dispatch": df_dispatch,
        "kpis": kpis,
        "p_gen_kw": p_gen,
        "p_grid_kw": p_grid_new,
        "operating_hours": operating_hours,
        "starts_count": starts_count,
        "total_fuel_units": total_fuel_units,
        "total_operating_cost": total_operating_cost,
        "peak_shaved_kw": peak_shaved_kw,
        "orig_peak_kw": orig_peak_kw,
        "new_peak_kw": new_peak_kw,
        "overload_hours_before": overload_hours_before,
        "overload_hours_after": overload_hours_after,
        "overload_energy_before_kwh": overload_energy_before_kwh,
        "overload_energy_after_kwh": overload_energy_after_kwh,
        "trigger_kw": trigger_kw,
    }


def compute_generator_sizing_sweep(
    load_kw: np.ndarray,
    grid_limit_kw: float,
    timestamps: pd.DatetimeIndex,
    base_config: GeneratorConfig,
    num_points: int = 12,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Sweeps generator rated capacity from 0 kW up to max overload breach + 25%,
    evaluating avoided overload hours (%), peak shaved (kW), and fuel consumption.
    Returns (df_sweep, presets_dict).
    """
    max_load = float(np.max(load_kw))
    max_breach = max(10.0, max_load - grid_limit_kw)
    max_sweep_kw = max_breach * 1.25

    step_sizes = np.linspace(10.0, max_sweep_kw, num_points)
    rows = []

    # Baseline overload without generator
    dt = 0.25
    base_overload_mask = load_kw > grid_limit_kw
    base_overload_hours = float(np.sum(base_overload_mask) * dt)
    base_overload_kwh = float(np.sum(np.maximum(0.0, load_kw - grid_limit_kw)) * dt)

    for kw_val in step_sizes:
        cfg = GeneratorConfig(
            rated_power_kw=float(kw_val),
            fuel_type=base_config.fuel_type,
            min_load_ratio_pct=base_config.min_load_ratio_pct,
            fuel_curve_slope_l_per_kwh=base_config.fuel_curve_slope_l_per_kwh,
            fuel_curve_intercept_l_per_kw_rated=base_config.fuel_curve_intercept_l_per_kw_rated,
            dispatch_mode="peak_shaving_assist",
            peak_shaving_trigger_kw=grid_limit_kw,
            fuel_price_per_unit=base_config.fuel_price_per_unit,
            maintenance_cost_per_op_hour=base_config.maintenance_cost_per_op_hour,
        )
        res = simulate_generator_dispatch_2025(
            load_kw=load_kw,
            timestamps=timestamps,
            grid_limit_kw=grid_limit_kw,
            gen_config=cfg,
            step_hours=dt,
        )
        avoided_hrs_pct = (
            ((base_overload_hours - res["overload_hours_after"]) / max(0.1, base_overload_hours)) * 100.0
            if base_overload_hours > 0 else 100.0
        )
        avoided_energy_pct = (
            ((base_overload_kwh - res["overload_energy_after_kwh"]) / max(0.1, base_overload_kwh)) * 100.0
            if base_overload_kwh > 0 else 100.0
        )
        rows.append({
            "rated_kw": round(float(kw_val), 1),
            "avoided_overload_hours_pct": round(max(0.0, min(100.0, avoided_hrs_pct)), 1),
            "avoided_overload_energy_pct": round(max(0.0, min(100.0, avoided_energy_pct)), 1),
            "peak_shaved_kw": round(res["peak_shaved_kw"], 1),
            "new_peak_kw": round(res["new_peak_kw"], 1),
            "operating_hours": round(res["operating_hours"], 1),
            "fuel_units": round(res["total_fuel_units"], 1),
            "operating_cost": round(res["total_operating_cost"], 2),
        })

    df_sweep = pd.DataFrame(rows)

    presets = {
        "zero_breach_100": round(max_breach, 0),
        "peak_cap_80": round(max_breach * 0.80, 0),
        "peak_cap_50": round(max_breach * 0.50, 0),
    }

    return df_sweep, presets


# ======================================================================================
# Interactive Plotly Visualization Builders
# ======================================================================================

def create_generator_dispatch_timeseries_figure(
    df: pd.DataFrame,
    trigger_kw: float,
    rated_power_kw: float,
) -> go.Figure:
    """
    Constructs an interactive 15-minute dispatch timeseries figure with:
      - Quick range selector buttons: 7D, 1M, 3M, All
      - Rangeslider for flexible zoom
      - Traces: Facility Load, Generator Output (amber fill), Residual Grid Import, Trigger Line
    """
    fig = go.Figure()
    step = 2 if len(df) > 20000 else 1
    plot_df = df.iloc[::step]
    timestamps = plot_df["timestamp"]

    # 1. Facility Load
    p_load_col = "P_Load_kW" if "P_Load_kW" in plot_df.columns else "Original_Load_kW"
    p_gen_col = "P_Gen_kW" if "P_Gen_kW" in plot_df.columns else "Generator_Power_kW"
    p_grid_col = "P_Grid_kW" if "P_Grid_kW" in plot_df.columns else "New_Grid_Load_kW"

    if p_load_col in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df[p_load_col],
                name="Facility Load (kW)",
                line=dict(color="#94A3B8", width=1.5),
                connectgaps=False,
                hovertemplate="<b>%{x|%d %b %Y %H:%M}</b><br>Facility Demand: <b>%{y:,.1f} kW</b><extra></extra>",
                showlegend=True,
            )
        )

    # 2. Generator Active Output
    if p_gen_col in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df[p_gen_col],
                name="Generator Active Power (kW)",
                line=dict(color="#F59E0B", width=2.0),
                fill="tozeroy",
                fillcolor="rgba(245, 158, 11, 0.28)",
                connectgaps=False,
                hovertemplate="Generator Output: <b>%{y:,.1f} kW</b><extra></extra>",
                showlegend=True,
            )
        )

    # 3. Residual Grid Import
    if p_grid_col in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df[p_grid_col],
                name="Residual Grid Import (kW)",
                line=dict(color="#38BDF8", width=1.5, dash="dash"),
                connectgaps=False,
                hovertemplate="Grid Import: <b>%{y:,.1f} kW</b><extra></extra>",
                showlegend=True,
            )
        )

    # 4. Trigger / Grid Limit Line
    if trigger_kw > 0:
        fig.add_hline(
            y=trigger_kw,
            line_dash="dash",
            line_color="#EF4444",
            line_width=2,
            annotation_text=f"Grid Limit / Trigger ({trigger_kw:,.0f} kW)",
            annotation_position="top left",
            annotation_font_color="#EF4444",
        )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>15-Minute Electrical Dispatch Profile (Generator vs. Facility Demand)</b> "
                 f"<span style='font-size:12px; color:#94A3B8;'>({rated_power_kw:,.0f} kW Rated Capacity)</span>",
            font=dict(size=14, color="#F8FAFC"),
        ),
        xaxis=dict(
            title="Date & Time",
            rangeslider=dict(visible=True, thickness=0.06),
            rangeselector=dict(
                buttons=list([
                    dict(count=7, label="7D", step="day", stepmode="backward"),
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(step="all", label="All"),
                ]),
                bgcolor="#1E293B",
                activecolor="#2563EB",
                font=dict(color="#F8FAFC", size=10),
            ),
            type="date",
            gridcolor="#1E293B",
        ),
        yaxis=dict(
            title="Active Power (kW)",
            gridcolor="#1E293B",
            zerolinecolor="#334155",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11),
        ),
        margin=dict(l=20, r=20, t=60, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=440,
    )

    return fig


def create_generator_monthly_fuel_figure(df: pd.DataFrame, fuel_type: str = "Diesel") -> go.Figure:
    """
    Constructs a 12-month dual-axis bar chart:
      - Primary Axis (Left, Amber Bars): Monthly Generator Electricity (MWh)
      - Secondary Axis (Right, Blue Line): Monthly Fuel Consumed (L or m³)
    """
    df_calc = df.copy()
    if "timestamp" in df_calc.columns:
        df_calc["month"] = pd.to_datetime(df_calc["timestamp"]).dt.month
    else:
        df_calc["month"] = 1

    months_idx = list(range(1, 13))
    gen_mwh_list = []
    fuel_units_list = []
    dt_hours = 0.25

    for m in months_idx:
        m_df = df_calc[df_calc["month"] == m]
        if not m_df.empty:
            g_col = "P_Gen_kW" if "P_Gen_kW" in m_df.columns else "Generator_Power_kW"
            f_col = "Fuel_Units" if "Fuel_Units" in m_df.columns else "Fuel_Liters"
            m_gen_kwh = float(m_df[g_col].sum() * dt_hours) if g_col in m_df.columns else 0.0
            m_fuel = float(m_df[f_col].sum()) if f_col in m_df.columns else 0.0
        else:
            m_gen_kwh, m_fuel = 0.0, 0.0

        gen_mwh_list.append(m_gen_kwh / 1000.0)
        fuel_units_list.append(m_fuel)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Left: Generator Output Bar
    fig.add_trace(
        go.Bar(
            name="Generator Generation (MWh)",
            x=MONTH_NAMES,
            y=gen_mwh_list,
            marker_color="#F59E0B",
            hovertemplate="<b>%{x}</b> - Generation: <b>%{y:,.2f} MWh</b><extra></extra>",
        ),
        secondary_y=False,
    )

    # Right: Fuel Consumption Line
    unit_label = "m³" if fuel_type == "Natural Gas" else "Liters"
    fig.add_trace(
        go.Scatter(
            name=f"Fuel Consumption ({unit_label})",
            x=MONTH_NAMES,
            y=fuel_units_list,
            mode="lines+markers",
            line=dict(color="#38BDF8", width=2.5),
            marker=dict(size=7),
            hovertemplate=f"Fuel: <b>%{{y:,.0f}} {unit_label}</b><extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text="<b>Monthly Generator Generation & Fuel Consumption</b>", font=dict(size=14, color="#F8FAFC")),
        xaxis=dict(gridcolor="#1E293B"),
        margin=dict(l=20, r=20, t=50, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
    )
    fig.update_yaxes(title_text="Generation (MWh)", gridcolor="#1E293B", secondary_y=False)
    fig.update_yaxes(title_text=f"Fuel ({unit_label})", gridcolor="#1E293B", secondary_y=True)

    return fig


def create_generator_sankey_figure(
    total_load_kwh: float,
    gen_kwh: float,
    grid_kwh: float,
    fuel_units: float,
    fuel_type: str = "Diesel",
) -> go.Figure:
    """
    Constructs a Sankey diagram tracing Energy Sources (Grid + Genset Fuel) -> Facility Sinks.
    """
    load_val = max(1.0, total_load_kwh)
    gen_val = max(0.0, gen_kwh)
    grid_val = max(0.0, grid_kwh)

    unit_lbl = "m³" if fuel_type == "Natural Gas" else "L"
    nodes_labels = [
        f"<b>Grid Electricity Supply</b><br>{grid_val:,.0f} kWh ({(grid_val/load_val*100):.1f}%)",
        f"<b>On-Site Generator</b><br>{gen_val:,.0f} kWh ({(gen_val/load_val*100):.1f}%)<br><i>{fuel_units:,.0f} {unit_lbl} Fuel</i>",
        f"<b>Total Facility Demand</b><br>{load_val:,.0f} kWh (100%)",
    ]

    nodes_colors = [
        "#38BDF8",  # Grid (Sky Blue)
        "#F59E0B",  # Generator (Amber)
        "#64748B",  # Facility Load (Slate)
    ]

    links_source = [0, 1]
    links_target = [2, 2]
    links_value = [max(1.0, grid_val), max(0.1, gen_val)]

    fig = go.Figure(
        go.Sankey(
            node=dict(
                pad=20,
                thickness=25,
                line=dict(color="#0B0F19", width=1.5),
                label=nodes_labels,
                color=nodes_colors,
            ),
            link=dict(
                source=links_source,
                target=links_target,
                value=links_value,
                color=["rgba(56, 189, 248, 0.40)", "rgba(245, 158, 11, 0.45)"],
            ),
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text="<b>Energy Balance & Dispatch Sinks (Sankey Diagram)</b>", font=dict(size=14, color="#F8FAFC")),
        font=dict(size=11, color="#F8FAFC"),
        margin=dict(l=20, r=20, t=50, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380,
    )

    return fig


def create_generator_sweep_figure(
    df_sweep: pd.DataFrame,
    selected_kw: float,
) -> go.Figure:
    """
    Dual-axis curve displaying:
      - Left: Avoided Overload Breach Hours (%) [Amber]
      - Right: Annual Fuel Consumption (L or m³) [Blue line]
      - Selected capacity vertical dashed marker
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=df_sweep["rated_kw"],
            y=df_sweep["avoided_overload_hours_pct"],
            name="Avoided Overload Hours (%)",
            mode="lines+markers",
            line=dict(color="#F59E0B", width=2.5),
            marker=dict(size=7),
            hovertemplate="Generator: <b>%{x:,.0f} kW</b><br>Avoided Overload: <b>%{y:.1f}%</b><extra></extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=df_sweep["rated_kw"],
            y=df_sweep["fuel_units"],
            name="Annual Fuel Burn (Units)",
            mode="lines+markers",
            line=dict(color="#38BDF8", width=2.0, dash="dash"),
            marker=dict(size=6),
            hovertemplate="Generator: <b>%{x:,.0f} kW</b><br>Fuel: <b>%{y:,.0f} units</b><extra></extra>",
        ),
        secondary_y=True,
    )

    # Selected marker line
    if selected_kw > 0:
        fig.add_vline(
            x=selected_kw,
            line_dash="dot",
            line_color="#10B981",
            line_width=2,
            annotation_text=f"Active: {selected_kw:,.0f} kW",
            annotation_position="top left",
            annotation_font_color="#10B981",
        )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text="<b>Generator Sizing Tradeoff: Avoided Overload vs. Fuel Burn</b>", font=dict(size=14, color="#F8FAFC")),
        xaxis=dict(title="Generator Continuous Rated Capacity (kW)", gridcolor="#1E293B"),
        margin=dict(l=20, r=20, t=50, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
    )
    fig.update_yaxes(title_text="Avoided Overload Hours (%)", gridcolor="#1E293B", secondary_y=False)
    fig.update_yaxes(title_text="Fuel Burn (Units/yr)", gridcolor="#1E293B", secondary_y=True)

    return fig

