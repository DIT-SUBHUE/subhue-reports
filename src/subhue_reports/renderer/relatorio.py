"""
Renderer de relatórios HTML self-contained a partir de JSON estruturado.

Tipos de seção:
    contexto      callout de objetivo + parágrafo descritivo
    tabela        tabela genérica com colunas tipadas
    grafico       Plotly Figure JSON
    metrica       grid de stat boxes
    texto         bloco narrativo
    achados       lista com ícone semântico
    excecao       two-col: explicação + tabela + stat boxes
    recomendacao  spec técnica em campos label/valor
"""

import logging
from collections.abc import Callable
from pathlib import Path

from subhue_reports.renderer._html import (
    esc,
    fmt_num,
    render_badge_pct,
    render_cell,
    render_code,
    render_pill,
)
from subhue_reports.renderer._meta import ensure_generation_timestamp, get_generation_timestamp
from subhue_reports.renderer._plotly import get_plotly_js, prepare_figure_json

logger = logging.getLogger(__name__)

ICO_MAP = {
    "ok": "✅",
    "warn": "⚠️",
    "info": "📊",
    "time": "🕐",
    "error": "❌",
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
.scope-notice { background: #fffbeb; border: 1px solid #fcd34d;
  border-left: 4px solid #b45309; border-radius: 3px;
  padding: 10px 14px; margin-bottom: 20px; font-size: 11px; color: #b45309; line-height: 1.5; }
.scope-notice strong { font-weight: 700; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 4px;
  padding: 18px 20px; margin-bottom: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.04); min-width: 0; }
.card-title { font-size: 10px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: var(--ink-4);
  padding-bottom: 12px; margin-bottom: 14px; border-bottom: 1px solid var(--border-light); }
.card-title span { color: var(--ink-5); font-weight: 400;
  letter-spacing: 0; text-transform: none; font-size: 10px; }
.callout { background: #eef4fd; border-left: 3px solid var(--navy-mid);
  padding: 10px 14px; border-radius: 0 3px 3px 0;
  font-size: 12px; color: #1e3a5a; margin-bottom: 12px; }
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
.pill { display: inline-block; font-size: 10px; font-weight: 700;
  padding: 2px 8px; border-radius: 10px; letter-spacing: .02em; white-space: nowrap; }
.pill-h { background: var(--blue-bg); color: var(--blue); }
.pill-u { background: var(--green-bg); color: var(--green); }
.pill-c { background: var(--purple-bg); color: var(--purple); }
.pill-o { background: #ffedd5; color: #c2410c; }
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
.two-col { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; align-items: start; }
.two-col > * { min-width: 0; }
.rec { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 4px; padding: 14px 16px; }
.rec-title { font-size: 10px; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;
  color: var(--green); margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #bbf7d0; }
.rec-row { display: flex; gap: 12px; font-size: 12px; color: #166534;
  padding: 4px 0; border-bottom: 1px solid #d1fae5; align-items: baseline; }
.rec-row:last-of-type { border-bottom: none; }
.rec-label { font-size: 10px; font-weight: 700; letter-spacing: .05em;
  text-transform: uppercase; color: #15803d; min-width: 90px; flex-shrink: 0; }
.rec-note { font-size: 10.5px; color: #166534; margin-top: 10px; padding-top: 8px; border-top: 1px solid #bbf7d0; }
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


def render_header(meta: dict) -> str:
    fontes = ", ".join(render_code(f) for f in meta.get("fontes", []))
    data = esc(get_generation_timestamp(meta))
    return f"""
  <header class="header">
    <div class="header-rail">
      <div class="header-rail-logo" aria-label="DIID">{_diid_logo()}</div>
    </div>
    <div class="header-main">
      <div>
        <div class="header-label">Relatório de Dados — SUBHUE</div>
        <div class="header-title">{esc(meta.get("titulo", ""))}</div>
        <div class="header-subtitle">{esc(meta.get("subtitulo", ""))}</div>
      </div>
      <div class="header-meta">
        <div class="header-meta-item"><strong>Período:</strong> {esc(meta.get("periodo", ""))}</div>
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


def render_footer(meta: dict) -> str:
    data = esc(get_generation_timestamp(meta))
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


def render_contexto(sec: dict) -> str:
    objetivo = esc(sec.get("objetivo", ""))
    descricao = esc(sec.get("descricao", ""))
    return f"""
  <div class="card">
    <div class="card-title">Contexto <span>· objetivo e definição de escopo</span></div>
    <div class="callout"><strong>Objetivo:</strong> {objetivo}</div>
    <p class="prose" style="margin-top:10px">{descricao}</p>
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


def _nota_html(nota: str) -> str:
    if not nota:
        return ""
    style = (
        "font-size:11px;color:var(--ink-4);margin-top:10px;"
        "padding-top:8px;border-top:1px solid var(--border-light)"
    )
    return f'<p style="{style}">{esc(nota)}</p>'


def render_tabela(sec: dict) -> str:
    titulo = esc(sec.get("titulo", ""))
    subtitulo = esc(sec.get("subtitulo", ""))
    colunas = sec.get("colunas", [])
    sub_html = f" <span>· {subtitulo}</span>" if subtitulo else ""
    return f"""
  <div class="card">
    <div class="card-title">{titulo}{sub_html}</div>
    <div class="table-scroll">
      <table>
        <thead><tr>{_table_ths(colunas)}</tr></thead>
        <tbody>{_table_rows(sec.get("linhas", []), colunas)}</tbody>
      </table>
    </div>
    {_nota_html(sec.get("nota", ""))}
  </div>"""


def render_grafico(sec: dict, chart_idx: int) -> str:
    div_id = f"chart_{chart_idx}"
    titulo = esc(sec.get("titulo", ""))
    subtitulo = esc(sec.get("subtitulo", ""))
    fig_raw = sec.get("figura", {"data": [], "layout": {}})

    try:
        fig_json_str = prepare_figure_json(fig_raw)
    except Exception as exc:
        return (
            f'<div class="card"><p style="color:var(--red);font-size:12px">'
            f"Erro ao processar figura: {esc(str(exc))}</p></div>"
        )

    sub_html = f" <span>· {subtitulo}</span>" if subtitulo else ""
    titulo_html = f'<div class="card-title">{titulo}{sub_html}</div>' if titulo else ""
    nota_html = _nota_html(sec.get("nota", ""))
    return f"""
  <div class="card">
    {titulo_html}
    <div id="{div_id}"></div>
    {nota_html}
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
    </script>
  </div>"""


def _stat_box(item: dict) -> str:
    valor = esc(item.get("valor", ""))
    label = esc(item.get("label", ""))
    cor = esc(item.get("cor", "var(--ink)"))
    sub = esc(item.get("sub", ""))
    sub_html = f'<div class="stat-sub">{sub}</div>' if sub else ""
    return f"""
      <div class="stat-box">
        <div class="stat-num" style="color:{cor}">{valor}</div>
        <div class="stat-label">{label}</div>
        {sub_html}
      </div>"""


def render_metrica(sec: dict) -> str:
    titulo = esc(sec.get("titulo", ""))
    items_html = "".join(_stat_box(item) for item in sec.get("items", []))
    return f"""
  <div class="card">
    <div class="card-title">{titulo}</div>
    <div class="metrics-grid">{items_html}</div>
  </div>"""


def render_texto(sec: dict) -> str:
    titulo = esc(sec.get("titulo", ""))
    paras = "".join(f"<p>{esc(p)}</p>" for p in sec.get("paragrafos", []))
    return f"""
  <div class="card">
    <div class="card-title">{titulo}</div>
    <div class="prose">{paras}</div>
  </div>"""


def _achado_item(item: dict) -> str:
    ico = ICO_MAP.get(item.get("tipo", "info"), "📊")
    titulo = esc(item.get("titulo", ""))
    texto = esc(item.get("texto", ""))
    return f"""
      <li>
        <span class="ico">{ico}</span>
        <span><strong>{titulo}</strong> {texto}</span>
      </li>"""


def render_achados(sec: dict) -> str:
    items_html = "".join(_achado_item(item) for item in sec.get("items", []))
    return f"""
  <div class="card">
    <div class="card-title">Principais achados</div>
    <ul class="ilist">{items_html}</ul>
  </div>"""


def _excecao_table(linhas: list, col_labels: list[str]) -> str:
    ths = "".join(
        f'<th class="n">{esc(col)}</th>' if i > 0 else f'<th>{esc(col)}</th>'
        for i, col in enumerate(col_labels)
    )
    rows = ""
    for linha in linhas:
        nome = esc(linha.get("nome", ""))
        tipo = linha.get("tipo", "outro")
        pill = render_pill(tipo, tipo.upper())
        a = fmt_num(linha.get("a", 0))
        b = fmt_num(linha.get("b", 0))
        badge = render_badge_pct(linha.get("pct"))
        cells = f"<td>{pill} {nome}</td><td class='n'>{a}</td><td class='n'>{b}</td><td class='n'>{badge}</td>"
        rows += f"<tr>{cells}</tr>\n"
    return f"<thead><tr>{ths}</tr></thead><tbody>{rows}</tbody>"


def _excecao_stats(stats: list) -> str:
    parts = ""
    for stat in stats:
        valor = esc(stat.get("valor", ""))
        cor = esc(stat.get("cor", "var(--ink)"))
        label = esc(stat.get("label", ""))
        parts += f"""
        <div class="stat-box">
          <div class="stat-num" style="color:{cor}">{valor}</div>
          <div class="stat-label">{label}</div>
        </div>"""
    return parts


def render_excecao(sec: dict) -> str:
    titulo = esc(sec.get("titulo", ""))
    descricao = esc(sec.get("descricao", ""))
    col_labels = sec.get("colunas", ["Unidade", "Fonte A", "Fonte B", "Match"])
    table_html = _excecao_table(sec.get("linhas", []), col_labels)
    stats_html = _excecao_stats(sec.get("stats", []))
    return f"""
  <div class="card">
    <div class="card-title">{titulo}</div>
    <div class="two-col">
      <div>
        <p class="prose" style="margin-bottom:12px">{descricao}</p>
        <div class="table-scroll"><table>{table_html}</table></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:12px">{stats_html}</div>
    </div>
  </div>"""


def _rec_row(row: dict) -> str:
    label = esc(row.get("label", ""))
    valor = row.get("valor", "")
    if isinstance(valor, dict) and "code" in valor:
        valor_html = render_code(valor["code"])
    else:
        valor_html = esc(str(valor))
    return f"""
      <div class="rec-row">
        <span class="rec-label">{label}</span>
        <span>{valor_html}</span>
      </div>"""


def render_recomendacao(sec: dict) -> str:
    titulo = esc(sec.get("titulo", ""))
    subtitulo = esc(sec.get("subtitulo", ""))
    nota = sec.get("nota", "")
    rows_html = "".join(_rec_row(r) for r in sec.get("campos", []))
    nota_html = f'<p class="rec-note">{esc(nota)}</p>' if nota else ""
    sub_html = f" <span>· {subtitulo}</span>" if subtitulo else ""
    return f"""
  <div class="card">
    <div class="card-title">Recomendação{sub_html}</div>
    <div class="rec">
      <div class="rec-title">{titulo}</div>
      {rows_html}
      {nota_html}
    </div>
  </div>"""


SECAO_RENDERERS: dict[str, Callable] = {
    "contexto": render_contexto,
    "tabela": render_tabela,
    "metrica": render_metrica,
    "texto": render_texto,
    "achados": render_achados,
    "excecao": render_excecao,
    "recomendacao": render_recomendacao,
}


def _unknown_section(sec: dict) -> str:
    tipo = sec.get("tipo", "")
    return (
        f'<div class="card" style="border-color:var(--red-bg)">'
        f'<p style="color:var(--red);font-size:12px">'
        f"Tipo de seção desconhecido: <code>{esc(tipo)}</code></p></div>"
    )


def render_report(dados: dict, plotly_js: str = "") -> str:
    """Gera HTML completo do relatório. plotly_js injetado se houver graficos."""
    ensure_generation_timestamp(dados)
    meta = dados.get("meta", {})
    secoes = dados.get("secoes", [])
    titulo = esc(meta.get("titulo", "Relatório de Dados SUBHUE"))

    parts = [render_header(meta), render_scope_notice()]
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

    parser = argparse.ArgumentParser(description="Render relatório HTML a partir de JSON ou diretório.")
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
    out.write_text(render_report(dados))
    print(f"gerado: {out}", file=sys.stderr)
