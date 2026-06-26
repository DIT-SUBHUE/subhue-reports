"""CLI unificado: python -m subhue_reports.renderer <src> [-o output.html]"""

import argparse
import json
import sys
from pathlib import Path

from subhue_reports.renderer import render
from subhue_reports.renderer._output import resolve_output_dir, slugify
from subhue_reports.renderer._plotly import get_plotly_js
from subhue_reports.renderer.sections import assemble_report

parser = argparse.ArgumentParser(description="Render HTML a partir de JSON ou diretório de seções.")
parser.add_argument("source", help="Arquivo JSON ou diretório de seções")
parser.add_argument("-o", "--output", help="Arquivo HTML de saída (anula estrutura automática)")
parser.add_argument(
    "--base-dir",
    default="reports",
    help="Diretório base de saída (default: reports)",
)
args = parser.parse_args()

src = Path(args.source)
dados = assemble_report(src) if src.is_dir() else json.loads(src.read_text(encoding="utf-8"))

plotly_js = get_plotly_js()
html = render(dados, plotly_js)

if args.output:
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"gerado: {out}", file=sys.stderr)
else:
    out_dir = resolve_output_dir(dados, Path(args.base_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(dados.get("meta", {}).get("titulo", "documento")).lower()
    json_path = out_dir / f"{slug}.json"
    html_path = out_dir / f"{slug}.html"
    json_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    print(f"diretório: {out_dir}", file=sys.stderr)
    print(f"  json : {json_path.name}", file=sys.stderr)
    print(f"  html : {html_path.name}", file=sys.stderr)
