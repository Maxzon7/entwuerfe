import streamlit as st
from tabs.tab1_baseline import render_tab

# To run: python -m streamlit run app.py

def main():
    st.title("DRACBV energy simulator")
    st.warning("This is a work in progress")

    render_tab()


if __name__ == "__main__":
    main()