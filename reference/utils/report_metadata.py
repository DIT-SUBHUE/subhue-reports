#!/usr/bin/env python3
"""Padroniza metadados de geracao para relatorios/documentacoes HTML."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def current_timestamp_iso() -> str:
    """Retorna timestamp local ISO-8601 com offset e precisao de segundos."""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def get_generation_timestamp(meta: dict[str, Any]) -> str:
    """Retorna timestamp de geracao preferindo data_hora_geracao."""
    data_hora_geracao = str(meta.get("data_hora_geracao", "")).strip()
    if data_hora_geracao:
        return data_hora_geracao

    data_geracao = str(meta.get("data_geracao", "")).strip()
    if data_geracao:
        return data_geracao

    return current_timestamp_iso()


def ensure_generation_timestamp(
    payload: dict[str, Any],
    *,
    overwrite: bool = False,
    timestamp: str | None = None,
) -> bool:
    """Garante meta.data_hora_geracao no payload.

    Retorna True quando o payload foi alterado.
    """
    meta = payload.setdefault("meta", {})
    if not isinstance(meta, dict):
        raise ValueError("Campo meta deve ser um objeto JSON")

    has_timestamp = bool(str(meta.get("data_hora_geracao", "")).strip())
    if has_timestamp and not overwrite:
        return False

    meta["data_hora_geracao"] = timestamp or current_timestamp_iso()
    return True


def normalize_api_generation_timestamp(meta: dict[str, Any]) -> str:
    """Normaliza data enviada para a API sem inventar horario.

    JSONs legados podem ter apenas data_geracao (data, sem hora). Nesses casos,
    preservamos o valor original em vez de fabricar meia-noite.
    """
    data_hora_geracao = str(meta.get("data_hora_geracao", "")).strip()
    if data_hora_geracao:
        return data_hora_geracao

    data_geracao = str(meta.get("data_geracao", "")).strip()
    if not data_geracao:
        return current_timestamp_iso()
    return data_geracao


def update_json_file(path: Path, *, overwrite: bool, timestamp: str | None) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    changed = ensure_generation_timestamp(
        payload,
        overwrite=overwrite,
        timestamp=timestamp,
    )
    if changed:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def iter_json_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    for path in paths:
        if path.is_dir():
            result.extend(sorted(path.rglob("*.json")))
        else:
            result.append(path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Padroniza meta.data_hora_geracao em JSONs de relatorio/documentacao."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Arquivos JSON ou diretorios")
    parser.add_argument(
        "--set-now",
        action="store_true",
        help="Sobrescreve data_hora_geracao com o horario local atual.",
    )
    parser.add_argument(
        "--timestamp",
        help="Timestamp ISO explicito para usar com --set-now/overwrite.",
    )
    args = parser.parse_args()

    timestamp = args.timestamp or (current_timestamp_iso() if args.set_now else None)
    changed = 0
    inspected = 0
    for path in iter_json_paths(args.paths):
        inspected += 1
        if update_json_file(path, overwrite=args.set_now, timestamp=timestamp):
            changed += 1
            print(f"Atualizado: {path}")

    print(f"Resumo: {changed} atualizados, {inspected} avaliados.")


if __name__ == "__main__":
    main()
