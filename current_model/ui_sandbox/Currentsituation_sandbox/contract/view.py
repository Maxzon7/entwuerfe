"""
========================================================================================
Status Quo 2025 Contract & Billing View (contract/view.py)
========================================================================================

Orchestration module for the 4 unbundled contract sub-tabs:
  1. Regulated Grid Operator (DSO) - tab_dso.py
  2. Energy Retailer (Supplier) - tab_supplier.py
  3. Metering & Taxes - tab_metering.py
  4. Total Overview & Statement - tab_overview.py

Includes a compact total strip directly above the tabs for immediate visibility
of Annual Net Total, Annual Gross Total, Blended Net Rate, and Peak Demand.
========================================================================================
"""

from typing import Tuple, Any
import streamlit as st
import pandas as pd

# Styling & Common Components
try:
    from current_model.ui.common.styles import apply_custom_styles
    from current_model.ui.common.cards import render_kpi_card
except ImportError:
    try:
        from ui.common.styles import apply_custom_styles
        from ui.common.cards import render_kpi_card
    except ImportError:
        pass

# 2025 Models & Engine
try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        TariffStage,
        PricingMode,
        DSOTariff,
        SupplierTariff,
        MeteringTariff,
        LevyConfig,
        StatusQuoConfig2025,
        LoadSeries2025,
        StatusQuoAnnualResult,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
        extract_monthly_consumption_records,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        calculate_status_quo_master_2025,
    )
except ImportError:
    try:
        from engine.config_and_models import (
            TariffStage,
            PricingMode,
            DSOTariff,
            SupplierTariff,
            MeteringTariff,
            LevyConfig,
            StatusQuoConfig2025,
            LoadSeries2025,
            StatusQuoAnnualResult,
        )
        from engine.consumption_pipeline import (
            normalize_load_profile_2025,
            synthesize_benchmark_load_profile_2025,
            extract_monthly_consumption_records,
        )
        from engine.status_quo_master import (
            calculate_status_quo_master_2025,
        )
    except ImportError:
        from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
            TariffStage,
            PricingMode,
            DSOTariff,
            SupplierTariff,
            MeteringTariff,
            LevyConfig,
            StatusQuoConfig2025,
            LoadSeries2025,
            StatusQuoAnnualResult,
        )
        from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
            normalize_load_profile_2025,
            synthesize_benchmark_load_profile_2025,
            extract_monthly_consumption_records,
        )
        from current_model.ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
            calculate_status_quo_master_2025,
        )

# Per-Tab Modular Renderers
try:
    from ui_sandbox.Currentsituation_sandbox.contract.tab_dso import render_dso_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_supplier import render_supplier_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_metering import render_metering_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_overview import render_overview_tab
except ImportError:
    try:
        from .tab_dso import render_dso_tab
        from .tab_supplier import render_supplier_tab
        from .tab_metering import render_metering_tab
        from .tab_overview import render_overview_tab
    except ImportError:
        from contract.tab_dso import render_dso_tab
        from contract.tab_supplier import render_supplier_tab
        from contract.tab_metering import render_metering_tab
        from contract.tab_overview import render_overview_tab


def _find_or_create_load_series_2025() -> Tuple[LoadSeries2025, str]:
    """Retrieves or normalizes the active load profile for reference year 2025."""
    if "active_load_series_2025" in st.session_state and isinstance(st.session_state["active_load_series_2025"], LoadSeries2025):
        fname = st.session_state.get("active_csv_filename", "Active Profile")
        return st.session_state["active_load_series_2025"], f"Normalized 2025 Meter Data ({fname})"

    if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
        df_csv = st.session_state["active_csv_df"]
        if not df_csv.empty:
            fname = st.session_state.get("active_csv_filename", "Uploaded Meter File")
            p_col = "Total_Demand_kW" if "Total_Demand_kW" in df_csv.columns else df_csv.columns[1]
            t_col = "timestamp" if "timestamp" in df_csv.columns else None
            try:
                load_norm, _ = normalize_load_profile_2025(raw_df=df_csv, power_col=p_col, time_col=t_col)
                st.session_state["active_load_series_2025"] = load_norm
                return load_norm, f"CSV Real Meter Data ({fname})"
            except Exception:
                pass

    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
    st.session_state["active_load_series_2025"] = load_bench
    return load_bench, "Commercial Benchmark Simulation (250 kW peak)"


def render_tab2_base_contract(key_prefix: str = "currsit_contract") -> StatusQuoAnnualResult:
    """
    Renders the Status Quo 2025 Electricity Contract Configuration & Accounting view.
    Orchestrates the 4 modular tabs:
      1. Regulated Grid Operator (DSO)
      2. Energy Retailer (Supplier)
      3. Metering & Taxes
      4. Total Overview & Statement
    Displays a compact total KPI strip directly above the tabs.
    """
    load_series, source_label = _find_or_create_load_series_2025()

    # Active Baseline Banner
    st.info(
        f":material/bolt: **Active Consumption Baseline:** {source_label} | "
        f"**Annual Energy:** {load_series.total_energy_kwh:,.1f} kWh | "
        f"**Peak Demand:** {load_series.peak_demand_kw:,.1f} kW",
        icon=":material/info:"
    )

    # Compact Total Strip Container (rendered physically above the tabs)
    compact_strip_container = st.container()

    # 4 Modular Actor & Overview Tabs
    st.markdown("### :material/account_tree: 3-Party Unbundled Market Actors & Tariffs")
    actor_tabs = st.tabs([
        ":material/grid_view: 1. Regulated Grid Operator (DSO)",
        ":material/storefront: 2. Energy Retailer (Supplier)",
        ":material/receipt_long: 3. Metering & Taxes",
        ":material/analytics: 4. Total Overview & Statement"
    ])

    # Sub-Tab 1: Regulated Grid Operator (DSO)
    with actor_tabs[0]:
        dso_tariff, dso_results, dso_summary = render_dso_tab(load_series, key_prefix=key_prefix)

    # Sub-Tab 2: Energy Retailer (Supplier)
    with actor_tabs[1]:
        supplier_tariff, supplier_net_total, billing_rows = render_supplier_tab(load_series, key_prefix=key_prefix)

    # Sub-Tab 3: Metering & Taxes
    with actor_tabs[2]:
        metering_tariff, levy_config, meter_annual, annual_levies_net = render_metering_tab(load_series, key_prefix=key_prefix)

    # Assemble Full 2025 Unbundled Contract Configuration & Execute Master Accounting
    discount_rate = float(st.session_state.get(f"{key_prefix}_tco_r", 4.0))
    escalation_rate = float(st.session_state.get(f"{key_prefix}_tco_g", 3.0))

    active_config = StatusQuoConfig2025(
        stage=TariffStage.STAGE_1_DEFAULT,
        dso=dso_tariff,
        supplier=supplier_tariff,
        metering=metering_tariff,
        levies=levy_config,
        discount_rate_pct=discount_rate,
        energy_escalation_pct=escalation_rate,
        evaluation_horizon_years=15,
    )

    result = calculate_status_quo_master_2025(load=load_series, config=active_config)

    # Populate the Compact Total Strip above the tabs
    with compact_strip_container:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.caption(":material/receipt_long: Annual Net Total")
                st.markdown(f"#### € {result.total_status_quo_net:,.2f}")
            with c2:
                st.caption(":material/payments: Annual Gross Total (incl. VAT)")
                st.markdown(f"#### € {result.total_status_quo_gross:,.2f}")
            with c3:
                st.caption(":material/price_change: Blended Net Rate")
                st.markdown(f"#### € {result.blended_price_net_kwh:.4f} / kWh")
            with c4:
                st.caption(":material/speed: Annual Peak Demand")
                st.markdown(f"#### {result.annual_peak_demand_kw:,.1f} kW")

    # Sub-Tab 4: Total Overview & Statement (at the end)
    with actor_tabs[3]:
        render_overview_tab(
            result=result,
            active_config=active_config,
            load_series=load_series,
            key_prefix=key_prefix
        )

    return result


def render_tab2_contract(key_prefix: str = "currsit_contract") -> Any:
    """Alias for render_tab2_base_contract."""
    return render_tab2_base_contract(key_prefix=key_prefix)


def render_tab2_contract_switch(key_prefix: str = "currsit_contract") -> Any:
    """Compatibility switch alias rendering the base contract."""
    return render_tab2_base_contract(key_prefix=key_prefix)
