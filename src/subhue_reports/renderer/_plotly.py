"""Helpers Plotly: extração do JS bundle e merge de defaults de estilo."""

import json
from pathlib import Path

from subhue_reports.renderer._html import deep_merge

PLOTLY_PALETTE = [
    "#3b82f6", "#16a34a", "#9333ea",
    "#f97316", "#0891b2", "#dc2626", "#ca8a04",
]

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


def prepare_figure_json(fig_json: dict) -> str:
    """Aplica defaults de estilo SUBHUE e valida o Figure JSON do Plotly."""
    import plotly.io as pio

    layout_merged = deep_merge(PLOTLY_LAYOUT_DEFAULTS, fig_json.get("layout", {}))
    merged = {**fig_json, "layout": layout_merged}
    fig = pio.from_json(json.dumps(merged))
    return fig.to_json()
