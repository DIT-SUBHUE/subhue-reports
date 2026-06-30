"""Helpers Plotly: extração do JS bundle e merge de defaults de estilo."""

import json
from pathlib import Path

from subhue_reports.renderer._html import deep_merge

PLOTLY_PALETTE = [
    "#3b82f6", "#16a34a", "#9333ea",
    "#f97316", "#0891b2", "#dc2626", "#ca8a04",
]

BAR_SPLIT_THRESHOLD = 10

PLOTLY_LAYOUT_DEFAULTS: dict = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "system-ui, -apple-system, sans-serif", "size": 11, "color": "#334155"},
    "margin": {"l": 40, "r": 16, "t": 36, "b": 36},
    "height": 260,
    "showlegend": True,
    "legend": {"orientation": "h", "y": -0.2, "font": {"size": 10}},
    "xaxis": {"gridcolor": "#f1f5f9", "linecolor": "#e2e8f0", "tickfont": {"size": 10}},
    "yaxis": {
        "gridcolor": "#f1f5f9", "linecolor": "#e2e8f0",
        "tickfont": {"size": 10}, "zeroline": False,
    },
    "title": {"font": {"size": 13, "color": "#1e293b"}, "x": 0, "xanchor": "left", "pad": {"l": 0}},
    "hoverlabel": {"bgcolor": "#1e293b", "font": {"color": "#fff", "size": 11}},
    "colorway": PLOTLY_PALETTE,
}


def get_plotly_js() -> str:
    """Retorna plotly.min.js bundled com o pacote plotly instalado."""
    import plotly

    js_path = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    if not js_path.exists():
        raise FileNotFoundError(
            f"plotly.min.js não encontrado em {js_path}. "
            "Recebido: arquivo ausente. Esperado: instalação padrão do pacote plotly."
        )
    return js_path.read_text(encoding="utf-8")


def bar_x_categories(traces: list[dict]) -> list:
    """Retorna categorias X do primeiro trace bar vertical. Ignora bar_h (orientation='h')."""
    for trace in traces:
        if trace.get("type") == "bar" and trace.get("orientation") != "h" and trace.get("x"):
            return list(trace["x"])
    return []


def split_bar_traces(
    traces: list[dict], categories: list, mid: int
) -> tuple[list[dict], list[dict]]:
    """
    Divide traces bar pelo índice mid nas categorias X.
    Traces não-bar são copiados para ambas as metades.
    """
    first_set = set(str(c) for c in categories[:mid])
    first_traces, second_traces = [], []
    for trace in traces:
        if trace.get("type") != "bar":
            first_traces.append(trace)
            second_traces.append(trace)
            continue
        x = trace.get("x", [])
        y = trace.get("y", [])
        pairs = list(zip(x, y, strict=False))
        p1 = [(xi, yi) for xi, yi in pairs if str(xi) in first_set]
        p2 = [(xi, yi) for xi, yi in pairs if str(xi) not in first_set]
        if p1:
            first_traces.append({**trace, "x": [p[0] for p in p1], "y": [p[1] for p in p1]})
        if p2:
            second_traces.append({**trace, "x": [p[0] for p in p2], "y": [p[1] for p in p2]})
    return first_traces, second_traces


def _add_bar_text_labels(fig_json: dict) -> dict:
    """Injeta rótulos de dados em traces bar que não os definem explicitamente."""
    barmode = fig_json.get("layout", {}).get("barmode", "group")
    textposition = "inside" if barmode == "stack" else "outside"
    new_data = []
    for trace in fig_json.get("data", []):
        if (
            trace.get("type") == "bar"
            and "texttemplate" not in trace
            and "text" not in trace
        ):
            orientation = trace.get("orientation", "v")
            template = "%{x}" if orientation == "h" else "%{y}"
            trace = {**trace, "texttemplate": template, "textposition": textposition}
        new_data.append(trace)
    return {**fig_json, "data": new_data}


def prepare_figure_json(fig_json: dict) -> str:
    """Aplica defaults de estilo SUBHUE e valida o Figure JSON do Plotly."""
    import plotly.io as pio

    fig_with_labels = _add_bar_text_labels(fig_json)
    layout_merged = deep_merge(PLOTLY_LAYOUT_DEFAULTS, fig_with_labels.get("layout", {}))
    merged = {**fig_with_labels, "layout": layout_merged}
    fig = pio.from_json(json.dumps(merged))
    return fig.to_json()
