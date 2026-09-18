"""
========================================================================================
CSV Ingestion & Mapping Forms (current_model/ui/csv_inspector/forms.py)
========================================================================================

Description:
------------
Streamlit forms and file uploader widgets for CSV load profile ingestion and column mapping.
"""

from typing import List, Tuple, Optional
import re
import streamlit as st
import pandas as pd


def render_csv_uploader_section(key_prefix: str = "csv_inspector") -> Tuple[Optional[List], bool]:
    """
    Renders the file uploader and demo loader button.
    Returns (uploaded_files, demo_requested).
    """
    st.subheader("1. CSV Data Ingestion & Demo Data")
    col_up, col_demo = st.columns([5, 2])

    with col_up:
        uploaded_files = st.file_uploader(
            "Upload Load Profile CSV(s):",
            type=["csv", "txt"],
            accept_multiple_files=True,
            key=f"{key_prefix}_uploader"
        )

    demo_requested = False
    with col_demo:
        st.write("")
        st.write("")
        if st.session_state.get(f"{key_prefix}_demo_loaded"):
            if st.button("Reset / Reload Demo Data", icon=":material/refresh:", key=f"{key_prefix}_reload_btn", use_container_width=True):
                keys_to_clear = [k for k in st.session_state if k.startswith(key_prefix)]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.session_state[f"{key_prefix}_demo_loaded"] = True
                st.rerun()
        else:
            if st.button("Load 15-Min Demo CSV", key=f"{key_prefix}_demo_btn", use_container_width=True):
                keys_to_clear = [k for k in st.session_state if k.startswith(key_prefix)]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.session_state[f"{key_prefix}_demo_loaded"] = True
                st.rerun()

    return uploaded_files, bool(st.session_state.get(f"{key_prefix}_demo_loaded"))
