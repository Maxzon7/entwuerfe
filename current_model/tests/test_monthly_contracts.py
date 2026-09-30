"""
========================================================================================
Unit Tests: Monthly Electricity Contract Configuration & Resolution (tests/test_monthly_contracts.py)
========================================================================================
Verifies that:
1. Contract default applicable_months covers all 12 months [1..12].
2. Contract.applies_to_month supports int, abbreviation, and full month strings.
3. Serialization to and from dictionary / JSON preserves applicable_months.
4. _resolve_contract_for_month correctly routes months to their respective contracts.
5. compute_financial_bill evaluates multi-contract schedules per month accurately.
========================================================================================
"""

import unittest
import numpy as np
import pandas as pd
from current_model.models.contract import Contract, get_contract_presets
from current_model.core.financial_engine import compute_financial_bill, _resolve_contract_for_month


class TestMonthlyContractSystem(unittest.TestCase):
    """Tests for month-specific electricity contracts and dispatch."""

    def test_default_contract_applicable_months(self):
        c = Contract()
        self.assertEqual(len(c.applicable_months), 12)
        self.assertEqual(c.applicable_months, list(range(1, 13)))
        for m in range(1, 13):
            self.assertTrue(c.applies_to_month(m))
            self.assertTrue(c.applies_to_month(c.MONTH_NAMES[m - 1]))
            self.assertTrue(c.applies_to_month(c.MONTH_ABBRS[m - 1]))

    def test_custom_applicable_months(self):
        # Contract valid only for Q1 (Jan, Feb, Mar)
        q1_contract = Contract(name="Q1 Contract", applicable_months=[1, 2, 3])
        self.assertTrue(q1_contract.applies_to_month(1))
        self.assertTrue(q1_contract.applies_to_month("January"))
        self.assertTrue(q1_contract.applies_to_month("Jan"))
        self.assertTrue(q1_contract.applies_to_month("Feb"))
        self.assertTrue(q1_contract.applies_to_month(3))
        self.assertFalse(q1_contract.applies_to_month(4))
        self.assertFalse(q1_contract.applies_to_month("April"))
        self.assertFalse(q1_contract.applies_to_month("Jul"))

    def test_contract_serialization_with_months(self):
        c = Contract(name="Summer Dutch Contract", applicable_months=[6, 7, 8])
        d = c.to_dict()
        self.assertIn("applicable_months", d)
        self.assertEqual(d["applicable_months"], [6, 7, 8])

        reconstructed = Contract.from_dict(d)
        self.assertEqual(reconstructed.applicable_months, [6, 7, 8])
        self.assertTrue(reconstructed.applies_to_month("June"))
        self.assertFalse(reconstructed.applies_to_month("January"))

    def test_resolve_contract_for_month(self):
        winter = Contract(name="Winter", applicable_months=[12, 1, 2])
        summer = Contract(name="Summer", applicable_months=[6, 7, 8])
        base = Contract(name="Base", applicable_months=list(range(1, 13)))

        portfolio = [base, winter, summer]

        # Month 1 (Jan) should resolve to winter
        resolved_jan = _resolve_contract_for_month(portfolio, 1)
        self.assertEqual(resolved_jan.name, "Winter")

        # Month 7 (Jul) should resolve to summer
        resolved_jul = _resolve_contract_for_month(portfolio, 7)
        self.assertEqual(resolved_jul.name, "Summer")

        # Month 4 (Apr) should resolve to base
        resolved_apr = _resolve_contract_for_month(portfolio, 4)
        self.assertEqual(resolved_apr.name, "Base")

    def test_compute_financial_bill_multi_contract(self):
        # 24-hour synthetic flat load
        hours = np.linspace(0, 24, 96, endpoint=False)
        load_kw = [100.0] * 96

        c_cheap = Contract(
            name="Cheap Summer",
            default_energy_rate=0.10,
            monthly_capacity_tariff=1.0,
            contracted_capacity_kw=200.0,
            applicable_months=[6, 7, 8]
        )
        c_expensive = Contract(
            name="Expensive Winter",
            default_energy_rate=0.30,
            monthly_capacity_tariff=5.0,
            contracted_capacity_kw=200.0,
            applicable_months=[12, 1, 2]
        )
        c_standard = Contract(
            name="Standard",
            default_energy_rate=0.20,
            monthly_capacity_tariff=2.0,
            contracted_capacity_kw=200.0,
            applicable_months=list(range(1, 13))
        )

        portfolio = [c_standard, c_expensive, c_cheap]
        breakdown = compute_financial_bill(load_data=load_kw, contract=portfolio, duration_days=1.0)

        self.assertEqual(len(breakdown.monthly_series), 12)
        records_by_name = {m.period_label: m for m in breakdown.monthly_series}

        # January (Winter) should have higher effective rate than July (Summer)
        jan = records_by_name["January"]
        jul = records_by_name["July"]
        self.assertGreater(jan.effective_rate_kwh, jul.effective_rate_kwh)
        self.assertGreater(jan.capacity_cost_net, jul.capacity_cost_net)

    def test_netherlands_preset_exists(self):
        presets = get_contract_presets()
        self.assertIn("Netherlands Commercial Multi-Tariff (EUR)", presets)
        nl_c = presets["Netherlands Commercial Multi-Tariff (EUR)"]
        self.assertEqual(nl_c.currency, "EUR")
        self.assertEqual(len(nl_c.applicable_months), 12)


if __name__ == "__main__":
    unittest.main()
