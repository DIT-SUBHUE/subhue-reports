"""
Verifica se as fontes declaradas em um relatório estão na versão atual do registry.

Uso direto:
    python -m subhue_reports.registry.checker data/reports/meu_relatorio.json
"""

import argparse
import json
import sys
from pathlib import Path


def check_sources(report_json: dict, registry: dict) -> list[dict]:
    """
    Cruza fontes declaradas no JSON do relatório com versões atuais do registry.
    Retorna lista de warnings; lista vazia = tudo ok.
    """
    warnings = []
    for fonte in report_json.get("meta", {}).get("fontes", []):
        model_name = fonte.split(".")[-1]
        current = registry.get(model_name)
        if not current:
            warnings.append({"fonte": fonte, "issue": "model não encontrado no registry"})
            continue
        snapshotted = report_json["meta"].get("model_versions", {}).get(fonte)
        if snapshotted and snapshotted != current.get("version"):
            warnings.append({
                "fonte": fonte,
                "issue": "versão desatualizada",
                "no_relatorio": snapshotted,
                "atual": current.get("version"),
            })
    return warnings


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Valida fontes de um relatório contra o registry")
    p.add_argument("report", help="path para o JSON do relatório")
    args = p.parse_args()

    from subhue_reports.registry.loader import build_registry, load_manifest

    report_json = json.loads(Path(args.report).read_text())
    manifest = load_manifest()
    registry = build_registry(manifest)
    warnings = check_sources(report_json, registry)

    if not warnings:
        print("ok — todas as fontes estão na versão atual")
        sys.exit(0)

    print(f"{len(warnings)} problema(s) encontrado(s):")
    for w in warnings:
        print(f"  {w['fonte']}: {w['issue']}", end="")
        if "no_relatorio" in w:
            print(f" (relatório={w['no_relatorio']}, atual={w['atual']})", end="")
        print()
    sys.exit(1)
