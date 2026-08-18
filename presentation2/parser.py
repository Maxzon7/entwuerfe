"""
Parser & CSV Ingestion Module
==============================
Handles encoding detection, delimiter sniffing, metadata row skipping, and
smart heuristic column classification for European/international load profile CSVs.
"""

from io import StringIO
from typing import Tuple, List
import pandas as pd
import numpy as np


# Keyword synonym lists for heuristic detection
DATE_SYNONYMS = ['#', 'datum', 'date', 'zeit', 'timestamp', 'datetime', 'zeitstempel', 'period']
TIME_SYNONYMS = ['code', 'uhrzeit', 'time', 'time_of_day', 'tod', 'intervall', 'stunde', 'hour']
UNIT_SYNONYMS = ['eenheid', 'unit', 'einheit', 'status', 'valid', 'type', 'statuscode']


def read_raw_content(file) -> str:
    """
    Extracts raw string content from an uploaded file buffer across common encodings
    (UTF-8, Latin-1, CP1252, ISO-8859-1).
    """
    file.seek(0)
    raw_bytes = file.read()
    content = None
    for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        content = raw_bytes.decode('utf-8', errors='ignore')
    return content


def parse_csv_content(content: str, skiprows: int = 0) -> pd.DataFrame:
    """
    Parses string CSV content into a pandas DataFrame using Python's sniffing engine.
    """
    return pd.read_csv(StringIO(content), sep=None, engine='python', skiprows=skiprows)


def detect_suggested_columns(df: pd.DataFrame) -> Tuple[List[str], List[str], str]:
    """
    Scans the DataFrame columns and values to guess:
      1. Suggested Timestamp column(s) (e.g. ['#', 'CODE'] for split Date+Time files)
      2. Suggested Power measurement columns (numeric meter IDs)
      3. Suggested Unit / Conversion ('kWh (15-min interval) → kW' or 'kW')
    """
    cols = list(df.columns)
    time_cols: List[str] = []
    power_cols: List[str] = []
    suggested_unit = "kW (Active Power - Direct)"

    # 1. Detect Date Column
    date_col = None
    for c in cols:
        c_clean = str(c).strip().lower()
        if any(syn == c_clean or syn in c_clean for syn in DATE_SYNONYMS):
            date_col = c
            time_cols.append(c)
            break

    # 2. Detect separate Time-of-Day Column (e.g. 'CODE', 'Uhrzeit')
    for c in cols:
        if c == date_col:
            continue
        c_clean = str(c).strip().lower()
        if any(syn == c_clean for syn in TIME_SYNONYMS):
            time_cols.append(c)
            break

    if not time_cols and cols:
        time_cols = [cols[0]]

    # 3. Check for unit indicators (e.g. 'Eenheid' column containing 'kWh')
    for c in cols:
        c_clean = str(c).strip().lower()
        if any(u in c_clean for u in UNIT_SYNONYMS):
            sample_val = str(df[c].dropna().iloc[0]).lower() if not df[c].dropna().empty else ""
            if "kwh" in sample_val:
                suggested_unit = "kWh (15-min interval) → kW"
            elif "w" == sample_val:
                suggested_unit = "W (Watt) → kW"

    # 4. Detect Numeric Measurement / Power Columns (Exclude date, time, and unit columns)
    for c in cols:
        if c in time_cols:
            continue
        c_clean = str(c).strip().lower()
        if any(u in c_clean for u in UNIT_SYNONYMS):
            continue
        col_clean_str = df[c].astype(str).str.replace(' ', '').str.replace(',', '.')
        valid_numeric = pd.to_numeric(col_clean_str, errors='coerce').notnull().sum()
        if valid_numeric > (0.4 * len(df)):
            power_cols.append(c)

    return time_cols, power_cols, suggested_unit


def generate_sample_demo_csv(days: int = 7) -> Tuple[str, str]:
    """
    Synthesizes a realistic 15-minute European load profile CSV formatted with
    split date/time columns (#, CODE) and Dutch meter layout (Eenheid: kWh).
    Returns (filename, csv_text_content).
    """
    periods = 96 * days
    dates = pd.date_range(start="2024-01-01 00:00", periods=periods, freq="15min")
    hours = dates.hour
    workdays = dates.dayofweek < 5
    base = 2.0
    energy_kwh = np.where(workdays & (hours >= 7) & (hours <= 17), base + 6.0, base)
    energy_kwh = np.round(np.clip(energy_kwh + np.random.normal(0, 0.4, len(energy_kwh)), 0.5, None), 2)

    demo_df = pd.DataFrame({
        "#": dates.strftime("%d.%m.%Y"),
        "CODE": dates.strftime("%H:%M"),
        "Eenheid": "kWh",
        "871687400008864731MV": energy_kwh
    })
    buf = StringIO()
    demo_df.to_csv(buf, index=False, sep=";")
    return "Sample_Synthetic_Demo_Data.csv", buf.getvalue()
