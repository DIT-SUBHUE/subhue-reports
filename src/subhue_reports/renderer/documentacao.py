"""
Renderer de documentação técnica HTML self-contained.

Tipos de seção:
    visao_geral     descrição do artefato e propósito
    dependencias    upstream (fontes) e downstream (consumers)
    colunas         campos com tipo, constraints e descrição
    especificacao   configuração técnica em campos label/valor
    observacoes     pontos de atenção, limitações, comportamentos
    changelog       histórico de versões
    texto           bloco narrativo
    tabela          tabela genérica com colunas tipadas
    metrica         grid de indicadores em destaque
    grafico         Plotly Figure JSON
"""

import logging
from collections.abc import Callable
from pathlib import Path

from subhue_reports.renderer._html import (
    esc,
    render_badge_label,
    render_cell,
    render_code,
)
from subhue_reports.renderer._meta import ensure_generation_timestamp, get_generation_timestamp
from subhue_reports.renderer._plotly import (
    BAR_SPLIT_THRESHOLD,
    bar_x_categories,
    get_plotly_js,
    prepare_figure_json,
    split_bar_traces,
)

logger = logging.getLogger(__name__)

ICO_MAP = {
    "ok": "✅",
    "warn": "⚠️",
    "info": "ℹ️",
    "limit": "🔲",
    "time": "🕐",
    "error": "❌",
}

CHANGELOG_TIPO: dict[str, tuple[str, str, str]] = {
    "feat":     ("#dbeafe", "#1d4ed8", "FEAT"),
    "fix":      ("#dcfce7", "#15803d", "FIX"),
    "refactor": ("#ede9fe", "#6d28d9", "REFACTOR"),
    "break":    ("#fee2e2", "#dc2626", "BREAKING"),
    "docs":     ("#f1f5f9", "#475569", "DOCS"),
    "chore":    ("#f1f5f9", "#475569", "CHORE"),
}

_TITULO_PADRAO: dict[str, str] = {
    "visao_geral":   "Visão Geral",
    "dependencias":  "Dependências",
    "colunas":       "Colunas",
    "especificacao": "Especificação Técnica",
    "observacoes":   "Observações",
    "changelog":     "Histórico de Mudanças",
}

CSS = """
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
  --purple: #6d28d9; --purple-bg: #ede9fe;
  --blue: #1d4ed8; --blue-bg: #dbeafe;
}
.page { max-width: 1200px; margin: 0 auto; padding: 28px 24px 48px; }
.header { display: flex; border: 1px solid var(--border); border-radius: 4px;
  overflow: hidden; margin-bottom: 20px; background: var(--surface);
  box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.header-rail { background: var(--surface); padding: 18px 16px; display: flex;
  align-items: center; justify-content: center; min-width: 150px; flex-shrink: 0; }
.header-rail-logo { width: 88px; max-width: 100%; }
.header-rail-logo svg { display: block; width: 100%; height: auto; }
.header-main { background: var(--navy); padding: 22px 24px; flex: 1;
  display: flex; flex-direction: column; justify-content: space-between; }
.header-label { font-size: 9px; font-weight: 700; letter-spacing: .14em;
  text-transform: uppercase; color: rgba(255,255,255,.72); margin-bottom: 6px; }
.header-title { font-family: Georgia, 'Times New Roman', serif; font-size: 20px;
  font-weight: normal; color: #fff; line-height: 1.3; margin-bottom: 4px; }
.header-subtitle { font-size: 12px; color: rgba(255,255,255,.82); margin-bottom: 16px; }
.header-meta { display: flex; gap: 20px; flex-wrap: wrap;
  padding-top: 14px; border-top: 1px solid rgba(255,255,255,.18); }
.header-meta-item { font-size: 11px; color: rgba(255,255,255,.78); }
.header-meta-item strong { color: #fff; font-weight: 600; }
.header-meta-item code { background: rgba(255,255,255,.12); color: #fff; }
.toc { background: var(--surface); border: 1px solid var(--border);
  border-left: 3px solid var(--navy-mid); border-radius: 4px;
  padding: 14px 18px; margin-bottom: 20px; font-size: 11.5px; }
.toc-title { font-size: 9px; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: var(--ink-4); margin-bottom: 10px; }
.toc ol { padding-left: 18px; }
.toc li { color: var(--ink-3); line-height: 2; }
.toc a { color: var(--navy-mid); text-decoration: none; }
.toc a:hover { text-decoration: underline; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 4px;
  padding: 18px 20px; margin-bottom: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.04); min-width: 0; }
.card-title { font-size: 10px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: var(--ink-4);
  padding-bottom: 12px; margin-bottom: 14px; border-bottom: 1px solid var(--border-light);
  display: flex; justify-content: space-between; align-items: center; }
.card-title span { color: var(--ink-5); font-weight: 400;
  letter-spacing: 0; text-transform: none; font-size: 10px; }
.callout { background: #eef4fd; border-left: 3px solid var(--navy-mid);
  padding: 10px 14px; border-radius: 0 3px 3px 0;
  font-size: 12px; color: #1e3a5a; margin-bottom: 12px; line-height: 1.6; }
.callout strong { font-weight: 700; }
.table-scroll { width: 100%; max-width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
.table-scroll table { min-width: max-content; }
thead tr { background: var(--surface-2); }
th { font-size: 10px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase;
  color: var(--ink-4); padding: 8px 10px; text-align: left;
  border-bottom: 1px solid var(--border); white-space: nowrap; }
th.n, td.n { text-align: right; font-variant-numeric: tabular-nums; }
td { padding: 7px 10px; color: var(--ink-2); border-bottom: 1px solid var(--border-light); vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:nth-child(even) { background: #fafaf8; }
.badge { display: inline-block; font-size: 10px; font-weight: 700;
  padding: 2px 7px; border-radius: 3px; letter-spacing: .03em; }
.hi { background: var(--green-bg); color: var(--green); }
.md { background: var(--yellow-bg); color: var(--yellow); }
.lo { background: var(--red-bg); color: var(--red); }
.na { background: var(--surface-2); color: var(--ink-4); }
.ex { background: var(--purple-bg); color: var(--purple); }
.tag { display: inline-block; font-size: 10px; font-weight: 700;
  padding: 2px 8px; border-radius: 10px; letter-spacing: .02em; white-space: nowrap; }
code { background: #e8e4f8; color: #3730a3;
  font-family: 'JetBrains Mono', 'Courier New', monospace;
  font-size: 10.5px; padding: 1px 5px; border-radius: 3px; }
.metrics-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
.stat-box { text-align: center; padding: 16px 12px;
  border: 1px solid var(--border-light); border-radius: 4px; background: var(--surface-2); }
.stat-num { font-size: 28px; font-weight: 700; line-height: 1.1;
  font-variant-numeric: tabular-nums; letter-spacing: -.01em; }
.stat-label { font-size: 11px; color: var(--ink-4); margin-top: 4px; line-height: 1.4; }
.stat-sub { font-size: 10px; color: var(--ink-5); margin-top: 2px; }
.prose { font-size: 12px; color: var(--ink-3); line-height: 1.7; }
.prose p + p { margin-top: 10px; }
.prose strong { color: var(--ink-2); font-weight: 600; }
.ilist { list-style: none; display: flex; flex-direction: column; gap: 10px; }
.ilist li { display: flex; gap: 10px; align-items: flex-start;
  font-size: 12px; color: var(--ink-2); line-height: 1.5; }
.ico { flex-shrink: 0; width: 18px; text-align: center; font-size: 13px; margin-top: 1px; }
.spec { background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 4px; padding: 14px 16px; }
.spec-title { font-size: 10px; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;
  color: #0369a1; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #bae6fd; }
.spec-row { display: flex; gap: 12px; font-size: 12px; color: #0c4a6e;
  padding: 5px 0; border-bottom: 1px solid #e0f2fe; align-items: baseline; }
.spec-row:last-of-type { border-bottom: none; }
.spec-label { font-size: 10px; font-weight: 700; letter-spacing: .05em;
  text-transform: uppercase; color: #0369a1; min-width: 110px; flex-shrink: 0; }
.spec-note { font-size: 10.5px; color: #0c4a6e; margin-top: 10px;
  padding-top: 8px; border-top: 1px solid #bae6fd; }
.dep-section { font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .07em; padding: 6px 0 4px; border-bottom: 1px solid var(--border-light);
  margin-bottom: 6px; }
.dep-section.up { color: var(--blue); }
.dep-section.down { color: var(--green); }
.dep-list { list-style: none; display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; }
.dep-item { display: flex; gap: 8px; align-items: baseline; font-size: 12px; }
.dep-desc { font-size: 11px; color: var(--ink-4); }
.col-desc { font-size: 11.5px; color: var(--ink-3); }
.footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px; }
.footer-left { font-size: 10px; color: var(--ink-5); line-height: 1.6; }
.footer-right { font-size: 10px; color: var(--ink-5); text-align: right; line-height: 1.6; }
@media print {
  body { background: #fff; } .page { padding: 0; }
  .card { box-shadow: none; break-inside: avoid; }
  .js-plotly-plot .plotly-notifier, .modebar { display: none !important; }
}
"""

_LOGO_PATH = Path(__file__).with_name("diid_vertical_fix.svg")


def _diid_logo() -> str:
    if not _LOGO_PATH.exists():
        return ""
    return _LOGO_PATH.read_text(encoding="utf-8")


def _nota_html(nota: str) -> str:
    if not nota:
        return ""
    style = (
        "font-size:11px;color:var(--ink-4);margin-top:10px;"
        "padding-top:8px;border-top:1px solid var(--border-light)"
    )
    return f'<p style="{style}">{esc(nota)}</p>'


def _card_title_html(sec: dict, tipo: str) -> str:
    titulo = esc(sec.get("titulo") or _TITULO_PADRAO.get(tipo, ""))
    subtitulo = esc(sec.get("subtitulo", ""))
    anchor = sec.get("_anchor", "")
    anchor_attr = f' id="{anchor}"' if anchor else ""
    sub_html = f"<span>· {subtitulo}</span>" if subtitulo else ""
    return f'<div class="card-title"{anchor_attr}>{titulo} {sub_html}</div>'


def render_header(meta: dict) -> str:
    data = esc(get_generation_timestamp(meta))
    meta_items = []
    if meta.get("versao"):
        meta_items.append(f'<div class="header-meta-item"><strong>Versão:</strong> {esc(meta["versao"])}</div>')
    if meta.get("autores"):
        autores = meta["autores"]
        autores_str = ", ".join(autores) if isinstance(autores, list) else autores
        meta_items.append(f'<div class="header-meta-item"><strong>Autores:</strong> {esc(autores_str)}</div>')
    if meta.get("periodo"):
        meta_items.append(f'<div class="header-meta-item"><strong>Vigência:</strong> {esc(meta["periodo"])}</div>')
    if meta.get("fontes"):
        fontes = ", ".join(render_code(f) for f in meta["fontes"])
        meta_items.append(f'<div class="header-meta-item"><strong>Fontes:</strong> {fontes}</div>')
    meta_items.append(f'<div class="header-meta-item"><strong>Gerado em:</strong> {data}</div>')

    return f"""
  <header class="header">
    <div class="header-rail">
      <div class="header-rail-logo" aria-label="DIID">{_diid_logo()}</div>
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


def render_toc(secoes: list[dict]) -> str:
    """Gera TOC e injeta _anchor em cada seção com título."""
    itens = []
    counter = 0
    for sec in secoes:
        titulo = sec.get("titulo") or _TITULO_PADRAO.get(sec.get("tipo", ""), "")
        if not titulo:
            continue
        counter += 1
        anchor = f"sec-{counter}"
        sec["_anchor"] = anchor
        itens.append(f'<li><a href="#{anchor}">{esc(titulo)}</a></li>')
    if not itens:
        return ""
    return f"""
  <nav class="toc">
    <div class="toc-title">Conteúdo</div>
    <ol>{"".join(itens)}</ol>
  </nav>"""


def render_footer(meta: dict) -> str:
    data = esc(get_generation_timestamp(meta))
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


def render_visao_geral(sec: dict) -> str:
    descricao = esc(sec.get("descricao", ""))
    detalhes = sec.get("detalhes", [])
    detalhes_html = ""
    if detalhes:
        itens = "".join(f"<li>{esc(d)}</li>" for d in detalhes)
        style = "margin-top:10px;padding-left:18px;font-size:12px;color:var(--ink-3);line-height:1.8"
        detalhes_html = f'<ul style="{style}">{itens}</ul>'
    return f"""
  <div class="card">
    {_card_title_html(sec, "visao_geral")}
    <div class="callout">{descricao}</div>
    {detalhes_html}
  </div>"""


def _dep_list_html(items: list, css_class: str, label: str) -> str:
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


def render_dependencias(sec: dict) -> str:
    upstream = _dep_list_html(sec.get("upstream", []), "up", "▲ Upstream — fontes")
    downstream = _dep_list_html(sec.get("downstream", []), "down", "▼ Downstream — consumers")
    return f"""
  <div class="card">
    {_card_title_html(sec, "dependencias")}
    {upstream}
    {downstream}
    {_nota_html(sec.get("nota", ""))}
  </div>"""


def _coluna_row(item: dict) -> str:
    nome = esc(item.get("nome", ""))
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
    return (
        f"<tr>"
        f'<td><code>{nome}</code></td>'
        f'<td><code style="background:#f1f5f9;color:var(--ink-3)">{tipo_dado}</code></td>'
        f'<td>{" ".join(badges)}</td>'
        f'<td class="col-desc">{descricao}</td>'
        f"</tr>"
    )


def render_colunas(sec: dict) -> str:
    rows_html = "".join(_coluna_row(item) for item in sec.get("items", []))
    return f"""
  <div class="card">
    {_card_title_html(sec, "colunas")}
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Campo</th><th>Tipo</th>
            <th style="min-width:130px"></th><th>Descrição</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    {_nota_html(sec.get("nota", ""))}
  </div>"""


def _spec_row(row: dict) -> str:
    label = esc(row.get("label", ""))
    valor = row.get("valor", "")
    if isinstance(valor, dict) and "code" in valor:
        valor_html = render_code(valor["code"])
    else:
        valor_html = esc(str(valor))
    return f'<div class="spec-row"><span class="spec-label">{label}</span><span>{valor_html}</span></div>'


def render_especificacao(sec: dict) -> str:
    rows_html = "".join(_spec_row(r) for r in sec.get("campos", []))
    nota_html = f'<p class="spec-note">{esc(sec.get("nota", ""))}</p>' if sec.get("nota") else ""
    return f"""
  <div class="card">
    {_card_title_html(sec, "especificacao")}
    <div class="spec">
      {rows_html}
      {nota_html}
    </div>
  </div>"""


def render_observacoes(sec: dict) -> str:
    items_html = ""
    for item in sec.get("items", []):
        ico = ICO_MAP.get(item.get("tipo", "info"), "ℹ️")
        titulo = esc(item.get("titulo", ""))
        texto = esc(item.get("texto", ""))
        texto_html = f" {texto}" if texto else ""
        items_html += f'<li><span class="ico">{ico}</span><span><strong>{titulo}</strong>{texto_html}</span></li>'
    return f"""
  <div class="card">
    {_card_title_html(sec, "observacoes")}
    <ul class="ilist">{items_html}</ul>
  </div>"""


def _changelog_row(item: dict) -> str:
    versao = esc(item.get("versao", ""))
    data = esc(item.get("data", ""))
    autor = esc(item.get("autor", ""))
    tipo_key = item.get("tipo", "feat").lower()
    descricao = esc(item.get("descricao", ""))
    bg, fg, label = CHANGELOG_TIPO.get(tipo_key, ("#f1f5f9", "#475569", tipo_key.upper()))
    tag = f'<span class="tag" style="background:{bg};color:{fg};font-size:9px">{label}</span>'
    autor_html = f' <span style="color:var(--ink-5);font-size:10.5px">— {autor}</span>' if autor else ""
    return (
        f"<tr>"
        f'<td style="white-space:nowrap"><code>{versao}</code></td>'
        f'<td style="white-space:nowrap;color:var(--ink-4);font-size:11px">{data}</td>'
        f'<td>{tag}</td>'
        f'<td style="font-size:12px;color:var(--ink-2)">{descricao}{autor_html}</td>'
        f"</tr>"
    )


def render_changelog(sec: dict) -> str:
    rows_html = "".join(_changelog_row(item) for item in sec.get("items", []))
    return f"""
  <div class="card">
    {_card_title_html(sec, "changelog")}
    <div class="table-scroll">
      <table>
        <thead><tr><th>Versão</th><th>Data</th><th>Tipo</th><th>Mudança</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </div>"""


def render_texto(sec: dict) -> str:
    paras = "".join(f"<p>{esc(p)}</p>" for p in sec.get("paragrafos", []))
    return f"""
  <div class="card">
    {_card_title_html(sec, "texto")}
    <div class="prose">{paras}</div>
  </div>"""


def _table_ths(colunas: list[dict]) -> str:
    ths = ""
    for col in colunas:
        align = ' class="n"' if col.get("tipo") in ("numero", "badge_pct") else ""
        ths += f'<th{align}>{esc(col.get("label", ""))}</th>\n'
    return ths


def _table_rows(linhas: list, colunas: list[dict]) -> str:
    rows = ""
    for linha in linhas:
        cells = ""
        for i, val in enumerate(linha):
            col_tipo = colunas[i].get("tipo", "texto") if i < len(colunas) else "texto"
            cells += render_cell(val, col_tipo)
        rows += f"<tr>{cells}</tr>\n"
    return rows


def render_tabela(sec: dict) -> str:
    colunas = sec.get("colunas", [])
    return f"""
  <div class="card">
    {_card_title_html(sec, "tabela")}
    <div class="table-scroll">
      <table>
        <thead><tr>{_table_ths(colunas)}</tr></thead>
        <tbody>{_table_rows(sec.get("linhas", []), colunas)}</tbody>
      </table>
    </div>
    {_nota_html(sec.get("nota", ""))}
  </div>"""


def render_metrica(sec: dict) -> str:
    items_html = ""
    for item in sec.get("items", []):
        valor = esc(item.get("valor", ""))
        label = esc(item.get("label", ""))
        cor = esc(item.get("cor", "var(--ink)"))
        sub = esc(item.get("sub", ""))
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


def _chart_inner(div_id: str, fig_raw: dict) -> str:
    """Retorna div+script de um único gráfico Plotly (sem wrapper .card)."""
    try:
        fig_json_str = prepare_figure_json(fig_raw)
    except Exception as exc:
        return (
            f'<p style="color:var(--red);font-size:12px">'
            f"Erro ao processar figura: {esc(str(exc))}</p>"
        )
    return f"""
    <div id="{div_id}"></div>
    <script>
      (function() {{
        var fig = {fig_json_str};
        var config = {{
          responsive: true, displayModeBar: true,
          modeBarButtonsToRemove: ['select2d','lasso2d','autoScale2d'],
          displaylogo: false
        }};
        Plotly.newPlot("{div_id}", fig.data, fig.layout, config);
      }})();
    </script>"""


def render_grafico(sec: dict, chart_idx: int) -> str:
    fig_raw = sec.get("figura", {"data": [], "layout": {}})
    nota_html = _nota_html(sec.get("nota", ""))

    cats = bar_x_categories(fig_raw.get("data", []))
    if len(cats) > BAR_SPLIT_THRESHOLD:
        mid = len(cats) // 2
        t1, t2 = split_bar_traces(fig_raw.get("data", []), cats, mid)
        inner = (
            _chart_inner(f"chart_{chart_idx}a", {**fig_raw, "data": t1})
            + _chart_inner(f"chart_{chart_idx}b", {**fig_raw, "data": t2})
        )
        return f"""
  <div class="card">
    {_card_title_html(sec, "grafico")}
    {inner}
    {nota_html}
  </div>"""

    return f"""
  <div class="card">
    {_card_title_html(sec, "grafico")}
    {_chart_inner(f"chart_{chart_idx}", fig_raw)}
    {nota_html}
  </div>"""


SECAO_RENDERERS: dict[str, Callable] = {
    "visao_geral":   render_visao_geral,
    "dependencias":  render_dependencias,
    "colunas":       render_colunas,
    "especificacao": render_especificacao,
    "observacoes":   render_observacoes,
    "changelog":     render_changelog,
    "texto":         render_texto,
    "tabela":        render_tabela,
    "metrica":       render_metrica,
}


def _unknown_section(sec: dict) -> str:
    tipo = sec.get("tipo", "")
    return (
        f'<div class="card" style="border-color:var(--red-bg)">'
        f'<p style="color:var(--red);font-size:12px">'
        f"Tipo de seção desconhecido: <code>{esc(tipo)}</code></p></div>"
    )


def render_doc(dados: dict, plotly_js: str = "") -> str:
    """Gera HTML completo da documentação com TOC."""
    ensure_generation_timestamp(dados)
    meta = dados.get("meta", {})
    secoes = dados.get("secoes", [])
    titulo = esc(meta.get("titulo", "Documentação Técnica SUBHUE"))

    toc_html = render_toc(secoes)
    parts = [render_header(meta), toc_html]
    chart_idx = 0
    for secao in secoes:
        tipo = secao.get("tipo")
        if tipo == "grafico":
            chart_idx += 1
            parts.append(render_grafico(secao, chart_idx))
        elif tipo in SECAO_RENDERERS:
            parts.append(SECAO_RENDERERS[tipo](secao))
        else:
            parts.append(_unknown_section(secao))
    parts.append(render_footer(meta))

    tem_graficos = chart_idx > 0
    if tem_graficos and not plotly_js:
        logger.debug("carregando plotly.js do pacote")
        plotly_js = get_plotly_js()
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
{"".join(parts)}
</div>
</body>
</html>"""


if __name__ == "__main__":
    import argparse
    import json
    import sys
    from pathlib import Path

    from subhue_reports.renderer.sections import assemble_report

    parser = argparse.ArgumentParser(description="Render documentação HTML a partir de JSON ou diretório.")
    parser.add_argument("source", help="Arquivo JSON ou diretório de seções")
    parser.add_argument("-o", "--output", help="Arquivo HTML de saída")
    args = parser.parse_args()

    src = Path(args.source)
    if src.is_dir():
        dados = assemble_report(src)
        out = Path(args.output) if args.output else src.parent / f"{src.name}.html"
    else:
        dados = json.loads(src.read_text())
        out = Path(args.output) if args.output else src.with_suffix(".html")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_doc(dados))
    print(f"gerado: {out}", file=sys.stderr)
