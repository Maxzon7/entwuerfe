import datetime
import streamlit as st
from models.Load_profile import LoadProfile


def render_tab():
    st.subheader("Lastprofil / Maschine anlegen")

    with st.form(key="loadprofile_form"):
        name = st.text_input("Name der Maschine / Last", value="Maschine 1")
        power = st.number_input("Leistung (kW)", min_value=0.0, value=10.0, step=1.0)
        days_per_week = st.slider("Tage pro Woche", 1, 7, 5)

        col1, col2 = st.columns(2)
        with col1:
            start_time = st.time_input("Startzeit", value=datetime.time(8, 0), step=60)
        with col2:
            end_time = st.time_input("Endzeit", value=datetime.time(16, 30), step=60)

        submitted = st.form_submit_button("Profil berechnen")

    if submitted:
        # LoadProfile erstellen und Zeitfenster hinzufügen
        profile = LoadProfile(name=name, power=power, days_per_week=days_per_week)
        profile.add_time_window(start_time, end_time)

        # Daten generieren & berechnen
        df = profile.generate()
        daily_hours = profile.get_daily_operating_hours()
        annual_kwh = profile.get_annual_consumption_kwh()

        # Ergebnisse anzeigen
        st.success(f"Profil **{name}** erfolgreich erstellt!")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Betriebsstunden / Tag", f"{daily_hours:.2f} h")
        c2.metric("Leistung", f"{power:.1f} kW")
        c3.metric("Jahresverbrauch", f"{annual_kwh:,.0f} kWh")

        st.dataframe(df.head(20), use_container_width=True)