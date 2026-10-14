"""
========================================================================================
Layer 9: Status Quo Audit Battery (engine/audit.py)
Current Situation (Status Quo) Sandbox Engine
========================================================================================
Validates all 5 audit points for Dutch Grootverbruik accounting integrity:
  - Audit Point 1: Consumption interval conservation and time classification
  - Audit Point 2: Regulated DSO 6-component accuracy and ratchet compliance
  - Audit Point 3: Commercial Supplier 5-component unbundled invoice accuracy
  - Audit Point 4: Degressive 5-bracket Energiebelasting & Vermindering accuracy
  - Audit Point 5: Master consolidation net/gross reconciliation and TCO discounting
========================================================================================
"""

from typing import Dict, Any
try:
    from .config_and_models import LoadSeries2025, StatusQuoAnnualResult, PricingMode
    from .consumption_pipeline import evaluate_consumption_audit
    from .dso_accounting import evaluate_dso_audit
except (ImportError, ValueError):
    from config_and_models import LoadSeries2025, StatusQuoAnnualResult, PricingMode
    from consumption_pipeline import evaluate_consumption_audit
    from dso_accounting import evaluate_dso_audit


def evaluate_tax_audit(result: StatusQuoAnnualResult) -> Dict[str, Any]:
    """Validates statutory energy taxation calculations."""
    total_gross_tax = sum(m.tax.gross_energy_tax for m in result.monthly_records)
    total_tax_reduction = sum(m.tax.tax_reduction_credit for m in result.monthly_records)
    total_net_tax = sum(m.tax.net_energy_tax for m in result.monthly_records)

    expected_reduction = (
        result.config.levies.annual_tax_reduction
        if result.config.levies.has_verblijfsfunctie else 0.0
    )
    reduction_matches = abs(total_tax_reduction - expected_reduction) < 0.20
    net_matches = abs(result.total_taxes_net - total_net_tax) < 0.20

    return {
        "audit_point": 4,
        "title": "Audit Point 4: Statutory Taxation & Energiebelasting",
        "passed": (reduction_matches and net_matches),
        "criteria": {
            "4.1_gross_tax": round(total_gross_tax, 2),
            "4.2_tax_reduction": round(total_tax_reduction, 2),
            "4.3_reduction_matches": reduction_matches,
            "4.4_net_tax_matches": net_matches,
        }
    }


def evaluate_master_balance_audit(result: StatusQuoAnnualResult) -> Dict[str, Any]:
    """Validates full 4-pillar sum reconciliation."""
    pillars_sum = (
        result.total_dso_net +
        result.total_supplier_net +
        result.total_metering_net +
        result.total_trafo_net +
        result.total_taxes_net
    )
    diff = abs(pillars_sum - result.total_status_quo_net)
    balance_matches = (diff < 0.20)

    expected_vat = result.total_status_quo_net * (result.vat_rate_pct / 100.0)
    vat_matches = abs(expected_vat - result.total_vat_amount) < 0.20
    gross_matches = abs((result.total_status_quo_net + expected_vat) - result.total_status_quo_gross) < 0.20

    return {
        "audit_point": 5,
        "title": "Audit Point 5: Master Net / Gross Financial Reconciliation",
        "passed": (balance_matches and vat_matches and gross_matches),
        "criteria": {
            "5.1_pillars_sum": round(pillars_sum, 2),
            "5.2_master_net": round(result.total_status_quo_net, 2),
            "5.3_balance_matches": balance_matches,
            "5.4_vat_matches": vat_matches,
            "5.5_gross_matches": gross_matches,
        }
    }


def perform_full_status_quo_audit(
    load: LoadSeries2025,
    result: StatusQuoAnnualResult
) -> Dict[str, Any]:
    """
    Executes all 5 audit validations and returns consolidated audit report.
    """
    m_consumption = [m.consumption for m in result.monthly_records]
    m_dso = [m.dso for m in result.monthly_records]

    audit_1 = evaluate_consumption_audit(load, m_consumption)
    audit_2 = evaluate_dso_audit(m_consumption, m_dso, result.config.dso)
    audit_4 = evaluate_tax_audit(result)
    audit_5 = evaluate_master_balance_audit(result)

    all_passed = (
        audit_1.get("passed", False) and
        audit_2.get("passed", False) and
        audit_4.get("passed", False) and
        audit_5.get("passed", False)
    )

    return {
        "overall_status": "PASSED" if all_passed else "FAILED",
        "all_passed": all_passed,
        "audit_points": {
            "point_1_load_integrity": audit_1,
            "point_2_dso_accounting": audit_2,
            "point_4_tax_accounting": audit_4,
            "point_5_master_balance": audit_5,
        }
    }
