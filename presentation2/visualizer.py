"""
Visualization Module (Plotly Dark Theme)
========================================
Builds high-contrast, interactive load profile time series figures with sub-meters,
total demand curve, peak annotations, and range sliders.
"""

from typing import List, Optional
import pandas as pd
import plotly.graph_objects as go


def create_dark_load_profile_figure(
    df_clean: pd.DataFrame,
    file_name: str,
    selected_power_cols: List[str],
    total_col: str = "Total_Demand_kW",
    peak_kw: Optional[float] = None,
    grid_limit_kw: Optional[float] = None,
    target_cap_kw: Optional[float] = None
) -> go.Figure:
    """
    Constructs an interactive dark-theme Plotly line chart with optional grid limit & target cap lines.
    """
    fig = go.Figure()

    if df_clean.empty or total_col not in df_clean.columns:
        fig.update_layout(
            template="plotly_dark",
            title="No data available to display",
            plot_bgcolor="#0B0F19",
            paper_bgcolor="#0B0F19"
        )
        return fig

    palette = ["#38BDF8", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6"]

    # 1. Plot individual sub-meter measurement lines (if multiple selected)
    if len(selected_power_cols) > 1:
        for idx, col_name in enumerate(selected_power_cols):
            if col_name in df_clean.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df_clean["timestamp"],
                        y=df_clean[col_name],
                        mode="lines",
                        name=col_name,
                        line=dict(width=1.0, color=palette[idx % len(palette)]),
                        hovertemplate=f"<b>{col_name}</b>: %{{y:.2f}} kW<extra></extra>"
                    )
                )

    # 2. Main Total Demand Trace (Solid White Line)
    fig.add_trace(
        go.Scatter(
            x=df_clean["timestamp"],
            y=df_clean[total_col],
            mode="lines",
            name="Total Grid Demand (kW)",
            line=dict(color="#FFFFFF", width=2.0),
            fill="tozeroy" if len(selected_power_cols) == 1 else "none",
            fillcolor="rgba(56, 189, 248, 0.15)",
            hovertemplate="<b>Total Power</b>: %{y:.2f} kW<br>Time: %{x}<extra></extra>"
        )
    )

    # 3. Grid Limit & Shaving Target Lines
    if grid_limit_kw and grid_limit_kw > 0:
        fig.add_hline(
            y=grid_limit_kw,
            line_dash="dash",
            line_color="#f43f5e",
            line_width=2,
            annotation_text=f"Max Grid Limit ({grid_limit_kw:.1f} kW)",
            annotation_position="top right"
        )

    if target_cap_kw and target_cap_kw > 0 and (grid_limit_kw is None or target_cap_kw < grid_limit_kw):
        fig.add_hline(
            y=target_cap_kw,
            line_dash="dot",
            line_color="#38bdf8",
            line_width=1.5,
            annotation_text=f"Target Shaving Cap ({target_cap_kw:.1f} kW)",
            annotation_position="bottom right"
        )

    # 4. Peak Annotation Marker
    if peak_kw is None:
        peak_kw = float(df_clean[total_col].max())

    peak_idx = df_clean[total_col].idxmax()
    peak_time = df_clean.loc[peak_idx, "timestamp"]

    fig.add_annotation(
        x=peak_time,
        y=peak_kw,
        text=f"Peak: {peak_kw:.1f} kW",
        showarrow=True,
        arrowhead=2,
        arrowcolor="#EF4444",
        font=dict(color="#F87171", size=11, family="Arial Black"),
        bgcolor="rgba(15, 23, 42, 0.9)",
        bordercolor="#EF4444",
        borderwidth=1.5,
        borderpad=4
    )

    # 5. Dark Theme Layout
    fig.update_layout(
        template="plotly_dark",
        title=dict(text=f"<b>Load Profile: {file_name}</b>", font=dict(size=16, color="#F8FAFC")),
        xaxis=dict(
            title="Timestamp",
            gridcolor="#1E293B",
            rangeslider=dict(visible=True, thickness=0.06),
            type="date"
        ),
        yaxis=dict(
            title="Active Electrical Power (kW)",
            rangemode="tozero",
            gridcolor="#1E293B"
        ),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=470
    )

    return fig

