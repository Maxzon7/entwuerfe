"""
========================================================================================
UI Sandbox & Prototyping Laboratory (ui_sandbox)
========================================================================================
Dedicated isolated testing environment for experimenting with Streamlit UI components,
custom widgets, charts, and layout prototypes without launching the main application.

Modular Sandbox Packages:
1. Currentsituation_sandbox: Tab 1 & Tab 2 replicas with upgraded 3-party financial architecture
2. status_quo_2025: Unbundled 5-layer 2025 commercial accounting & 4-point audit framework
3. monthly_baseline_lab: 12-month baseline & commercial tariff laboratory (Pozo 600, Enexis/Liander)
4. three_party_contract_lab: European 3-party unbundled electricity contract lab (15-min CSV)

IMPORTANT ARCHITECTURAL RULE:
- ui_sandbox may import from core, models, and ui.
- The main application (app.py, core/, models/, ui/) MUST NEVER import from ui_sandbox.
========================================================================================
"""

# Re-exports for backward compatibility and clean top-level access
from current_model.ui_sandbox.monthly_baseline_lab import (
    compute_monthly_billing,
    render_monthly_baseline_lab,
    get_salentein_pozo600_preset,
    get_3tier_argentine_preset,
    get_netherlands_commercial_preset,
    build_enexis_2025_tariff_dataframe,
    build_liander_2025_tariff_dataframe,
    ENEXIS_2025_GRID_TIERS,
    ENEXIS_2025_CONNECTION_CAPACITIES,
    LIANDER_2025_GRID_TIERS,
    LIANDER_2025_CONNECTION_CAPACITIES,
    TOUTierConfig,
    AnnualBillingSummary,
    MonthlyBillingResult,
)

from current_model.ui_sandbox.three_party_contract_lab import (
    ThreePartyContract,
    render_minimal_contract_system,
)

