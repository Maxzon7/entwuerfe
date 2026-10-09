"""
========================================================================================
Monthly Baseline Detailed Mathematical Audit Panel
(current_model/ui_sandbox/monthly_audit.py)
========================================================================================

Description:
------------
Renders the step-by-step mathematical audit and intermediate numerical calculations
for the 12-Month Baseline & Commercial Tariff Lab.
- Monthly Bill Audit: Step-by-step arithmetic (net rate x volume x tax multiplier)
  for capacity, peak demand, exceedance penalties, base standing fees, and TOU tiers.
- Full-Year Grand Totals: Comprehensive annual summation and weighted blended rate.
========================================================================================
"""

from typing import List
import pandas as pd
import streamlit as st

# Safe imports
try:
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_presets import TOUTierConfig
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_calc import AnnualBillingSummary
except ImportError:
    from monthly_presets import TOUTierConfig
    from monthly_calc import AnnualBillingSummary


def render_mathematical_audit_panel(
    summary: AnnualBillingSummary,
    active_tiers: List[TOUTierConfig],
    tariff_df: pd.DataFrame,
    selected_cur: str = "EUR",
    key_prefix: str = "monthly_baseline"
):
    """
    Renders an expandable Streamlit container providing cent-level mathematical audit
    and arithmetic explanations for any individual monthly bill or the annual total.
    """
    with st.expander(":material/calculate: Detailed Mathematical Audit & Intermediate Calculations", expanded=True):
        st.caption(
            "Inspect the exact numerical arithmetic for each monthly bill and full-year totals "
            "with all applied rates, taxes, and volumes."
        )

        tab_month_audit, tab_annual_audit = st.tabs([
            ":material/calendar_today: Monthly Bill Audit",
            ":material/functions: Full-Year Grand Totals"
        ])

        # ----------------------------------------------------------------------
        # Tab 1: Single Month Detailed Calculation Breakdown
        # ----------------------------------------------------------------------
        with tab_month_audit:
            month_names = [r.month_name for r in summary.monthly_results]
            sel_m_idx = st.selectbox(
                "Select Month to Audit",
                options=list(range(len(month_names))),
                format_func=lambda x: f"Month {x+1}: {month_names[x]}",
                key=f"{key_prefix}_audit_month_select"
            )
            res_m = summary.monthly_results[sel_m_idx]
            t_row_m = tariff_df.iloc[sel_m_idx] if sel_m_idx < len(tariff_df) else tariff_df.iloc[-1]
            tax_pct_m = float(t_row_m.get("tax_rate_pct", 21.0))

            c_audit1, c_audit2 = st.columns(2)
            with c_audit1:
                st.markdown(f"#### :material/power: Capacity, Demand & Fixed Charges ({res_m.month_name})")

                # Contracted capacity calculation
                rate_cap_m = float(t_row_m.get("rate_contracted_kw", 0.0))
                net_cap_val = res_m.contracted_capacity_kw * rate_cap_m
                st.markdown(
                    f"**1. Contracted Capacity Fee ($P_{{contract}}$):**  \n"
                    f"`{res_m.contracted_capacity_kw:,.0f} kW` × `{rate_cap_m:,.3f} {selected_cur}/kW` = `{net_cap_val:,.2f} {selected_cur}` net  \n"
                    f"→ Gross (incl. {tax_pct_m:.1f}% Tax): **€ {res_m.cost_contracted_capacity_eur:,.2f}**"
                )

                # Measured peak demand calculation
                rate_dem_m = float(t_row_m.get("rate_peak_demand_kw", 0.0))
                net_dem_val = res_m.peak_demand_kw * rate_dem_m
                st.markdown(
                    f"**2. Measured Peak Demand Fee ($P_{{max}}$):**  \n"
                    f"`{res_m.peak_demand_kw:,.0f} kW` × `{rate_dem_m:,.3f} {selected_cur}/kW` = `{net_dem_val:,.2f} {selected_cur}` net  \n"
                    f"→ Gross (incl. {tax_pct_m:.1f}% Tax): **€ {res_m.cost_measured_demand_eur:,.2f}**"
                )

                # Limit exceedance penalty calculation
                rate_pen_m = float(t_row_m.get("rate_excess_kw", 0.0))
                if res_m.excess_peak_kw > 0:
                    net_pen_val = res_m.excess_peak_kw * rate_pen_m
                    st.markdown(
                        f"**3. Capacity Exceedance Penalty:**  \n"
                        f"`({res_m.peak_demand_kw:,.0f} - {res_m.contracted_capacity_kw:,.0f}) = {res_m.excess_peak_kw:,.0f} kW Overrun` × `{rate_pen_m:,.3f} {selected_cur}/kW` = `{net_pen_val:,.2f} {selected_cur}` net  \n"
                        f"→ Gross (incl. {tax_pct_m:.1f}% Tax): **€ {res_m.cost_penalty_eur:,.2f}**"
                    )
                else:
                    st.markdown(f"**3. Capacity Exceedance Penalty:**  \n`0 kW Overrun` (Within contracted limit) → **€ 0.00**")

                # Base Standing fee calculation
                base_val = float(t_row_m.get("base_fee", 0.0))
                st.markdown(
                    f"**4. Standing Base Fee (DSO):**  \n"
                    f"`{base_val:,.2f} {selected_cur}` net × (1 + {tax_pct_m:.1f}% Tax) → **€ {res_m.cost_base_fee_eur + res_m.cost_exempt_surcharge_eur:,.2f}**"
                )

                # Meetbedrijf Metering fee calculation
                meter_val = float(t_row_m.get("metering_fee", 0.0))
                if res_m.cost_metering_eur > 0 or meter_val > 0:
                    st.markdown(
                        f"**5. Metering & Telemetry Fee (Meetbedrijf):**  \n"
                        f"`{meter_val:,.2f} {selected_cur}` net × (1 + {tax_pct_m:.1f}% Tax) → **€ {res_m.cost_metering_eur:,.2f}**"
                    )

            with c_audit2:
                st.markdown(f"#### :material/bolt: TOU Energy Volume Charges ({res_m.month_name})")

                tot_e_gross = 0.0
                for tier in active_tiers:
                    kwh_t = res_m.kwh_by_tier.get(tier.id, 0.0)
                    rate_t = float(t_row_m.get(f"rate_{tier.id}", 0.0))
                    cost_t_eur = res_m.cost_energy_by_tier_eur.get(tier.id, 0.0)
                    tot_e_gross += cost_t_eur
                    st.markdown(
                        f"**• {tier.name} (Supplier):**  \n"
                        f"`{kwh_t:,.0f} kWh` × `{rate_t:,.4f} {selected_cur}/kWh` × (1 + {tax_pct_m:.1f}% Tax) = **€ {cost_t_eur:,.2f}**"
                    )

                st.markdown(f"**Total Energy Volume Cost ({res_m.month_name}):** `€ {tot_e_gross:,.2f}` (`{res_m.kwh_total:,.0f} kWh`)")

                st.markdown("---")
                meter_str = f" + `€ {res_m.cost_metering_eur:,.2f} (Meetbedrijf)`" if res_m.cost_metering_eur > 0 else ""
                st.markdown(
                    f"### :material/receipt_long: **Month Total ({res_m.month_name}):**  \n"
                    f"`€ {res_m.cost_energy_total_eur:,.2f} (Energy)` + `€ {res_m.cost_contracted_capacity_eur:,.2f} (Capacity)` + "
                    f"`€ {res_m.cost_measured_demand_eur:,.2f} (Demand)` + `€ {res_m.cost_penalty_eur:,.2f} (Penalty)` + "
                    f"`€ {res_m.cost_base_fee_eur + res_m.cost_exempt_surcharge_eur:,.2f} (DSO Base)`{meter_str}  \n"
                    f"= **€ {res_m.cost_total_eur:,.2f}** *(Effective Blended: `€ {res_m.blended_rate_eur_per_kwh:.4f} / kWh`)*"
                )

        # ----------------------------------------------------------------------
        # Tab 2: Full-Year Grand Totals & Aggregations
        # ----------------------------------------------------------------------
        with tab_annual_audit:
            st.markdown("#### :material/summarize: Full-Year Grand Aggregations (12 Months)")
            a_col1, a_col2 = st.columns(2)
            with a_col1:
                st.markdown(
                    f"1. **Annual Energy Total (Supplier):** `{summary.total_kwh:,.0f} kWh`  \n"
                    f"   → Grand Energy Cost: **€ {summary.cost_energy_total_eur:,.2f}**"
                )
                st.markdown(
                    f"2. **Annual Contracted Capacity Fees (DSO):**  \n"
                    f"   → Sum across 12 months: **€ {summary.cost_contracted_capacity_annual_eur:,.2f}**"
                )
                st.markdown(
                    f"3. **Annual Measured Peak Demand Fees (DSO):**  \n"
                    f"   → Sum across 12 months: **€ {summary.cost_measured_demand_annual_eur:,.2f}**"
                )
            with a_col2:
                st.markdown(
                    f"4. **Annual Exceedance Penalties (DSO):**  \n"
                    f"   → Total Overrun ({summary.months_with_excess_peak} months): **€ {summary.cost_penalty_annual_eur:,.2f}**"
                )
                st.markdown(
                    f"5. **Annual Standing & Base Fees (DSO):**  \n"
                    f"   → Total Base Charges: **€ {summary.cost_base_fee_annual_eur + summary.cost_exempt_surcharge_annual_eur:,.2f}**"
                )
                if summary.cost_metering_annual_eur > 0:
                    st.markdown(
                        f"6. **Annual Metering & Telemetry Fees (Meetbedrijf):**  \n"
                        f"   → Total Metering Charges: **€ {summary.cost_metering_annual_eur:,.2f}**"
                    )
                st.markdown(
                    f"### :material/account_balance_wallet: **Grand Total Annual Electricity Cost:**  \n"
                    f"= **€ {summary.cost_total_annual_eur:,.2f}**  \n"
                    f"*(Annual Blended Average: `€ {summary.blended_rate_annual_eur:.4f} / kWh`)*"
                )
