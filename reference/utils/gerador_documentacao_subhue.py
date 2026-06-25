#!/usr/bin/env python3
"""
gerador_documentacao_subhue.py
──────────────────────────────
Gera documentação técnica HTML self-contained a partir de um JSON estruturado.
Plotly.js é embutido diretamente no HTML — sem CDN, sem kaleido.

Uso:
    python gerador_documentacao_subhue.py dados.json
    python gerador_documentacao_subhue.py dados.json -o data/reports/doc.html
    python gerador_documentacao_subhue.py --exemplo      # gera schema_exemplo_doc.json

Tipos de seção disponíveis:
    visao_geral     descrição do artefato e seu propósito
    dependencias    upstream (fontes) e downstream (consumers)
    colunas         campos com tipo, constraints e descrição
    especificacao   configuração técnica em campos label/valor
    observacoes     pontos de atenção, limitações, comportamentos esperados
    changelog       histórico de versões
    texto           bloco narrativo, lógica de negócio, metodologia
    tabela          tabela genérica com colunas tipadas
    metrica         grid de indicadores em destaque
    grafico         qualquer Figure JSON do Plotly
"""

import argparse
import html as html_module
import json
import sys
from pathlib import Path

from report_metadata import ensure_generation_timestamp, get_generation_timestamp


# ─── PLOTLY JS ────────────────────────────────────────────────────────────────

def _get_plotly_js() -> str:
    import plotly
    js_path = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    if not js_path.exists():
        raise FileNotFoundError(f"plotly.min.js não encontrado em {js_path}.")
    return js_path.read_text(encoding="utf-8")


def _get_diid_logo_svg() -> str:
    """Retorna o SVG da marca DIID para embutir no HTML final."""
    svg_path = Path(__file__).with_name("diid_vertical_fix.svg")
    if not svg_path.exists():
        raise FileNotFoundError(f"Logo DIID não encontrada em {svg_path}.")
    return svg_path.read_text(encoding="utf-8")


# ─── PALETA & TOKENS ──────────────────────────────────────────────────────────

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

ICO_MAP = {
    "ok":    "✅",
    "warn":  "⚠️",
    "info":  "ℹ️",
    "limit": "🔲",
    "time":  "🕐",
    "error": "❌",
}

CHANGELOG_TIPO = {
    "feat":     ("#dbeafe", "#1d4ed8", "FEAT"),
    "fix":      ("#dcfce7", "#15803d", "FIX"),
    "refactor": ("#ede9fe", "#6d28d9", "REFACTOR"),
    "break":    ("#fee2e2", "#dc2626", "BREAKING"),
    "docs":     ("#f1f5f9", "#475569", "DOCS"),
    "chore":    ("#f1f5f9", "#475569", "CHORE"),
}

COL_TYPES = {"texto", "numero", "badge_pct", "badge_label", "codigo", "pill"}

PILL = {
    "hospital": ("pill-h", "#dbeafe", "#1d4ed8"),
    "upa":      ("pill-u", "#dcfce7", "#15803d"),
    "cer":      ("pill-c", "#ede9fe", "#6d28d9"),
    "outro":    ("pill-o", "#ffedd5", "#c2410c"),
}


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
    cls = f"badge {nivel}" if nivel in ("hi", "md", "lo", "na", "ex") else "badge na"
    return f'<span class="{cls}">{esc(label)}</span>'


def render_code(text: str) -> str:
    return f"<code>{esc(text)}</code>"


def render_cell(value, col_tipo: str) -> str:
    if value is None:
        return '<td><span style="color:var(--ink-5)">—</span></td>'
    if col_tipo == "numero":
        return f'<td class="n">{esc(fmt_num(value))}</td>'
    if col_tipo == "badge_pct":
        if isinstance(value, dict):
            return f'<td class="n">{render_badge_pct(value.get("pct"), value.get("label"))}</td>'
        return f'<td class="n">{render_badge_pct(float(value))}</td>'
    if col_tipo == "badge_label":
        if isinstance(value, dict):
            return f'<td>{render_badge_label(value.get("label",""), value.get("nivel","na"))}</td>'
        return f'<td>{render_badge_label(str(value))}</td>'
    if col_tipo == "codigo":
        return f'<td>{render_code(str(value))}</td>'
    if col_tipo == "pill":
        if isinstance(value, dict):
            tipo = value.get("tipo", "outro")
            lbl  = value.get("label", "")
            _, bg, fg = PILL.get(tipo, PILL["outro"])
            return f'<td><span class="tag" style="background:{bg};color:{fg}">{esc(lbl)}</span></td>'
        return f'<td>{esc(str(value))}</td>'
    return f'<td>{esc(str(value))}</td>'


# ─── PLOTLY: MERGE DE DEFAULTS ───────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def prepare_figure_json(fig_json: dict) -> str:
    import plotly.io as pio
    layout_merged = _deep_merge(PLOTLY_LAYOUT_DEFAULTS, fig_json.get("layout", {}))
    fig_json_merged = dict(fig_json)
    fig_json_merged["layout"] = layout_merged
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

/* ─── TOC ────────────────────────────────────────────── */
.toc {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--navy-mid);
  border-radius: 4px;
  padding: 14px 18px;
  margin-bottom: 20px;
  font-size: 11.5px;
}
.toc-title {
  font-size: 9px; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: var(--ink-4); margin-bottom: 10px;
}
.toc ol { padding-left: 18px; }
.toc li { color: var(--ink-3); line-height: 2; }
.toc a { color: var(--navy-mid); text-decoration: none; }
.toc a:hover { text-decoration: underline; }

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
  display: flex; justify-content: space-between; align-items: center;
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
  line-height: 1.6;
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

/* ─── TAG (pill inline) ──────────────────────────────── */
.tag {
  display: inline-block; font-size: 10px; font-weight: 700;
  padding: 2px 8px; border-radius: 10px;
  letter-spacing: .02em; white-space: nowrap;
}

/* ─── CÓDIGO ─────────────────────────────────────────── */
code {
  background: #e8e4f8; color: #3730a3;
  font-family: 'JetBrains Mono', 'Courier New', monospace;
  font-size: 10.5px; padding: 1px 5px; border-radius: 3px;
}

/* ─── MÉTRICAS ───────────────────────────────────────── */
.metrics-grid {
  display: grid; gap: 12px;
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

/* ─── LISTA DE ITENS (observações) ──────────────────── */
.ilist { list-style: none; display: flex; flex-direction: column; gap: 10px; }
.ilist li {
  display: flex; gap: 10px; align-items: flex-start;
  font-size: 12px; color: var(--ink-2); line-height: 1.5;
}
.ico { flex-shrink: 0; width: 18px; text-align: center; font-size: 13px; margin-top: 1px; }

/* ─── ESPECIFICAÇÃO ──────────────────────────────────── */
.spec {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 4px; padding: 14px 16px;
}
.spec-title {
  font-size: 10px; font-weight: 700; letter-spacing: .09em;
  text-transform: uppercase; color: #0369a1;
  margin-bottom: 12px; padding-bottom: 8px;
  border-bottom: 1px solid #bae6fd;
}
.spec-row {
  display: flex; gap: 12px; font-size: 12px; color: #0c4a6e;
  padding: 5px 0; border-bottom: 1px solid #e0f2fe; align-items: baseline;
}
.spec-row:last-of-type { border-bottom: none; }
.spec-label {
  font-size: 10px; font-weight: 700; letter-spacing: .05em;
  text-transform: uppercase; color: #0369a1;
  min-width: 110px; flex-shrink: 0;
}
.spec-note {
  font-size: 10.5px; color: #0c4a6e;
  margin-top: 10px; padding-top: 8px; border-top: 1px solid #bae6fd;
}

/* ─── DEPENDÊNCIAS ───────────────────────────────────── */
.dep-section {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .07em; padding: 6px 0 4px;
  border-bottom: 1px solid var(--border-light); margin-bottom: 6px;
}
.dep-section.up   { color: var(--blue); }
.dep-section.down { color: var(--green); }
.dep-list { list-style: none; display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; }
.dep-item { display: flex; gap: 8px; align-items: baseline; font-size: 12px; }
.dep-desc { font-size: 11px; color: var(--ink-4); }

/* ─── COLUNAS ────────────────────────────────────────── */
.col-desc { font-size: 11.5px; color: var(--ink-3); }

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
  .js-plotly-plot .plotly-notifier,
  .modebar { display: none !important; }
}
"""


# ─── HEADER ──────────────────────────────────────────────────────────────────

def render_header(meta: dict) -> str:
    data = esc(get_generation_timestamp(meta))
    diid_logo = _get_diid_logo_svg()

    meta_items = []
    if meta.get("versao"):
        meta_items.append(f'<div class="header-meta-item"><strong>Versão:</strong> {esc(meta["versao"])}</div>')
    if meta.get("autores"):
        autores = ", ".join(meta["autores"]) if isinstance(meta["autores"], list) else meta["autores"]
        meta_items.append(f'<div class="header-meta-item"><strong>Autores:</strong> {esc(autores)}</div>')
    if meta.get("periodo"):
        meta_items.append(f'<div class="header-meta-item"><strong>Vigência:</strong> {esc(meta["periodo"])}</div>')
    if meta.get("fontes"):
        fontes = ", ".join(render_code(f) for f in meta["fontes"])
        meta_items.append(f'<div class="header-meta-item"><strong>Fontes:</strong> {fontes}</div>')
    meta_items.append(f'<div class="header-meta-item"><strong>Gerado em:</strong> {data}</div>')

    return f"""
  <header class="header">
    <div class="header-rail">
      <div class="header-rail-logo" aria-label="DIID">{diid_logo}</div>
    </div>
    <div class="header-main">
      <div>
        <div class="header-label">Documentação Técnica — SUBHUE</div>
        <div class="header-title">{esc(meta.get("titulo", ""))}</div>
        <div class="header-subtitle">{esc(meta.get("subtitulo", ""))}</div>
      </div>
      <div class="header-meta">{"".join(meta_items)}</div>
    </div>
  </header>"""


# ─── TOC ─────────────────────────────────────────────────────────────────────

def render_toc(secoes: list) -> str:
    itens = []
    contador = 0
    for sec in secoes:
        titulo = sec.get("titulo") or _titulo_padrao(sec.get("tipo", ""))
        if not titulo:
            continue
        contador += 1
        anchor = f"sec-{contador}"
        sec["_anchor"] = anchor
        itens.append(f'<li><a href="#{anchor}">{esc(titulo)}</a></li>')
    if not itens:
        return ""
    return f"""
  <nav class="toc">
    <div class="toc-title">Conteúdo</div>
    <ol>{"".join(itens)}</ol>
  </nav>"""


def _titulo_padrao(tipo: str) -> str:
    return {
        "visao_geral":   "Visão Geral",
        "dependencias":  "Dependências",
        "colunas":       "Colunas",
        "especificacao": "Especificação Técnica",
        "observacoes":   "Observações",
        "changelog":     "Histórico de Mudanças",
        "texto":         "",
        "tabela":        "",
        "metrica":       "",
        "grafico":       "",
    }.get(tipo, "")


def _card_title_html(sec: dict, tipo_default: str) -> str:
    titulo    = esc(sec.get("titulo") or _titulo_padrao(tipo_default))
    subtitulo = esc(sec.get("subtitulo", ""))
    anchor    = sec.get("_anchor", "")
    anchor_attr = f' id="{anchor}"' if anchor else ""
    sub_html  = f'<span>· {subtitulo}</span>' if subtitulo else ""
    return f'<div class="card-title"{anchor_attr}>{titulo} {sub_html}</div>'


# ─── RENDERIZADORES DE SEÇÃO ─────────────────────────────────────────────────

def render_visao_geral(sec: dict) -> str:
    """
    Descrição do artefato: o que é, para que serve, escopo.

    sec = {
      "tipo": "visao_geral",
      "titulo": "Visão Geral",       # opcional, default "Visão Geral"
      "descricao": "Texto livre descrevendo o artefato.",
      "detalhes": [                   # opcional — lista de pontos objetivos
        "Model incremental com estratégia delete+insert.",
        "Grain: janela_30min × estabelecimento × tipo_atendimento."
      ]
    }
    """
    descricao = esc(sec.get("descricao", ""))
    detalhes  = sec.get("detalhes", [])

    detalhes_html = ""
    if detalhes:
        itens = "".join(f"<li>{esc(d)}</li>" for d in detalhes)
        detalhes_html = f'<ul style="margin-top:10px;padding-left:18px;font-size:12px;color:var(--ink-3);line-height:1.8">{itens}</ul>'

    return f"""
  <div class="card">
    {_card_title_html(sec, "visao_geral")}
    <div class="callout">{descricao}</div>
    {detalhes_html}
  </div>"""


def render_dependencias(sec: dict) -> str:
    """
    Upstream (fontes) e downstream (consumers) do artefato.

    sec = {
      "tipo": "dependencias",
      "titulo": "Dependências",       # opcional
      "upstream": [
        {"nome": "raw_timed_dtw.fat_atendimento", "descricao": "Fonte de atendimentos"},
        "raw_timed_dtw.fat_boletim"
      ],
      "downstream": [
        {"nome": "gold_timed.vw_censo_atendimento", "descricao": "View principal"},
        "gold_timed.fat_paciente_agg"
      ],
      "nota": "..."   # opcional
    }
    """
    nota = sec.get("nota", "")

    def render_list(items: list, css_class: str, label: str) -> str:
        if not items:
            return ""
        rows = ""
        for item in items:
            if isinstance(item, dict):
                nome = esc(item.get("nome", ""))
                desc = esc(item.get("descricao", ""))
            else:
                nome = esc(str(item))
                desc = ""
            desc_html = f'<span class="dep-desc">— {desc}</span>' if desc else ""
            rows += f'<li class="dep-item"><code>{nome}</code>{desc_html}</li>'
        return f'<div class="dep-section {css_class}">{label}</div><ul class="dep-list">{rows}</ul>'

    upstream_html   = render_list(sec.get("upstream",   []), "up",   "▲ Upstream — fontes")
    downstream_html = render_list(sec.get("downstream", []), "down", "▼ Downstream — consumers")

    nota_html = (
        f'<p style="font-size:11px;color:var(--ink-4);margin-top:4px;padding-top:8px;'
        f'border-top:1px solid var(--border-light)">{esc(nota)}</p>'
    ) if nota else ""

    return f"""
  <div class="card">
    {_card_title_html(sec, "dependencias")}
    {upstream_html}
    {downstream_html}
    {nota_html}
  </div>"""


def render_colunas(sec: dict) -> str:
    """
    Tabela de colunas de um model ou campos de um processo.

    sec = {
      "tipo": "colunas",
      "titulo": "Colunas",            # opcional
      "nota": "...",                  # opcional
      "items": [
        {
          "nome": "pk_agg_gid",
          "tipo_dado": "UUID",
          "pk": true,                 # opcional — chave primária
          "obrigatorio": true,        # opcional — true=NOT NULL / false=nullable
          "incrementa": true,         # opcional — campo de controle incremental
          "descricao": "Chave primária gerada via uuid_generate_v4()"
        }
      ]
    }
    """
    nota  = sec.get("nota", "")
    items = sec.get("items", [])

    rows_html = ""
    for item in items:
        nome      = esc(item.get("nome", ""))
        tipo_dado = esc(item.get("tipo_dado", ""))
        descricao = esc(item.get("descricao", ""))
        badges = []
        if item.get("pk"):
            badges.append(render_badge_label("PK", "ex"))
        if item.get("obrigatorio") is True:
            badges.append(render_badge_label("NOT NULL", "lo"))
        elif item.get("obrigatorio") is False:
            badges.append(render_badge_label("nullable", "na"))
        if item.get("incrementa"):
            badges.append(render_badge_label("incremental", "md"))
        badges_html = " ".join(badges)
        rows_html += f"""
        <tr>
          <td><code>{nome}</code></td>
          <td><code style="background:#f1f5f9;color:var(--ink-3)">{tipo_dado}</code></td>
          <td>{badges_html}</td>
          <td class="col-desc">{descricao}</td>
        </tr>"""

    nota_html = (
        f'<p style="font-size:11px;color:var(--ink-4);margin-top:10px;padding-top:8px;'
        f'border-top:1px solid var(--border-light)">{esc(nota)}</p>'
    ) if nota else ""

    return f"""
  <div class="card">
    {_card_title_html(sec, "colunas")}
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Campo</th>
            <th>Tipo</th>
            <th style="min-width:130px"></th>
            <th>Descrição</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    {nota_html}
  </div>"""


def render_especificacao(sec: dict) -> str:
    """
    Configuração técnica do artefato em campos label/valor.

    sec = {
      "tipo": "especificacao",
      "titulo": "Especificação Técnica",   # opcional
      "subtitulo": "fat_alta_agg_timed",   # opcional
      "nota": "Observação final...",       # opcional
      "campos": [
        {"label": "Fonte",       "valor": {"code": "raw_timed_dtw.fat_alta"}},
        {"label": "Grain",       "valor": "janela_30min × estabelecimento × tipo_alta"},
        {"label": "Strategy",    "valor": "incremental — delete+insert por dh_janela_30min::date"},
        {"label": "Filtro",      "valor": "tipo_alta_detalhada = 'ALTA HOSPITALAR'"}
      ]
    }

    O campo "valor" aceita string ou {"code": "..."} para renderizar como <code>.
    """
    nota = sec.get("nota", "")

    rows_html = ""
    for row in sec.get("campos", []):
        label = esc(row.get("label", ""))
        valor = row.get("valor", "")
        if isinstance(valor, dict) and "code" in valor:
            valor_html = render_code(valor["code"])
        else:
            valor_html = esc(str(valor))
        rows_html += f"""
      <div class="spec-row">
        <span class="spec-label">{label}</span>
        <span>{valor_html}</span>
      </div>"""

    nota_html = f'<p class="spec-note">{esc(nota)}</p>' if nota else ""

    return f"""
  <div class="card">
    {_card_title_html(sec, "especificacao")}
    <div class="spec">
      {rows_html}
      {nota_html}
    </div>
  </div>"""


def render_observacoes(sec: dict) -> str:
    """
    Pontos de atenção, limitações e comportamentos esperados.

    sec = {
      "tipo": "observacoes",
      "titulo": "Observações",    # opcional, default "Observações"
      "items": [
        {
          "tipo": "ok | warn | info | limit | time | error",
          "titulo": "Afirmação principal.",
          "texto": "Detalhe complementar."
        }
      ]
    }
    """
    items_html = ""
    for item in sec.get("items", []):
        ico    = ICO_MAP.get(item.get("tipo", "info"), "ℹ️")
        titulo = esc(item.get("titulo", ""))
        texto  = esc(item.get("texto", ""))
        texto_html = f" {texto}" if texto else ""
        items_html += f"""
      <li>
        <span class="ico">{ico}</span>
        <span><strong>{titulo}</strong>{texto_html}</span>
      </li>"""

    return f"""
  <div class="card">
    {_card_title_html(sec, "observacoes")}
    <ul class="ilist">{items_html}</ul>
  </div>"""


def render_changelog(sec: dict) -> str:
    """
    Histórico de versões.

    sec = {
      "tipo": "changelog",
      "titulo": "Histórico de Mudanças",   # opcional
      "items": [
        {
          "versao": "v1.2",
          "data": "12/06/2026",
          "autor": "Moscarde",           # opcional
          "tipo": "feat|fix|refactor|break|docs|chore",
          "descricao": "Adicionado campo motivo_saida"
        }
      ]
    }
    """
    rows_html = ""
    for item in sec.get("items", []):
        versao    = esc(item.get("versao", ""))
        data      = esc(item.get("data", ""))
        autor     = esc(item.get("autor", ""))
        tipo_key  = item.get("tipo", "feat").lower()
        descricao = esc(item.get("descricao", ""))
        bg, fg, label = CHANGELOG_TIPO.get(tipo_key, ("#f1f5f9", "#475569", tipo_key.upper()))
        tag_html  = f'<span class="tag" style="background:{bg};color:{fg};font-size:9px">{label}</span>'
        autor_html = f' <span style="color:var(--ink-5);font-size:10.5px">— {autor}</span>' if autor else ""
        rows_html += f"""
        <tr>
          <td style="white-space:nowrap"><code>{versao}</code></td>
          <td style="white-space:nowrap;color:var(--ink-4);font-size:11px">{data}</td>
          <td>{tag_html}</td>
          <td style="font-size:12px;color:var(--ink-2)">{descricao}{autor_html}</td>
        </tr>"""

    return f"""
  <div class="card">
    {_card_title_html(sec, "changelog")}
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Versão</th>
            <th>Data</th>
            <th>Tipo</th>
            <th>Mudança</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </div>"""


def render_texto(sec: dict) -> str:
    """
    Bloco narrativo — lógica de negócio, metodologia, notas.

    sec = {
      "tipo": "texto",
      "titulo": "...",
      "paragrafos": ["Parágrafo 1...", "Parágrafo 2..."]
    }
    """
    paras = "".join(f"<p>{esc(p)}</p>" for p in sec.get("paragrafos", []))
    return f"""
  <div class="card">
    {_card_title_html(sec, "texto")}
    <div class="prose">{paras}</div>
  </div>"""


def render_tabela(sec: dict) -> str:
    """
    Tabela genérica com colunas tipadas.

    sec = {
      "tipo": "tabela",
      "titulo": "...",
      "subtitulo": "...",         # opcional
      "nota": "...",              # opcional
      "colunas": [
        {"label": "Campo",  "tipo": "texto"},
        {"label": "Valor",  "tipo": "numero"},
        {"label": "Status", "tipo": "badge_label"}
      ],
      "linhas": [[val1, val2, val3], ...]
    }

    Tipos: texto | numero | badge_pct | badge_label | codigo | pill
    """
    nota    = sec.get("nota", "")
    colunas = sec.get("colunas", [])

    ths = ""
    for col in colunas:
        alinha = ' class="n"' if col.get("tipo") in ("numero", "badge_pct") else ""
        ths += f'<th{alinha}>{esc(col.get("label", ""))}</th>\n'

    rows_html = ""
    for linha in sec.get("linhas", []):
        cells = ""
        for i, val in enumerate(linha):
            col_tipo = colunas[i].get("tipo", "texto") if i < len(colunas) else "texto"
            cells += render_cell(val, col_tipo)
        rows_html += f"<tr>{cells}</tr>\n"

    nota_html = (
        f'<p style="font-size:11px;color:var(--ink-4);margin-top:10px;padding-top:8px;'
        f'border-top:1px solid var(--border-light)">{esc(nota)}</p>'
    ) if nota else ""

    return f"""
  <div class="card">
    {_card_title_html(sec, "tabela")}
    <div class="table-scroll">
      <table>
        <thead><tr>{ths}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    {nota_html}
  </div>"""


def render_metrica(sec: dict) -> str:
    """
    Grid de indicadores em destaque.

    sec = {
      "tipo": "metrica",
      "titulo": "...",
      "items": [
        {"valor": "1.2M", "label": "Atendimentos", "sub": "Maio/2026", "cor": "var(--green)"}
      ]
    }
    """
    items_html = ""
    for item in sec.get("items", []):
        valor = esc(item.get("valor", ""))
        label = esc(item.get("label", ""))
        sub   = esc(item.get("sub",   ""))
        cor   = esc(item.get("cor",   "var(--ink)"))
        sub_html = f'<div class="stat-sub">{sub}</div>' if sub else ""
        items_html += f"""
      <div class="stat-box">
        <div class="stat-num" style="color:{cor}">{valor}</div>
        <div class="stat-label">{label}</div>
        {sub_html}
      </div>"""

    return f"""
  <div class="card">
    {_card_title_html(sec, "metrica")}
    <div class="metrics-grid">{items_html}</div>
  </div>"""


_chart_counter = 0

def render_grafico(sec: dict) -> str:
    """
    Seção de gráfico Plotly.

    sec = {
      "tipo": "grafico",
      "titulo": "...",       # opcional
      "subtitulo": "...",    # opcional
      "nota": "...",         # opcional
      "figura": {            # Plotly Figure JSON
        "data": [...],
        "layout": {...}
      }
    }
    """
    global _chart_counter
    _chart_counter += 1
    div_id = f"chart_{_chart_counter}"

    nota       = sec.get("nota", "")
    fig_json_raw = sec.get("figura", {"data": [], "layout": {}})
    try:
        fig_json_str = prepare_figure_json(fig_json_raw)
    except Exception as e:
        return f'<div class="card"><p style="color:var(--red);font-size:12px">Erro ao processar figura: {esc(str(e))}</p></div>'

    nota_html = f'<p style="font-size:10.5px;color:var(--ink-4);margin-top:6px;line-height:1.45">{esc(nota)}</p>' if nota else ""

    return f"""
  <div class="card">
    {_card_title_html(sec, "grafico")}
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


# ─── FOOTER ──────────────────────────────────────────────────────────────────

def render_footer(meta: dict) -> str:
    data   = esc(get_generation_timestamp(meta))
    versao = esc(meta.get("versao", ""))
    versao_html = f" · {versao}" if versao else ""
    fontes_list = meta.get("fontes", [])
    fontes_html = ", ".join(render_code(f) for f in fontes_list) if fontes_list else "—"
    return f"""
  <footer class="footer">
    <div class="footer-left">
      Gerado em <strong>{data}</strong>{versao_html}<br>
      DIID · Divisão de Inovação e Inteligência de Dados — SUBHUE / SMS-Rio
    </div>
    <div class="footer-right">
      Fontes: {fontes_html}<br>
      Documentação técnica · uso interno
    </div>
  </footer>"""


# ─── DISPATCH ─────────────────────────────────────────────────────────────────

SECAO_RENDERERS = {
    "visao_geral":   render_visao_geral,
    "dependencias":  render_dependencias,
    "colunas":       render_colunas,
    "especificacao": render_especificacao,
    "observacoes":   render_observacoes,
    "changelog":     render_changelog,
    "texto":         render_texto,
    "tabela":        render_tabela,
    "metrica":       render_metrica,
    "grafico":       render_grafico,
}


# ─── MONTAGEM DO HTML ─────────────────────────────────────────────────────────

def gerar_html(dados: dict, plotly_js: str) -> str:
    global _chart_counter
    _chart_counter = 0

    meta   = dados.get("meta", {})
    secoes = dados.get("secoes", [])
    titulo = esc(meta.get("titulo", "Documentação Técnica SUBHUE"))

    toc_html  = render_toc(secoes)
    body_parts = [render_header(meta), toc_html]

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
            "titulo": "fat_atendimento_emergencia_agg_timed",
            "subtitulo": "Model incremental — atendimentos de emergência agregados por janela de 30 minutos",
            "versao": "v1.2",
            "autores": ["Moscarde"],
            "periodo": "Vigente desde 05/2026",
            "fontes": ["raw_timed_dtw.fat_atendimento", "raw_timed_dtw.fat_boletim"],
            "data_hora_geracao": "2026-06-18T14:30:00Z"
        },
        "secoes": [
            {
                "tipo": "visao_geral",
                "descricao": "Agrega atendimentos de emergência em janelas de 30 minutos por estabelecimento e tipo de atendimento. Fonte primária para análises de fluxo intradiário na camada gold.",
                "detalhes": [
                    "Grain: dh_janela_30min × cd_estabelecimento × tipo_atendimento.",
                    "Strategy: incremental delete+insert por dh_janela_30min::date.",
                    "Cobre todos os tipos de saída — internação, alta ambulatorial, transferência."
                ]
            },
            {
                "tipo": "dependencias",
                "upstream": [
                    {"nome": "raw_timed_dtw.fat_atendimento", "descricao": "Atendimentos individuais com timestamp completo"},
                    {"nome": "raw_timed_dtw.fat_boletim",     "descricao": "Enriquecimento de tipo de atendimento"}
                ],
                "downstream": [
                    {"nome": "gold_timed.vw_censo_atendimento",     "descricao": "View principal de consumo"},
                    {"nome": "gold_timed.fat_paciente_agg_mes",     "descricao": "Agregação mensal de pacientes"}
                ]
            },
            {
                "tipo": "especificacao",
                "subtitulo": "fat_atendimento_emergencia_agg_timed",
                "campos": [
                    {"label": "Fonte",       "valor": {"code": "raw_timed_dtw.fat_atendimento"}},
                    {"label": "Grain",       "valor": "dh_janela_30min × cd_estabelecimento × tipo_atendimento"},
                    {"label": "Bucketing",   "valor": {"code": "date_trunc('hour', dh_atendimento) + floor(extract(minute from dh_atendimento)/30) * interval '30 min'"}},
                    {"label": "Strategy",    "valor": "incremental — delete+insert por dh_janela_30min::date"},
                    {"label": "Unique key",  "valor": {"code": "pk_agg_gid"}},
                    {"label": "Partição",    "valor": "dh_janela_30min::date — janela de 2 dias de lookback"}
                ]
            },
            {
                "tipo": "colunas",
                "items": [
                    {"nome": "pk_agg_gid",          "tipo_dado": "UUID",                     "pk": True,  "obrigatorio": True,  "descricao": "Chave primária gerada via uuid_generate_v4()"},
                    {"nome": "dh_janela_30min",      "tipo_dado": "TIMESTAMP",                             "obrigatorio": True,  "incrementa": True, "descricao": "Início da janela de 30 minutos — chave de controle incremental"},
                    {"nome": "cd_estabelecimento",   "tipo_dado": "VARCHAR",                               "obrigatorio": True,  "descricao": "Código do estabelecimento de saúde"},
                    {"nome": "tipo_atendimento",     "tipo_dado": "VARCHAR",                               "obrigatorio": False, "descricao": "Tipo do atendimento (INTERNACAO, AMBULATORIO, EMERGENCIA)"},
                    {"nome": "qtd_atendimentos",     "tipo_dado": "INTEGER",                               "obrigatorio": False, "descricao": "Contagem de atendimentos abertos na janela"},
                    {"nome": "qtd_saidas",           "tipo_dado": "INTEGER",                               "obrigatorio": False, "descricao": "Contagem de saídas registradas na janela"},
                    {"nome": "dh_carga",             "tipo_dado": "TIMESTAMP WITH TIME ZONE",              "obrigatorio": True,  "descricao": "Timestamp de carga do registro no DW"}
                ]
            },
            {
                "tipo": "observacoes",
                "items": [
                    {"tipo": "warn",  "titulo": "Alta Ambulatorial representa 80–98% do volume real de saídas em UPAs.", "texto": "Deve ser filtrada por tipo_atendimento para equivalência com fat_censo_estatistica."},
                    {"tipo": "limit", "titulo": "Lookback de 2 dias pode perder atualizações tardias de registros.", "texto": "Ajustar para 7 dias em ambientes com alta latência de extração."},
                    {"tipo": "info",  "titulo": "Perfil horário varia significativamente por tipo de unidade.", "texto": "Hospital pico às 13h; CER pico às 16–19h; UPA sem padrão definido."}
                ]
            },
            {
                "tipo": "changelog",
                "items": [
                    {"versao": "v1.2", "data": "12/06/2026", "autor": "Moscarde", "tipo": "feat",     "descricao": "Adicionado campo tipo_atendimento como dimensão do grain"},
                    {"versao": "v1.1", "data": "20/05/2026", "autor": "Moscarde", "tipo": "fix",      "descricao": "Corrigido bucketing para fuso horário UTC-3"},
                    {"versao": "v1.0", "data": "01/05/2026", "autor": "Moscarde", "tipo": "feat",     "descricao": "Criação inicial do model"}
                ]
            }
        ]
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera documentação técnica HTML SUBHUE a partir de um arquivo JSON."
    )
    parser.add_argument("json_input", nargs="?",
        help="Arquivo JSON de dados. Se omitido, gera schema_exemplo_doc.json.")
    parser.add_argument("-o", "--output", default="data/reports/documentacao.html",
        help="Arquivo HTML de saída (padrão: data/reports/documentacao.html)")
    parser.add_argument("--exemplo", action="store_true",
        help="Gera schema_exemplo_doc.json e sai.")

    args = parser.parse_args()

    if args.exemplo or args.json_input is None:
        exemplo = schema_exemplo()
        out_path = Path("schema_exemplo_doc.json")
        out_path.write_text(json.dumps(exemplo, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ schema_exemplo_doc.json gerado em {out_path.resolve()}")
        if args.json_input is None:
            print("\nUso: python gerador_documentacao_subhue.py schema_exemplo_doc.json -o data/reports/doc.html")
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

    tem_graficos = any(s.get("tipo") == "grafico" for s in dados.get("secoes", []))
    if tem_graficos:
        print("Carregando Plotly.js...")
        plotly_js = _get_plotly_js()
    else:
        plotly_js = ""

    print("Gerando HTML...")
    html = gerar_html(dados, plotly_js)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    size_kb = output_path.stat().st_size / 1024
    print(f"✓ Documentação gerada: {output_path.resolve()} ({size_kb:.0f}KB)")


if __name__ == "__main__":
    main()
