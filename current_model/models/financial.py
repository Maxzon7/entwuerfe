"""
========================================================================================
Financial & Cost Breakdown Data Models (current_model/models/financial.py)
========================================================================================

Description:
------------
Defines dataclasses for itemized electricity cost breakdowns, monthly billing calculations,
and period totals based on contract parameters and active load profiles.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class CostLineItem:
    """Represents a single row on an itemized electricity invoice."""
    category: str              # e.g., 'Energy (Active)', 'Capacity', 'Base Fee', 'Penalty', 'Taxes & Levies'
    description: str           # e.g., 'Peak Tariff (08:00 - 20:00)', 'Contracted Capacity (400 kW)'
    basis_quantity: float      # e.g., kWh or kW or month count
    unit: str                  # e.g., 'kWh', 'kW', 'Month', '%'
    unit_rate: float           # e.g., €/kWh or €/kW/month
    cost_period: float         # Cost across the analyzed period (€)
    cost_monthly: float        # Projected/normalized monthly cost (€/month)
    share_pct: float = 0.0     # Share of total gross cost (%)


@dataclass
class FinancialCostBreakdown:
    """Holds complete financial assessment and itemized billing components."""
    currency: str = "EUR"
    duration_days: float = 1.0
    total_consumption_kwh: float = 0.0
    peak_demand_kw: float = 0.0
    contracted_capacity_kw: float = 0.0

    # Line items
    line_items: List[CostLineItem] = field(default_factory=list)

    # Subtotals (Net)
    energy_cost_period: float = 0.0
    energy_cost_monthly: float = 0.0

    capacity_cost_period: float = 0.0
    capacity_cost_monthly: float = 0.0

    penalty_cost_period: float = 0.0
    penalty_cost_monthly: float = 0.0

    base_fee_period: float = 0.0
    base_fee_monthly: float = 0.0

    reactive_cost_period: float = 0.0
    reactive_cost_monthly: float = 0.0

    # Taxes and Totals
    total_net_period: float = 0.0
    total_net_monthly: float = 0.0

    total_taxes_period: float = 0.0
    total_taxes_monthly: float = 0.0

    total_gross_period: float = 0.0
    total_gross_monthly: float = 0.0

    # Financial Performance Indicators
    effective_kwh_price: float = 0.0       # Total gross / total kWh (€/kWh)
    fixed_cost_share_pct: float = 0.0      # (Capacity + Base fee) / Total Net (%)
    variable_cost_share_pct: float = 0.0   # Energy / Total Net (%)
    capacity_utilization_pct: float = 0.0  # Peak kW / Contracted kW (%)
