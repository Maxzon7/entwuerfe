"""
========================================================================================
KPI & Alert Card Components (current_model/ui/common/cards.py)
========================================================================================

Description:
------------
Reusable Streamlit UI helper functions to render styled KPI metric and status alert cards.
"""

from typing import Optional
import streamlit as st


def render_kpi_card(
    title: str,
    value: str,
    subtext: Optional[str] = None,
    status: str = "default"
) -> None:
    """
    Renders a styled metric card.

    Args:
        title (str): Card title / label.
        value (str): Main metric value (large text).
        subtext (Optional[str]): Explanatory text beneath the value.
        status (str): Card theme ('default', 'ok', or 'alert').
    """
    card_class = "sandbox-card"
    if status == "alert":
        card_class = "sandbox-card-alert"
    elif status == "ok":
        card_class = "sandbox-card-ok"

    sub_html = f'<div class="sandbox-sub">{subtext}</div>' if subtext else ""

    st.markdown(
        f"""
        <div class="{card_class}">
            <div class="sandbox-title">{title}</div>
            <div class="sandbox-value">{value}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True
    )


def render_active_scenario_banner() -> None:
    """
    Renders an executive header banner displaying the currently active scenario branch,
    its technology mix, color indicator, and context across all workspace tabs.
    """
    from current_model.core.project_io import export_project_from_session
    project = export_project_from_session()

    if project.active_sub_scenario_id:
        sub = project.get_sub_scenario(project.active_sub_scenario_id)
        if sub:
            scen_name = sub.name
            scen_tech = sub.technology_mix_label
            color = sub.color_code or "#059669"
            badge_icon = ":material/alt_route:"
            badge_text = "Active Sub-Scenario"
        else:
            scen_name = "Status Quo (Base Benchmark)"
            scen_tech = "Grid Supply Only (Baseline Reference)"
            color = "#3B82F6"
            badge_icon = ":material/lock:"
            badge_text = "Base Benchmark"
    else:
        scen_name = "Status Quo (Base Benchmark)"
        scen_tech = "Grid Supply Only (Baseline Reference)"
        color = "#3B82F6"
        badge_icon = ":material/lock:"
        badge_text = "Base Benchmark"

    st.markdown(
        f"""
        <div style="background: linear-gradient(90deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.85) 100%); 
                    border-left: 5px solid {color}; border-top: 1px solid rgba(51, 65, 85, 0.8); 
                    border-right: 1px solid rgba(51, 65, 85, 0.8); border-bottom: 1px solid rgba(51, 65, 85, 0.8); 
                    border-radius: 8px; padding: 10px 16px; margin: 6px 0 14px 0; display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="background: {color}22; border: 1px solid {color}66; color: {color}; border-radius: 6px; padding: 3px 10px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">
                    {badge_text}
                </div>
                <div>
                    <span style="font-size: 1.05rem; font-weight: 700; color: #F8FAFC;">{scen_name}</span>
                    <span style="font-size: 0.85rem; color: #94A3B8; margin-left: 8px;">| Technology: <strong style="color: #E2E8F0;">{scen_tech}</strong></span>
                </div>
            </div>
            <div style="font-size: 0.8rem; color: #64748B; text-align: right;">
                <span>Switch / create branches in the left sidebar &larr;</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

