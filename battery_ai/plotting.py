"""Plotly figures with a consistent research-dashboard visual language."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


TEAL = "#0F766E"
NAVY = "#174A5C"
AMBER = "#D97706"
RED = "#C2413B"
GRID = "#DDE9E6"


def _style_figure(figure: go.Figure, *, height: int = 460) -> go.Figure:
    figure.update_layout(
        height=height,
        margin=dict(l=18, r=18, t=35, b=18),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Inter, Source Sans Pro, sans-serif", color="#17332F"),
        hoverlabel=dict(bgcolor="#17332F", font_color="white"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    figure.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    figure.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    return figure


def cycle_performance_figure(summary: pd.DataFrame) -> go.Figure:
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Scatter(
            x=summary["cycle"],
            y=summary["charge_capacity_mah"],
            name="充电容量",
            mode="lines+markers",
            line=dict(color=TEAL, width=2.5),
            marker=dict(size=5),
            hovertemplate="循环 %{x}<br>充电容量 %{y:.3f} mAh<extra></extra>",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=summary["cycle"],
            y=summary["discharge_capacity_mah"],
            name="放电容量",
            mode="lines+markers",
            line=dict(color=NAVY, width=2.5),
            marker=dict(size=5),
            hovertemplate="循环 %{x}<br>放电容量 %{y:.3f} mAh<extra></extra>",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=summary["cycle"],
            y=summary["coulombic_efficiency_pct"],
            name="库伦效率",
            mode="lines",
            line=dict(color=AMBER, width=1.8, dash="dot"),
            hovertemplate="循环 %{x}<br>库伦效率 %{y:.2f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    figure.update_xaxes(title_text="循环序号")
    figure.update_yaxes(title_text="容量 (mAh)", secondary_y=False)
    figure.update_yaxes(title_text="库伦效率 (%)", secondary_y=True)
    return _style_figure(figure)


def voltage_capacity_figure(data: pd.DataFrame, cycles: Iterable[int]) -> go.Figure:
    figure = go.Figure()
    palette = ["#0F766E", "#2563EB", "#7C3AED", "#D97706", "#C2413B", "#334155"]
    dash_by_state = {"charge": "solid", "discharge": "dot"}
    label_by_state = {"charge": "充电", "discharge": "放电"}
    for color_index, cycle in enumerate(cycles):
        cycle_data = data[data["cycle"].eq(int(cycle))]
        for state in ("charge", "discharge"):
            subset = cycle_data[cycle_data["state"].eq(state)].sort_values("time_s")
            if subset.empty:
                continue
            figure.add_trace(
                go.Scatter(
                    x=subset["capacity_mah"],
                    y=subset["voltage_v"],
                    name=f"第 {cycle} 圈 · {label_by_state[state]}",
                    mode="lines",
                    line=dict(
                        color=palette[color_index % len(palette)],
                        width=2.2,
                        dash=dash_by_state[state],
                    ),
                    hovertemplate=(
                        f"第 {cycle} 圈 · {label_by_state[state]}"
                        "<br>容量 %{x:.3f} mAh<br>电压 %{y:.4f} V<extra></extra>"
                    ),
                )
            )
    figure.update_xaxes(title_text="容量 (mAh)")
    figure.update_yaxes(title_text="电压 (V)")
    return _style_figure(figure, height=520)


def anomaly_score_figure(result: pd.DataFrame) -> go.Figure:
    ordered = result.sort_values("cycle")
    colors = [RED if flag else TEAL for flag in ordered["is_anomaly"]]
    figure = go.Figure(
        go.Bar(
            x=ordered["cycle"],
            y=ordered["anomaly_score"],
            marker_color=colors,
            customdata=ordered[["reason"]],
            hovertemplate="循环 %{x}<br>判定分数 %{y:.4f}<br>%{customdata[0]}<extra></extra>",
        )
    )
    figure.add_hline(
        y=0,
        line_dash="dash",
        line_color="#475569",
        annotation_text="Isolation Forest 判定边界",
        annotation_position="top right",
    )
    figure.update_xaxes(title_text="循环序号")
    figure.update_yaxes(title_text="判定分数（低于 0 标记为异常）")
    return _style_figure(figure, height=400)

