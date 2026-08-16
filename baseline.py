import streamlit as st

import random
# To Run: & C:/Users/mwien/AppData/Local/Programs/Python/Python312/python.exe -m streamlit run baseline.py)
st.title("This is a Testwebsite")
st.warning("This is a work in progress") 
a = st.button("Press me")
if a == True:
    st.write("Hallo")

st.header("We will test some new Models here")
st.divider()
st.write("wohin soll es gehen?")

cities = ["NYC","Tokyo","LA","Rio"]

selected_city = st.radio("wähle eine Stadt", options=cities)

if selected_city == "NYC":
    st.image("NYC.jpg")
elif selected_city == "Tokyo":
    st.image("Tokyo.jpg")
elif selected_city == "LA":
    st.image("La.jpg")
elif selected_city == "Rio":
    st.image("Rio.jpg")
st.divider()





if st.button("random"):
    st.session_state.random = random.choice(cities)
    st.image(st.session_state.random + ".jpg")

