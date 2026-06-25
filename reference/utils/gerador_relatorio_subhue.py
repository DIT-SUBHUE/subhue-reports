#!/usr/bin/env python3
"""
gerador_relatorio_subhue.py
───────────────────────────
Gera relatórios HTML self-contained a partir de um JSON estruturado.
Plotly.js é embutido diretamente no HTML — sem CDN, sem kaleido.

Uso:
    python gerador_relatorio_subhue.py dados.json
    python gerador_relatorio_subhue.py dados.json -o data/reports/relatorio.html
    python gerador_relatorio_subhue.py --exemplo      # gera schema_exemplo.json

Tipos de seção disponíveis:
    contexto        callout de objetivo + parágrafo descritivo
    tabela          tabela genérica com colunas tipadas
    grafico         qualquer Figure JSON do Plotly
    metrica         grid de números em destaque (stat boxes)
    texto           bloco narrativo / metodologia / notas
    achados         lista com ícone + afirmações verificáveis
    excecao         two-col: explicação + tabela + stat boxes
    recomendacao    spec técnica em formato de campos
"""

import argparse
import html as html_module
import json
import sys
from pathlib import Path

from report_metadata import ensure_generation_timestamp, get_generation_timestamp


# ─── PLOTLY JS ────────────────────────────────────────────────────────────────

def _get_plotly_js() -> str:
    """Retorna o conteúdo do plotly.min.js bundled com o pacote plotly."""
    import plotly
    js_path = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    if not js_path.exists():
        raise FileNotFoundError(
            f"plotly.min.js não encontrado em {js_path}. "
            "Verifique a instalação do plotly."
        )
    return js_path.read_text(encoding="utf-8")


def _get_diid_logo_svg() -> str:
    """Retorna o SVG da marca DIID para embutir no HTML final."""
    svg_path = Path(__file__).with_name("diid_vertical_fix.svg")
    if not svg_path.exists():
        raise FileNotFoundError(f"Logo DIID não encontrada em {svg_path}.")
    return svg_path.read_text(encoding="utf-8")


# ─── PALETA & TOKENS ──────────────────────────────────────────────────────────

# Cores para aplicar nos Figure JSON quando o LLM não especificar
PLOTLY_PALETTE = ["#3b82f6", "#16a34a", "#9333ea", "#f97316", "#0891b2", "#dc2626", "#ca8a04"]

PLOTLY_LAYOUT_DEFAULTS = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor":  "rgba(0,0,0,0)",
    "font":          {"family": "system-ui, -apple-system, sans-serif", "size": 11, "color": "#334155"},
    "margin":        {"l": 40, "r": 16, "t": 36, "b": 36},
    "height":        260,
    "showlegend":    True,
    "legend":        {"orientation": "h", "y": -0.2, "font": {"size": 10}},
    "xaxis":         {"gridcolor": "#f1f5f9", "linecolor": "#e2e8f0", "tickfont": {"size": 10}},
    "yaxis":         {"gridcolor": "#f1f5f9", "linecolor": "#e2e8f0", "tickfont": {"size": 10}, "zeroline": False},
    "title":         {"font": {"size": 13, "color": "#1e293b"}, "x": 0, "xanchor": "left", "pad": {"l": 0}},
    "hoverlabel":    {"bgcolor": "#1e293b", "font": {"color": "#fff", "size": 11}},
    "colorway":      PLOTLY_PALETTE,
}

PILL = {
    "hospital": "pill-h",
    "upa":      "pill-u",
    "cer":      "pill-c",
    "outro":    "pill-o",
}

ICO_MAP = {
    "ok":    "✅",
    "warn":  "⚠️",
    "info":  "📊",
    "time":  "🕐",
    "error": "❌",
}

# Tipos de coluna para tabelas genéricas
# texto | numero | badge_pct | badge_label | codigo | pill | link
COL_TYPES = {"texto", "numero", "badge_pct", "badge_label", "codigo", "pill"}


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def esc(text) -> str:
    return html_module.escape(str(text)) if text is not None else ""


def fmt_num(value) -> str:
    try:
        n = int(value)
        return f"{n:,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(value)


def badge_class(pct: float | None) -> str:
    if pct is None:
        return "badge na"
    if pct >= 90:
        return "badge hi"
    if pct >= 70:
        return "badge md"
    return "badge lo"


def render_badge_pct(pct: float | None, label: str | None = None) -> str:
    if pct is None:
        return '<span class="badge na">—</span>'
    display = label or f"{pct:.0f}%"
    cls = badge_class(pct)
    return f'<span class="{cls}">{esc(display)}</span>'


def render_badge_label(label: str, nivel: str = "na") -> str:
    cls = f"badge {nivel}" if nivel in ("hi","md","lo","na","ex") else "badge na"
    return f'<span class="{cls}">{esc(label)}</span>'


def render_pill(tipo: str, label: str) -> str:
    cls = PILL.get(tipo.lower(), "pill-o")
    return f'<span class="pill {cls}">{esc(label)}</span>'


def render_code(text: str) -> str:
    return f"<code>{esc(text)}</code>"


def render_cell(value, col_tipo: str) -> str:
    """Renderiza uma célula de tabela genérica de acordo com o tipo da coluna."""
    if value is None:
        return '<td><span style="color:var(--ink-5)">—</span></td>'

    if col_tipo == "numero":
        return f'<td class="n">{esc(fmt_num(value))}</td>'

    if col_tipo == "badge_pct":
        # value pode ser float (83.5) ou dict {"pct": 83, "label": "83%"}
        if isinstance(value, dict):
            return f'<td class="n">{render_badge_pct(value.get("pct"), value.get("label"))}</td>'
        return f'<td class="n">{render_badge_pct(float(value))}</td>'

    if col_tipo == "badge_label":
        # value pode ser str ou dict {"label": "...", "nivel": "hi"}
        if isinstance(value, dict):
            return f'<td>{render_badge_label(value.get("label",""), value.get("nivel","na"))}</td>'
        return f'<td>{render_badge_label(str(value))}</td>'

    if col_tipo == "codigo":
        return f'<td>{render_code(str(value))}</td>'

    if col_tipo == "pill":
        # value: {"tipo": "hospital", "label": "HMSF"}
        if isinstance(value, dict):
            return f'<td>{render_pill(value.get("tipo","outro"), value.get("label",""))}</td>'
        return f'<td>{esc(str(value))}</td>'

    # texto (default)
    return f'<td>{esc(str(value))}</td>'


# ─── PLOTLY: MERGE DE DEFAULTS ───────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """Merge recursivo: override tem precedência, base preenche o que falta."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def prepare_figure_json(fig_json: dict) -> str:
    """
    Recebe um Plotly Figure JSON do LLM, aplica defaults de estilo SUBHUE,
    e retorna a string JSON pronta para Plotly.newPlot().
    """
    import plotly.io as pio

    # Merge do layout: defaults primeiro, override do LLM por cima
    layout_merged = _deep_merge(PLOTLY_LAYOUT_DEFAULTS, fig_json.get("layout", {}))
    fig_json_merged = dict(fig_json)
    fig_json_merged["layout"] = layout_merged

    # Validar via plotly (normaliza tipos, preenche defaults internos)
    fig = pio.from_json(json.dumps(fig_json_merged))
    return fig.to_json()


# ─── CSS ─────────────────────────────────────────────────────────────────────

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 13px;
  line-height: 1.55;
  color: #1e293b;
  background: #f0ede8;
  -webkit-font-smoothing: antialiased;
}

:root {
  --navy:        #1a3a5c;
  --navy-mid:    #2b5484;
  --ink:         #1e293b;
  --ink-2:       #334155;
  --ink-3:       #475569;
  --ink-4:       #64748b;
  --ink-5:       #94a3b8;
  --surface:     #ffffff;
  --surface-2:   #f8f7f4;
  --border:      #ddd9d2;
  --border-light:#eeebe6;
  --green:       #15803d;
  --green-bg:    #dcfce7;
  --red:         #dc2626;
  --red-bg:      #fee2e2;
  --yellow:      #a16207;
  --yellow-bg:   #fef9c3;
  --purple:      #6d28d9;
  --purple-bg:   #ede9fe;
  --blue:        #1d4ed8;
  --blue-bg:     #dbeafe;
}

/* ─── LAYOUT ─────────────────────────────────────────── */
.page { max-width: 1200px; margin: 0 auto; padding: 28px 24px 48px; }

/* ─── HEADER ─────────────────────────────────────────── */
.header {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 20px;
  background: var(--surface);
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.header-rail {
  background: var(--surface);
  padding: 18px 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 150px;
  flex-shrink: 0;
}
.header-rail-logo {
  width: 88px;
  max-width: 100%;
}
.header-rail-logo svg {
  display: block;
  width: 100%;
  height: auto;
}
.header-main {
  background: var(--navy);
  padding: 22px 24px; flex: 1;
  display: flex; flex-direction: column; justify-content: space-between;
}
.header-label {
  font-size: 9px; font-weight: 700; letter-spacing: .14em;
  text-transform: uppercase; color: rgba(255,255,255,.72); margin-bottom: 6px;
}
.header-title {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 20px; font-weight: normal;
  color: #fff; line-height: 1.3; margin-bottom: 4px;
}
.header-subtitle { font-size: 12px; color: rgba(255,255,255,.82); margin-bottom: 16px; }
.header-meta {
  display: flex; gap: 20px; flex-wrap: wrap;
  padding-top: 14px; border-top: 1px solid rgba(255,255,255,.18);
}
.header-meta-item { font-size: 11px; color: rgba(255,255,255,.78); }
.header-meta-item strong { color: #fff; font-weight: 600; }
.header-meta-item code { background: rgba(255,255,255,.12); color: #fff; }

/* ─── SCOPE NOTICE ───────────────────────────────────── */
.scope-notice {
  background: #fffbeb;
  border: 1px solid #fcd34d;
  border-left: 4px solid #b45309;
  border-radius: 3px;
  padding: 10px 14px;
  margin-bottom: 20px;
  font-size: 11px;
  color: #b45309;
  line-height: 1.5;
}
.scope-notice strong { font-weight: 700; }

/* ─── CARD ───────────────────────────────────────────── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 18px 20px;
  margin-bottom: 14px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04);
  min-width: 0;
}
.card-title {
  font-size: 10px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: var(--ink-4);
  padding-bottom: 12px; margin-bottom: 14px;
  border-bottom: 1px solid var(--border-light);
}
.card-title span {
  color: var(--ink-5); font-weight: 400;
  letter-spacing: 0; text-transform: none; font-size: 10px;
}

/* ─── CALLOUT ────────────────────────────────────────── */
.callout {
  background: #eef4fd;
  border-left: 3px solid var(--navy-mid);
  padding: 10px 14px;
  border-radius: 0 3px 3px 0;
  font-size: 12px; color: #1e3a5a;
  margin-bottom: 12px;
}
.callout strong { font-weight: 700; }

/* ─── TABELA ─────────────────────────────────────────── */
.table-scroll {
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
table { width: 100%; border-collapse: collapse; font-size: 12px; }
.table-scroll table { min-width: max-content; }
thead tr { background: var(--surface-2); }
th {
  font-size: 10px; font-weight: 700; letter-spacing: .07em;
  text-transform: uppercase; color: var(--ink-4);
  padding: 8px 10px; text-align: left;
  border-bottom: 1px solid var(--border); white-space: nowrap;
}
th.n, td.n { text-align: right; font-variant-numeric: tabular-nums; }
td {
  padding: 7px 10px; color: var(--ink-2);
  border-bottom: 1px solid var(--border-light);
  vertical-align: middle;
}
tbody tr:last-child td { border-bottom: none; }
tbody tr:nth-child(even) { background: #fafaf8; }

/* ─── BADGES ─────────────────────────────────────────── */
.badge {
  display: inline-block; font-size: 10px; font-weight: 700;
  padding: 2px 7px; border-radius: 3px; letter-spacing: .03em;
}
.hi { background: var(--green-bg);  color: var(--green);  }
.md { background: var(--yellow-bg); color: var(--yellow); }
.lo { background: var(--red-bg);    color: var(--red);    }
.na { background: var(--surface-2); color: var(--ink-4);  }
.ex { background: var(--purple-bg); color: var(--purple); }

/* ─── PILLS ──────────────────────────────────────────── */
.pill {
  display: inline-block; font-size: 10px; font-weight: 700;
  padding: 2px 8px; border-radius: 10px;
  letter-spacing: .02em; white-space: nowrap;
}
.pill-h { background: var(--blue-bg);   color: var(--blue);   }
.pill-u { background: var(--green-bg);  color: var(--green);  }
.pill-c { background: var(--purple-bg); color: var(--purple); }
.pill-o { background: #ffedd5;          color: #c2410c;        }

/* ─── CÓDIGO ─────────────────────────────────────────── */
code {
  background: #e8e4f8; color: #3730a3;
  font-family: 'JetBrains Mono', 'Courier New', monospace;
  font-size: 10.5px; padding: 1px 5px; border-radius: 3px;
}

/* ─── MÉTRICAS ───────────────────────────────────────── */
.metrics-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}
.stat-box {
  text-align: center; padding: 16px 12px;
  border: 1px solid var(--border-light);
  border-radius: 4px; background: var(--surface-2);
}
.stat-num {
  font-size: 28px; font-weight: 700; line-height: 1.1;
  font-variant-numeric: tabular-nums; letter-spacing: -.01em;
}
.stat-label { font-size: 11px; color: var(--ink-4); margin-top: 4px; line-height: 1.4; }
.stat-sub   { font-size: 10px; color: var(--ink-5); margin-top: 2px; }

/* ─── TEXTO NARRATIVO ────────────────────────────────── */
.prose {
  font-size: 12px; color: var(--ink-3); line-height: 1.7;
}
.prose p + p { margin-top: 10px; }
.prose strong { color: var(--ink-2); font-weight: 600; }

/* ─── ACHADOS ────────────────────────────────────────── */
.ilist { list-style: none; display: flex; flex-direction: column; gap: 10px; }
.ilist li {
  display: flex; gap: 10px; align-items: flex-start;
  font-size: 12px; color: var(--ink-2); line-height: 1.5;
}
.ico { flex-shrink: 0; width: 18px; text-align: center; font-size: 13px; margin-top: 1px; }

/* ─── TWO-COL ────────────────────────────────────────── */
.two-col { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; align-items: start; }
.two-col > * { min-width: 0; }

/* ─── RECOMENDAÇÃO ───────────────────────────────────── */
.rec {
  background: #f0fdf4; border: 1px solid #bbf7d0;
  border-radius: 4px; padding: 14px 16px;
}
.rec-title {
  font-size: 10px; font-weight: 700; letter-spacing: .09em;
  text-transform: uppercase; color: var(--green);
  margin-bottom: 12px; padding-bottom: 8px;
  border-bottom: 1px solid #bbf7d0;
}
.rec-row {
  display: flex; gap: 12px; font-size: 12px; color: #166534;
  padding: 4px 0; border-bottom: 1px solid #d1fae5; align-items: baseline;
}
.rec-row:last-of-type { border-bottom: none; }
.rec-label {
  font-size: 10px; font-weight: 700; letter-spacing: .05em;
  text-transform: uppercase; color: #15803d;
  min-width: 90px; flex-shrink: 0;
}
.rec-note {
  font-size: 10.5px; color: #166534;
  margin-top: 10px; padding-top: 8px; border-top: 1px solid #bbf7d0;
}

/* ─── RODAPÉ ─────────────────────────────────────────── */
.footer {
  margin-top: 32px; padding-top: 16px;
  border-top: 1px solid var(--border);
  display: flex; justify-content: space-between;
  align-items: flex-start; flex-wrap: wrap; gap: 8px;
}
.footer-left  { font-size: 10px; color: var(--ink-5); line-height: 1.6; }
.footer-right { font-size: 10px; color: var(--ink-5); text-align: right; line-height: 1.6; }

/* ─── PRINT ──────────────────────────────────────────── */
@media print {
  body { background: #fff; }
  .page { padding: 0; }
  .card { box-shadow: none; break-inside: avoid; }
  /* Oculta controles interativos do Plotly */
  .js-plotly-plot .plotly-notifier,
  .modebar { display: none !important; }
}
"""


# ─── RENDERIZADORES DE SEÇÃO ──────────────────────────────────────────────────

def render_header(meta: dict) -> str:
    fontes = ", ".join(render_code(f) for f in meta.get("fontes", []))
    data = esc(get_generation_timestamp(meta))
    diid_logo = _get_diid_logo_svg()
    return f"""
  <header class="header">
    <div class="header-rail">
      <div class="header-rail-logo" aria-label="DIID">{diid_logo}</div>
    </div>
    <div class="header-main">
      <div>
        <div class="header-label">Relatório de Dados — SUBHUE</div>
        <div class="header-title">{esc(meta.get("titulo",""))}</div>
        <div class="header-subtitle">{esc(meta.get("subtitulo",""))}</div>
      </div>
      <div class="header-meta">
        <div class="header-meta-item"><strong>Período:</strong> {esc(meta.get("periodo",""))}</div>
        <div class="header-meta-item"><strong>Fontes:</strong> {fontes}</div>
        <div class="header-meta-item"><strong>Gerado em:</strong> {data}</div>
      </div>
    </div>
  </header>"""


def render_scope_notice() -> str:
    return """
  <aside class="scope-notice">
    <strong>Documento de validação de base de dados.</strong>
    Este relatório tem finalidade técnica de auditoria e análise de cobertura de fontes.
    Os dados apresentados refletem o estado das tabelas no período indicado e podem conter
    inconsistências em investigação.
    <strong>Não deve ser utilizado como fonte de verdade para fins assistenciais,
    regulatórios ou de gestão fora do contexto de desenvolvimento de dados.</strong>
  </aside>"""


def render_contexto(sec: dict) -> str:
    objetivo = esc(sec.get("objetivo", ""))
    descricao = esc(sec.get("descricao", ""))
    return f"""
  <div class="card">
    <div class="card-title">Contexto <span>· objetivo e definição de escopo</span></div>
    <div class="callout"><strong>Objetivo:</strong> {objetivo}</div>
    <p class="prose" style="margin-top:10px">{descricao}</p>
  </div>"""


def render_tabela(sec: dict) -> str:
    """
    Tabela genérica com colunas tipadas.

    sec = {
      "tipo": "tabela",
      "titulo": "...",
      "subtitulo": "...",          # opcional
      "nota": "...",               # opcional, aparece abaixo da tabela
      "colunas": [
        {"label": "Unidade",       "tipo": "texto"},
        {"label": "Atendimentos",  "tipo": "numero"},
        {"label": "Atingimento",   "tipo": "badge_pct"},
        {"label": "Status",        "tipo": "badge_label"},
        {"label": "Tabela",        "tipo": "codigo"},
        {"label": "Tipo",          "tipo": "pill"}
      ],
      "linhas": [
        [valor1, valor2, valor3, ...]   // um valor por coluna, na mesma ordem
      ]
    }

    Tipos de coluna:
      texto        string simples
      numero       inteiro com separador de milhar pt-BR, alinhado à direita
      badge_pct    float 0-100 → badge hi/md/lo, ou {"pct": 83, "label": "83%"}
      badge_label  string → badge na, ou {"label": "...", "nivel": "hi|md|lo|na|ex"}
      codigo       <code> inline
      pill         {"tipo": "hospital|upa|cer|outro", "label": "HMSF"}
    """
    titulo = esc(sec.get("titulo", ""))
    subtitulo = esc(sec.get("subtitulo", ""))
    nota = sec.get("nota", "")
    colunas = sec.get("colunas", [])

    ths = ""
    for col in colunas:
        alinha = ' class="n"' if col.get("tipo") in ("numero", "badge_pct") else ""
        ths += f'<th{alinha}>{esc(col.get("label",""))}</th>\n'

    rows_html = ""
    for linha in sec.get("linhas", []):
        cells = ""
        for i, val in enumerate(linha):
            col_tipo = colunas[i].get("tipo", "texto") if i < len(colunas) else "texto"
            cells += render_cell(val, col_tipo)
        rows_html += f"<tr>{cells}</tr>\n"

    sub_html = f" <span>· {subtitulo}</span>" if subtitulo else ""
    nota_html = (
        f'<p style="font-size:11px;color:var(--ink-4);margin-top:10px;padding-top:8px;'
        f'border-top:1px solid var(--border-light)">{esc(nota)}</p>'
    ) if nota else ""

    return f"""
  <div class="card">
    <div class="card-title">{titulo}{sub_html}</div>
    <div class="table-scroll">
      <table>
        <thead><tr>{ths}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    {nota_html}
  </div>"""


_chart_counter = 0

def render_grafico(sec: dict) -> str:
    """
    Seção de gráfico Plotly.

    sec = {
      "tipo": "grafico",
      "titulo": "...",             # título do card (card-title), opcional
      "subtitulo": "...",          # opcional
      "nota": "...",               # legenda abaixo do gráfico, opcional
      "figura": {                  # Plotly Figure JSON — gerado pelo LLM
        "data": [...],
        "layout": {...}
      }
    }

    O Figure JSON segue a spec do Plotly (plotly.io.from_json).
    Defaults de cor, fonte e fundo SUBHUE são aplicados automaticamente
    sem sobrescrever o que o LLM especificou explicitamente.
    """
    global _chart_counter
    _chart_counter += 1
    div_id = f"chart_{_chart_counter}"

    titulo = esc(sec.get("titulo", ""))
    subtitulo = esc(sec.get("subtitulo", ""))
    nota = sec.get("nota", "")

    fig_json_raw = sec.get("figura", {"data": [], "layout": {}})
    try:
        fig_json_str = prepare_figure_json(fig_json_raw)
    except Exception as e:
        return f'<div class="card"><p style="color:var(--red);font-size:12px">Erro ao processar figura: {esc(str(e))}</p></div>'

    sub_html = f" <span>· {subtitulo}</span>" if subtitulo else ""
    titulo_html = f'<div class="card-title">{titulo}{sub_html}</div>' if titulo else ""
    nota_html = f'<p style="font-size:10.5px;color:var(--ink-4);margin-top:6px;line-height:1.45">{esc(nota)}</p>' if nota else ""

    return f"""
  <div class="card">
    {titulo_html}
    <div id="{div_id}"></div>
    {nota_html}
    <script>
      (function() {{
        var fig = {fig_json_str};
        var config = {{
          responsive: true,
          displayModeBar: true,
          modeBarButtonsToRemove: ['select2d','lasso2d','autoScale2d'],
          displaylogo: false
        }};
        Plotly.newPlot("{div_id}", fig.data, fig.layout, config);
      }})();
    </script>
  </div>"""


def render_metrica(sec: dict) -> str:
    """
    Grid de números em destaque.

    sec = {
      "tipo": "metrica",
      "titulo": "...",
      "items": [
        {
          "valor": "99%",
          "label": "Match Alta Hospitalar",
          "sub": "HMSF · Maio/2026",    # opcional
          "cor": "var(--green)"          # opcional, default var(--ink)
        }
      ]
    }
    """
    titulo = esc(sec.get("titulo", ""))
    items_html = ""
    for item in sec.get("items", []):
        valor = esc(item.get("valor", ""))
        label = esc(item.get("label", ""))
        sub   = esc(item.get("sub", ""))
        cor   = esc(item.get("cor", "var(--ink)"))
        sub_html = f'<div class="stat-sub">{sub}</div>' if sub else ""
        items_html += f"""
      <div class="stat-box">
        <div class="stat-num" style="color:{cor}">{valor}</div>
        <div class="stat-label">{label}</div>
        {sub_html}
      </div>"""

    return f"""
  <div class="card">
    <div class="card-title">{titulo}</div>
    <div class="metrics-grid">
      {items_html}
    </div>
  </div>"""


def render_texto(sec: dict) -> str:
    """
    Bloco narrativo / metodologia / notas longas.

    sec = {
      "tipo": "texto",
      "titulo": "...",
      "paragrafos": ["Parágrafo 1...", "Parágrafo 2..."]
    }
    """
    titulo = esc(sec.get("titulo", ""))
    paras = "".join(f"<p>{esc(p)}</p>" for p in sec.get("paragrafos", []))
    return f"""
  <div class="card">
    <div class="card-title">{titulo}</div>
    <div class="prose">{paras}</div>
  </div>"""


def render_achados(sec: dict) -> str:
    """
    Lista de achados com ícone semântico.

    sec = {
      "tipo": "achados",
      "items": [
        {
          "tipo": "ok | warn | info | time | error",
          "titulo": "Afirmação principal.",
          "texto": "Complemento explicativo."
        }
      ]
    }
    """
    items_html = ""
    for item in sec.get("items", []):
        ico   = ICO_MAP.get(item.get("tipo", "info"), "📊")
        titulo = esc(item.get("titulo", ""))
        texto  = esc(item.get("texto", ""))
        items_html += f"""
      <li>
        <span class="ico">{ico}</span>
        <span><strong>{titulo}</strong> {texto}</span>
      </li>"""

    return f"""
  <div class="card">
    <div class="card-title">Principais achados</div>
    <ul class="ilist">{items_html}</ul>
  </div>"""


def render_excecao(sec: dict) -> str:
    """
    Two-col: explicação causal + tabela de comparação + stat boxes.

    sec = {
      "tipo": "excecao",
      "titulo": "Por que X diverge entre A e B",
      "descricao": "Texto explicativo...",
      "colunas": ["Unidade", "Fonte A", "Fonte B", "Match"],   # opcional, usa default se ausente
      "linhas": [
        { "nome": "UPA João XXIII", "tipo": "upa", "a": 80, "b": 79, "pct": 99 }
      ],
      "stats": [
        { "valor": "99%", "cor": "var(--green)", "label": "Match UPA — ..." },
        { "valor": "32%", "cor": "var(--red)",   "label": "Match CER — ..." }
      ]
    }
    """
    titulo    = esc(sec.get("titulo", ""))
    descricao = esc(sec.get("descricao", ""))
    col_labels = sec.get("colunas", ["Unidade", "Fonte A", "Fonte B", "Match"])

    rows_html = ""
    for linha in sec.get("linhas", []):
        nome  = esc(linha.get("nome", ""))
        tipo  = linha.get("tipo", "outro")
        pill  = render_pill(tipo, tipo.upper())
        a     = fmt_num(linha.get("a", 0))
        b     = fmt_num(linha.get("b", 0))
        pct   = linha.get("pct")
        badge = render_badge_pct(pct)
        rows_html += f"""
          <tr>
            <td>{pill} {nome}</td>
            <td class="n">{a}</td>
            <td class="n">{b}</td>
            <td class="n">{badge}</td>
          </tr>"""

    ths = "".join(
        f'<th class="n">{esc(l)}</th>' if i > 0 else f'<th>{esc(l)}</th>'
        for i, l in enumerate(col_labels)
    )

    stats_html = ""
    for stat in sec.get("stats", []):
        valor = esc(stat.get("valor", ""))
        cor   = esc(stat.get("cor", "var(--ink)"))
        label = esc(stat.get("label", ""))
        stats_html += f"""
        <div class="stat-box">
          <div class="stat-num" style="color:{cor}">{valor}</div>
          <div class="stat-label">{label}</div>
        </div>"""

    return f"""
  <div class="card">
    <div class="card-title">{titulo}</div>
    <div class="two-col">
      <div>
        <p class="prose" style="margin-bottom:12px">{descricao}</p>
        <div class="table-scroll">
          <table>
            <thead><tr>{ths}</tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:12px">
        {stats_html}
      </div>
    </div>
  </div>"""


def render_recomendacao(sec: dict) -> str:
    """
    Spec técnica em formato de campos.

    sec = {
      "tipo": "recomendacao",
      "titulo": "Escopo e estratégia para...",
      "subtitulo": "model fat_alta_agg_timed",
      "nota": "Observação final...",
      "campos": [
        { "label": "Fonte",  "valor": "raw_timed_dtw.fat_alta" },
        { "label": "Grain",  "valor": {"code": "date_trunc(...)"} },
        { "label": "Filtro", "valor": "tipo_alta_detalhada = 'ALTA HOSPITALAR'" }
      ]
    }
    """
    titulo    = esc(sec.get("titulo", ""))
    subtitulo = esc(sec.get("subtitulo", ""))
    nota      = sec.get("nota", "")

    rows_html = ""
    for row in sec.get("campos", []):
        label = esc(row.get("label", ""))
        valor = row.get("valor", "")
        if isinstance(valor, dict) and "code" in valor:
            valor_html = render_code(valor["code"])
        else:
            valor_html = esc(str(valor))
        rows_html += f"""
      <div class="rec-row">
        <span class="rec-label">{label}</span>
        <span>{valor_html}</span>
      </div>"""

    nota_html = f'<p class="rec-note">{esc(nota)}</p>' if nota else ""
    sub_html  = f" <span>· {subtitulo}</span>" if subtitulo else ""

    return f"""
  <div class="card">
    <div class="card-title">Recomendação{sub_html}</div>
    <div class="rec">
      <div class="rec-title">{titulo}</div>
      {rows_html}
      {nota_html}
    </div>
  </div>"""


def render_footer(meta: dict) -> str:
    data   = esc(get_generation_timestamp(meta))
    fontes = ", ".join(render_code(f) for f in meta.get("fontes", []))
    return f"""
  <footer class="footer">
    <div class="footer-left">
      Gerado em <strong>{data}</strong><br>
      DIID · Divisão de Inovação e Inteligência de Dados — SUBHUE / SMS-Rio
    </div>
    <div class="footer-right">
      Fontes: {fontes}<br>
      Documento de validação técnica · uso interno
    </div>
  </footer>"""


# ─── DISPATCH ─────────────────────────────────────────────────────────────────

SECAO_RENDERERS = {
    "contexto":     render_contexto,
    "tabela":       render_tabela,
    "grafico":      render_grafico,
    "metrica":      render_metrica,
    "texto":        render_texto,
    "achados":      render_achados,
    "excecao":      render_excecao,
    "recomendacao": render_recomendacao,
}


# ─── MONTAGEM DO HTML ─────────────────────────────────────────────────────────

def gerar_html(dados: dict, plotly_js: str) -> str:
    global _chart_counter
    _chart_counter = 0

    meta   = dados.get("meta", {})
    secoes = dados.get("secoes", [])
    titulo = esc(meta.get("titulo", "Relatório de Dados SUBHUE"))

    body_parts = [render_header(meta), render_scope_notice()]

    for secao in secoes:
        tipo     = secao.get("tipo")
        renderer = SECAO_RENDERERS.get(tipo)
        if renderer:
            body_parts.append(renderer(secao))
        else:
            body_parts.append(
                f'<div class="card" style="border-color:var(--red-bg)">'
                f'<p style="color:var(--red);font-size:12px">'
                f'Tipo de seção desconhecido: <code>{esc(tipo or "")}</code></p></div>'
            )

    body_parts.append(render_footer(meta))
    body = "\n".join(body_parts)

    # Plotly só é incluído se houver seções de gráfico
    tem_graficos = any(s.get("tipo") == "grafico" for s in secoes)
    plotly_script = f"<script>{plotly_js}</script>" if tem_graficos else ""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titulo}</title>
{plotly_script}
<style>{CSS}</style>
</head>
<body>
<div class="page">
{body}
</div>
</body>
</html>"""


# ─── SCHEMA EXEMPLO ───────────────────────────────────────────────────────────

def schema_exemplo() -> dict:
    return {
        "meta": {
            "titulo": "Análise de Altas por Estabelecimento",
            "subtitulo": "Cobertura de fontes para modelo de altas com granularidade de 30 minutos",
            "periodo": "Maio/2026",
            "fontes": ["raw_timed_dtw.fat_alta", "silver_timed.fat_censo_estatistica"],
            "data_hora_geracao": "2026-06-18T14:30:00Z"
        },
        "secoes": [
            {
                "tipo": "contexto",
                "objetivo": "Identificar a melhor fonte para um model de altas com granularidade de 30 minutos.",
                "descricao": (
                    "fat_censo_estatistica.alta conta leitos com movimentação tipo ALTA em "
                    "fat_historico_leito_estavel. Granularidade diária, escopo restrito a "
                    "internação hospitalar — não captura emergência, ambulatório ou transferências "
                    "ambulatoriais. fat_alta registra o mesmo evento com timestamp completo e cobre "
                    "todos os tipos de saída, sendo a fonte indicada para análises intradiárias."
                )
            },
            {
                "tipo": "metrica",
                "titulo": "Resumo de cobertura — Maio/2026",
                "items": [
                    {"valor": "~100%", "label": "Match Alta Hospitalar", "sub": "HMSF", "cor": "var(--green)"},
                    {"valor": "89%",   "label": "Match Alta Hospitalar", "sub": "UPA João XXIII", "cor": "var(--green)"},
                    {"valor": "32%",   "label": "Match Transferência",   "sub": "CER Barra",      "cor": "var(--red)"},
                    {"valor": "80–98%","label": "Volume invisível ao censo (Alta Ambulatorial)", "cor": "var(--yellow)"}
                ]
            },
            {
                "tipo": "tabela",
                "titulo": "Correlação fat_alta × fat_censo_estatistica",
                "subtitulo": "Maio/2026 · dedup: 1 boletim → 1 alta (último data_alta)",
                "nota": "O censo captura apenas saídas de leito de internação. Alta Ambulatorial representa 80–98% do volume real.",
                "colunas": [
                    {"label": "Tipo de alta",  "tipo": "texto"},
                    {"label": "Campo censo",   "tipo": "codigo"},
                    {"label": "HMSF · A/B",    "tipo": "texto"},
                    {"label": "UPA JXXIII · A/B","tipo": "texto"},
                    {"label": "CER Barra · A/B","tipo": "texto"}
                ],
                "linhas": [
                    ["ALTA HOSPITALAR",   "alta",                              "917/914 ~100%", "97/86 89%",   "476/443 93%"],
                    ["ÓBITO",             "obito_maior_24 + obito_menor_24",   "136/132 97%",   "12/13 92%",   "62/59 95%"],
                    ["TRANSFERÊNCIA",     "transf_ext + transf_int + transf_emer","1295/763 59%","80/79 99%",  "873/283 32%"],
                    ["ALTA AMBULATORIAL", "— fora do censo",                   "9.740",         "10.555",      "11.162"]
                ]
            },
            {
                "tipo": "grafico",
                "titulo": "Distribuição horária — Alta Hospitalar por unidade",
                "subtitulo": "Maio/2026, acumulado",
                "nota": "Cada tipo de unidade tem perfil horário distinto. O modelo de 30min deve dimensionar esse comportamento por tipo de unidade.",
                "figura": {
                    "data": [
                        {
                            "type": "bar",
                            "name": "HMSF (Hospital)",
                            "x": list(range(24)),
                            "y": [2,1,1,1,1,1,2,15,35,51,66,78,87,100,88,70,52,38,25,15,8,5,3,2],
                            "marker": {"color": "#3b82f6"}
                        },
                        {
                            "type": "bar",
                            "name": "UPA João XXIII",
                            "x": list(range(24)),
                            "y": [3,2,2,2,3,5,8,20,30,38,42,50,55,60,65,70,80,100,60,40,25,15,8,5],
                            "marker": {"color": "#16a34a"}
                        },
                        {
                            "type": "bar",
                            "name": "CER Barra",
                            "x": list(range(24)),
                            "y": [1,1,1,1,1,1,2,5,10,18,28,42,60,72,82,90,100,97,90,75,45,20,8,3],
                            "marker": {"color": "#9333ea"}
                        }
                    ],
                    "layout": {
                        "barmode": "group",
                        "xaxis": {"title": {"text": "Hora do dia"}, "tickmode": "linear", "dtick": 2},
                        "yaxis": {"title": {"text": "Volume relativo (índice pico=100)"}},
                        "height": 320
                    }
                }
            },
            {
                "tipo": "excecao",
                "titulo": "Por que Transferência diverge entre Hospital/CER e UPA",
                "descricao": (
                    "fat_alta.TRANSFERENCIA captura saídas com destino externo de todos os fluxos "
                    "— internação, emergência e ambulatório. fat_historico_leito_estavel registra "
                    "apenas movimentações de leito físico, perdendo as transferências de pacientes ambulatoriais."
                ),
                "linhas": [
                    {"nome": "João XXIII", "tipo": "upa",      "a": 80,   "b": 79,  "pct": 99},
                    {"nome": "HMSF",       "tipo": "hospital", "a": 1308, "b": 763, "pct": 58},
                    {"nome": "CER Barra",  "tipo": "cer",      "a": 876,  "b": 283, "pct": 32}
                ],
                "stats": [
                    {"valor": "99%", "cor": "var(--green)", "label": "Match UPA — quase toda transferência é de leito de internação, capturada pelo censo"},
                    {"valor": "32%", "cor": "var(--red)",   "label": "Match CER — alto volume de transferências ambulatoriais fora do escopo do censo"}
                ]
            },
            {
                "tipo": "achados",
                "items": [
                    {"tipo": "ok",   "titulo": "fat_alta é a única fonte com timestamp de saída para análises intradiárias.", "texto": "fat_historico_leito_estavel tem hil_dataalta mas cobertura restrita a leitos com movimentação ALTA."},
                    {"tipo": "ok",   "titulo": "Alta Hospitalar em fat_alta replica com 90–99% de fidelidade o campo alta do censo.", "texto": "Diferença residual por timing de extração."},
                    {"tipo": "warn", "titulo": "Transferência apresenta divergência significativa em hospitais e CER (58% e 32%).", "texto": "fat_alta inclui transferências ambulatoriais que o censo não captura."},
                    {"tipo": "info", "titulo": "Alta Ambulatorial representa 80–98% do volume real de saídas e é completamente invisível ao censo.", "texto": "Em UPAs, é o tipo dominante com ~99% dos eventos."},
                    {"tipo": "time", "titulo": "Cada tipo de unidade tem perfil horário distinto.", "texto": "Hospital pico às 13h, CER às 16h–19h, UPA sem padrão definido de internação. Modelo 30min precisa dimensionar esse comportamento por tipo de unidade."}
                ]
            },
            {
                "tipo": "recomendacao",
                "titulo": "Escopo e estratégia para o model de 30 minutos",
                "subtitulo": "fat_alta_agg_timed",
                "nota": "Sem filtro de tipo — tipo_alta_detalhada como dimensão — permite análises para todos os escopos sem modelo dual.",
                "campos": [
                    {"label": "Fonte",       "valor": {"code": "raw_timed_dtw.fat_alta"}},
                    {"label": "Grain",       "valor": "janela 30min × estabelecimento × tipo_alta_detalhada × motivo_saida"},
                    {"label": "Bucketing",   "valor": {"code": "date_trunc('hour', data_alta) + floor(extract(minute from data_alta)/30) * interval '30 min'"}},
                    {"label": "Incremental", "valor": "delete+insert por dh_janela_30min::date — idêntico ao atendimento_emergencia_agg"},
                    {"label": "Filtro censo","valor": "Para equivalência com fat_censo_estatistica.alta: filtrar tipo_alta_detalhada = 'ALTA HOSPITALAR'"}
                ]
            },
            {
                "tipo": "texto",
                "titulo": "Metodologia",
                "paragrafos": [
                    "A deduplicação aplicada considera 1 boletim → 1 alta, retendo o último registro por data_alta quando múltiplos boletins existem para o mesmo paciente no período.",
                    "A comparação entre fat_alta e fat_censo_estatistica foi realizada no nível de contagem agregada por tipo de saída e estabelecimento. Não foi realizado match em nível de paciente individual.",
                    "Os percentuais de match foram calculados como min(A,B)/max(A,B) para evitar distorções quando a fonte B supera a fonte A em categorias específicas (ex: óbito UPA João XXIII, onde censo=13 e fat_alta=12)."
                ]
            }
        ]
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera relatório HTML SUBHUE a partir de um arquivo JSON."
    )
    parser.add_argument("json_input", nargs="?",
        help="Arquivo JSON de dados. Se omitido, gera schema_exemplo.json.")
    parser.add_argument("-o", "--output", default="data/reports/relatorio.html",
        help="Arquivo HTML de saída (padrão: data/reports/relatorio.html)")
    parser.add_argument("--exemplo", action="store_true",
        help="Gera schema_exemplo.json com o schema completo e sai.")
    parser.add_argument("--schema-only", action="store_true",
        help="Gera apenas o schema_exemplo.json sem rodar o gerador.")

    args = parser.parse_args()

    if args.exemplo or args.schema_only or args.json_input is None:
        exemplo = schema_exemplo()
        out_path = Path("schema_exemplo.json")
        out_path.write_text(json.dumps(exemplo, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ schema_exemplo.json gerado em {out_path.resolve()}")
        if args.schema_only or args.json_input is None:
            print("\nUso: python gerador_relatorio_subhue.py schema_exemplo.json -o data/reports/relatorio.html")
            return

    input_path = Path(args.json_input)
    if not input_path.exists():
        print(f"Erro: arquivo não encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    dados = json.loads(input_path.read_text(encoding="utf-8"))
    if ensure_generation_timestamp(dados):
        input_path.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print("Carregando Plotly.js...")
    plotly_js = _get_plotly_js()

    print("Gerando HTML...")
    html = gerar_html(dados, plotly_js)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"✓ Relatório gerado: {output_path.resolve()} ({size_mb:.1f}MB)")


if __name__ == "__main__":
    main()
