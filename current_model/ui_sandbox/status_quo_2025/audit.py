"""
========================================================================================
Audit & Verification Protocol Engine (audit.py)
========================================================================================
Executes the comprehensive, automated 4-point verification protocol across all
13 mathematical criteria defined in the Status Quo 2025 specification:
  - Audit Point 1: Lastgang-Integrität (Criteria 1.1, 1.2, 1.3)
  - Audit Point 2: DSO-Zwischenergebnisse & Breach Logic (Criteria 2.1, 2.2, 2.3, 2.4)
  - Audit Point 3: Handels- und Steuerkomponenten (Criteria 3.1, 3.2, 3.3, 3.4)
  - Audit Point 4: Gesamtrechnung und 15-Jahres-TCO (Criteria 4.1, 4.2, 4.3)
Emits structured dictionary reports and human-readable Markdown verification badges.
========================================================================================
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List

try:
    from .config_and_models import LoadSeries2025, StatusQuoAnnualResult
    from .consumption_pipeline import evaluate_load_integrity_audit
    from .dso_accounting import evaluate_dso_audit
    from .commercial_accounting import evaluate_commercial_audit
    from .status_quo_master import evaluate_master_audit
except (ImportError, ValueError):
    from config_and_models import LoadSeries2025, StatusQuoAnnualResult
    from consumption_pipeline import evaluate_load_integrity_audit
    from dso_accounting import evaluate_dso_audit
    from commercial_accounting import evaluate_commercial_audit
    from status_quo_master import evaluate_master_audit


@dataclass
class AuditReport:
    """Consolidated audit report across all 4 audit protocols."""
    passed_all: bool
    total_criteria_count: int = 14
    passed_criteria_count: int = 0
    failed_criteria_count: int = 0
    point_1_load: Dict[str, Any] = field(default_factory=dict)
    point_2_dso: Dict[str, Any] = field(default_factory=dict)
    point_3_commercial: Dict[str, Any] = field(default_factory=dict)
    point_4_master: Dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Renders an executive audit table with status icons."""
        lines = []
        overall_badge = f"PASSED ({self.passed_criteria_count}/{self.total_criteria_count} Checks)" if self.passed_all else f"FAILED ({self.failed_criteria_count} Discrepancies)"
        status_color = "#10B981" if self.passed_all else "#EF4444"

        lines.append(f"### Verification Protocol Status: <span style='color:{status_color}; font-weight:bold;'>{overall_badge}</span>\n")
        lines.append("| Audit Point | Criterion Description | Status | Evidence / Values |")
        lines.append("| :--- | :--- | :---: | :--- |")

        # Point 1
        p1 = self.point_1_load.get("criteria", {})
        c11 = p1.get("1.1_step_count_35040", {})
        lines.append(
            f"| **1. Load Integrity** | 1.1 Exact 35,040 steps (0.25 h) | {'PASS' if c11.get('passed') else 'FAIL'} | "
            f"Steps: {c11.get('actual_count'):,} (Expected: {c11.get('expected_count'):,}) |"
        )
        c12 = p1.get("1.2_energy_conservation", {})
        lines.append(
            f"| **1. Load Integrity** | 1.2 Energy conservation $\\sum P(t)\\Delta t = \\sum E_m$ | {'PASS' if c12.get('passed') else 'FAIL'} | "
            f"Interval: {c12.get('interval_sum_kwh'):,.1f} kWh | Monthly: {c12.get('monthly_sum_kwh'):,.1f} kWh |"
        )
        c13 = p1.get("1.3_time_classification", {})
        lines.append(
            f"| **1. Load Integrity** | 1.3 Month indices (1-12) & TOU classification | {'PASS' if c13.get('passed') else 'FAIL'} | "
            f"Valid calendar segmentation |"
        )

        # Point 2
        p2 = self.point_2_dso.get("criteria", {})
        c21 = p2.get("2.1_monthly_peaks_12", {})
        lines.append(
            f"| **2. DSO Accounting** | 2.1 Exactly 12 monthly peak demand values | {'PASS' if c21.get('passed') else 'FAIL'} | "
            f"12 calendar months evaluated |"
        )
        c22 = p2.get("2.2_peak_demand_fees_sum", {})
        lines.append(
            f"| **2. DSO Accounting** | 2.2 Peak demand fees $\\sum (P_{{\\text{{peak}},m}} \\times \\text{{Rate}})$ | {'PASS' if c22.get('passed') else 'FAIL'} | "
            f"Sum: € {c22.get('actual_sum', 0):,.2f} |"
        )
        c23 = p2.get("2.3_contract_capacity_breach_logic", {})
        lines.append(
            f"| **2. DSO Accounting** | 2.3 Contract capacity & Breach logic | {'PASS' if c23.get('passed') else 'FAIL'} | "
            f"Breaches detected: {c23.get('breaches_detected', 0)} |"
        )
        c24 = p2.get("2.4_fixed_and_volumetric_fees", {})
        lines.append(
            f"| **2. DSO Accounting** | 2.4 Standing connection/vastrecht & volumetric transport | {'PASS' if c24.get('passed') else 'FAIL'} | "
            f"Fixed and HT/NT volume rates verified |"
        )

        # Point 3
        p3 = self.point_3_commercial.get("criteria", {})
        c31 = p3.get("3.1_supplier_pricing_mode", {})
        lines.append(
            f"| **3. Commercial & Tax** | 3.1 Supplier pricing (Mode: {c31.get('mode', '').upper()}) | {'PASS' if c31.get('passed') else 'FAIL'} | "
            f"Commodity: € {c31.get('supplier_energy_cost', 0):,.2f} |"
        )
        c32 = p3.get("3.2_metering_independence", {})
        lines.append(
            f"| **3. Commercial & Tax** | 3.2 Certified metering flat fee independence | {'PASS' if c32.get('passed') else 'FAIL'} | "
            f"Annual fee: € {c32.get('actual_fee', 0):,.2f} |"
        )
        c33 = p3.get("3.3_statutory_levies", {})
        lines.append(
            f"| **3. Commercial & Tax** | 3.3 Statutory levies ($E_{{\\text{{total}}}} \\times \\text{{Rate}}$) | {'PASS' if c33.get('passed') else 'FAIL'} | "
            f"Levies: € {c33.get('actual_levies', 0):,.2f} |"
        )
        c34 = p3.get("3.4_feed_in_lock_zero", {})
        lines.append(
            f"| **3. Commercial & Tax** | 3.4 Feed-in compensation locked at € 0.00 | {'PASS' if c34.get('passed') else 'FAIL'} | "
            f"Credit: € {c34.get('actual_feed_in_credit', 0):,.2f} |"
        )

        # Point 4
        p4 = self.point_4_master.get("criteria", {})
        c41 = p4.get("4.1_net_annual_sum", {})
        lines.append(
            f"| **4. Master KPI & TCO** | 4.1 Annual net sum (DSO + Supp + Meter + Levies) | {'PASS' if c41.get('passed') else 'FAIL'} | "
            f"Net Total: € {c41.get('actual_net', 0):,.2f} |"
        )
        c42 = p4.get("4.2_blended_net_price", {})
        lines.append(
            f"| **4. Master KPI & TCO** | 4.2 Blended electricity price (€/kWh) | {'PASS' if c42.get('passed') else 'FAIL'} | "
            f"Blended Net: € {c42.get('actual_blended_eur_kwh', 0):.4f}/kWh |"
        )
        c43 = p4.get("4.3_tco_15_npv", {})
        lines.append(
            f"| **4. Master KPI & TCO** | 4.3 15-Year TCO NPV discounted lifecycle sum | {'PASS' if c43.get('passed') else 'FAIL'} | "
            f"15y NPV: € {c43.get('actual_tco_npv', 0):,.2f} |"
        )

        return "\n".join(lines)


def perform_full_status_quo_audit(
    load: LoadSeries2025,
    result: StatusQuoAnnualResult
) -> AuditReport:
    """
    Executes the complete audit battery against the 4 audit points and returns an AuditReport.
    """
    # 1. Load integrity
    monthly_consumption = [r.consumption for r in result.monthly_records]
    p1 = evaluate_load_integrity_audit(load, monthly_consumption)

    # 2. DSO
    dso_results = [r.dso for r in result.monthly_records]
    p2 = evaluate_dso_audit(monthly_consumption, dso_results, result.config.dso)

    # 3. Commercial
    comm_results = [r.commercial for r in result.monthly_records]
    p3 = evaluate_commercial_audit(
        load, monthly_consumption, comm_results,
        result.config.supplier, result.config.metering, result.config.levies
    )

    # 4. Master
    p4 = evaluate_master_audit(result)

    # Count passes
    checks = [
        p1["criteria"]["1.1_step_count_35040"]["passed"],
        p1["criteria"]["1.2_energy_conservation"]["passed"],
        p1["criteria"]["1.3_time_classification"]["passed"],
        p2["criteria"]["2.1_monthly_peaks_12"]["passed"],
        p2["criteria"]["2.2_peak_demand_fees_sum"]["passed"],
        p2["criteria"]["2.3_contract_capacity_breach_logic"]["passed"],
        p2["criteria"]["2.4_fixed_and_volumetric_fees"]["passed"],
        p3["criteria"]["3.1_supplier_pricing_mode"]["passed"],
        p3["criteria"]["3.2_metering_independence"]["passed"],
        p3["criteria"]["3.3_statutory_levies"]["passed"],
        p3["criteria"]["3.4_feed_in_lock_zero"]["passed"],
        p4["criteria"]["4.1_net_annual_sum"]["passed"],
        p4["criteria"]["4.2_blended_net_price"]["passed"],
        p4["criteria"]["4.3_tco_15_npv"]["passed"],
    ]

    passed_count = sum(1 for c in checks if c)
    total_count = len(checks)
    failed_count = total_count - passed_count
    passed_all = (failed_count == 0)

    return AuditReport(
        passed_all=passed_all,
        total_criteria_count=total_count,
        passed_criteria_count=passed_count,
        failed_criteria_count=failed_count,
        point_1_load=p1,
        point_2_dso=p2,
        point_3_commercial=p3,
        point_4_master=p4,
    )
