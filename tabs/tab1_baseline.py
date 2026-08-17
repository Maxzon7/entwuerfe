import streamlit as st

with st.form(key="profile_form"):
    st.text_input("name", "")
    st.number_input("age", 0, 120, 30, 1)
    submitted = st.form_submit_button("Submit")
