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
