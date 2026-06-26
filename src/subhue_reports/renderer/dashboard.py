"""
Dashboard interativo single-file HTML — Plotly + vanilla JS.

Tipos de painel:
    metrica   stat box com agregação (soma/media/contagem/max/min)
    grafico   gráfico Plotly reativo
    tabela    tabela filtrável com scroll

Filtros:
    select    dropdown com opções predefinidas
"""

import json
import logging
from pathlib import Path

from subhue_reports.renderer._meta import ensure_generation_timestamp, get_generation_timestamp
from subhue_reports.renderer._plotly import PLOTLY_LAYOUT_DEFAULTS, PLOTLY_PALETTE

logger = logging.getLogger(__name__)

_LOGO_PATH = Path(__file__).with_name("diid_vertical_fix.svg")

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 13px; line-height: 1.55; color: #1e293b;
  background: #f0ede8; -webkit-font-smoothing: antialiased;
}
:root {
  --navy: #1a3a5c; --navy-mid: #2b5484;
  --ink: #1e293b; --ink-2: #334155; --ink-3: #475569; --ink-4: #64748b; --ink-5: #94a3b8;
  --surface: #ffffff; --surface-2: #f8f7f4;
  --border: #ddd9d2; --border-light: #eeebe6;
  --green: #15803d; --green-bg: #dcfce7;
  --red: #dc2626; --red-bg: #fee2e2;
  --yellow: #a16207; --yellow-bg: #fef9c3;
}
.page { max-width: 1280px; margin: 0 auto; padding: 28px 24px 48px; }
.header { display: flex; border: 1px solid var(--border); border-radius: 4px;
  overflow: hidden; margin-bottom: 16px; background: var(--surface);
  box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.header-rail { background: var(--surface); padding: 18px 16px; display: flex;
  align-items: center; justify-content: center; min-width: 150px; flex-shrink: 0; }
.header-rail-logo { width: 88px; max-width: 100%; }
.header-rail-logo svg { display: block; width: 100%; height: auto; }
.header-main { background: var(--navy); padding: 20px 24px; flex: 1;
  display: flex; flex-direction: column; justify-content: center; }
.header-label { font-size: 9px; font-weight: 700; letter-spacing: .14em;
  text-transform: uppercase; color: rgba(255,255,255,.65); margin-bottom: 4px; }
.header-title { font-family: Georgia, 'Times New Roman', serif; font-size: 20px;
  font-weight: normal; color: #fff; line-height: 1.3; }
.header-subtitle { font-size: 12px; color: rgba(255,255,255,.78); margin-top: 4px; }
.dash-filter-bar { background: var(--surface); border: 1px solid var(--border);
  border-radius: 4px; padding: 12px 16px; margin-bottom: 16px;
  display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end;
  box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.dash-filter-group { display: flex; flex-direction: column; gap: 4px; }
.dash-filter-label { font-size: 10px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: var(--ink-4); }
.dash-filter-group select { border: 1px solid var(--border); border-radius: 3px;
  padding: 5px 28px 5px 10px; font-size: 12px; color: var(--ink);
  background: var(--surface); cursor: pointer; min-width: 160px;
  appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2364748b'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 10px center; }
.dash-filter-group select:focus { outline: 2px solid var(--navy-mid); outline-offset: 1px; }
.dash-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }
.dash-span-12 { grid-column: span 12; }
.dash-span-6  { grid-column: span 6; }
.dash-span-4  { grid-column: span 4; }
.dash-span-3  { grid-column: span 3; }
@media (max-width: 900px) {
  .dash-span-6, .dash-span-4, .dash-span-3 { grid-column: span 12; }
}
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 4px;
  padding: 16px 18px; box-shadow: 0 1px 2px rgba(0,0,0,.04); min-width: 0; }
.card-title { font-size: 10px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: var(--ink-4);
  padding-bottom: 10px; margin-bottom: 12px; border-bottom: 1px solid var(--border-light); }
.dash-metrica { display: flex; flex-direction: column; align-items: flex-start;
  padding: 8px 0 4px; }
.dash-metrica-valor { font-size: 34px; font-weight: 700; line-height: 1;
  color: var(--navy); letter-spacing: -.02em; margin-top: 4px;
  font-variant-numeric: tabular-nums; transition: opacity .15s; }
.dash-metrica-sublabel { font-size: 10px; color: var(--ink-5); margin-top: 6px; }
.table-scroll { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
.table-scroll table { min-width: max-content; }
thead tr { background: var(--surface-2); }
th { font-size: 10px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase;
  color: var(--ink-4); padding: 8px 10px; text-align: left;
  border-bottom: 1px solid var(--border); white-space: nowrap; }
td { padding: 7px 10px; color: var(--ink-2); border-bottom: 1px solid var(--border-light);
  vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:nth-child(even) { background: #fafaf8; }
.footer { margin-top: 28px; padding-top: 14px; border-top: 1px solid var(--border);
  display: flex; justify-content: space-between; font-size: 10px; color: var(--ink-5); }
.dash-texto { font-size: 12px; color: var(--ink-3); line-height: 1.7; }
.dash-texto p + p { margin-top: 6px; }
"""

# Static JS — all dynamic values injected before this block
_STATIC_JS = r"""
function filtrar(dataset, filtrosAtivos) {
  const rows = DADOS[dataset] || [];
  if (!filtrosAtivos || !filtrosAtivos.length) return rows;
  return rows.filter(row => filtrosAtivos.every(fid => {
    const val = estado[fid];
    if (!val || val === '__todos__') return true;
    const fCfg = CONFIG.filtros.find(f => f.id === fid);
    if (!fCfg) return true;
    if (row[fCfg.campo] == null) return true;  // coluna ausente: filtro não se aplica a este dataset
    return String(row[fCfg.campo]) === String(val);
  }));
}

function computeAgr(rows, campo, agr) {
  const vals = rows.map(r => Number(r[campo])).filter(v => !isNaN(v));
  if (!vals.length) return null;
  switch (agr) {
    case 'soma':     return vals.reduce((a, b) => a + b, 0);
    case 'media':    return vals.reduce((a, b) => a + b, 0) / vals.length;
    case 'max':      return Math.max(...vals);
    case 'min':      return Math.min(...vals);
    case 'contagem': return vals.length;
    default:         return vals.length;
  }
}

function fmt(val, formato) {
  if (val == null) return '—';
  switch (formato) {
    case 'pct':     return val.toFixed(1) + '%';
    case 'numero':  return Math.round(val).toLocaleString('pt-BR');
    case 'inteiro': return String(Math.round(val));
    case 'decimal': return val.toFixed(2);
    default:        return String(val);
  }
}

function buildTraces(painel, rows) {
  if (painel.chart_type === 'pie' || painel.chart_type === 'donut') {
    return [{
      type: 'pie',
      labels: rows.map(r => r[painel.x]),
      values: rows.map(r => Number(r[painel.y])),
      hole: painel.chart_type === 'donut' ? 0.4 : 0,
      marker: { colors: PLOTLY_PALETTE },
    }];
  }
  const isBarH = painel.chart_type === 'bar_h';
  const type = painel.chart_type === 'line' ? 'scatter' : 'bar';
  const mode = painel.chart_type === 'line' ? 'lines+markers' : undefined;
  const orientation = isBarH ? 'h' : undefined;

  if (!painel.agrupar_por) {
    const xKey = isBarH ? painel.y : painel.x;
    const yKey = isBarH ? painel.x : painel.y;
    const trace = {
      type, x: rows.map(r => r[xKey]), y: rows.map(r => Number(r[yKey])),
    };
    if (mode) trace.mode = mode;
    if (orientation) trace.orientation = orientation;
    return [trace];
  }

  const grupos = [...new Set(rows.map(r => String(r[painel.agrupar_por])))].sort();
  return grupos.map(g => {
    const gr = rows.filter(r => String(r[painel.agrupar_por]) === g);
    const trace = {
      type, name: g,
      x: gr.map(r => r[painel.x]), y: gr.map(r => Number(r[painel.y])),
    };
    if (mode) trace.mode = mode;
    return trace;
  });
}

function addBarLabels(traces, barmode) {
  const pos = barmode === 'stack' ? 'inside' : 'outside';
  return traces.map(t => {
    if (t.type === 'bar' && !t.texttemplate && !t.text) {
      const tmpl = t.orientation === 'h' ? '%{x}' : '%{y}';
      return Object.assign({}, t, { texttemplate: tmpl, textposition: pos });
    }
    return t;
  });
}

function buildLayout(painel) {
  const layout = JSON.parse(JSON.stringify(PLOTLY_DEFAULTS));
  delete layout.title;
  layout.height = painel.altura || 280;
  if (painel.barmode) layout.barmode = painel.barmode;
  if (painel.layout_override) Object.assign(layout, painel.layout_override);
  return layout;
}

function renderMetrica(p, rows) {
  const el = document.getElementById('val_' + p.id);
  if (!el) return;
  const val = computeAgr(rows, p.campo, p.agregacao);
  el.textContent = fmt(val, p.formato);
}

function renderGrafico(p, rows) {
  const el = document.getElementById('chart_' + p.id);
  if (!el) return;
  const barmode = p.barmode || 'group';
  let traces = buildTraces(p, rows);
  if (p.chart_type !== 'pie' && p.chart_type !== 'donut') {
    traces = addBarLabels(traces, barmode);
  }
  const layout = buildLayout(p);
  Plotly.react(el, traces, layout, PLOTLY_CONFIG);
}

function renderTabela(p, rows) {
  const tbody = document.getElementById('tbody_' + p.id);
  if (!tbody) return;
  tbody.innerHTML = rows.map(row => {
    const cells = p.colunas.map(col => '<td>' + fmt(row[col.campo], col.formato) + '</td>');
    return '<tr>' + cells.join('') + '</tr>';
  }).join('');
}

function renderPainel(p) {
  if (p.tipo === 'texto') return;
  const rows = filtrar(p.dataset, p.filtros_ativos);
  if (p.tipo === 'metrica') renderMetrica(p, rows);
  else if (p.tipo === 'grafico') renderGrafico(p, rows);
  else if (p.tipo === 'tabela') renderTabela(p, rows);
}

function atualizar() {
  CONFIG.paineis.forEach(p => renderPainel(p));
}

(function init() {
  CONFIG.filtros.forEach(f => {
    const el = document.getElementById('filtro_' + f.id);
    estado[f.id] = el ? el.value : null;
    if (el) {
      el.addEventListener('change', e => {
        estado[e.target.dataset.filtroId] = e.target.value;
        atualizar();
      });
    }
  });
  atualizar();
})();
"""


def _diid_logo() -> str:
    if not _LOGO_PATH.exists():
        return ""
    return f'<div class="header-rail-logo">{_LOGO_PATH.read_text()}</div>'


def _largura_span(largura: str) -> str:
    spans = {"completo": "12", "metade": "6", "terco": "4", "quarto": "3"}
    return "dash-span-" + spans.get(largura, "12")


def render_filtro(f: dict) -> str:
    fid = f["id"]
    label = f.get("label", fid)
    opcoes = f.get("opcoes", [])
    todos = f.get("todos_label", "Todos")
    options_html = f'<option value="__todos__">{todos}</option>'
    options_html += "".join(f'<option value="{o}">{o}</option>' for o in opcoes)
    return (
        f'<div class="dash-filter-group">'
        f'<label class="dash-filter-label" for="filtro_{fid}">{label}</label>'
        f'<select id="filtro_{fid}" class="dash-filtro" data-filtro-id="{fid}">'
        f"{options_html}</select></div>"
    )


def render_filtro_bar(filtros: list[dict]) -> str:
    if not filtros:
        return ""
    inner = "".join(render_filtro(f) for f in filtros)
    return f'<div class="dash-filter-bar">{inner}</div>'


def render_painel_metrica(p: dict) -> str:
    span = _largura_span(p.get("largura", "quarto"))
    pid = p["id"]
    titulo = p.get("titulo", "")
    sublabel = p.get("sublabel", "")
    sub_html = f'<div class="dash-metrica-sublabel">{sublabel}</div>' if sublabel else ""
    return (
        f'<div class="card {span}">'
        f'<div class="card-title">{titulo}</div>'
        f'<div class="dash-metrica">'
        f'<div class="dash-metrica-valor" id="val_{pid}">&mdash;</div>'
        f"{sub_html}</div></div>"
    )


def render_painel_grafico(p: dict) -> str:
    span = _largura_span(p.get("largura", "completo"))
    pid = p["id"]
    titulo = p.get("titulo", "")
    altura = p.get("altura", 280)
    return (
        f'<div class="card {span}">'
        f'<div class="card-title">{titulo}</div>'
        f'<div id="chart_{pid}" style="height:{altura}px"></div>'
        f"</div>"
    )


def render_painel_tabela(p: dict) -> str:
    span = _largura_span(p.get("largura", "completo"))
    pid = p["id"]
    titulo = p.get("titulo", "")
    colunas = p.get("colunas", [])
    headers = "".join(f'<th>{c.get("label", c["campo"])}</th>' for c in colunas)
    return (
        f'<div class="card {span}">'
        f'<div class="card-title">{titulo}</div>'
        f'<div class="table-scroll"><table>'
        f"<thead><tr>{headers}</tr></thead>"
        f'<tbody id="tbody_{pid}"></tbody>'
        f"</table></div></div>"
    )


def render_painel_texto(p: dict) -> str:
    span = _largura_span(p.get("largura", "completo"))
    titulo = p.get("titulo", "")
    titulo_html = f'<div class="card-title">{titulo}</div>' if titulo else ""
    linhas_html = "".join(f"<p>{linha}</p>" for linha in p.get("linhas", []))
    return (
        f'<div class="card {span}">'
        f"{titulo_html}"
        f'<div class="dash-texto">{linhas_html}</div>'
        f"</div>"
    )


def render_painel(p: dict) -> str:
    tipo = p.get("tipo", "")
    if tipo == "metrica":
        return render_painel_metrica(p)
    if tipo == "grafico":
        return render_painel_grafico(p)
    if tipo == "tabela":
        return render_painel_tabela(p)
    if tipo == "texto":
        return render_painel_texto(p)
    return f'<div class="card dash-span-12"><em>Tipo de painel desconhecido: {tipo}</em></div>'


def _dashboard_js(dados_raw: dict, filtros: list[dict], paineis: list[dict]) -> str:
    dados_json = json.dumps(dados_raw, ensure_ascii=False, default=str)
    config_json = json.dumps({"filtros": filtros, "paineis": paineis}, ensure_ascii=False)
    palette_json = json.dumps(PLOTLY_PALETTE)
    defaults_json = json.dumps(PLOTLY_LAYOUT_DEFAULTS, ensure_ascii=False)
    plotly_cfg = json.dumps({
        "responsive": True,
        "displayModeBar": True,
        "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
        "displaylogo": False,
    })
    return (
        f"const DADOS = {dados_json};\n"
        f"const CONFIG = {config_json};\n"
        f"const PLOTLY_DEFAULTS = {defaults_json};\n"
        f"const PLOTLY_PALETTE = {palette_json};\n"
        f"const PLOTLY_CONFIG = {plotly_cfg};\n"
        f"const estado = {{}};\n"
        + _STATIC_JS
    )


def render_dashboard(dados: dict, plotly_js: str = "") -> str:
    """Gera HTML single-file de dashboard interativo a partir do JSON estruturado."""
    ensure_generation_timestamp(dados)
    meta = dados.get("meta", {})
    titulo = meta.get("titulo", "Dashboard")
    subtitulo = meta.get("subtitulo", "")
    gerado_em = get_generation_timestamp(meta)

    filtros: list[dict] = dados.get("filtros", [])
    dados_raw: dict = dados.get("dados", {})
    paineis: list[dict] = dados.get("paineis", [])

    logo_html = _diid_logo()
    sub_html = f'<div class="header-subtitle">{subtitulo}</div>' if subtitulo else ""
    panels_html = "\n".join(render_painel(p) for p in paineis)

    if plotly_js:
        plotly_tag = f"<script>{plotly_js}</script>"
    else:
        plotly_tag = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'

    js_block = _dashboard_js(dados_raw, filtros, paineis)

    logger.debug("render_dashboard: %d paineis, %d filtros", len(paineis), len(filtros))

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titulo}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">

<div class="header">
  <div class="header-rail">{logo_html}</div>
  <div class="header-main">
    <div class="header-label">Dashboard</div>
    <div class="header-title">{titulo}</div>
    {sub_html}
  </div>
</div>

{render_filtro_bar(filtros)}

<div class="dash-grid">
{panels_html}
</div>

<div class="footer">
  <span>SUBHUE &mdash; Núcleo de Dados</span>
  <span>Gerado em {gerado_em}</span>
</div>
</div>

{plotly_tag}
<script>
{js_block}
</script>
</body>
</html>"""


if __name__ == "__main__":
    import argparse
    import sys

    from subhue_reports.renderer._plotly import get_plotly_js
    from subhue_reports.renderer.sections import assemble_report

    parser = argparse.ArgumentParser(description="Gera HTML de dashboard a partir de JSON")
    parser.add_argument("source", help="JSON ou diretório de seções")
    parser.add_argument("-o", "--output", help="Arquivo HTML de saída (opcional)")
    args = parser.parse_args()

    src = Path(args.source)
    if src.is_dir():
        dados = assemble_report(src)
        out = Path(args.output) if args.output else src.parent / f"{src.name}.html"
    else:
        dados = json.loads(src.read_text())
        out = Path(args.output) if args.output else src.with_suffix(".html")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_dashboard(dados, get_plotly_js()))
    print(f"dashboard: {out}", file=sys.stderr)
