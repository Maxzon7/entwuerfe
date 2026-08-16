import streamlit as st

st.title("Loan calculator")

with st.form("finacial information"):
    income= st.number_input("monthly income")
    desired_loan = st.number_input("desired loan amount")
    lenght_of_loan = st.slider("loan duration (years)",3,30,10)
    submitted = st.form_submit_button("calculate")

if submitted:
    if desired_loan > income*lenght_of_loan*5:
        st.error("no way brookie,you can't afford that")
    else:
        st.success("loan is possible")
        col1, col2 = st.columns(2)

        with col1:
            st.header("loan option 1")

        with col2:
            st.header("loan option 2")
            monthly_payment2 = income*0.34
            