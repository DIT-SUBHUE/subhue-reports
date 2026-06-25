"""
Explode/assemble de seções como arquivos separados.

Estrutura em disco:
    data/reports/meu-relatorio/
        meta.json
        01_contexto.json
        02_grafico_atendimentos.json
        03_tabela_tops.json

Deletar arquivo = remover seção. Renomear prefixo numérico = reordenar.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def explode_report(dados: dict, dest_dir: Path) -> None:
    """Salva JSON único em meta.json + 01_<tipo>.json por seção."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    meta = dados.get("meta", {})
    (dest_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for idx, secao in enumerate(dados.get("secoes", []), start=1):
        tipo = secao.get("tipo", "secao")
        filename = f"{idx:02d}_{tipo}.json"
        (dest_dir / filename).write_text(
            json.dumps(secao, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("salvo %s", filename)

    logger.info("explodido em %d arquivos → %s", len(dados.get("secoes", [])) + 1, dest_dir)


def assemble_report(report_dir: Path) -> dict:
    """Lê meta.json + seções ordenadas → dict no schema original."""
    meta_path = report_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(
            f"meta.json não encontrado. "
            f"Recebido: {report_dir}. Esperado: arquivo meta.json no diretório."
        )

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    section_files = sorted(report_dir.glob("[0-9][0-9]_*.json"))
    secoes = [json.loads(f.read_text(encoding="utf-8")) for f in section_files]

    logger.info("montado: %d seções de %s", len(secoes), report_dir)
    return {"meta": meta, "secoes": secoes}


def list_sections(report_dir: Path) -> list[tuple[int, str, str]]:
    """Retorna [(idx, tipo, filename)] para exibição no CLI."""
    section_files = sorted(report_dir.glob("[0-9][0-9]_*.json"))
    result = []
    for idx, path in enumerate(section_files, start=1):
        try:
            secao = json.loads(path.read_text(encoding="utf-8"))
            tipo = secao.get("tipo", "?")
        except json.JSONDecodeError:
            tipo = "erro-json"
        result.append((idx, tipo, path.name))
    return result
