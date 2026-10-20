"""
========================================================================================
3-Party Electricity Contract & Consumption Lab (ui_sandbox/minimal_contract_system.py)
========================================================================================

Description:
------------
Isolated, single-page sandbox laboratory demonstrating the European 3-Party Unbundled
Electricity Market Architecture:
  1. Regulated Grid Operator (DSO / Netbeheerder): Capacity, peak demand, volume transport, overload
  2. Certified Metering Company (Meetbedrijf / Messstellenbetrieb): Flat monthly telemetry & meter fee
  3. Competitive Energy Supplier (Energieleverancier): Commodity (Fixed TOU or EPEX Spot), opslag/margin
  4. Statutory Taxes & Dynamic Levies: VAT/BTW, energy taxes, concessions
========================================================================================
"""

import io
import os
import sys
import re
import zipfile
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# Ensure project root and current_model are on sys.path
SANDBOX_DIR = os.path.dirname(os.path.abspath(__file__))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(SANDBOX_DIR, ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))

for path in [WORKSPACE_ROOT, CURRENT_MODEL_DIR, SANDBOX_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

from current_model.models.contract import Contract
from current_model.models.financial import FinancialCostBreakdown, CostLineItem, MonthlyPaymentRecord
from current_model.core.financial_engine import compute_financial_bill, _resolve_contract_for_month
from current_model.ui.common.styles import apply_custom_styles
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.tab1_consumption.csv_inspector.view import render_csv_inspector
from current_model.ui.tab2_contract.form import (
    _sanitize_rate_val,
    _sanitize_tax_val,
    _sanitize_filename,
)


# ======================================================================================
# 1. Domain Model: 3-Party Unbundled Contract
# ======================================================================================

@dataclass
class ThreePartyContract(Contract):
    """
    Extended Contract data model supporting European 3-Party market unbundling:
      1. Regulated Grid Operator (DSO / Netbeheerder)
      2. Certified Metering Company (Meetbedrijf / Messstellenbetrieb)
      3. Competitive Energy Supplier (Energieleverancier)
    Fully backward-compatible with standard Contract dataclass and .drac payloads.
    """
    # 1. Regulated Grid Operator (DSO / Netbeheerder)
    dso_name: str = "Liander Netbeheer"
    connection_category: str = "AC4b (Medium Voltage 10 kV)"

    # 2. Certified Metering Company (Meetbedrijf / Messstellenbetrieb)
    meter_company_name: str = "Fudura B.V."
    metering_monthly_fee: float = 75.00  # Flat monthly telemetry & interval meter fee (EUR/month)

    # 3. Energy Commodity Supplier (Energieleverancier)
    supplier_name: str = "Eneco Zakelijk"
    supplier_base_fee_monthly: float = 15.00  # Supplier administrative monthly fee (EUR/month)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the 3-Party Contract to a JSON-ready dictionary."""
        d = super().to_dict()
        d["dso_name"] = str(self.dso_name)
        d["connection_category"] = str(self.connection_category)
        d["meter_company_name"] = str(self.meter_company_name)
        d["metering_monthly_fee"] = float(self.metering_monthly_fee)
        d["supplier_name"] = str(self.supplier_name)
        d["supplier_base_fee_monthly"] = float(self.supplier_base_fee_monthly)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThreePartyContract":
        """Deserializes a dictionary or JSON payload into a ThreePartyContract instance."""
        if not isinstance(data, dict):
            return cls()

        base_c = Contract.from_dict(data)
        return cls(
            name=base_c.name,
            currency=base_c.currency,
            base_monthly_fee=base_c.base_monthly_fee,
            contracted_capacity_kw=base_c.contracted_capacity_kw,
            monthly_capacity_tariff=base_c.monthly_capacity_tariff,
            demand_capacity_tariff=base_c.demand_capacity_tariff,
            max_physical_limit_kw=base_c.max_physical_limit_kw,
            peak_penalty_rate=base_c.peak_penalty_rate,
            network_volume_tariff=base_c.network_volume_tariff,
            pricing_model=base_c.pricing_model,
            supplier_margin=base_c.supplier_margin,
            market_price_profile_id=base_c.market_price_profile_id,
            reactive_power_tariff=base_c.reactive_power_tariff,
            min_power_factor=base_c.min_power_factor,
            reactive_power_allowance_pct=base_c.reactive_power_allowance_pct,
            tou_rates=base_c.tou_rates,
            default_energy_rate=base_c.default_energy_rate,
            weekend_is_off_peak=base_c.weekend_is_off_peak,
            applicable_months=base_c.applicable_months,
            taxes_and_fees=base_c.taxes_and_fees,
            dso_name=str(data.get("dso_name", "Liander Netbeheer")),
            connection_category=str(data.get("connection_category", "AC4b (Medium Voltage 10 kV)")),
            meter_company_name=str(data.get("meter_company_name", "Fudura B.V.")),
            metering_monthly_fee=float(data.get("metering_monthly_fee", 0.0)),
            supplier_name=str(data.get("supplier_name", "Eneco Zakelijk")),
            supplier_base_fee_monthly=float(data.get("supplier_base_fee_monthly", 0.0)),
        )

    def to_json(self, indent: int = 2) -> str:
        """Serializes the Contract to a formatted JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "ThreePartyContract":
        """Reconstructs a ThreePartyContract from a JSON string."""
        import json
        data = json.loads(json_str)
        return cls.from_dict(data)


# ======================================================================================
# 2. Industry Presets: Real-World 3-Party Market Configurations
# ======================================================================================

def get_three_party_presets() -> Dict[str, ThreePartyContract]:
    """Provides standard industry contract templates with explicit 3-Party unbundling."""
    return {
        "Netherlands 3-Party Dynamic (Liander MS + Eneco + Fudura)": ThreePartyContract(
            name="Netherlands 3-Party Dynamic (Liander + Eneco + Fudura)",
            currency="EUR",
            # 1. Regulated DSO (Liander Netbeheer - MS 136 - 2000 kW)
            dso_name="Liander Netbeheer",
            connection_category="AC4b (Medium Voltage 10 kV)",
            base_monthly_fee=36.75,
            contracted_capacity_kw=147.0,
            monthly_capacity_tariff=2.2233,
            demand_capacity_tariff=3.4600,
            network_volume_tariff=0.0220,
            max_physical_limit_kw=1000.0,
            peak_penalty_rate=10.50,
            # 2. Certified Metering Company (Meetbedrijf)
            meter_company_name="Fudura B.V.",
            metering_monthly_fee=75.00,
            # 3. Energy Supplier (Commodity + Opslag)
            supplier_name="Eneco Zakelijk",
            supplier_base_fee_monthly=15.00,
            pricing_model="day_ahead_dynamic",
            supplier_margin=0.0075,
            market_price_profile_id="epex_nl_2025",
            default_energy_rate=0.0900,
            # 4. Technical & Taxes
            reactive_power_tariff=0.03,
            min_power_factor=0.90,
            applicable_months=list(range(1, 13)),
            taxes_and_fees=[
                {"name": "VAT / BTW", "type": "percentage", "value": 21.0, "description": "Statutory Value Added Tax"}
            ]
        ),
        "Netherlands 3-Party Fixed TOU (Enexis MS-D + Vattenfall + Kenter)": ThreePartyContract(
            name="Netherlands 3-Party Fixed TOU (Enexis + Vattenfall + Kenter)",
            currency="EUR",
            # 1. Regulated DSO (Enexis Netbeheer - MS-D 125 - 1500 kW)
            dso_name="Enexis Netbeheer",
            connection_category="MS-D (Medium Voltage Distribution)",
            base_monthly_fee=174.50,
            contracted_capacity_kw=250.0,
            monthly_capacity_tariff=2.4400,
            demand_capacity_tariff=0.0,
            network_volume_tariff=0.0250,
            max_physical_limit_kw=1000.0,
            peak_penalty_rate=8.50,
            # 2. Certified Metering Company (Meetbedrijf)
            meter_company_name="Kenter B.V.",
            metering_monthly_fee=85.00,
            # 3. Energy Supplier (Fixed TOU Commodity)
            supplier_name="Vattenfall Zakelijk",
            supplier_base_fee_monthly=20.00,
            pricing_model="time_of_use",
            supplier_margin=0.0,
            tou_rates=[
                {"name": "Piek (07:00 - 23:00)", "rate": 0.1450, "start_time": "07:00", "end_time": "23:00"},
                {"name": "Dal (23:00 - 07:00)", "rate": 0.0950, "start_time": "23:00", "end_time": "07:00"}
            ],
            default_energy_rate=0.1200,
            weekend_is_off_peak=True,
            # 4. Technical & Taxes
            reactive_power_tariff=0.03,
            min_power_factor=0.90,
            applicable_months=list(range(1, 13)),
            taxes_and_fees=[
                {"name": "VAT / BTW", "type": "percentage", "value": 21.0, "description": "Statutory Value Added Tax"}
            ]
        ),
        "Germany Industrial 3-Party (Netze BW + E.ON + Infraserv)": ThreePartyContract(
            name="Germany Industrial 3-Party (Netze BW + E.ON + Infraserv)",
            currency="EUR",
            # 1. Regulated DSO
            dso_name="Netze BW GmbH",
            connection_category="Mittelspannung (MS, 20 kV)",
            base_monthly_fee=50.00,
            contracted_capacity_kw=400.0,
            monthly_capacity_tariff=3.1000,
            demand_capacity_tariff=0.0,
            network_volume_tariff=0.0180,
            max_physical_limit_kw=1200.0,
            peak_penalty_rate=12.00,
            # 2. Certified Metering Company (Meetbedrijf)
            meter_company_name="Infraserv Höchst Metering",
            metering_monthly_fee=95.00,
            # 3. Energy Supplier
            supplier_name="E.ON Energie Deutschland",
            supplier_base_fee_monthly=25.00,
            pricing_model="time_of_use",
            supplier_margin=0.0,
            tou_rates=[
                {"name": "Hochtarif (HT 06:00 - 22:00)", "rate": 0.1650, "start_time": "06:00", "end_time": "22:00"},
                {"name": "Niedertarif (NT 22:00 - 06:00)", "rate": 0.1150, "start_time": "22:00", "end_time": "06:00"}
            ],
            default_energy_rate=0.1400,
            weekend_is_off_peak=True,
            # 4. Technical & Taxes
            reactive_power_tariff=0.035,
            min_power_factor=0.92,
            applicable_months=list(range(1, 13)),
            taxes_and_fees=[
                {"name": "Stromsteuer (Electricity Tax)", "type": "per_kwh", "value": 0.0205, "description": "Statutory German Electricity Tax"},
                {"name": "Umsatzsteuer (VAT 19%)", "type": "percentage", "value": 19.0, "description": "Statutory VAT"}
            ]
        ),
        "Bodegas Salentein (EDEMSA T2 R MT - Argentina)": ThreePartyContract(
            name="Bodegas Salentein (EDEMSA T2 R MT)",
            currency="ARS",
            dso_name="EDEMSA",
            connection_category="T2 R MT (Media Tensión)",
            base_monthly_fee=514145.55,
            contracted_capacity_kw=430.0,
            monthly_capacity_tariff=40607.0460,
            demand_capacity_tariff=8554.4390,
            network_volume_tariff=0.0,
            max_physical_limit_kw=1000.0,
            peak_penalty_rate=40607.0460,
            meter_company_name="EDEMSA Medición",
            metering_monthly_fee=0.0,
            supplier_name="EDEMSA Suministro",
            supplier_base_fee_monthly=0.0,
            pricing_model="time_of_use",
            supplier_margin=0.0,
            tou_rates=[
                {"name": "Valle (23:00 - 05:00)", "rate": 66.1017, "start_time": "00:00", "end_time": "05:00"},
                {"name": "Resto (05:00 - 18:00)", "rate": 66.7737, "start_time": "05:00", "end_time": "18:00"},
                {"name": "Pico (18:00 - 23:00)", "rate": 68.4335, "start_time": "18:00", "end_time": "23:00"},
                {"name": "Valle (23:00 - 05:00)", "rate": 66.1017, "start_time": "23:00", "end_time": "24:00"}
            ],
            default_energy_rate=66.7737,
            weekend_is_off_peak=False,
            reactive_power_tariff=0.0,
            min_power_factor=0.90,
            applicable_months=list(range(1, 13)),
            taxes_and_fees=[
                {"name": "I.V.A. Resp. Inscripto", "type": "percentage", "value": 27.00, "description": "IVA Nacional"},
                {"name": "CCCE art 74 inc d) Ley 6497", "type": "percentage", "value": 9.00, "description": "Fondo Compensador Provincial"},
                {"name": "Impuestos Provinciales IIBB", "type": "percentage", "value": 3.09, "description": "Ingresos Brutos"},
                {"name": "Tasa Fisc. y Control art 64", "type": "percentage", "value": 1.50, "description": "EPRE Fiscalización"},
                {"name": "Cargo AP Municipal Ord. 3028", "type": "fixed_monthly", "value": 43091.00, "description": "Alumbrado Público"}
            ]
        ),
        "Standard Commercial Utility Contract (Baseline)": ThreePartyContract(
            name="Standard Commercial Utility Contract (Baseline)",
            currency="EUR",
            dso_name="Regional Utility DSO",
            connection_category="Commercial LV/MV",
            base_monthly_fee=50.0,
            contracted_capacity_kw=400.0,
            monthly_capacity_tariff=0.15,
            demand_capacity_tariff=0.0,
            network_volume_tariff=0.0,
            max_physical_limit_kw=1000.0,
            peak_penalty_rate=0.25,
            meter_company_name="Standard Metering Provider",
            metering_monthly_fee=45.0,
            supplier_name="Standard Power Supplier",
            supplier_base_fee_monthly=15.0,
            pricing_model="time_of_use",
            supplier_margin=0.0,
            tou_rates=[
                {"name": "Standard Rate", "rate": 0.20, "start_time": "00:00", "end_time": "24:00"}
            ],
            default_energy_rate=0.20,
            weekend_is_off_peak=False,
            applicable_months=list(range(1, 13)),
            taxes_and_fees=[]
        )
    }


# ======================================================================================
# 3. Calculation Engine: 3-Party Billing Aggregator
# ======================================================================================

def compute_three_party_financial_bill(
    load_data: Any,
    contract: Any,
    duration_days: Optional[float] = None,
    step_hours: float = 0.25,
    target_month: Optional[str] = None
) -> FinancialCostBreakdown:
    """
    Computes interval-level financial billing and augments line items with
    explicit Meetbedrijf (Metering Company) and Supplier Standing charges.
    """
    # 1. Compute core billing
    breakdown: FinancialCostBreakdown = compute_financial_bill(
        load_data=load_data,
        contract=contract,
        duration_days=duration_days,
        step_hours=step_hours,
        target_month=target_month
    )

    # 2. Extract governing contract
    if isinstance(contract, list) and contract:
        primary_c = contract[0]
    else:
        primary_c = contract

    months_in_period = breakdown.duration_days / 30.4375
    monthly_multiplier = 30.4375 / max(0.1, breakdown.duration_days)

    meter_monthly = float(getattr(primary_c, "metering_monthly_fee", 0.0))
    sup_base_monthly = float(getattr(primary_c, "supplier_base_fee_monthly", 0.0))

    added_net_period = 0.0
    added_net_monthly = 0.0

    # 3. Meetbedrijf (Metering Company) Line Item
    if meter_monthly > 0:
        meter_provider = getattr(primary_c, "meter_company_name", "") or "Meetbedrijf"
        meter_period = meter_monthly * months_in_period
        breakdown.line_items.append(
            CostLineItem(
                category="Metering (Meetbedrijf)",
                description=f"Interval Metering & Telemetry ({meter_provider})",
                basis_quantity=round(months_in_period, 2),
                unit="Months",
                unit_rate=meter_monthly,
                cost_period=round(meter_period, 2),
                cost_monthly=round(meter_monthly, 2)
            )
        )
        added_net_period += meter_period
        added_net_monthly += meter_monthly

    # 4. Energy Supplier Administrative Standing Charge
    if sup_base_monthly > 0:
        sup_provider = getattr(primary_c, "supplier_name", "") or "Energy Supplier"
        sup_period = sup_base_monthly * months_in_period
        breakdown.line_items.append(
            CostLineItem(
                category="Energy Supplier",
                description=f"Supplier Standing Charge ({sup_provider})",
                basis_quantity=round(months_in_period, 2),
                unit="Months",
                unit_rate=sup_base_monthly,
                cost_period=round(sup_period, 2),
                cost_monthly=round(sup_base_monthly, 2)
            )
        )
        added_net_period += sup_period
        added_net_monthly += sup_base_monthly

    # 5. Integrate added costs into totals
    if added_net_period > 0:
        breakdown.total_net_period += added_net_period
        breakdown.total_net_monthly += added_net_monthly
        breakdown.total_gross_period += added_net_period
        breakdown.total_gross_monthly += added_net_monthly

        if breakdown.total_consumption_kwh > 0:
            breakdown.effective_kwh_price = breakdown.total_gross_period / breakdown.total_consumption_kwh

        # Recalculate percentage shares
        for item in breakdown.line_items:
            item.share_pct = round((item.cost_period / breakdown.total_gross_period * 100.0), 1) if breakdown.total_gross_period > 0 else 0.0

        # Update monthly payment series
        if breakdown.monthly_series:
            extra_per_month = added_net_monthly
            for m in breakdown.monthly_series:
                m.base_fee_net += extra_per_month
                m.total_net += extra_per_month
                m.total_gross += extra_per_month
                if m.energy_kwh > 0:
                    m.effective_rate_kwh = m.total_gross / m.energy_kwh

    return breakdown


# ======================================================================================
# 4. Visualizations: 3-Party Donut & Payment Series Charts
# ======================================================================================

THREE_PARTY_COST_PALETTE: Dict[str, str] = {
    "Energy (Active)": "#38BDF8",       # Sky Blue (Commodity)
    "Capacity (Contracted)": "#F59E0B",  # Amber (DSO Reserved Power)
    "Demand (Measured)": "#FB923C",      # Orange (DSO Peak Demand)
    "Network (Volume)": "#06B6D4",      # Cyan (DSO Transport Fee)
    "Peak Penalty": "#EF4444",          # Red (DSO Overload)
    "Base Fee": "#8B5CF6",              # Violet (DSO Standing Charge)
    "Metering (Meetbedrijf)": "#D946EF", # Fuchsia (Meetbedrijf Telemetry & Meter Rental)
    "Energy Supplier": "#6366F1",        # Indigo (Supplier Standing Charge & Opslag)
    "Taxes & Levies": "#10B981",        # Emerald (VAT & Statutory Levies)
    "Other": "#94A3B8"                  # Slate
}


def create_three_party_donut_figure(breakdown: FinancialCostBreakdown) -> go.Figure:
    """Constructs a clean Donut chart displaying monthly cost distribution across all 3 parties."""
    is_synthetic_annual = (len(breakdown.monthly_series) == 12 and breakdown.duration_days <= 1.5)
    category_totals: Dict[str, float] = {}

    for item in breakdown.line_items:
        cat = item.category
        val = item.cost_monthly if (breakdown.duration_days > 35 or is_synthetic_annual) else item.cost_period
        if val > 0:
            category_totals[cat] = category_totals.get(cat, 0.0) + val

    labels = list(category_totals.keys())
    values = list(category_totals.values())
    colors = [THREE_PARTY_COST_PALETTE.get(cat, THREE_PARTY_COST_PALETTE["Other"]) for cat in labels]

    if not values:
        labels = ["No Cost Data"]
        values = [1.0]
        colors = ["#64748B"]

    currency = breakdown.currency

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.58,
                textinfo="percent",
                textposition="inside",
                insidetextorientation="horizontal",
                marker=dict(colors=colors, line=dict(color="#0B0F19", width=2)),
                hovertemplate=f"<b>%{{label}}</b><br>Amount: %{{value:,.2f}} {currency}<br>Share: %{{percent}}<extra></extra>"
            )
        ]
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>3-Party Cost Distribution</b>",
            font=dict(size=14, color="#F8FAFC"),
            x=0.05,
            y=0.96
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.06,
            xanchor="center",
            x=0.5,
            font=dict(size=11, color="#94A3B8")
        ),
        margin=dict(l=20, r=20, t=40, b=50),
        height=380,
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19"
    )
    return fig


def create_three_party_series_figure(breakdown: FinancialCostBreakdown) -> go.Figure:
    """Constructs an interactive stacked bar chart visualizing monthly payment timeseries across 12 months."""
    fig = go.Figure()
    currency = breakdown.currency

    if not breakdown.monthly_series:
        fig.update_layout(
            template="plotly_dark",
            title="No monthly payment data available",
            plot_bgcolor="#0B0F19",
            paper_bgcolor="#0B0F19"
        )
        return fig

    months = [m.period_label for m in breakdown.monthly_series]
    energy_costs = [m.energy_cost_net for m in breakdown.monthly_series]
    capacity_costs = [m.capacity_cost_net for m in breakdown.monthly_series]
    penalty_costs = [m.penalty_cost_net for m in breakdown.monthly_series]
    fixed_fees = [m.base_fee_net for m in breakdown.monthly_series]
    taxes = [m.taxes_and_levies for m in breakdown.monthly_series]
    network_costs = [getattr(m, "network_cost_net", 0.0) for m in breakdown.monthly_series]

    fig.add_trace(go.Bar(x=months, y=energy_costs, name="Commodity Energy", marker_color=THREE_PARTY_COST_PALETTE["Energy (Active)"]))
    fig.add_trace(go.Bar(x=months, y=capacity_costs, name="DSO Capacity", marker_color=THREE_PARTY_COST_PALETTE["Capacity (Contracted)"]))
    if any(n > 0 for n in network_costs):
        fig.add_trace(go.Bar(x=months, y=network_costs, name="DSO Network Transport", marker_color=THREE_PARTY_COST_PALETTE["Network (Volume)"]))
    if any(p > 0 for p in penalty_costs):
        fig.add_trace(go.Bar(x=months, y=penalty_costs, name="DSO Peak Penalty", marker_color=THREE_PARTY_COST_PALETTE["Peak Penalty"]))
    fig.add_trace(go.Bar(x=months, y=fixed_fees, name="Standing & Metering Fees", marker_color=THREE_PARTY_COST_PALETTE["Base Fee"]))
    fig.add_trace(go.Bar(x=months, y=taxes, name="Taxes & Levies", marker_color=THREE_PARTY_COST_PALETTE["Taxes & Levies"]))

    fig.update_layout(
        template="plotly_dark",
        barmode="stack",
        title=dict(
            text="<b>Monthly Payment Series (Zahlungsreihe)</b>",
            font=dict(size=14, color="#F8FAFC"),
            x=0.05,
            y=0.96
        ),
        xaxis=dict(title="", tickfont=dict(size=11, color="#94A3B8"), gridcolor="#1E293B"),
        yaxis=dict(title=f"Total Cost ({currency})", tickfont=dict(size=11, color="#94A3B8"), gridcolor="#1E293B"),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5, font=dict(size=11, color="#94A3B8")),
        margin=dict(l=30, r=20, t=40, b=50),
        height=380,
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19"
    )
    return fig


# ======================================================================================
# 5. UI Helpers: File I/O & State Synchronization
# ======================================================================================

def _parse_uploaded_3party_contract_files(uploaded_files: List[Any]) -> Dict[str, ThreePartyContract]:
    """Parses one or multiple .drac, .json, or .zip files containing 3-Party contracts."""
    parsed_contracts: Dict[str, ThreePartyContract] = {}
    if not uploaded_files:
        return parsed_contracts

    for f in uploaded_files:
        fname = getattr(f, "name", "contract.drac")
        if fname.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(f.getvalue())) as z:
                    for member in z.namelist():
                        if member.lower().endswith((".drac", ".json")) and not member.startswith("__MACOSX"):
                            try:
                                content = z.read(member).decode("utf-8")
                                c = ThreePartyContract.from_json(content)
                                base_member = os.path.basename(member)
                                label = f"{c.name} ({base_member})" if c.name else base_member
                                parsed_contracts[label] = c
                            except Exception:
                                continue
            except Exception:
                continue
        else:
            try:
                content = f.getvalue().decode("utf-8")
                c = ThreePartyContract.from_json(content)
                label = f"{c.name} ({fname})" if c.name else fname
                parsed_contracts[label] = c
            except Exception:
                continue
    return parsed_contracts


def _sync_3party_contract_to_state(contract: ThreePartyContract, key_prefix: str) -> None:
    """Synchronizes a ThreePartyContract object into Streamlit session state and editors."""
    st.session_state[f"{key_prefix}_contract_model"] = contract
    st.session_state[f"{key_prefix}_tou_rates_df"] = pd.DataFrame(contract.tou_rates)
    st.session_state[f"{key_prefix}_taxes_df"] = pd.DataFrame(contract.taxes_and_fees) if contract.taxes_and_fees else pd.DataFrame(columns=["name", "type", "value", "description"])
    st.session_state[f"{key_prefix}_active_contract_label"] = contract.name


# ======================================================================================
# 6. UI Component: 3-Party Unbundled Contract Form
# ======================================================================================

def render_simplified_contract_form(key_prefix: str = "sandbox_contract") -> ThreePartyContract:
    """
    Renders the Electricity Supply Contract form with explicit 3-Party Unbundling:
      1. Regulated Grid Operator (DSO)
      2. Certified Metering Company (Meetbedrijf)
      3. Energy Commodity Supplier
      4. Technical Rules & Taxes
    """
    state_contract_key = f"{key_prefix}_contract_model"
    state_tou_key = f"{key_prefix}_tou_rates_df"
    state_taxes_key = f"{key_prefix}_taxes_df"
    loaded_contracts_dict_key = f"{key_prefix}_loaded_contracts_dict"
    uploader_sig_key = f"{key_prefix}_last_files_sig"

    # Initialize default state with 3-party contract if absent
    if state_contract_key not in st.session_state:
        presets = get_three_party_presets()
        first_preset = presets["Netherlands 3-Party Dynamic (Liander MS + Eneco + Fudura)"]
        st.session_state[state_contract_key] = first_preset

    current: ThreePartyContract = st.session_state[state_contract_key]

    if not isinstance(current, ThreePartyContract):
        current = ThreePartyContract.from_dict(current.to_dict() if hasattr(current, "to_dict") else {})
        st.session_state[state_contract_key] = current

    if state_tou_key not in st.session_state:
        st.session_state[state_tou_key] = pd.DataFrame(current.tou_rates)

    if state_taxes_key not in st.session_state:
        st.session_state[state_taxes_key] = pd.DataFrame(current.taxes_and_fees) if current.taxes_and_fees else pd.DataFrame(columns=["name", "type", "value", "description"])

    with st.container():
        # Toolbar: Import / Export / Presets
        st.markdown("### :material/handshake: 3-Party Contract Configuration & Presets")
        st.caption("Manage contracts separating Regulated Grid Operator (DSO), Metering Company (Meetbedrijf), and Energy Supplier.")

        col_up, col_down = st.columns([1, 1])

        # --- LEFT: Upload / Presets / Selection ---
        with col_up:
            st.markdown("##### :material/file_open: Contract Selection & Presets")
            uploaded_files = st.file_uploader(
                "Upload `.drac` or `.json` contract files:",
                type=["drac", "json", "zip"],
                accept_multiple_files=True,
                key=f"{key_prefix}_file_uploader"
            )

            if loaded_contracts_dict_key not in st.session_state:
                st.session_state[loaded_contracts_dict_key] = {}

            if uploaded_files:
                current_sig = "|".join(sorted([f"{f.name}_{f.size}" for f in uploaded_files]))
                if st.session_state.get(uploader_sig_key) != current_sig:
                    new_contracts = _parse_uploaded_3party_contract_files(uploaded_files)
                    if new_contracts:
                        st.session_state[loaded_contracts_dict_key] = new_contracts
                        st.session_state[uploader_sig_key] = current_sig
                        first_label = list(new_contracts.keys())[0]
                        _sync_3party_contract_to_state(new_contracts[first_label], key_prefix=key_prefix)
                        st.success(f"Loaded **{len(new_contracts)}** contract(s)!")
                        st.rerun()

            loaded_dict = st.session_state.get(loaded_contracts_dict_key, {})
            if current.name not in loaded_dict:
                loaded_dict[current.name] = current
                st.session_state[loaded_contracts_dict_key] = loaded_dict

            labels = list(loaded_dict.keys())
            current_sel = st.session_state.get(f"{key_prefix}_active_contract_label", labels[0])
            if current_sel not in labels:
                current_sel = labels[0]
                st.session_state[f"{key_prefix}_active_contract_label"] = current_sel
            sel_idx = labels.index(current_sel)

            selected_label = st.selectbox("Active Contract:", options=labels, index=sel_idx)
            if selected_label != current_sel and selected_label in loaded_dict:
                _sync_3party_contract_to_state(loaded_dict[selected_label], key_prefix=key_prefix)
                st.rerun()

            # Presets Toolbar
            presets = get_three_party_presets()
            selected_preset_name = st.selectbox(
                "Or load an unbundled industry preset:",
                options=["-- Select a Template --"] + list(presets.keys()),
                index=0,
                key=f"{key_prefix}_preset_select"
            )
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                if selected_preset_name in presets:
                    if st.button("Apply Preset", icon=":material/playlist_add_check:", key=f"{key_prefix}_apply_preset_btn", use_container_width=True):
                        preset_c = presets[selected_preset_name]
                        preset_copy = ThreePartyContract.from_dict(preset_c.to_dict())
                        loaded_dict[preset_copy.name] = preset_copy
                        st.session_state[loaded_contracts_dict_key] = loaded_dict
                        _sync_3party_contract_to_state(preset_copy, key_prefix=key_prefix)
                        st.success(f"Loaded preset: {selected_preset_name}")
                        st.rerun()
            with p_col2:
                if st.button("Reset to Baseline", icon=":material/restart_alt:", key=f"{key_prefix}_reset_basic_c_btn", use_container_width=True):
                    default_c = presets["Netherlands 3-Party Dynamic (Liander MS + Eneco + Fudura)"]
                    loaded_dict[default_c.name] = default_c
                    st.session_state[loaded_contracts_dict_key] = loaded_dict
                    _sync_3party_contract_to_state(default_c, key_prefix=key_prefix)
                    st.rerun()

        # --- RIGHT: Download / Export ---
        with col_down:
            st.markdown("##### :material/download: Export 3-Party Contract (.drac)")
            default_file_base = re.sub(r'[^a-zA-Z0-9_-]', '_', current.name.lower().strip()) or "contract"
            custom_download_filename = st.text_input(
                "Export Filename (.drac):",
                value=f"{default_file_base}.drac",
                key=f"{key_prefix}_custom_filename_input"
            )
            final_filename = _sanitize_filename(custom_download_filename, default=f"{default_file_base}.drac")

            contract_json_data = current.to_json(indent=2)
            st.download_button(
                label=f"Download `{final_filename}`",
                data=contract_json_data,
                file_name=final_filename,
                mime="application/json",
                icon=":material/download:",
                key=f"{key_prefix}_download_btn",
                use_container_width=True
            )
            st.caption(
                f"Active Contract: **{current.name}** | DSO: `{current.dso_name}` | "
                f"Meetbedrijf: `{current.meter_company_name}` ({current.metering_monthly_fee:.2f} {current.currency}/mo) | "
                f"Supplier: `{current.supplier_name}`"
            )

        st.divider()

        # ==============================================================================
        # 3-Party Unbundled Contract Parameter Form
        # ==============================================================================
        with st.form(key=f"{key_prefix}_3party_contract_form"):
            # Master Contract Identifier & Currency
            head_col1, head_col2 = st.columns([3, 1])
            with head_col1:
                contract_name_val = st.text_input(
                    "Contract Title / Portfolio Name:",
                    value=str(current.name),
                    help="Custom name for this supply agreement."
                )
            with head_col2:
                curr_options = ["EUR", "USD", "ARS", "GBP", "CHF"]
                current_curr = getattr(current, "currency", "EUR")
                curr_idx = curr_options.index(current_curr) if current_curr in curr_options else 0
                currency = st.selectbox("Currency:", options=curr_options, index=curr_idx)

            # --------------------------------------------------------------------------
            # SECTION 1: Regulated Grid Operator (DSO / Netbeheerder)
            # --------------------------------------------------------------------------
            st.markdown("#### :material/account_balance: 1. Regulated Grid Operator (DSO / Netbeheerder)")
            st.caption("Regulated infrastructure charges determined by national energy regulator (ACM in NL, BNetzA in DE).")

            dso_c1, dso_c2 = st.columns(2)
            with dso_c1:
                dso_name_val = st.text_input(
                    "Grid Operator Name (DSO):",
                    value=str(getattr(current, "dso_name", "Liander Netbeheer")),
                    help="Name of regional distribution network operator (e.g. Liander, Enexis, Stedin, Netze BW)."
                )
                connection_category_val = st.text_input(
                    "Connection Level / Category:",
                    value=str(getattr(current, "connection_category", "AC4b (Medium Voltage)")),
                    help="Voltage tier and tariff class (e.g. LS, MS-D, MS, HS)."
                )
                contracted_kw = st.number_input(
                    "Reserved Grid Capacity (kW - Gekontrakteerd Vermogen):",
                    min_value=0.0,
                    value=float(current.contracted_capacity_kw),
                    step=10.0,
                    format="%.1f",
                    help="Contracted power limit reserved on the grid transformer."
                )
                base_fee = st.number_input(
                    f"DSO Fixed Standing Charge ({currency}/month):",
                    min_value=0.0,
                    value=float(current.base_monthly_fee),
                    step=5.0,
                    format="%.2f",
                    help="Fixed monthly standing fee for grid connection maintenance."
                )

            with dso_c2:
                capacity_tariff = st.number_input(
                    f"Contracted Capacity Tariff ({currency}/kW/month):",
                    min_value=0.0,
                    value=float(current.monthly_capacity_tariff),
                    step=0.1,
                    format="%.4f",
                    help="Monthly fee billed per reserved kW (capaciteitstarief)."
                )
                demand_tariff = st.number_input(
                    f"Measured Peak Demand Tariff ({currency}/kW/month):",
                    min_value=0.0,
                    value=float(getattr(current, "demand_capacity_tariff", 0.0)),
                    step=0.1,
                    format="%.4f",
                    help="Monthly charge for the highest recorded 15-minute peak (piektarief)."
                )
                network_volume_tariff_val = st.number_input(
                    f"Grid Transport Volume Fee ({currency}/kWh):",
                    min_value=0.0,
                    value=float(getattr(current, "network_volume_tariff", 0.0220)),
                    step=0.0025,
                    format="%.4f",
                    help="Regulated transport fee charged per delivered active kWh (Netznutzung)."
                )
                penalty_rate = st.number_input(
                    f"Capacity Overload Penalty Rate ({currency}/kW):",
                    min_value=0.0,
                    value=float(current.peak_penalty_rate),
                    step=1.0,
                    format="%.4f",
                    help="Penalty fee billed for each kW exceeding the reserved capacity limit."
                )
                max_physical_kw = st.number_input(
                    "Absolute Fuse Limit (kW):",
                    min_value=0.0,
                    value=float(current.max_physical_limit_kw),
                    step=50.0,
                    format="%.1f",
                    help="Physical transformer or circuit breaker capacity limit."
                )

            # --------------------------------------------------------------------------
            # SECTION 2: Certified Metering Company (Meetbedrijf / Messstellenbetrieb)
            # --------------------------------------------------------------------------
            st.markdown("#### :material/speed: 2. Certified Metering Company (Meetbedrijf / Messstellenbetrieb)")
            st.caption("Independent commercial metering service provider responsible for interval telemetry meters (Fudura, Kenter, etc.).")

            m_col1, m_col2 = st.columns(2)
            with m_col1:
                meter_company_val = st.text_input(
                    "Metering Company Name (Meetbedrijf):",
                    value=str(getattr(current, "meter_company_name", "Fudura B.V.")),
                    help="Name of certified metering company (e.g. Fudura, Kenter, Joulz)."
                )
            with m_col2:
                metering_monthly_val = st.number_input(
                    f"Monthly Meter Rental & Telemetry Fee ({currency}/month):",
                    min_value=0.0,
                    value=float(getattr(current, "metering_monthly_fee", 75.00)),
                    step=5.0,
                    format="%.2f",
                    help="Flat monthly fee for interval meter hardware rental and GSM/SIM telemetry."
                )

            # --------------------------------------------------------------------------
            # SECTION 3: Energy Commodity & Supplier (Energieleverancier)
            # --------------------------------------------------------------------------
            st.markdown("#### :material/electric_bolt: 3. Energy Commodity & Supplier (Energieleverancier)")
            st.caption("Competitive energy supplier providing wholesale commodity procurement (Eneco, Vattenfall, Shell, etc.).")

            sup_col1, sup_col2 = st.columns(2)
            with sup_col1:
                supplier_name_val = st.text_input(
                    "Energy Supplier Name:",
                    value=str(getattr(current, "supplier_name", "Eneco Zakelijk")),
                    help="Commercial electricity retailer (e.g. Eneco, Vattenfall, E.ON)."
                )
            with sup_col2:
                supplier_base_fee_val = st.number_input(
                    f"Supplier Standing Administrative Fee ({currency}/month):",
                    min_value=0.0,
                    value=float(getattr(current, "supplier_base_fee_monthly", 15.00)),
                    step=5.0,
                    format="%.2f",
                    help="Fixed monthly account and billing administrative fee charged by the supplier."
                )

            # Pricing Mode Toggle
            pricing_options = [
                "Dynamic Spot Market (Day-Ahead NL 2025)",
                "Fixed Time-of-Use Tariffs"
            ]
            current_pricing_model = getattr(current, "pricing_model", "day_ahead_dynamic")
            default_pricing_idx = 0 if current_pricing_model == "day_ahead_dynamic" else 1

            selected_pricing_mode = st.radio(
                "Commodity Procurement Model:",
                options=pricing_options,
                index=default_pricing_idx,
                horizontal=True,
                key=f"{key_prefix}_pricing_mode_radio"
            )
            is_dynamic_selected = (selected_pricing_mode == "Dynamic Spot Market (Day-Ahead NL 2025)")

            if is_dynamic_selected:
                st.markdown("##### :material/trending_up: Day-Ahead Spot Market Parameters")
                dyn_c1, dyn_c2 = st.columns(2)
                with dyn_c1:
                    supplier_margin_val = st.number_input(
                        f"Supplier Margin / Opslag ({currency}/kWh):",
                        min_value=0.0,
                        value=float(getattr(current, "supplier_margin", 0.0075)),
                        step=0.0010,
                        format="%.4f",
                        help="Supplier surcharge / opslag added on top of the hourly spot price (e.g. 0.0075 EUR/kWh)."
                    )
                    market_profile_val = st.selectbox(
                        "Wholesale Auction Market:",
                        options=["epex_nl_2025"],
                        format_func=lambda x: "Netherlands EPEX Spot Day-Ahead 2025",
                        index=0
                    )
                with dyn_c2:
                    default_rate_val = st.number_input(
                        f"Fallback Commodity Rate ({currency}/kWh):",
                        min_value=0.0,
                        value=float(getattr(current, "default_energy_rate", 0.0900)),
                        step=0.0050,
                        format="%.4f",
                        help="Safety fallback price if a price timestamp is missing."
                    )
                edited_tou = None
                weekend_off_peak = False
            else:
                st.markdown("##### :material/schedule: Time-of-Use Rate Windows")
                edited_tou = st.data_editor(
                    st.session_state[state_tou_key],
                    num_rows="dynamic",
                    use_container_width=True,
                    column_config={
                        "name": st.column_config.TextColumn("Tariff Window", required=True),
                        "rate": st.column_config.NumberColumn(f"Commodity Rate ({currency}/kWh)", format="%.4f", min_value=0.0, step=0.0001, required=True),
                        "start_time": st.column_config.TextColumn("Start Time (HH:MM)", required=True),
                        "end_time": st.column_config.TextColumn("End Time (HH:MM)", required=True)
                    },
                    key=f"{key_prefix}_tou_editor"
                )
                weekend_off_peak = st.checkbox("Apply Off-Peak Tariff to Weekends", value=bool(current.weekend_is_off_peak))
                supplier_margin_val = 0.0
                market_profile_val = getattr(current, "market_price_profile_id", "epex_nl_2025") or "epex_nl_2025"
                default_rate_val = float(getattr(current, "default_energy_rate", 0.1200))

            # --------------------------------------------------------------------------
            # SECTION 4: Technical Rules, Validity & Taxes
            # --------------------------------------------------------------------------
            st.markdown("#### :material/tune: 4. Technical Constraints, Validity & Taxes")

            t_col1, t_col2, t_col3 = st.columns(3)
            with t_col1:
                reactive_tariff = st.number_input("Excess Reactive Tariff (/kVARh):", min_value=0.0, value=float(current.reactive_power_tariff), step=0.005, format="%.4f")
            with t_col2:
                min_cos_phi = st.number_input("Min Power Factor (cos phi):", min_value=0.50, max_value=1.00, value=float(current.min_power_factor), step=0.02, format="%.2f")
            with t_col3:
                reactive_allowance = st.number_input("Free Reactive Allowance (% of kWh):", min_value=0.0, max_value=100.0, value=float(current.reactive_power_allowance_pct), step=1.0, format="%.1f")

            # Applicable Validity Months
            all_month_abbrs = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            curr_app_months = getattr(current, "applicable_months", list(range(1, 13))) or list(range(1, 13))
            curr_selected_abbrs = [all_month_abbrs[m - 1] for m in curr_app_months if 1 <= m <= 12]

            selected_months = st.multiselect(
                "Governed Calendar Months (Default: All 12 Months):",
                options=all_month_abbrs,
                default=curr_selected_abbrs,
                key=f"{key_prefix}_months_multiselect"
            )
            parsed_app_months = [all_month_abbrs.index(m) + 1 for m in selected_months if m in all_month_abbrs]
            if not parsed_app_months:
                parsed_app_months = list(range(1, 13))

            # Dynamic Taxes Table
            st.markdown("##### Statutory Taxes and Levies (BTW / VAT, Energy Tax)")
            edited_taxes = st.data_editor(
                st.session_state[state_taxes_key],
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "name": st.column_config.TextColumn("Tax / Levy Name"),
                    "type": st.column_config.SelectboxColumn("Type", options=["percentage", "per_kwh", "fixed_monthly"], default="percentage"),
                    "value": st.column_config.NumberColumn("Rate / Value", format="%.4f"),
                    "description": st.column_config.TextColumn("Notes / Description")
                },
                key=f"{key_prefix}_taxes_editor"
            )

            submitted = st.form_submit_button("Save 3-Party Contract Configuration", icon=":material/save:", type="primary", use_container_width=True)

        if submitted:
            pricing_model_val = "day_ahead_dynamic" if is_dynamic_selected else "time_of_use"

            if is_dynamic_selected:
                cleaned_tou = [{"name": "Day-Ahead Dynamic Spot", "rate": default_rate_val, "start_time": "00:00", "end_time": "24:00"}]
                default_energy_rate = default_rate_val
            else:
                cleaned_tou = edited_tou.dropna(subset=["name", "rate"]).to_dict(orient="records") if edited_tou is not None and not edited_tou.empty else []
                for r in cleaned_tou:
                    r["rate"] = _sanitize_rate_val(r.get("rate", 0.20))
                    if r.get("name") == "Resto" and r.get("end_time") == "23:00":
                        r["end_time"] = "18:00"

                if not cleaned_tou:
                    cleaned_tou = [{"name": "Standard Rate", "rate": 0.20, "start_time": "00:00", "end_time": "24:00"}]
                default_energy_rate = float(cleaned_tou[0].get("rate", 0.20)) if cleaned_tou else 0.20

            st.session_state[state_tou_key] = pd.DataFrame(cleaned_tou)

            cleaned_taxes = []
            if edited_taxes is not None and not edited_taxes.empty:
                valid_tax_df = edited_taxes.dropna(subset=["name", "value"]).copy()
                mask = ~valid_tax_df["name"].astype(str).str.strip().str.lower().isin(["", "none", "nan"])
                valid_tax_df = valid_tax_df.loc[mask]
                raw_tax_records = valid_tax_df.to_dict(orient="records")
                for t in raw_tax_records:
                    t_name = str(t.get("name", "")).strip()
                    t_val = _sanitize_tax_val(t.get("value", 0.0))
                    if t_name and abs(t_val) > 1e-6:
                        cleaned_taxes.append({
                            "name": t_name,
                            "type": str(t.get("type", "percentage")).strip(),
                            "value": t_val,
                            "description": str(t.get("description", "")).strip() if pd.notnull(t.get("description")) else ""
                        })

            st.session_state[state_taxes_key] = pd.DataFrame(cleaned_taxes) if cleaned_taxes else pd.DataFrame(columns=["name", "type", "value", "description"])

            updated_contract = ThreePartyContract(
                name=contract_name_val,
                currency=currency,
                dso_name=dso_name_val,
                connection_category=connection_category_val,
                base_monthly_fee=base_fee,
                contracted_capacity_kw=contracted_kw,
                monthly_capacity_tariff=capacity_tariff,
                demand_capacity_tariff=demand_tariff,
                network_volume_tariff=network_volume_tariff_val,
                max_physical_limit_kw=max_physical_kw,
                peak_penalty_rate=penalty_rate,
                meter_company_name=meter_company_val,
                metering_monthly_fee=metering_monthly_val,
                supplier_name=supplier_name_val,
                supplier_base_fee_monthly=supplier_base_fee_val,
                pricing_model=pricing_model_val,
                supplier_margin=supplier_margin_val,
                market_price_profile_id=market_profile_val,
                reactive_power_tariff=reactive_tariff,
                min_power_factor=min_cos_phi,
                reactive_power_allowance_pct=reactive_allowance,
                tou_rates=cleaned_tou,
                default_energy_rate=default_energy_rate,
                weekend_is_off_peak=weekend_off_peak,
                applicable_months=parsed_app_months,
                taxes_and_fees=cleaned_taxes
            )

            if current.name in loaded_dict and current.name != updated_contract.name:
                del loaded_dict[current.name]

            st.session_state[state_contract_key] = updated_contract
            loaded_dict[updated_contract.name] = updated_contract
            st.session_state[loaded_contracts_dict_key] = loaded_dict
            st.session_state[f"{key_prefix}_active_contract_label"] = updated_contract.name
            st.toast(f"Saved 3-Party Contract '{updated_contract.name}'!", icon=":material/check_circle:")
            st.rerun()

    return st.session_state[state_contract_key]


# ======================================================================================
# 7. Main Single-Page Coordinator
# ======================================================================================

def render_minimal_contract_system(key_prefix: str = "sandbox_min") -> None:
    """
    Renders the unified 3-Party Electricity Contract & Consumption Lab:
      1. Consumption (CSV Load Profile Ingestion)
      2. 3-Party Electricity Contract Configuration
      3. Live Financial Assessment & Unbundled Cost Structure
    """
    st.title(":material/electric_meter: 3-Party Electricity Contract & Load Assessment Lab")
    st.caption("Isolated sandbox demonstrating European unbundled billing: Regulated DSO, Independent Metering (Meetbedrijf), and Supplier Procurement.")

    # 1. Consumption Ingestion
    st.header(":material/upload_file: 1. Consumption (CSV Load Profile Ingestion)")
    render_csv_inspector(key_prefix=f"{key_prefix}_csv")

    st.markdown("---")

    # Locate active load dataframe
    active_load_df = st.session_state.get("active_csv_df")
    if active_load_df is None or not isinstance(active_load_df, pd.DataFrame) or active_load_df.empty:
        for k in reversed(list(st.session_state.keys())):
            if "calc_data" in k and isinstance(st.session_state[k], dict) and "df_clean" in st.session_state[k]:
                df_c = st.session_state[k]["df_clean"]
                if isinstance(df_c, pd.DataFrame) and not df_c.empty:
                    active_load_df = df_c
                    break

    # 2. 3-Party Electricity Contract Form
    st.header(":material/description: 2. 3-Party Electricity Contract Model")
    contract = render_simplified_contract_form(key_prefix=f"{key_prefix}_contract")
    st.session_state["active_contract"] = contract

    st.divider()

    # 3. Financial Assessment & Live Billing Section
    st.subheader(":material/analytics: 3. Unbundled Billing & Financial Assessment")

    if active_load_df is None or active_load_df.empty:
        st.info("Upload a CSV meter profile in Section 1 above to trigger the automated 3-Party financial simulation.", icon=":material/info:")
        return

    # Form portfolio of loaded contracts for monthly routing
    loaded_dict = st.session_state.get(f"{key_prefix}_contract_loaded_contracts_dict", {})
    contracts_portfolio = list(loaded_dict.values()) if loaded_dict else [contract]
    if contract not in contracts_portfolio:
        contracts_portfolio.append(contract)

    # Compute live bill breakdown
    full_breakdown = compute_three_party_financial_bill(load_data=active_load_df, contract=contracts_portfolio)
    curr = getattr(contract, "currency", "EUR")

    # Period filter selector
    is_synthetic_annual = (len(full_breakdown.monthly_series) == 12 and full_breakdown.duration_days <= 1.5)
    overview_label = "All Months (Full Year Overview)" if is_synthetic_annual else "All Months (Full Duration Overview)"
    month_options = [overview_label]
    if full_breakdown.monthly_series:
        month_options += [m.period_label for m in full_breakdown.monthly_series]

    col_sel1, col_sel2 = st.columns([5, 3])
    with col_sel1:
        selected_period = st.selectbox(
            "Select Billing Period / Month to Inspect:",
            options=month_options,
            index=0,
            key=f"{key_prefix}_period_select"
        )
    with col_sel2:
        st.write("")
        st.write("")
        is_single_month = (selected_period != overview_label)
        if is_single_month:
            active_month_c = _resolve_contract_for_month(contracts_portfolio, selected_period, default_contract=contract)
            pricing_type_str = "Dynamic Spot" if getattr(active_month_c, "pricing_model", "time_of_use") == "day_ahead_dynamic" else "Fixed / TOU"
            st.info(
                f":material/contract: Month: **{selected_period}** | DSO: `{getattr(active_month_c, 'dso_name', 'DSO')}` | "
                f"Meetbedrijf: `{getattr(active_month_c, 'meter_company_name', 'Meetbedrijf')}` | "
                f"Supplier: `{getattr(active_month_c, 'supplier_name', 'Supplier')}` ({pricing_type_str})"
            )
        else:
            distinct_names = list(dict.fromkeys(c.name for c in contracts_portfolio))
            if len(distinct_names) > 1:
                st.info(f":material/account_tree: Multi-Contract portfolio active (**{len(distinct_names)}** contract configurations across 12 months).")

    if is_single_month:
        breakdown = compute_three_party_financial_bill(load_data=active_load_df, contract=contracts_portfolio, target_month=selected_period)
    else:
        breakdown = full_breakdown

    # Financial KPI Cards
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    if is_single_month:
        excess_p = max(0.0, breakdown.peak_demand_kw - breakdown.contracted_capacity_kw)
        with kpi_col1:
            render_kpi_card(
                title=f"{selected_period} Gross Total",
                value=f"{breakdown.total_gross_period:,.2f} {curr}",
                subtext=f"Net: {breakdown.total_net_period:,.2f} | Taxes: {breakdown.total_taxes_period:,.2f}"
            )
        with kpi_col2:
            render_kpi_card(
                title=f"{selected_period} Peak Demand",
                value=f"{breakdown.peak_demand_kw:,.1f} kW",
                subtext=f"Overload: +{excess_p:,.1f} kW (Limit: {breakdown.contracted_capacity_kw:.0f} kW)",
                status="alert" if excess_p > 0 else "ok"
            )
        with kpi_col3:
            render_kpi_card(
                title=f"{selected_period} Energy",
                value=f"{breakdown.total_consumption_kwh:,.0f} kWh",
                subtext=f"Duration: {breakdown.duration_days:.0f} days"
            )
        with kpi_col4:
            render_kpi_card(
                title="Effective Unit Rate",
                value=f"{breakdown.effective_kwh_price:.4f} {curr}/kWh",
                subtext="All-inclusive unit cost"
            )
    else:
        if breakdown.monthly_series:
            sched_gross = sum(m.total_gross for m in breakdown.monthly_series)
            sched_net = sum(m.total_net for m in breakdown.monthly_series)
            sched_taxes = sum(m.taxes_and_levies for m in breakdown.monthly_series)
            sched_kwh = sum(m.energy_kwh for m in breakdown.monthly_series)
            n_months = len(breakdown.monthly_series)
            avg_monthly_gross = sched_gross / max(1, n_months)
            effective_price = (sched_gross / sched_kwh) if sched_kwh > 0 else breakdown.effective_kwh_price
        else:
            sched_gross = breakdown.total_gross_period
            sched_net = breakdown.total_net_period
            sched_taxes = breakdown.total_taxes_period
            avg_monthly_gross = breakdown.total_gross_monthly
            effective_price = breakdown.effective_kwh_price

        with kpi_col1:
            render_kpi_card(
                title="Total Gross Electricity Cost",
                value=f"{sched_gross:,.2f} {curr}",
                subtext=f"Net: {sched_net:,.2f} | Taxes: {sched_taxes:,.2f}"
            )
        with kpi_col2:
            render_kpi_card(
                title="Monthly Average Invoice",
                value=f"{avg_monthly_gross:,.2f} {curr}",
                subtext=f"12-month unbundled share",
                status="info"
            )
        with kpi_col3:
            render_kpi_card(
                title="Total Energy Consumed",
                value=f"{breakdown.total_consumption_kwh:,.0f} kWh",
                subtext=f"Peak Demand: {breakdown.peak_demand_kw:,.1f} kW"
            )
        with kpi_col4:
            render_kpi_card(
                title="Effective Unit Rate",
                value=f"{effective_price:.4f} {curr}/kWh",
                subtext="Total cost ÷ total kWh",
                status="success"
            )

    # Charts: Donut & Payment Series
    col_chart1, col_chart2 = st.columns([1, 1])
    with col_chart1:
        st.subheader("3-Party Cost Breakdown")
        fig_donut = create_three_party_donut_figure(breakdown=breakdown)
        st.plotly_chart(fig_donut, use_container_width=True)

    with col_chart2:
        st.subheader("Payment Schedule Series (Zahlungsreihe)")
        fig_series = create_three_party_series_figure(breakdown=full_breakdown)
        st.plotly_chart(fig_series, use_container_width=True)

    # Itemized Billing Line Items Table
    st.subheader(":material/format_list_bulleted: Unbundled Itemized Billing Statement")
    if breakdown.line_items:
        t_rows = []
        for it in breakdown.line_items:
            t_rows.append({
                "Category": it.category,
                "Description": it.description,
                "Basis": f"{it.basis_quantity:,.2f} {it.unit}",
                "Unit Rate": f"{it.unit_rate:.4f} {curr}",
                "Period Total": f"{it.cost_period:,.2f} {curr}",
                "Monthly Total": f"{it.cost_monthly:,.2f} {curr}",
                "Share": f"{it.share_pct:.1f} %"
            })
        st.dataframe(pd.DataFrame(t_rows), use_container_width=True, hide_index=True)


def main():
    st.set_page_config(
        page_title="3-Party Electricity Contract & Load Assessment Lab",
        page_icon=":material/electric_meter:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    if apply_custom_styles:
        apply_custom_styles()
    render_minimal_contract_system()


if __name__ == "__main__":
    main()
