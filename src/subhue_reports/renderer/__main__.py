"""CLI unificado: python -m subhue_reports.renderer <src> [-o output.html]"""

import argparse
import json
import sys
from pathlib import Path

from subhue_reports.renderer import render
from subhue_reports.renderer.sections import assemble_report

parser = argparse.ArgumentParser(description="Render HTML a partir de JSON ou diretório de seções.")
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
out.write_text(render(dados))
print(f"gerado: {out}", file=sys.stderr)
