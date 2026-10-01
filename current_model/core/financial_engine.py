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
  - Monthly payment timeseries schedule (Zahlungsreihe) across the full duration
  - Itemized invoice tables and normalized monthly vs. period cost totals
"""

from typing import Union, Optional, List, Dict, Any, Tuple
import datetime
import numpy as np
import pandas as pd

from current_model.models.contract import Contract
from current_model.models.financial import CostLineItem, MonthlyPaymentRecord, FinancialCostBreakdown
from current_model.core.market_price_engine import get_aligned_market_prices

DAYS_PER_MONTH = 30.4167  # Average days per month across the year


def _calculate_taxes_for_subtotal(
    subtotal_net: float,
    consumption_kwh: float,
    months_count: float,
    taxes_and_fees_config: List[Dict[str, Any]]
) -> float:
    """Helper to evaluate taxes and levies given a net subtotal and kWh consumption."""
    tax_sum = 0.0
    for tax in taxes_and_fees_config:
        t_type = tax.get("type", "percentage")
        t_val = float(tax.get("value", 0.0))
        if t_type == "percentage":
            tax_sum += subtotal_net * (t_val / 100.0)
        elif t_type == "per_kwh":
            tax_sum += consumption_kwh * t_val
        else:  # fixed_monthly
            tax_sum += t_val * months_count
    return tax_sum


def _resolve_contract_for_month(
    contract_input: Union[Contract, List[Contract], Dict[Any, Contract]],
    month_val: Any,
    default_contract: Optional[Contract] = None
) -> Contract:
    """
    Finds the applicable Contract for a given month (1-12, or month name).
    If a list of contracts is provided, searches in reverse for the first matching contract
    whose applicable_months contains month_val. If none matches, returns default_contract.
    """
    if isinstance(contract_input, Contract):
        return contract_input
    if isinstance(contract_input, dict):
        if isinstance(month_val, int) and month_val in contract_input:
            return contract_input[month_val]
        m_str = str(month_val).strip().lower()
        for k, v in contract_input.items():
            if str(k).strip().lower() == m_str:
                return v
            if isinstance(v, Contract) and v.applies_to_month(month_val):
                return v
        return default_contract or next(iter(contract_input.values()))
    if isinstance(contract_input, list):
        if not contract_input:
            return default_contract or Contract()
        for c in reversed(contract_input):
            if isinstance(c, Contract) and c.applies_to_month(month_val):
                return c
        return default_contract or contract_input[0]
    return default_contract or Contract()


def compute_financial_bill(
    load_data: Union[pd.DataFrame, np.ndarray, List[float]],
    contract: Union[Contract, List[Contract], Dict[Any, Contract]],
    duration_days: Optional[float] = None,
    step_hours: float = 0.25,
    target_month: Optional[str] = None
) -> FinancialCostBreakdown:
    """
    Evaluates a load curve against a Contract (or portfolio of monthly Contracts) to generate
    a comprehensive, itemized financial assessment including monthly payment timeseries schedule
    across the full duration, or focused on a specific target month.
    """
    # Determine primary contract for general metadata fallback
    if isinstance(contract, list):
        primary_contract = contract[0] if contract else Contract()
    elif isinstance(contract, dict):
        primary_contract = next(iter(contract.values())) if contract else Contract()
    else:
        primary_contract = contract

    # If a specific target month is requested (e.g. 'Feb 2026'), compute full series first then isolate target month
    if target_month and isinstance(load_data, pd.DataFrame) and "timestamp" in load_data.columns:
        full_breakdown = compute_financial_bill(load_data, contract, duration_days=duration_days, step_hours=step_hours, target_month=None)
        ts = pd.to_datetime(load_data["timestamp"], errors="coerce")
        mask = (ts.dt.strftime("%b %Y") == target_month)
        if mask.any():
            month_df = load_data.loc[mask].copy()
            month_days = len(month_df) * step_hours / 24.0
            month_contract = _resolve_contract_for_month(contract, target_month, default_contract=primary_contract)
            month_breakdown = compute_financial_bill(
                load_data=month_df,
                contract=month_contract,
                duration_days=month_days,
                step_hours=step_hours,
                target_month=None
            )
            # Reattach full monthly series so charts can still display the full timeline
            month_breakdown.monthly_series = full_breakdown.monthly_series
            return month_breakdown

    currency = getattr(primary_contract, "currency", "ARS")

    # 1. Standardize input data and calculate duration & sampling
    if isinstance(load_data, pd.DataFrame):
        df_clean_ref = load_data.copy()
        if "Total_Demand_kW" in df_clean_ref.columns:
            df_clean_ref["Total_Demand_kW"] = pd.to_numeric(df_clean_ref["Total_Demand_kW"], errors="coerce").fillna(0.0)
            power_series = df_clean_ref["Total_Demand_kW"]
        else:
            num_cols = df_clean_ref.select_dtypes(include=[np.number]).columns
            df_clean_ref[num_cols] = df_clean_ref[num_cols].fillna(0.0)
            power_series = df_clean_ref[num_cols].sum(axis=1) if len(num_cols) > 0 else pd.Series([0.0])

        count = len(df_clean_ref)

        if "timestamp" in df_clean_ref.columns and count > 0:
            ts_series = pd.to_datetime(df_clean_ref["timestamp"], errors="coerce")
            t_min = ts_series.min()
            t_max = ts_series.max()
            if duration_days is None:
                if count > 1 and pd.notnull(t_min) and pd.notnull(t_max):
                    sec_diff = (t_max - t_min).total_seconds()
                    duration_days = max(1.0, sec_diff / 86400.0)
                    if len(ts_series) > 1 and pd.notnull(ts_series.iloc[0]) and pd.notnull(ts_series.iloc[1]):
                        dt_sec = (ts_series.iloc[1] - ts_series.iloc[0]).total_seconds()
                        if dt_sec > 0:
                            step_hours = dt_sec / 3600.0
                else:
                    duration_days = max(1.0, (count * step_hours) / 24.0)

            timestamps = ts_series.tolist()
            df_clean_ref["timestamp"] = ts_series
        else:
            if duration_days is None:
                duration_days = max(1.0, (count * step_hours) / 24.0)
            timestamps = None

        powers = np.nan_to_num(power_series.to_numpy(dtype=float), nan=0.0)

    else:
        powers = np.nan_to_num(np.asarray(load_data, dtype=float), nan=0.0)
        count = len(powers)
        duration_days = duration_days if duration_days is not None else max(1.0, (count * step_hours) / 24.0)
        timestamps = None
        df_clean_ref = None

    months_in_period = duration_days / DAYS_PER_MONTH
    monthly_multiplier = DAYS_PER_MONTH / duration_days

    total_consumption_kwh = float(powers.sum() * step_hours)
    peak_demand_kw = float(powers.max()) if len(powers) > 0 else 0.0
    contracted_kw = float(getattr(contract, "contracted_capacity_kw", 0.0))
    cap_tariff = float(getattr(contract, "monthly_capacity_tariff", 0.0))
    penalty_rate = float(getattr(contract, "peak_penalty_rate", 0.0))
    base_fee_monthly = float(getattr(contract, "base_monthly_fee", 0.0))
    taxes_and_fees_config = getattr(contract, "taxes_and_fees", [])

    # 2. Compute Active Energy Costs across Dynamic TOU Windows or Day-Ahead Spot Market
    is_primary_dynamic = (getattr(primary_contract, "pricing_model", "time_of_use") == "day_ahead_dynamic")
    line_items: List[CostLineItem] = []
    total_energy_period = 0.0

    if is_primary_dynamic:
        profile_id = getattr(primary_contract, "market_price_profile_id", "epex_nl_2025") or "epex_nl_2025"
        def_rate = getattr(primary_contract, "default_energy_rate", 0.20)
        supp_margin = float(getattr(primary_contract, "supplier_margin", 0.0))

        aligned_spot_prices = get_aligned_market_prices(
            timestamps=timestamps,
            profile_id=profile_id,
            default_rate=def_rate,
            n_steps=count,
            step_hours=step_hours
        )

        spot_cost_period = float(np.sum(powers * step_hours * aligned_spot_prices))
        margin_cost_period = float(np.sum(powers * step_hours * supp_margin))
        total_energy_period = spot_cost_period + margin_cost_period

        avg_spot_rate = (spot_cost_period / total_consumption_kwh) if total_consumption_kwh > 0 else def_rate
        profile_label = "EPEX Spot NL 2025" if "nl" in profile_id.lower() else profile_id.upper()
        line_items.append(
            CostLineItem(
                category="Energy (Active)",
                description=f"Day-Ahead Spot Energy ({profile_label})",
                basis_quantity=round(total_consumption_kwh, 2),
                unit="kWh",
                unit_rate=round(avg_spot_rate, 4),
                cost_period=round(spot_cost_period, 2),
                cost_monthly=round(spot_cost_period * monthly_multiplier, 2)
            )
        )
        if supp_margin > 0:
            line_items.append(
                CostLineItem(
                    category="Energy (Active)",
                    description="Supplier Surcharge / Margin (Opslag)",
                    basis_quantity=round(total_consumption_kwh, 2),
                    unit="kWh",
                    unit_rate=supp_margin,
                    cost_period=round(margin_cost_period, 2),
                    cost_monthly=round(margin_cost_period * monthly_multiplier, 2)
                )
            )
    else:
        tou_rates_config = getattr(contract, "tou_rates", [])
        if not tou_rates_config:
            def_rate = getattr(contract, "default_energy_rate", 0.20)
            tou_rates_config = [{"name": "Standard Rate", "rate": def_rate, "start_time": "00:00", "end_time": "24:00"}]

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

        # Evaluate each interval
        for idx, p_kw in enumerate(powers):
            slot_kwh = p_kw * step_hours

            if timestamps and idx < len(timestamps) and pd.notnull(timestamps[idx]):
                dt = timestamps[idx]
                slot_month = dt.month if hasattr(dt, "month") else 1
                slot_contract = _resolve_contract_for_month(contract, slot_month, default_contract=primary_contract)
            else:
                minute_of_day = int((idx * (step_hours * 60)) % 1440)
                dt = datetime.time(minute_of_day // 60, minute_of_day % 60)
                slot_contract = primary_contract

            matched_bucket_name = None
            matched_rate = slot_contract.get_energy_rate(dt)

            for tou in tou_rates_config:
                if float(tou.get("rate", 0.0)) == matched_rate:
                    matched_bucket_name = tou.get("name")
                    break

            if not matched_bucket_name:
                matched_bucket_name = tou_rates_config[0].get("name", "Standard Rate")

            if matched_bucket_name in tou_energy_buckets:
                tou_energy_buckets[matched_bucket_name]["kwh"] += slot_kwh
                tou_energy_buckets[matched_bucket_name]["cost"] += (slot_kwh * matched_rate)

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

    # 3. Contracted Capacity Charge (Uso de Red)
    capacity_cost_monthly = contracted_kw * cap_tariff
    capacity_cost_period = capacity_cost_monthly * months_in_period

    if contracted_kw > 0 and cap_tariff > 0:
        line_items.append(
            CostLineItem(
                category="Capacity (Contracted)",
                description=f"Contracted Capacity ({contracted_kw:.1f} kW)",
                basis_quantity=contracted_kw,
                unit="kW",
                unit_rate=cap_tariff,
                cost_period=round(capacity_cost_period, 2),
                cost_monthly=round(capacity_cost_monthly, 2)
            )
        )

    # 3b. Measured Demand Capacity Charge (Consumo de Potencia)
    demand_cap_tariff = float(getattr(contract, "demand_capacity_tariff", 0.0))
    demand_cost_monthly = peak_demand_kw * demand_cap_tariff if demand_cap_tariff > 0 else 0.0
    demand_cost_period = demand_cost_monthly * months_in_period

    if peak_demand_kw > 0 and demand_cap_tariff > 0:
        line_items.append(
            CostLineItem(
                category="Demand (Measured)",
                description=f"Measured Peak Demand ({peak_demand_kw:.1f} kW)",
                basis_quantity=peak_demand_kw,
                unit="kW",
                unit_rate=demand_cap_tariff,
                cost_period=round(demand_cost_period, 2),
                cost_monthly=round(demand_cost_monthly, 2)
            )
        )

    # 3c. Regulated Grid Transport / Volume Charge (Netznutzungsentgelt Enexis)
    net_vol_tariff = float(getattr(primary_contract, "network_volume_tariff", 0.0))
    net_vol_cost_period = total_consumption_kwh * net_vol_tariff
    net_vol_cost_monthly = net_vol_cost_period * monthly_multiplier

    if net_vol_tariff > 0:
        line_items.append(
            CostLineItem(
                category="Network (Volume)",
                description=f"Grid Transport Volume Fee ({net_vol_tariff:.4f} {currency}/kWh)",
                basis_quantity=round(total_consumption_kwh, 2),
                unit="kWh",
                unit_rate=net_vol_tariff,
                cost_period=round(net_vol_cost_period, 2),
                cost_monthly=round(net_vol_cost_monthly, 2)
            )
        )

    # 4. Peak Overload Penalty (Exceso de Potencia)
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

    # 5. Base Monthly Fee (Cargo Comercialización / Vastrecht)
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

    # 6. Reactive Power Costs
    reactive_cost_monthly = 0.0
    reactive_cost_period = 0.0

    # Net Subtotals
    total_net_period = total_energy_period + capacity_cost_period + demand_cost_period + penalty_cost_period + base_fee_period + reactive_cost_period + net_vol_cost_period
    total_net_monthly = total_energy_monthly + capacity_cost_monthly + demand_cost_monthly + penalty_cost_monthly + base_fee_monthly + reactive_cost_monthly + net_vol_cost_monthly

    # 7. Taxes & Dynamic Levies
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

    for item in line_items:
        item.share_pct = round((item.cost_period / total_gross_period * 100.0), 1) if total_gross_period > 0 else 0.0

    effective_kwh_price = (total_gross_period / total_consumption_kwh) if total_consumption_kwh > 0 else 0.0
    fixed_costs_monthly = capacity_cost_monthly + base_fee_monthly
    fixed_share = (fixed_costs_monthly / total_gross_monthly * 100.0) if total_gross_monthly > 0 else 0.0
    variable_share = (total_energy_monthly / total_gross_monthly * 100.0) if total_gross_monthly > 0 else 0.0
    capacity_utilization = (peak_demand_kw / contracted_kw * 100.0) if contracted_kw > 0 else 0.0

    # 8. Construct Full-Duration Monthly Payment Series (Zahlungsreihe)
    monthly_series: List[MonthlyPaymentRecord] = []

    # Case A: Real timestamped data from CSV or annual timeseries
    is_real_timestamped_data = False
    if df_clean_ref is not None and "timestamp" in df_clean_ref.columns:
        ts_series = pd.to_datetime(df_clean_ref["timestamp"], errors="coerce")
        if ts_series.notnull().any():
            unique_periods = ts_series.dropna().dt.to_period("M").unique()
            if len(unique_periods) >= 1:
                is_real_timestamped_data = True
                for period in unique_periods:
                    mask = (ts_series.dt.to_period("M") == period)
                    sub_df = df_clean_ref.loc[mask]
                    if "Total_Demand_kW" in sub_df.columns:
                        sub_powers = np.nan_to_num(sub_df["Total_Demand_kW"].to_numpy(dtype=float), nan=0.0)
                    else:
                        sub_powers = np.nan_to_num(sub_df.select_dtypes(include=[np.number]).sum(axis=1).to_numpy(dtype=float), nan=0.0)
                    sub_ts = sub_df["timestamp"].tolist()

                    sub_kwh = float(sub_powers.sum() * step_hours)
                    sub_peak = float(sub_powers.max()) if len(sub_powers) > 0 else 0.0
                    sub_days = max(1.0, len(sub_df) * step_hours / 24.0)

                    # Determine contract for this specific month
                    sub_month_int = period.month
                    sub_contract = _resolve_contract_for_month(contract, sub_month_int, default_contract=primary_contract)

                    sub_contracted_kw = float(getattr(sub_contract, "contracted_capacity_kw", 0.0))
                    sub_cap_tariff = float(getattr(sub_contract, "monthly_capacity_tariff", 0.0))
                    sub_demand_cap_tariff = float(getattr(sub_contract, "demand_capacity_tariff", 0.0))
                    sub_penalty_rate = float(getattr(sub_contract, "peak_penalty_rate", 0.0))
                    sub_base_monthly = float(getattr(sub_contract, "base_monthly_fee", 0.0))
                    sub_taxes_config = getattr(sub_contract, "taxes_and_fees", [])
                    sub_pricing_model = getattr(sub_contract, "pricing_model", "time_of_use")
                    sub_supp_margin = float(getattr(sub_contract, "supplier_margin", 0.0))
                    sub_net_vol_tariff = float(getattr(sub_contract, "network_volume_tariff", 0.0))
                    sub_net_vol_cost = sub_kwh * sub_net_vol_tariff

                    # Compute energy cost for this calendar month
                    if sub_pricing_model == "day_ahead_dynamic":
                        sub_profile_id = getattr(sub_contract, "market_price_profile_id", "epex_nl_2025") or "epex_nl_2025"
                        sub_def_rate = getattr(sub_contract, "default_energy_rate", 0.20)
                        sub_spot_prices = get_aligned_market_prices(
                            timestamps=sub_ts,
                            profile_id=sub_profile_id,
                            default_rate=sub_def_rate,
                            n_steps=len(sub_powers),
                            step_hours=step_hours
                        )
                        sub_energy_cost = float(np.sum(sub_powers * step_hours * (sub_spot_prices + sub_supp_margin)))
                    else:
                        sub_energy_cost = 0.0
                        for s_idx, s_kw in enumerate(sub_powers):
                            s_dt = sub_ts[s_idx]
                            sub_energy_cost += (s_kw * step_hours * sub_contract.get_energy_rate(s_dt))

                    # Capacity & Demand & Base fees for this month
                    sub_cap_cost = sub_contracted_kw * sub_cap_tariff + (sub_peak * sub_demand_cap_tariff)
                    sub_excess = max(0.0, sub_peak - sub_contracted_kw)
                    sub_penalty = sub_excess * sub_penalty_rate
                    sub_base = sub_base_monthly
                    sub_net = sub_energy_cost + sub_cap_cost + sub_penalty + sub_base + sub_net_vol_cost
                    sub_taxes = _calculate_taxes_for_subtotal(sub_net, sub_kwh, 1.0, sub_taxes_config)
                    sub_gross = sub_net + sub_taxes
                    sub_rate = (sub_gross / sub_kwh) if sub_kwh > 0 else 0.0

                    monthly_series.append(
                        MonthlyPaymentRecord(
                            period_label=period.strftime("%b %Y"),
                            days_count=int(round(sub_days)),
                            energy_kwh=round(sub_kwh, 2),
                            peak_demand_kw=round(sub_peak, 2),
                            energy_cost_net=round(sub_energy_cost, 2),
                            capacity_cost_net=round(sub_cap_cost, 2),
                            penalty_cost_net=round(sub_penalty, 2),
                            base_fee_net=round(sub_base, 2),
                            reactive_cost_net=0.0,
                            total_net=round(sub_net, 2),
                            taxes_and_levies=round(sub_taxes, 2),
                            total_gross=round(sub_gross, 2),
                            effective_rate_kwh=round(sub_rate, 4),
                            network_cost_net=round(sub_net_vol_cost, 2)
                        )
                    )

    # Case B: Standard 12-month calendar schedule for 24h synthetic typical daily profile (no real calendar dates)
    if not is_real_timestamped_data:
        daily_kwh = total_consumption_kwh / max(1.0, duration_days)
        month_days_calendar = [
            ("January", 31), ("February", 28), ("March", 31), ("April", 30),
            ("May", 31), ("June", 30), ("July", 31), ("August", 31),
            ("September", 30), ("October", 31), ("November", 30), ("December", 31)
        ]

        for m_idx, (m_name, m_days) in enumerate(month_days_calendar, start=1):
            m_contract = _resolve_contract_for_month(contract, m_idx, default_contract=primary_contract)
            m_contracted_kw = float(getattr(m_contract, "contracted_capacity_kw", 0.0))
            m_cap_tariff = float(getattr(m_contract, "monthly_capacity_tariff", 0.0))
            m_demand_cap_tariff = float(getattr(m_contract, "demand_capacity_tariff", 0.0))
            m_penalty_rate = float(getattr(m_contract, "peak_penalty_rate", 0.0))
            m_base_monthly = float(getattr(m_contract, "base_monthly_fee", 0.0))
            m_taxes_config = getattr(m_contract, "taxes_and_fees", [])
            m_pricing_model = getattr(m_contract, "pricing_model", "time_of_use")
            m_supp_margin = float(getattr(m_contract, "supplier_margin", 0.0))
            m_net_vol_tariff = float(getattr(m_contract, "network_volume_tariff", 0.0))

            if m_pricing_model == "day_ahead_dynamic":
                m_profile_id = getattr(m_contract, "market_price_profile_id", "epex_nl_2025") or "epex_nl_2025"
                m_def_rate = getattr(m_contract, "default_energy_rate", 0.20)
                m_spot_prices = get_aligned_market_prices(
                    timestamps=timestamps,
                    profile_id=m_profile_id,
                    default_rate=m_def_rate,
                    n_steps=len(powers),
                    step_hours=step_hours
                )
                m_daily_energy_cost = float(np.sum(powers * step_hours * (m_spot_prices + m_supp_margin))) / max(1.0, duration_days)
            else:
                m_daily_energy_cost = 0.0
                for idx, p_kw in enumerate(powers):
                    slot_kwh = p_kw * step_hours
                    if timestamps and idx < len(timestamps) and pd.notnull(timestamps[idx]):
                        dt = timestamps[idx]
                    else:
                        minute_of_day = int((idx * (step_hours * 60)) % 1440)
                        dt = datetime.time(minute_of_day // 60, minute_of_day % 60)
                    m_daily_energy_cost += (slot_kwh * m_contract.get_energy_rate(dt))
                m_daily_energy_cost = m_daily_energy_cost / max(1.0, duration_days)

            m_kwh = daily_kwh * m_days
            m_energy_cost = m_daily_energy_cost * m_days
            m_net_vol_cost = m_kwh * m_net_vol_tariff
            m_cap_cost = m_contracted_kw * m_cap_tariff + (peak_demand_kw * m_demand_cap_tariff)
            m_excess = max(0.0, peak_demand_kw - m_contracted_kw)
            m_penalty = m_excess * m_penalty_rate
            m_base = m_base_monthly
            m_net = m_energy_cost + m_cap_cost + m_penalty + m_base + m_net_vol_cost
            m_taxes = _calculate_taxes_for_subtotal(m_net, m_kwh, 1.0, m_taxes_config)
            m_gross = m_net + m_taxes
            m_rate = (m_gross / m_kwh) if m_kwh > 0 else 0.0

            monthly_series.append(
                MonthlyPaymentRecord(
                    period_label=m_name,
                    days_count=m_days,
                    energy_kwh=round(m_kwh, 2),
                    peak_demand_kw=round(peak_demand_kw, 2),
                    energy_cost_net=round(m_energy_cost, 2),
                    capacity_cost_net=round(m_cap_cost, 2),
                    penalty_cost_net=round(m_penalty, 2),
                    base_fee_net=round(m_base, 2),
                    reactive_cost_net=0.0,
                    total_net=round(m_net, 2),
                    taxes_and_levies=round(m_taxes, 2),
                    total_gross=round(m_gross, 2),
                    effective_rate_kwh=round(m_rate, 4),
                    network_cost_net=round(m_net_vol_cost, 2)
                )
            )

    if monthly_series:
        total_energy_period = sum(m.energy_cost_net for m in monthly_series)
        capacity_cost_period = sum(m.capacity_cost_net for m in monthly_series)
        penalty_cost_period = sum(m.penalty_cost_net for m in monthly_series)
        base_fee_period = sum(m.base_fee_net for m in monthly_series)
        total_net_period = sum(m.total_net for m in monthly_series)
        total_taxes_period = sum(m.taxes_and_levies for m in monthly_series)
        total_gross_period = sum(m.total_gross for m in monthly_series)

        m_count = max(1.0, float(len(monthly_series)))
        total_energy_monthly = total_energy_period / m_count
        capacity_cost_monthly = capacity_cost_period / m_count
        penalty_cost_monthly = penalty_cost_period / m_count
        base_fee_monthly = base_fee_period / m_count
        total_net_monthly = total_net_period / m_count
        total_taxes_monthly = total_taxes_period / m_count
        total_gross_monthly = total_gross_period / m_count

        demand_cap_tariff = float(getattr(primary_contract, "demand_capacity_tariff", 0.0))
        net_vol_tariff = float(getattr(primary_contract, "network_volume_tariff", 0.0))
        supp_margin = float(getattr(primary_contract, "supplier_margin", 0.0))

        meas_demand_sum = sum(m.peak_demand_kw * demand_cap_tariff for m in monthly_series)
        contracted_cap_sum = capacity_cost_period - meas_demand_sum

        for item in line_items:
            if item.category == "Peak Penalty":
                item.cost_period = round(penalty_cost_period, 2)
                item.cost_monthly = round(penalty_cost_monthly, 2)
            elif item.category == "Capacity (Contracted)":
                item.cost_period = round(contracted_cap_sum, 2)
                item.cost_monthly = round(contracted_cap_sum / m_count, 2)
            elif item.category == "Demand (Measured)":
                item.cost_period = round(meas_demand_sum, 2)
                item.cost_monthly = round(meas_demand_sum / m_count, 2)
            elif item.category == "Base Fee":
                item.cost_period = round(base_fee_period, 2)
                item.cost_monthly = round(base_fee_monthly, 2)
            elif item.category == "Network (Volume)":
                net_vol_sum = sum(m.energy_kwh * net_vol_tariff for m in monthly_series)
                item.cost_period = round(net_vol_sum, 2)
                item.cost_monthly = round(net_vol_sum / m_count, 2)
            elif item.category == "Energy (Active)":
                if "Supplier" in item.description or "Opslag" in item.description:
                    supp_margin_sum = sum(m.energy_kwh * supp_margin for m in monthly_series)
                    item.cost_period = round(supp_margin_sum, 2)
                    item.cost_monthly = round(supp_margin_sum / m_count, 2)
                elif is_primary_dynamic:
                    spot_sum = total_energy_period - sum(m.energy_kwh * supp_margin for m in monthly_series)
                    item.cost_period = round(spot_sum, 2)
                    item.cost_monthly = round(spot_sum / m_count, 2)
                else:
                    item.cost_period = round(total_energy_period, 2)
                    item.cost_monthly = round(total_energy_monthly, 2)
            elif item.category == "Taxes & Levies":
                # Find matching tax rule
                t_match = None
                for t in taxes_and_fees_config:
                    if t.get("name", "") in item.description:
                        t_match = t
                        break
                if t_match:
                    t_type = t_match.get("type", "percentage")
                    t_val = float(t_match.get("value", 0.0))
                    if t_type == "percentage":
                        t_cost = total_net_period * (t_val / 100.0)
                    elif t_type == "per_kwh":
                        t_cost = total_consumption_kwh * t_val
                    else:
                        t_cost = t_val * m_count
                    item.cost_period = round(t_cost, 2)
                    item.cost_monthly = round(t_cost / m_count, 2)

            item.share_pct = round((item.cost_period / total_gross_period * 100.0), 1) if total_gross_period > 0 else 0.0

        effective_kwh_price = (total_gross_period / total_consumption_kwh) if total_consumption_kwh > 0 else 0.0
        fixed_costs_monthly = capacity_cost_monthly + base_fee_monthly
        fixed_share = (fixed_costs_monthly / total_gross_monthly * 100.0) if total_gross_monthly > 0 else 0.0
        variable_share = (total_energy_monthly / total_gross_monthly * 100.0) if total_gross_monthly > 0 else 0.0


    return FinancialCostBreakdown(
        currency=currency,
        duration_days=round(duration_days, 1),
        total_consumption_kwh=round(total_consumption_kwh, 2),
        peak_demand_kw=round(peak_demand_kw, 2),
        contracted_capacity_kw=round(contracted_kw, 2),
        line_items=line_items,
        monthly_series=monthly_series,
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
