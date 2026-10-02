"""
========================================================================================
Monthly Baseline Time-of-Use (TOU) Tier Management Module
(current_model/ui_sandbox/monthly_tou_manager.py)
========================================================================================

Description:
------------
Manages dynamic N-tier Time-of-Use energy pricing windows:
- Add new TOU windows with assigned color and default rates/volumes.
- Remove trailing TOU windows and clean up dependent DataFrame columns.
- Inline renameable tier labels.
- Synchronizes Table A (kWh) and Table B ($/kWh) column structures.
========================================================================================
"""

from typing import List
import streamlit as st

# Safe import
try:
    from current_model.ui_sandbox.monthly_presets import TOUTierConfig
except ImportError:
    from monthly_presets import TOUTierConfig


def render_tou_window_manager(
    key_prefix: str = "monthly_baseline",
    selected_cur: str = "EUR"
) -> List[TOUTierConfig]:
    """
    Renders Section 2: Time-of-Use (TOU) Windows Configuration.
    Allows users to dynamically add, remove, and rename pricing windows.
    Returns:
        List[TOUTierConfig]: Updated list of active TOU tiers.
    """
    state_cdf_key = f"{key_prefix}_consumption_df"
    state_tdf_key = f"{key_prefix}_tariff_df"
    state_tiers_key = f"{key_prefix}_tou_tiers"

    active_tiers: List[TOUTierConfig] = st.session_state.get(state_tiers_key, [])

    st.markdown("### :material/schedule: 1. Time-of-Use (TOU) Windows Configuration")
    st.caption("Configure the number of TOU windows and their names. Both tables below automatically adapt their columns.")

    with st.container(border=True):
        col_t_title, col_t_actions = st.columns([3, 2])
        with col_t_title:
            st.markdown(f"**Active TOU Windows ({len(active_tiers)} Tiers)**")
        with col_t_actions:
            btn_add, btn_del = st.columns(2)
            with btn_add:
                if st.button(":material/add: Add TOU Tier", key=f"{key_prefix}_add_tier", use_container_width=True):
                    tier_idx = len(active_tiers) + 1
                    tier_colors = ["#EF4444", "#3B82F6", "#F59E0B", "#10B981", "#8B5CF6", "#EC4899", "#06B6D4"]
                    new_color = tier_colors[(tier_idx - 1) % len(tier_colors)]
                    new_tier = TOUTierConfig(
                        id=f"tier_{tier_idx}",
                        name=f"Tier {tier_idx} (Hours)",
                        time_window="Custom Hours",
                        color=new_color
                    )
                    active_tiers.append(new_tier)

                    # Update consumption DataFrame
                    c_col = f"kWh_{new_tier.id}"
                    if c_col not in st.session_state[state_cdf_key].columns:
                        st.session_state[state_cdf_key][c_col] = 5000.0

                    # Update tariff DataFrame
                    t_col = f"rate_{new_tier.id}"
                    if t_col not in st.session_state[state_tdf_key].columns:
                        st.session_state[state_tdf_key][t_col] = 100.0 if selected_cur == "ARS" else 0.1500

                    st.session_state[state_tiers_key] = active_tiers
                    st.rerun()

            with btn_del:
                if len(active_tiers) > 1:
                    if st.button(":material/delete: Remove Tier", key=f"{key_prefix}_del_tier", use_container_width=True):
                        removed = active_tiers.pop()
                        st.session_state[state_cdf_key].drop(columns=[f"kWh_{removed.id}"], inplace=True, errors="ignore")
                        st.session_state[state_tdf_key].drop(columns=[f"rate_{removed.id}"], inplace=True, errors="ignore")
                        st.session_state[state_tiers_key] = active_tiers
                        st.rerun()

        # Renameable tier headers
        tier_cols = st.columns(len(active_tiers))
        for t_idx, tier in enumerate(active_tiers):
            with tier_cols[t_idx]:
                st.markdown(f"<span style='color:{tier.color}; font-weight:bold;'>:material/circle: Tier {t_idx+1}</span>", unsafe_allow_html=True)
                new_name = st.text_input(
                    f"Tier {t_idx+1} Name",
                    value=tier.name,
                    key=f"{key_prefix}_tier_edit_name_{tier.id}_{t_idx}"
                )
                tier.name = new_name

        st.session_state[state_tiers_key] = active_tiers

    st.markdown("---")
    return active_tiers
