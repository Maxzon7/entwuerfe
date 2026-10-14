"""
========================================================================================
Layer 5: Commercial Supplier Accounting (engine/commercial_accounting.py)
Current Situation (Status Quo) Sandbox Engine
========================================================================================
Implements the 5-component Dutch Grootverbruik commercial supplier invoice:
  1. Commodity Base (Fixed, Variable, Dynamic Spot, or Tranche / Click)
  2. Supplier Markup (Leveranciersopslag €/kWh)
  3. Balancing Fee (Onbalanskosten €/kWh)
  4. Green Certificates (GvO €/kWh)
  5. Standing Base Fee (Vastrecht levering €/month)
========================================================================================
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd

try:
    from .config_and_models import (
        LoadSeries2025,
        SupplierTariff,
        PricingMode,
        TrancheBlock,
        MonthlyConsumptionRecord,
        CommercialMonthlyResult,
    )
except (ImportError, ValueError):
    from config_and_models import (
        LoadSeries2025,
        SupplierTariff,
        PricingMode,
        TrancheBlock,
        MonthlyConsumptionRecord,
        CommercialMonthlyResult,
    )

try:
    from current_model.core.market_price_engine import load_market_price_series
except ImportError:
    pass


# In-memory spot price cache to avoid repeating expensive timezone localization & re-indexing
_SPOT_PRICE_CACHE: Dict[Tuple[str, float, int], np.ndarray] = {}


def align_spot_prices_amsterdam_2025(
    load: LoadSeries2025,
    supplier_tariff: SupplierTariff
) -> np.ndarray:
    """
    Aligns 35,040 EPEX Spot wholesale electricity prices for the reference year 2025.
    Uses in-memory caching to eliminate redundant timezone conversions and re-indexing.
    """
    default_rate = float(supplier_tariff.spot_default_fallback_rate)
    profile_id = supplier_tariff.market_price_profile_id or "epex_nl_2025"
    cache_key = (profile_id, default_rate, len(load.power_kw))

    if cache_key in _SPOT_PRICE_CACHE:
        return _SPOT_PRICE_CACHE[cache_key].copy()

    try:
        spot_df = load_market_price_series(profile_id=profile_id)
        price_col = "price_eur_kwh"
        if price_col not in spot_df.columns:
            res = np.full(len(load.power_kw), default_rate, dtype=float)
            _SPOT_PRICE_CACHE[cache_key] = res
            return res.copy()

        ts_naive = load.timestamps
        ts_local = ts_naive.tz_localize("Europe/Amsterdam", ambiguous="NaT", nonexistent="shift_forward")
        ts_utc = ts_local.tz_convert("UTC")

        aligned_series = spot_df[price_col].reindex(ts_utc, method="ffill").bfill()
        spot_prices = aligned_series.fillna(default_rate).to_numpy(dtype=float)
        res = np.where(np.isnan(spot_prices), default_rate, spot_prices)
        _SPOT_PRICE_CACHE[cache_key] = res
        return res.copy()

    except Exception:
        res = np.full(len(load.power_kw), default_rate, dtype=float)
        _SPOT_PRICE_CACHE[cache_key] = res
        return res.copy()


def get_tranche_block_for_month(month: int, blocks: List[TrancheBlock]) -> TrancheBlock:
    """Finds the applicable hedge tranche block for a given calendar month."""
    for b in blocks:
        if month in b.months:
            return b
    return TrancheBlock(label=f"Month {month}", months=[month], hedged_share_pct=70.0, click_price_kwh=0.1080)


def calculate_commercial_accounting(
    load: LoadSeries2025,
    monthly_consumption: List[MonthlyConsumptionRecord],
    supplier_tariff: SupplierTariff
) -> Tuple[List[CommercialMonthlyResult], Dict[str, Any]]:
    """
    Calculates the 5-component supplier invoice breakdown for all 12 calendar months.
    """
    monthly_results: List[CommercialMonthlyResult] = []

    # Surcharges per kWh
    markup_rate = float(supplier_tariff.supplier_margin_kwh)
    balancing_rate = float(getattr(supplier_tariff, "balancing_fee_kwh", 0.0015))
    gvo_rate = float(supplier_tariff.green_certificate_surcharge_kwh)
    monthly_base_fee = float(supplier_tariff.base_fee_annual) / 12.0

    # Align wholesale spot series if DYNAMIC or TRANCHE mode is active
    needs_spot = supplier_tariff.pricing_mode in [PricingMode.DYNAMIC, PricingMode.TRANCHE]
    spot_prices = align_spot_prices_amsterdam_2025(load, supplier_tariff) if needs_spot else None

    annual_commodity = 0.0
    annual_markup = 0.0
    annual_balancing = 0.0
    annual_gvo = 0.0
    annual_supplier_energy = 0.0
    annual_hedged_kwh = 0.0
    annual_spot_kwh = 0.0

    for rec in monthly_consumption:
        m = rec.month_index
        m_kwh = float(rec.total_kwh)
        mask_m = (load.month_indices == m)

        # 1. Commodity Base Cost Calculation by Mode
        if supplier_tariff.pricing_mode == PricingMode.FIXED:
            if getattr(supplier_tariff, "is_dual_rate", False):
                r_ht = float(getattr(supplier_tariff, "fixed_rate_peak_kwh", supplier_tariff.fixed_rate_kwh))
                r_nt = float(getattr(supplier_tariff, "fixed_rate_offpeak_kwh", supplier_tariff.fixed_rate_kwh))
                m_commodity = (rec.peak_tou_kwh * r_ht) + (rec.offpeak_tou_kwh * r_nt)
            else:
                m_commodity = m_kwh * float(supplier_tariff.fixed_rate_kwh)
            m_hedged_kwh = m_kwh
            m_spot_kwh = 0.0

        elif supplier_tariff.pricing_mode == PricingMode.VARIABLE:
            var_rates = supplier_tariff.monthly_variable_rates
            m_rate = var_rates[m - 1] if (len(var_rates) >= m) else float(supplier_tariff.fixed_rate_kwh)
            m_commodity = m_kwh * float(m_rate)
            m_hedged_kwh = m_kwh
            m_spot_kwh = 0.0

        elif supplier_tariff.pricing_mode == PricingMode.DYNAMIC:
            # 15-minute interval energy * EPEX Spot price
            interval_energy = load.energy_kwh[mask_m]
            interval_spot = spot_prices[mask_m]
            m_commodity = float(np.sum(interval_energy * interval_spot))
            m_hedged_kwh = 0.0
            m_spot_kwh = m_kwh

        elif supplier_tariff.pricing_mode == PricingMode.TRANCHE:
            # Hybrid: Hedged block volume + residual spot volume
            block = get_tranche_block_for_month(m, supplier_tariff.tranche_blocks)
            hedged_ratio = block.hedged_share_pct / 100.0
            spot_ratio = 1.0 - hedged_ratio

            m_hedged_kwh = m_kwh * hedged_ratio
            m_spot_kwh = m_kwh * spot_ratio

            hedged_cost = m_hedged_kwh * block.click_price_kwh

            # Residual volume settled at 15-minute spot
            interval_energy = load.energy_kwh[mask_m]
            interval_spot = spot_prices[mask_m]
            spot_cost = float(np.sum(interval_energy * spot_ratio * interval_spot))

            m_commodity = hedged_cost + spot_cost

        else:
            m_commodity = m_kwh * float(supplier_tariff.fixed_rate_kwh)
            m_hedged_kwh = m_kwh
            m_spot_kwh = 0.0

        # 2. Opslag, Onbalans, GvO
        m_markup = m_kwh * markup_rate
        m_balancing = m_kwh * balancing_rate
        m_gvo = m_kwh * gvo_rate

        # 3. Monthly totals
        m_energy_cost = m_commodity + m_markup + m_balancing + m_gvo
        m_supplier_net = m_energy_cost + monthly_base_fee

        annual_commodity += m_commodity
        annual_markup += m_markup
        annual_balancing += m_balancing
        annual_gvo += m_gvo
        annual_supplier_energy += m_energy_cost
        annual_hedged_kwh += m_hedged_kwh
        annual_spot_kwh += m_spot_kwh

        monthly_results.append(
            CommercialMonthlyResult(
                month_index=m,
                commodity_cost=round(m_commodity, 2),
                markup_cost=round(m_markup, 2),
                balancing_cost=round(m_balancing, 2),
                gvo_cost=round(m_gvo, 2),
                supplier_base_fee=round(monthly_base_fee, 2),
                supplier_energy_cost=round(m_energy_cost, 2),
                subtotal_supplier_net=round(m_supplier_net, 2),
                hedged_kwh=round(m_hedged_kwh, 2),
                spot_kwh=round(m_spot_kwh, 2)
            )
        )

    summary = {
        "supplier_name": supplier_tariff.supplier_name,
        "supplier_category": supplier_tariff.supplier_category,
        "pricing_mode": supplier_tariff.pricing_mode.value,
        "total_commodity_annual": round(annual_commodity, 2),
        "total_markup_annual": round(annual_markup, 2),
        "total_balancing_annual": round(annual_balancing, 2),
        "total_gvo_annual": round(annual_gvo, 2),
        "total_base_fee_annual": round(monthly_base_fee * 12.0, 2),
        "total_supplier_energy_annual": round(annual_supplier_energy, 2),
        "total_supplier_net_annual": round(annual_supplier_energy + (monthly_base_fee * 12.0), 2),
        "total_hedged_kwh_annual": round(annual_hedged_kwh, 2),
        "total_spot_kwh_annual": round(annual_spot_kwh, 2),
        "average_spot_price_kwh": float(np.mean(spot_prices)) if spot_prices is not None else 0.0,
    }

    return monthly_results, summary
