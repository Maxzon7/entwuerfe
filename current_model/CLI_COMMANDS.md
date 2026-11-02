# Streamlit CLI Cheat Sheet & Run Commands

This file contains all commands to run the main application and every standalone sandbox directly from the project root (`current_model/`).

---

## 1. Prerequisites & Environment Activation

Ensure your virtual environment is activated and dependencies are installed before running any command:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows Command Prompt (cmd)
.\.venv\Scripts\activate.bat
```

---

## 2. Main Application

Runs the complete multi-tab integrated energy modeling platform:

```bash
python -m streamlit run app.py
```
*(Alternative syntax: `streamlit run app.py`)*

---

## 3. Standalone UI Sandboxes (`ui_sandbox/`)

Each sandbox runs independently in its own isolated Streamlit session, bypassing the rest of the application.

### A. Current Situation Sandbox (Scenario 1)
Evaluates facility consumption profiles and DSO electricity contracts:
```bash
python -m streamlit run ui_sandbox/Currentsituation_sandbox/app.py
```

### B. New Contract Sandbox (Scenario 2)
Analyzes new tariff contracts, capacity limit adjustments, and DSO fee comparisons:
```bash
python -m streamlit run ui_sandbox/NewContract_sandbox/app.py
```

### C. Solar PV Sandbox (Scenario 3)
Standalone sizing, PVGIS weather data, physical generation, and facility load coupling:
```bash
python -m streamlit run ui_sandbox/Solar_sandbox/app.py
```

### D. Generator & Grid Congestion Sandbox (Scenario 6)
Peaking generator sizing, Willans fuel curve, overload hours mitigation, and capacity sweep:
```bash
python -m streamlit run ui_sandbox/Generator_sandbox/app.py
```

### E. Battery Energy Storage (BESS) Sandbox
Arbitrage, peak shaving, and battery storage simulation:
```bash
python -m streamlit run ui_sandbox/BESS_sandbox/app.py
```

### F. Combined Solar + BESS Sandbox
Coupled PV generation and battery storage dispatch:
```bash
python -m streamlit run ui_sandbox/SolarBESS_sandbox/app.py
```

---

## 4. Test Suite Execution

Run unit and integration tests across all modules and sandboxes:

```bash
# Run all tests
pytest

# Run tests with detailed console output
pytest -v

# Run UI Sandbox AST validation tests
pytest tests/test_ui_sandbox.py -v
```

---

## 5. Helpful Streamlit CLI Flags

```bash
# Specify a custom port (e.g., 8502 if 8501 is occupied)
python -m streamlit run app.py --server.port 8502

# Run without automatically opening a browser tab
python -m streamlit run app.py --server.headless true

# Set max upload size (e.g., 200 MB for large CSV files)
python -m streamlit run app.py --server.maxUploadSize 200
```

