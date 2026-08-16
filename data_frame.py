import pandas as pd
import streamlit as st
# To run: & C:/Users/mwien/AppData/Local/Programs/Python/Python312/python.exe -m streamlit run data_frame.py
# or: python -m streamlit run data_frame.py

st.header("Training website for DRACBV")

st.subheader("Example Data set")

df = pd.DataFrame({
    "contract":["liander","Enexis","Rijkswaterstaat"],
    "base fee":[300,400,200],
    "volume":[500,600,700],
    "volume fee":[30,60,20]
    
})
st.table(df)
st.divider()
st.subheader("editable data")
edit_df = st.data_editor(df)

