"""
========================================================================================
Unit Tests: Standalone Monthly Baseline & Commercial Tariff Lab
(tests/test_monthly_baseline_lab.py)
========================================================================================
Validates that:
1. Bodegas Salentein (Pozo 600) reference dataset mathematically reproduces:
   - High Peak energy cost: € 16,062.92
   - Low Off-Peak energy cost: € 15,153.66
   - Fixed annual cost: € 5,018.40
   - Total annual cost: € 36,234.97 (within 0.01 € tolerance)
2. Argentine 3-Tier (Pico / Resto / Valle) correctly handles 3 dynamic TOU windows and peak penalties.
3. Netherlands commercial benchmark operates with EUR, Enexis capacity fees, and 1.0 FX rate.
4. Dynamic addition/modification of TOU windows in the dual-matrix layout operates correctly.
========================================================================================
"""

import unittest
import os
import sys
import pandas as pd

# Ensure project root and current_model are on sys.path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(TEST_DIR, ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))

for path in [WORKSPACE_ROOT, CURRENT_MODEL_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

from current_model.ui_sandbox.monthly_baseline_lab import (
    get_salentein_pozo600_preset,
    get_3tier_argentine_preset,
    get_netherlands_commercial_preset,
    compute_monthly_billing,
    build_enexis_2025_tariff_dataframe,
    build_liander_2025_tariff_dataframe,
    ENEXIS_2025_GRID_TIERS,
    ENEXIS_2025_CONNECTION_CAPACITIES,
    LIANDER_2025_GRID_TIERS,
    LIANDER_2025_CONNECTION_CAPACITIES,
    TOUTierConfig,
    AnnualBillingSummary
)


class TestMonthlyBaselineLab(unittest.TestCase):
    """Verifies mathematical precision and commercial contract functionality of the Monthly Baseline Lab."""

    def test_salentein_pozo600_cent_precise_reproduction(self):
        """
        Prüfziel: Anhand der exakten Originaldaten von Bodegas Salentein (Pozo 600) muss
        das Modul als mathematischen Zielwert centgenau die Jahreskosten von 36.234,97 EUR
        reproduzieren (Excel Blatt 1.1 & 1.3).
        """
        c_df, t_df, tiers, cur, fx, name = get_salentein_pozo600_preset()
        summary: AnnualBillingSummary = compute_monthly_billing(c_df, t_df, tiers, cur, fx)

        # 1. Total consumption volume check
        self.assertEqual(summary.total_kwh_by_tier["peak"], 88002.0, "Total High-Peak kWh must be 88,002")
        self.assertEqual(summary.total_kwh_by_tier["offpeak"], 133848.0, "Total Low-Peak kWh must be 133,848")
        self.assertEqual(summary.total_kwh, 221850.0, "Total consumption must be 221,850 kWh")
        self.assertEqual(summary.max_peak_kw, 105.0, "Maximum peak demand across months must be 105 kW")

        # 2. Itemized cost components
        # High Peak Cost: 88,002 * (172.46 * 1.3759 / 1300) = 16,062.92 EUR
        self.assertAlmostEqual(summary.cost_energy_by_tier_total_eur["peak"], 16062.92, places=2)
        # Low Off-Peak Cost: 133,848 * (106.97 * 1.3759 / 1300) = 15,153.66 EUR
        self.assertAlmostEqual(summary.cost_energy_by_tier_total_eur["offpeak"], 15153.66, places=2)
        # Total Energy Cost: 31,216.57 EUR
        self.assertAlmostEqual(summary.cost_energy_total_eur, 31216.57, delta=0.02)

        # 3. Fixed charges: 12 * (543,659.77 / 1300) = 5,018.40 EUR
        self.assertAlmostEqual(summary.cost_fixed_annual_eur, 5018.40, places=2)

        # 4. Grand Total Target: € 36,234.97 (deviation < 0.01 €)
        self.assertAlmostEqual(summary.cost_total_annual_eur, 36234.97, delta=0.01)
        self.assertTrue(summary.is_salentein_verified, "Status must be 100% verified against Excel Blatt 1.3")
        self.assertLess(summary.verification_delta_eur, 0.01)

    def test_3tier_argentine_contract_with_penalties(self):
        """Verifies 3-tier Time-of-Use pricing and capacity exceedance penalty calculations."""
        c_df, t_df, tiers, cur, fx, name = get_3tier_argentine_preset()
        summary_3t = compute_monthly_billing(c_df, t_df, tiers, cur, fx)

        self.assertEqual(len(summary_3t.total_kwh_by_tier), 3, "Must have exactly 3 TOU tiers")
        self.assertIn("peak", summary_3t.total_kwh_by_tier)
        self.assertIn("resto", summary_3t.total_kwh_by_tier)
        self.assertIn("valle", summary_3t.total_kwh_by_tier)

        # Check that exceedances are detected:
        # P_contract = 250 kW. Months with P_max > 250: March (252), Sept (258), Dec (255) -> 3 months with 2 + 8 + 5 = 15 kW excess
        self.assertEqual(summary_3t.months_with_excess_peak, 3)
        self.assertEqual(summary_3t.total_excess_peak_kw_months, 15.0)
        self.assertGreater(summary_3t.cost_penalty_annual_eur, 0.0)

    def test_netherlands_commercial_preset(self):
        """Verifies universal transferability to Dutch commercial energy tariffs with EUR, Enexis MS-D, and 1.0 FX."""
        c_df, t_df, tiers, cur, fx, name = get_netherlands_commercial_preset()
        summary_nl = compute_monthly_billing(c_df, t_df, tiers, cur, fx)

        self.assertEqual(summary_nl.total_kwh, 338400.0)
        self.assertEqual(cur, "EUR")
        self.assertEqual(fx, 1.0)
        self.assertGreater(summary_nl.cost_total_annual_eur, 0.0)
        # Check September exceedance (P_max = 260 kW vs P_contract = 250 kW -> 10 kW excess)
        self.assertEqual(summary_nl.months_with_excess_peak, 1)
        self.assertAlmostEqual(summary_nl.total_excess_peak_kw_months, 10.0)

        # Verify annual equivalence: Monthly Accrual vs Annual Settlement (Month 12)
        c_df_m, t_df_m, _, _, _, _ = get_netherlands_commercial_preset(billing_schedule="monthly")
        c_df_a, t_df_a, _, _, _, _ = get_netherlands_commercial_preset(billing_schedule="annual_settlement")

        sum_m = compute_monthly_billing(c_df_m, t_df_m, tiers, "EUR", 1.0)
        sum_a = compute_monthly_billing(c_df_a, t_df_a, tiers, "EUR", 1.0)

        # Total annual cost must match cent-precisely between monthly accrual and annual settlement
        self.assertAlmostEqual(sum_m.cost_total_annual_eur, sum_a.cost_total_annual_eur, delta=0.05)
        self.assertAlmostEqual(sum_m.cost_fixed_annual_eur, sum_a.cost_fixed_annual_eur, delta=0.05)

        # Verify that all 8 Enexis voltage levels construct valid 12-month tariff tables
        for tier_key in ENEXIS_2025_GRID_TIERS.keys():
            df_tier = build_enexis_2025_tariff_dataframe(grid_tier_key=tier_key)
            self.assertEqual(len(df_tier), 12)
            self.assertIn("rate_peak_demand_kw", df_tier.columns)

    def test_liander_commercial_preset(self):
        """Verifies Dutch commercial energy tariffs with EUR, Liander MS (Medium Voltage), and 1.0 FX."""
        c_df, t_df, tiers, cur, fx, name = get_netherlands_commercial_preset(provider="liander")
        summary_lia = compute_monthly_billing(c_df, t_df, tiers, cur, fx)

        self.assertEqual(summary_lia.total_kwh, 338400.0)
        self.assertEqual(cur, "EUR")
        self.assertEqual(fx, 1.0)
        self.assertGreater(summary_lia.cost_total_annual_eur, 0.0)
        self.assertIn("Liander", name)

        # Verify annual equivalence: Monthly Accrual vs Annual Settlement (Month 12)
        c_df_m, t_df_m, _, _, _, _ = get_netherlands_commercial_preset(provider="liander", billing_schedule="monthly")
        c_df_a, t_df_a, _, _, _, _ = get_netherlands_commercial_preset(provider="liander", billing_schedule="annual_settlement")

        sum_m = compute_monthly_billing(c_df_m, t_df_m, tiers, "EUR", 1.0)
        sum_a = compute_monthly_billing(c_df_a, t_df_a, tiers, "EUR", 1.0)

        # Total annual cost must match cent-precisely between monthly accrual and annual settlement
        self.assertAlmostEqual(sum_m.cost_total_annual_eur, sum_a.cost_total_annual_eur, delta=0.05)
        self.assertAlmostEqual(sum_m.cost_fixed_annual_eur, sum_a.cost_fixed_annual_eur, delta=0.05)

        # Verify that all 6 Liander grid tiers construct valid 12-month tariff tables
        for tier_key in LIANDER_2025_GRID_TIERS.keys():
            df_tier = build_liander_2025_tariff_dataframe(grid_tier_key=tier_key)
            self.assertEqual(len(df_tier), 12)
            self.assertIn("rate_peak_demand_kw", df_tier.columns)

    def test_dynamic_n_tier_addition(self):
        """Verifies adding a 3rd custom TOU tier dynamically recalculates billing accurately."""
        c_df, t_df, tiers, cur, fx, name = get_salentein_pozo600_preset()

        # Add a 3rd tier
        t3 = TOUTierConfig(id="tier_3", name="Super Off-Peak", time_window="02:00 - 06:00")
        tiers.append(t3)
        c_df["kWh_tier_3"] = 1000.0  # 1,000 kWh per month = 12,000 kWh/yr
        t_df["rate_tier_3"] = 50.0   # 50.0 ARS/kWh

        summary = compute_monthly_billing(c_df, t_df, tiers, cur, fx)
        self.assertEqual(len(summary.total_kwh_by_tier), 3)
        self.assertEqual(summary.total_kwh_by_tier["tier_3"], 12000.0)
        self.assertGreater(summary.cost_energy_by_tier_total_eur["tier_3"], 0.0)

    def test_eur_contract_with_capacity_and_peak_demand(self):
        """Verifies European contract math: 104 kW * 5.0 €/kW capacity + 103 kW * 34.0 €/kW demand + TOU energy."""
        c_df, _, tiers, _, _, _ = get_salentein_pozo600_preset()
        tariff_data = []
        for idx, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1):
            tariff_data.append({
                "month_index": idx,
                "Month": m,
                "base_fee": 20.00,
                "rate_contracted_kw": 5.00,
                "rate_excess_kw": 4.80,
                "rate_peak_demand_kw": 34.00,
                "rate_peak": 0.2000,
                "rate_offpeak": 0.0150,
                "tax_rate_pct": 22.00,
                "exempt_surcharge": 0.0
            })
        t_df = pd.DataFrame(tariff_data)

        # Even if fx_rate is passed as 1300.0, EUR currency must strictly evaluate with FX=1.0
        summary = compute_monthly_billing(c_df, t_df, tiers, currency="EUR", fx_rate=1300.0)

        # January Month 1 Check:
        # P_contract: 104 * 5.00 * 1.22 = 634.40 EUR
        # P_max: 103 * 34.00 * 1.22 = 4,272.44 EUR
        # Base fee: 20.00 * 1.22 = 24.40 EUR
        # Pico energy: 11,190 * 0.20 * 1.22 = 2,730.36 EUR
        # Low energy: 17,730 * 0.015 * 1.22 = 324.46 EUR
        # Month 1 Total Gross = 634.40 + 4272.44 + 24.40 + 2730.36 + 324.46 = 7,986.06 EUR
        m1 = summary.monthly_results[0]
        self.assertAlmostEqual(m1.cost_contracted_capacity_eur, 634.40, places=2)
        self.assertAlmostEqual(m1.cost_measured_demand_eur, 4272.44, places=2)
        self.assertAlmostEqual(m1.cost_base_fee_eur, 24.40, places=2)
        self.assertAlmostEqual(m1.cost_energy_total_eur, 3054.82, places=2)
        self.assertAlmostEqual(m1.cost_total_eur, 7986.06, places=2)

        # Annual sum check (~78k EUR)
        self.assertGreater(summary.cost_total_annual_eur, 70000.0)


if __name__ == "__main__":
    unittest.main()
