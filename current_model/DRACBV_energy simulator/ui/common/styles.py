"""
========================================================================================
UI Styles & Theme Customization (current_model/ui/common/styles.py)
========================================================================================

Description:
------------
Provides global CSS styling for modern dark mode aesthetics, glassmorphism containers,
and interactive KPI and Alert cards.
"""

import streamlit as st


def apply_custom_styles() -> None:
    """Injects custom CSS styling and icon stylesheets (Font Awesome, Remix Icon, Flag Icons) into the active Streamlit app."""
    st.markdown(
        """
        <!-- Icon Libraries: Font Awesome 6, Remix Icon, Flag Icons -->
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/remixicon@4.2.0/fonts/remixicon.css">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/lipis/flag-icons@7.2.3/css/flag-icons.min.css">

        <style>
        /* Card Containers */
        .sandbox-card {
            background-color: #1a1f2c;
            border-radius: 10px;
            padding: 16px 20px;
            border-left: 5px solid #38bdf8;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            margin-bottom: 12px;
        }
        .sandbox-card-alert {
            background-color: #2b1319;
            border-radius: 10px;
            padding: 16px 20px;
            border-left: 5px solid #f43f5e;
            box-shadow: 0 4px 10px rgba(244,63,94,0.25);
            margin-bottom: 12px;
        }
        .sandbox-card-ok {
            background-color: #11261f;
            border-radius: 10px;
            padding: 16px 20px;
            border-left: 5px solid #10b981;
            box-shadow: 0 4px 10px rgba(16,185,129,0.25);
            margin-bottom: 12px;
        }
        
        /* Typography */
        .sandbox-title {
            font-size: 0.85rem;
            color: #94a3b8;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.5px;
        }
        .sandbox-value {
            font-size: 1.7rem;
            font-weight: 700;
            color: #f8fafc;
            margin-top: 4px;
        }
        .sandbox-sub {
            font-size: 0.75rem;
            color: #64748b;
            margin-top: 2px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
