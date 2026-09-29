# :material/science: UI Sandbox & Prototyping Laboratory (`ui_sandbox`)

An isolated, dedicated testing environment for developing, styling, and verifying Streamlit UI components, Plotly visualizations, custom widgets, and layouts **without having to run `app.py`**.

---

## :material/verified_user: Architectural Rules & Dependency Boundary

> [!IMPORTANT]
> **Strict One-Way Dependency Isolation:**
> 1. **Allowed (`ui_sandbox` $\rightarrow$ Project):** Code inside `ui_sandbox/` is permitted to import modules from `core/`, `models/`, and `ui/` to test live functionality against domain engines.
> 2. **Prohibited (Main Project $\rightarrow$ `ui_sandbox`):** The main application (`app.py`), core calculation engines, domain models, or production UI tabs must **NEVER** import or reference anything located in `ui_sandbox/`.
> 3. **Design Standards:** All UI prototypes must strictly adhere to the project's iconography standard (**Streamlit native Google Material Symbols `:material/<icon_name>:`**, zero cartoon emojis) and English UI text.

---

## :material/folder_open: Directory Structure

```text
current_model/ui_sandbox/
├── __init__.py          # Module package initializer
├── sandbox_app.py       # Standalone Streamlit test runner & showcase
└── README.md            # Sandbox architecture & usage guide
```

---

## :material/play_arrow: Quick Start & Execution

You can run the UI Sandbox directly with Streamlit:

### From the `current_model` directory:
```bash
python -m streamlit run ui_sandbox/sandbox_app.py
```

### From the repository workspace root:
```bash
python -m streamlit run current_model/ui_sandbox/sandbox_app.py
```

---

## :material/featured_play_list: Included Playground Views

* **`:material/upload_file: CSV Consumption Input`**: Complete production CSV real-meter ingestion pipeline, multi-channel upload, 15-min demo data generator, interactive Plotly timeseries charts, and session state diagnostics.
* **`:material/waving_hand: Hello World & Overview`**: Quick status verification and architectural guidelines.
* **`:material/dashboard: Component Showcase`**: Test shared KPI cards (`render_kpi_card`) and interactive control inputs.
* **`:material/query_stats: Interactive Chart Lab`**: Fast Plotly theme, layout, and multi-series dispatch tuning.
* **`:material/edit_note: Scratchpad Playground`**: Blank sandbox for testing new ad-hoc Streamlit widgets or JSON structures.
