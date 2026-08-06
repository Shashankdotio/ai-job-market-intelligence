"""Reusable Plotly charts for ranked market-intelligence metrics."""

import pandas as pd
import plotly.graph_objects as go


BRAND_BLUE = "#2563EB"
BRAND_VIOLET = "#7C3AED"
BRAND_TEAL = "#0F766E"
BRAND_AMBER = "#D97706"
GRID_COLOR = "#E5E7EB"


def ranked_bar_chart(
    data: pd.DataFrame,
    *,
    label_column: str,
    value_column: str,
    title: str,
    color: str = BRAND_BLUE,
    limit: int = 10,
) -> go.Figure:
    """Return a clean, interactive horizontal bar chart for ranked datasets."""
    chart_data = data[[label_column, value_column]].nlargest(limit, value_column)
    chart_data = chart_data.sort_values(value_column, ascending=True)
    figure = go.Figure(
        go.Bar(
            x=chart_data[value_column],
            y=chart_data[label_column],
            orientation="h",
            marker_color=color,
            hovertemplate=(
                f"%{{y}}<br>{value_column.replace('_', ' ').title()}: "
                "%{x:,}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        title=title,
        height=max(320, len(chart_data) * 34),
        margin={"l": 8, "r": 8, "t": 52, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"showgrid": True, "gridcolor": GRID_COLOR, "zeroline": False},
        yaxis={"showgrid": False},
        showlegend=False,
    )
    return figure


def donut_chart(
    data: pd.DataFrame,
    *,
    label_column: str,
    value_column: str,
    title: str,
) -> go.Figure:
    """Return an interactive donut chart for categorical job distributions."""
    figure = go.Figure(
        go.Pie(
            labels=data[label_column],
            values=data[value_column],
            hole=0.62,
            textinfo="label+percent",
            hovertemplate="%{label}<br>Jobs: %{value:,}<extra></extra>",
        )
    )
    figure.update_layout(
        title=title,
        height=360,
        margin={"l": 8, "r": 8, "t": 52, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return figure
