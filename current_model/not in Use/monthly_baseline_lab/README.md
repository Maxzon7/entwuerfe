# :material/calendar_month: 12-Month Baseline & Commercial Tariff Laboratory (`monthly_baseline_lab`)

An isolated, modular laboratory for evaluating 12-month commercial and industrial electricity supply contracts and regulated DSO tariffs against annual monthly consumption metrics.

---

## :material/folder_open: Structure

- [`standalone_monthly_baseline_lab.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/monthly_baseline_lab/standalone_monthly_baseline_lab.py): Streamlit coordinator & UI page.
- [`monthly_calc.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/monthly_baseline_lab/monthly_calc.py): Pure mathematical calculation engine and dataclass models.
- [`monthly_presets.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/monthly_baseline_lab/monthly_presets.py): Standard contract presets (Bodegas Salentein Pozo 600, Argentina 3-Tier, Netherlands) and Dutch DSO catalogs (Enexis & Liander 2025).
- [`monthly_header_view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/monthly_baseline_lab/monthly_header_view.py): Preset loader toolbar, FX converter & currency switcher.
- [`monthly_editors.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/monthly_baseline_lab/monthly_editors.py): Dual interactive data editors (Table A Consumption, Table B Tariffs).
- [`monthly_charts.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/monthly_baseline_lab/monthly_charts.py): Plotly interactive stacked billing & energy volume charts.
- [`monthly_audit.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/monthly_baseline_lab/monthly_audit.py): Numerical and mathematical verification panel.
- [`monthly_financial_view.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/monthly_baseline_lab/monthly_financial_view.py): 4 Financial KPI cards & CSV/JSON export toolbar.
- [`monthly_tou_manager.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/monthly_baseline_lab/monthly_tou_manager.py): Dynamic Time-of-Use window configuration.
- [`monthly_dso_generator.py`](file:///c:/Users/mwien/Documents/One%20drive2/OneDrive/Desktop/Arbeit%20prog/Web%20Development/entwuerfe/current_model/ui_sandbox/monthly_baseline_lab/monthly_dso_generator.py): Dutch Grid Operator Tariff Generator (Enexis & Liander 2025).

---

## :material/play_arrow: Running Directly

```bash
python -m streamlit run current_model/ui_sandbox/monthly_baseline_lab/standalone_monthly_baseline_lab.py
```
