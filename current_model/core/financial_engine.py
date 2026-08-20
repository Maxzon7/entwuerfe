"""
========================================================================================
Financial & Billing Calculation Engine (current_model/core/financial_engine.py)
========================================================================================

Description:
------------
Integrates electric load profiles with electricity supply contract parameters to compute:
  - Exact Time-of-Use active energy expenditure
  - Contracted capacity charges and peak overload penalties
  - Fixed monthly base and metering fees
  - Dynamic taxes, levies, and surcharges
  - Itemized invoice tables and normalized monthly vs. period cost totals
"""

from typing import Union, Optional, List, Dict, Any
import datetime
import numpy as np
import pandas as pd

from current_model.models.contract import Contract
from current_model.models.financial import CostLineItem, FinancialCostBreakdown

DAYS_PER_MONTH = 30.4167  # Average days per month across the year


def compute_financial_bill(
    load_data: Union[pd.DataFrame, np.ndarray, List[float]],
    contract: Contract,
    duration_days: Optional[float] = None,
    step_hours: float = 0.25
) -> FinancialCostBreakdown:
    """
    Evaluates a load curve against a Contract to generate a comprehensive, itemized financial assessment.

    Args:
        load_data: DataFrame with 'Total_Demand_kW' (and optional 'timestamp') or a 96-element 24h numpy array.
        contract: Contract dataclass instance containing tariffs, capacity limits, TOU windows, and taxes.
        duration_days: Optional explicit duration in days. If None, inferred from timestamps or defaults to 1.0.
        step_hours: Interval step duration in hours (0.25 for 15-minute data).

    Returns:
        FinancialCostBreakdown with itemized invoice lines, subtotals, monthly projections, and KPIs.
    """
    currency = getattr(contract, "currency", "EUR")

    # 1. Standardize input data and calculate duration & sampling
    if isinstance(load_data, pd.DataFrame):
        if "Total_Demand_kW" in load_data.columns:
            power_series = load_data["Total_Demand_kW"].fillna(0.0)
        else:
            # Fallback to first numeric column or sum of numeric columns
            num_cols = load_data.select_dtypes(include=[np.number]).columns
            power_series = load_data[num_cols].sum(axis=1) if len(num_cols) > 0 else pd.Series([0.0])

        count = len(load_data)

        if duration_days is None:
            if "timestamp" in load_data.columns and count > 1:
                t_min = load_data["timestamp"].min()
                t_max = load_data["timestamp"].max()
                if pd.notnull(t_min) and pd.notnull(t_max):
                    sec_diff = (t_max - t_min).total_seconds()
                    duration_days = max(1.0, sec_diff / 86400.0)
                    # Sampling interval
                    dt_sec = (load_data["timestamp"].iloc[1] - load_data["timestamp"].iloc[0]).total_seconds()
                    if dt_sec > 0:
                        step_hours = dt_sec / 3600.0
                else:
                    duration_days = max(1.0, (count * step_hours) / 24.0)
            else:
                duration_days = max(1.0, (count * step_hours) / 24.0)

        timestamps = load_data["timestamp"].tolist() if "timestamp" in load_data.columns else None
        powers = power_series.to_numpy(dtype=float)

    else:
        powers = np.asarray(load_data, dtype=float)
        count = len(powers)
        duration_days = duration_days if duration_days is not None else max(1.0, (count * step_hours) / 24.0)
        timestamps = None

    months_in_period = duration_days / DAYS_PER_MONTH
    monthly_multiplier = DAYS_PER_MONTH / duration_days

    total_consumption_kwh = float(powers.sum() * step_hours)
    peak_demand_kw = float(powers.max()) if len(powers) > 0 else 0.0
    contracted_kw = float(getattr(contract, "contracted_capacity_kw", 0.0))

    # 2. Compute Active Energy Costs across Dynamic TOU Windows
    tou_rates_config = getattr(contract, "tou_rates", [])
    if not tou_rates_config:
        def_rate = getattr(contract, "default_energy_rate", 0.20)
        tou_rates_config = [{"name": "Standard Rate", "rate": def_rate, "start_time": "00:00", "end_time": "24:00"}]

    # Bucket energy into each configured TOU window
    tou_energy_buckets: Dict[str, Dict[str, Any]] = {}
    for idx, tou in enumerate(tou_rates_config):
        t_name = tou.get("name", f"Tariff {idx+1}")
        t_rate = float(tou.get("rate", 0.20))
        tou_energy_buckets[t_name] = {
            "name": t_name,
            "rate": t_rate,
            "kwh": 0.0,
            "cost": 0.0
        }

    # Evaluate each interval against TOU rules
    for idx, p_kw in enumerate(powers):
        slot_kwh = p_kw * step_hours

        if timestamps and idx < len(timestamps) and pd.notnull(timestamps[idx]):
            dt = timestamps[idx]
        else:
            # Synthetic step mapping to minute of 24h day
            minute_of_day = int((idx * (step_hours * 60)) % 1440)
            dt = datetime.time(minute_of_day // 60, minute_of_day % 60)

        # Match to correct bucket
        matched_bucket_name = None
        matched_rate = contract.get_energy_rate(dt)

        for tou in tou_rates_config:
            if float(tou.get("rate", 0.0)) == matched_rate:
                matched_bucket_name = tou.get("name")
                break

        if not matched_bucket_name:
            matched_bucket_name = tou_rates_config[0].get("name", "Standard Rate")

        if matched_bucket_name in tou_energy_buckets:
            tou_energy_buckets[matched_bucket_name]["kwh"] += slot_kwh
            tou_energy_buckets[matched_bucket_name]["cost"] += (slot_kwh * matched_rate)

    line_items: List[CostLineItem] = []
    total_energy_period = 0.0

    for b_name, b_data in tou_energy_buckets.items():
        b_kwh = float(b_data["kwh"])
        b_cost = float(b_data["cost"])
        b_rate = float(b_data["rate"])
        total_energy_period += b_cost
        b_monthly = b_cost * monthly_multiplier

        if b_kwh > 0 or len(tou_energy_buckets) == 1:
            line_items.append(
                CostLineItem(
                    category="Energy (Active)",
                    description=f"{b_name}",
                    basis_quantity=round(b_kwh, 2),
                    unit="kWh",
                    unit_rate=b_rate,
                    cost_period=round(b_cost, 2),
                    cost_monthly=round(b_monthly, 2)
                )
            )

    total_energy_monthly = total_energy_period * monthly_multiplier

    # 3. Capacity Charge
    cap_tariff = float(getattr(contract, "monthly_capacity_tariff", 0.0))
    capacity_cost_monthly = contracted_kw * cap_tariff
    capacity_cost_period = capacity_cost_monthly * months_in_period

    if contracted_kw > 0 and cap_tariff > 0:
        line_items.append(
            CostLineItem(
                category="Capacity Charge",
                description=f"Contracted Capacity ({contracted_kw:.1f} kW)",
                basis_quantity=contracted_kw,
                unit="kW",
                unit_rate=cap_tariff,
                cost_period=round(capacity_cost_period, 2),
                cost_monthly=round(capacity_cost_monthly, 2)
            )
        )

    # 4. Peak Overload Penalty (if actual peak exceeds contracted capacity)
    penalty_rate = float(getattr(contract, "peak_penalty_rate", 0.0))
    excess_kw = max(0.0, peak_demand_kw - contracted_kw)
    penalty_cost_monthly = excess_kw * penalty_rate if excess_kw > 0 else 0.0
    penalty_cost_period = penalty_cost_monthly * months_in_period

    if excess_kw > 0 and penalty_rate > 0:
        line_items.append(
            CostLineItem(
                category="Peak Penalty",
                description=f"Excess Peak Demand (+{excess_kw:.1f} kW over limit)",
                basis_quantity=excess_kw,
                unit="kW",
                unit_rate=penalty_rate,
                cost_period=round(penalty_cost_period, 2),
                cost_monthly=round(penalty_cost_monthly, 2)
            )
        )

    # 5. Base Monthly Fee
    base_fee_monthly = float(getattr(contract, "base_monthly_fee", 0.0))
    base_fee_period = base_fee_monthly * months_in_period

    if base_fee_monthly > 0:
        line_items.append(
            CostLineItem(
                category="Base Fee",
                description="Monthly Service & Metering Fee",
                basis_quantity=round(months_in_period, 2),
                unit="Month",
                unit_rate=base_fee_monthly,
                cost_period=round(base_fee_period, 2),
                cost_monthly=round(base_fee_monthly, 2)
            )
        )

    # 6. Reactive Power Costs (if applicable)
    reactive_cost_monthly = 0.0
    reactive_cost_period = 0.0

    # Net Subtotals
    total_net_period = total_energy_period + capacity_cost_period + penalty_cost_period + base_fee_period + reactive_cost_period
    total_net_monthly = total_energy_monthly + capacity_cost_monthly + penalty_cost_monthly + base_fee_monthly + reactive_cost_monthly

    # 7. Taxes & Dynamic Levies
    taxes_and_fees_config = getattr(contract, "taxes_and_fees", [])
    total_taxes_period = 0.0
    total_taxes_monthly = 0.0

    for tax in taxes_and_fees_config:
        t_name = tax.get("name", "Tax")
        t_type = tax.get("type", "percentage")
        t_val = float(tax.get("value", 0.0))

        if t_type == "percentage":
            tax_p = total_net_period * (t_val / 100.0)
            tax_m = total_net_monthly * (t_val / 100.0)
            u_str = "%"
        elif t_type == "per_kwh":
            tax_p = total_consumption_kwh * t_val
            tax_m = (total_consumption_kwh * monthly_multiplier) * t_val
            u_str = f"{currency}/kWh"
        else:  # fixed_monthly
            tax_m = t_val
            tax_p = t_val * months_in_period
            u_str = f"{currency}/Month"

        total_taxes_period += tax_p
        total_taxes_monthly += tax_m

        line_items.append(
            CostLineItem(
                category="Taxes & Levies",
                description=f"{t_name} ({t_val:.1f} {u_str})",
                basis_quantity=t_val,
                unit=u_str,
                unit_rate=t_val,
                cost_period=round(tax_p, 2),
                cost_monthly=round(tax_m, 2)
            )
        )

    # Gross Totals
    total_gross_period = total_net_period + total_taxes_period
    total_gross_monthly = total_net_monthly + total_taxes_monthly

    # Calculate percentage share for each line item
    for item in line_items:
        item.share_pct = round((item.cost_period / total_gross_period * 100.0), 1) if total_gross_period > 0 else 0.0

    # Key Performance Indicators
    effective_kwh_price = (total_gross_period / total_consumption_kwh) if total_consumption_kwh > 0 else 0.0
    fixed_costs_monthly = capacity_cost_monthly + base_fee_monthly
    fixed_share = (fixed_costs_monthly / total_gross_monthly * 100.0) if total_gross_monthly > 0 else 0.0
    variable_share = (total_energy_monthly / total_gross_monthly * 100.0) if total_gross_monthly > 0 else 0.0
    capacity_utilization = (peak_demand_kw / contracted_kw * 100.0) if contracted_kw > 0 else 0.0

    return FinancialCostBreakdown(
        currency=currency,
        duration_days=round(duration_days, 1),
        total_consumption_kwh=round(total_consumption_kwh, 2),
        peak_demand_kw=round(peak_demand_kw, 2),
        contracted_capacity_kw=round(contracted_kw, 2),
        line_items=line_items,
        energy_cost_period=round(total_energy_period, 2),
        energy_cost_monthly=round(total_energy_monthly, 2),
        capacity_cost_period=round(capacity_cost_period, 2),
        capacity_cost_monthly=round(capacity_cost_monthly, 2),
        penalty_cost_period=round(penalty_cost_period, 2),
        penalty_cost_monthly=round(penalty_cost_monthly, 2),
        base_fee_period=round(base_fee_period, 2),
        base_fee_monthly=round(base_fee_monthly, 2),
        reactive_cost_period=round(reactive_cost_period, 2),
        reactive_cost_monthly=round(reactive_cost_monthly, 2),
        total_net_period=round(total_net_period, 2),
        total_net_monthly=round(total_net_monthly, 2),
        total_taxes_period=round(total_taxes_period, 2),
        total_taxes_monthly=round(total_taxes_monthly, 2),
        total_gross_period=round(total_gross_period, 2),
        total_gross_monthly=round(total_gross_monthly, 2),
        effective_kwh_price=round(effective_kwh_price, 4),
        fixed_cost_share_pct=round(fixed_share, 1),
        variable_cost_share_pct=round(variable_share, 1),
        capacity_utilization_pct=round(capacity_utilization, 1)
    )
