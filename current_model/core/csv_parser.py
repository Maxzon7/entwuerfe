"""
========================================================================================
Parser & CSV Ingestion Engine (current_model/core/csv_parser.py)
========================================================================================

Description:
------------
Handles encoding detection, delimiter sniffing, metadata row skipping, and
smart heuristic value-based column classification for European, Spanish, German,
and international load profile CSVs.
"""

from io import StringIO
from typing import Tuple, List, Any, Optional
import re
import pandas as pd
import numpy as np


# Keyword synonym lists for heuristic detection (German, English, Spanish)
DATE_SYNONYMS = ['#', 'datum', 'date', 'zeit', 'timestamp', 'datetime', 'zeitstempel', 'period', 'fecha', 'dia']
TIME_SYNONYMS = ['code', 'uhrzeit', 'time', 'time_of_day', 'tod', 'intervall', 'stunde', 'hour', 'hora', 'horario']
UNIT_SYNONYMS = ['eenheid', 'unit', 'einheit', 'status', 'valid', 'type', 'statuscode', 'unidad']

# Regex patterns for value-based detection
DATE_PATTERNS = [
    r'^\s*\d{1,4}[./-]\d{1,2}[./-]\d{2,4}\s*$',
    r'^\s*\d{4}-\d{2}-\d{2}\s*$'
]
TIME_PATTERNS = [
    r'^\s*\d{1,2}:\d{2}(:\d{2})?\s*$'
]
DATETIME_PATTERNS = [
    r'^\s*\d{1,4}[./-]\d{1,2}[./-]\d{2,4}\s+\d{1,2}:\d{2}(:\d{2})?\s*$'
]


def read_raw_content(file: Any) -> str:
    """
    Extracts raw string content from an uploaded file buffer across common encodings
    (UTF-8, UTF-8-SIG, Latin-1, CP1252, ISO-8859-1).
    """
    file.seek(0)
    raw_bytes = file.read()
    content = None
    for enc in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        content = raw_bytes.decode('utf-8', errors='ignore')
    return content


def sniff_delimiter_and_decimal(lines: List[str]) -> Tuple[str, str]:
    """
    Analyzes non-empty sample lines to robustly determine the delimiter (';', '\t', ',', '|', r'\s+')
    and the decimal separator (',' or '.').
    """
    if not lines:
        return ';', ','

    sample_lines = [line.strip() for line in lines[:30] if line.strip()]
    if not sample_lines:
        return ';', ','

    delims = [';', '\t', '|', ',']
    delim_counts = {d: [line.count(d) for line in sample_lines] for d in delims}

    # 1. If semicolon, tab, or pipe has consistent positive count across all sample lines, use it
    for d in [';', '\t', '|']:
        counts = delim_counts[d]
        if len(counts) > 0 and counts[0] > 0 and all(c == counts[0] for c in counts):
            has_comma = any(',' in line for line in sample_lines)
            decimal = ',' if (has_comma and d != ',') else '.'
            return d, decimal

    # 2. Check comma ','
    comma_counts = delim_counts[',']
    if len(comma_counts) > 0 and comma_counts[0] > 0 and all(c == comma_counts[0] for c in comma_counts):
        return ',', '.'

    # 3. Sum of occurrences fallback
    semicolon_sum = sum(delim_counts[';'])
    tab_sum = sum(delim_counts['\t'])
    comma_sum = sum(delim_counts[','])

    if semicolon_sum > comma_sum and semicolon_sum > 0:
        return ';', ','
    if tab_sum > comma_sum and tab_sum > 0:
        return '\t', ','

    return ',', '.'


def parse_csv_content(content: str, skiprows: int = 0) -> pd.DataFrame:
    """
    Robustly parses string CSV content into a pandas DataFrame, trying multiple delimiter
    and decimal strategies to prevent ParserError on European/international datasets.
    """
    lines = content.strip().splitlines()
    if skiprows > 0 and len(lines) > skiprows:
        lines = lines[skiprows:]
        trimmed_content = "\n".join(lines)
    else:
        trimmed_content = content

    best_sep, best_dec = sniff_delimiter_and_decimal(lines)
    candidates = [
        (best_sep, best_dec),
        (';', ','),
        ('\t', ','),
        (';', '.'),
        ('\t', '.'),
        (',', '.'),
        (',', ','),
        (r'\s+', ','),
        (r'\s+', '.'),
        (None, '.')
    ]

    seen = set()
    unique_candidates = []
    for sep, dec in candidates:
        pair = (sep, dec)
        if pair not in seen:
            seen.add(pair)
            unique_candidates.append(pair)

    last_error = None
    for sep, dec in unique_candidates:
        try:
            if sep is None:
                df = pd.read_csv(StringIO(trimmed_content), sep=None, engine='python')
            elif sep == r'\s+':
                df = pd.read_csv(StringIO(trimmed_content), sep=r'\s+', decimal=dec, engine='python')
            else:
                df = pd.read_csv(StringIO(trimmed_content), sep=sep, decimal=dec, engine='python')

            if df is not None and not df.empty and len(df.columns) >= 1:
                cols = list(df.columns)
                has_date_in_header = any(bool(re.search(r'\d{2}[./-]\d{2}[./-]\d{2,4}', str(c))) for c in cols)
                if has_date_in_header:
                    df = pd.read_csv(StringIO(trimmed_content), sep=sep, decimal=dec, header=None, engine='python')
                    df.columns = [f"Col_{i+1}" for i in range(len(df.columns))]
                return df
        except Exception as e:
            last_error = e
            continue

    try:
        return pd.read_csv(StringIO(trimmed_content), sep=best_sep, decimal=best_dec, on_bad_lines='skip', engine='python')
    except Exception:
        raise last_error if last_error else RuntimeError("Failed to parse CSV content.")


def detect_suggested_columns(df: pd.DataFrame) -> Tuple[List[str], List[str], str]:
    """
    Scans both DataFrame column names AND row sample values to intelligently detect:
      1. Suggested Timestamp column(s) (e.g. ['FECHA_REG', 'HORA_REG'] or ['Col_2', 'Col_3'])
      2. Suggested Power measurement columns (numeric meter IDs like 'POTENCIA_A_KW' or 'Col_4')
      3. Suggested Unit / Conversion ('kWh (15-min interval) → kW' or 'kW')
    """
    cols = list(df.columns)
    time_cols: List[str] = []
    power_cols: List[str] = []
    suggested_unit = "kW (Active Power - Direct)"

    # --- Step 1: Column Header Name Matching ---
    date_col = None
    for c in cols:
        c_clean = str(c).strip().lower()
        if any(syn == c_clean or syn in c_clean for syn in DATE_SYNONYMS):
            date_col = c
            time_cols.append(c)
            break

    for c in cols:
        if c == date_col:
            continue
        c_clean = str(c).strip().lower()
        if any(syn == c_clean or syn in c_clean for syn in TIME_SYNONYMS):
            time_cols.append(c)
            break

    # --- Step 2: Value-Based Matching if header names were generic (e.g. Col_1, Col_2) ---
    if not time_cols:
        detected_date_cols = []
        detected_time_cols = []
        detected_dt_cols = []

        for c in cols:
            samples = df[c].dropna().head(10).astype(str).str.strip().tolist()
            if not samples:
                continue
            
            # Check combined datetime pattern
            if all(any(re.match(p, s) for p in DATETIME_PATTERNS) for s in samples):
                detected_dt_cols.append(c)
            # Check separate date pattern
            elif all(any(re.match(p, s) for p in DATE_PATTERNS) for s in samples):
                detected_date_cols.append(c)
            # Check separate time pattern
            elif all(any(re.match(p, s) for p in TIME_PATTERNS) for s in samples):
                detected_time_cols.append(c)

        if detected_dt_cols:
            time_cols = [detected_dt_cols[0]]
        elif detected_date_cols and detected_time_cols:
            time_cols = [detected_date_cols[0], detected_time_cols[0]]
        elif detected_date_cols:
            time_cols = [detected_date_cols[0]]
        elif cols:
            # Fallback to first non-ID column or first column
            time_cols = [cols[0]]

    # --- Step 3: Unit Detection ---
    for c in cols:
        c_clean = str(c).strip().lower()
        if any(u in c_clean for u in UNIT_SYNONYMS):
            sample_val = str(df[c].dropna().iloc[0]).lower() if not df[c].dropna().empty else ""
            if "kwh" in sample_val:
                suggested_unit = "kWh (15-min interval) → kW"
            elif "w" == sample_val:
                suggested_unit = "W (Watt) → kW"

    for c in cols:
        c_clean = str(c).strip().lower()
        if "_kw" in c_clean or " kw" in c_clean:
            suggested_unit = "kW (Active Power - Direct)"
            break
        elif "_kwh" in c_clean or " kwh" in c_clean:
            suggested_unit = "kWh (15-min interval) → kW"

    # --- Step 4: Detect Numeric Power Measurement Columns ---
    for c in cols:
        if c in time_cols:
            continue
        c_clean = str(c).strip().lower()
        if any(u in c_clean for u in UNIT_SYNONYMS):
            continue
        # Check if column is numeric
        col_clean_str = df[c].astype(str).str.replace(' ', '').str.replace(',', '.')
        valid_numeric = pd.to_numeric(col_clean_str, errors='coerce').notnull().sum()
        if valid_numeric > (0.4 * len(df)):
            power_cols.append(c)

    return time_cols, power_cols, suggested_unit


def generate_sample_demo_csv(days: int = 7) -> Tuple[str, str]:
    """
    Synthesizes a multi-channel commercial load profile CSV with explicit meter names
    (HVAC, Production, EV Charging, Lighting) measured directly in kW.
    Returns (filename, csv_text_content).
    """
    periods = 96 * days
    dates = pd.date_range(start="2025-01-01 00:00", periods=periods, freq="15min")
    hours = dates.hour
    workdays = dates.dayofweek < 5

    # 1. HVAC & Ventilation (kW): Active during workday hours (06:00 to 20:00)
    hvac_kw = np.where(workdays & (hours >= 6) & (hours <= 20), 25.0, 5.0)
    hvac_kw = np.round(np.clip(hvac_kw + np.random.normal(0, 1.5, len(hvac_kw)), 2.0, None), 1)

    # 2. Main Production Line (kW): High daytime operational load (07:30 to 17:00)
    prod_kw = np.where(workdays & (hours >= 7) & (hours <= 17), 45.0, 0.0)
    prod_kw = np.round(np.clip(prod_kw + np.random.normal(0, 3.0, len(prod_kw)), 0.0, None), 1)

    # 3. EV Charging Hub (kW): Morning and late afternoon charging peaks
    ev_peak = (hours >= 8) & (hours <= 10) | (hours >= 16) & (hours <= 18)
    ev_kw = np.where(workdays & ev_peak, 35.0, 0.0)
    ev_kw = np.round(np.clip(ev_kw + np.random.normal(0, 2.5, len(ev_kw)), 0.0, None), 1)

    # 4. Lighting & Standby Baseload (kW): Continuous baseload
    light_kw = np.where((hours >= 6) & (hours <= 22), 12.0, 4.0)
    light_kw = np.round(np.clip(light_kw + np.random.normal(0, 0.5, len(light_kw)), 2.0, None), 1)

    demo_df = pd.DataFrame({
        "Date": dates.strftime("%d.%m.%Y"),
        "Time": dates.strftime("%H:%M"),
        "Meter_HVAC_kW": hvac_kw,
        "Meter_Production_kW": prod_kw,
        "Meter_EV_Chargers_kW": ev_kw,
        "Meter_Lighting_Baseload_kW": light_kw
    })

    buf = StringIO()
    demo_df.to_csv(buf, index=False, sep=";")
    return "Sample_Commercial_MultiMeter_kW.csv", buf.getvalue()
