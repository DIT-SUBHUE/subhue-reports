"""Resolução de caminho de saída com estrutura de diretórios por tipo e timestamp."""

import unicodedata
from datetime import datetime
from pathlib import Path

_TIPO_PASTA: dict[str, str] = {
    "relatorio": "relatorios",
    "documentacao": "documentacoes",
    "dashboard": "dashboards",
}


def slugify(texto: str) -> str:
    """Converte título para slug maiúsculo sem acentos: 'Painel Geral' → 'PAINEL_GERAL'."""
    normalizado = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in normalizado if unicodedata.category(c) != "Mn")
    slug = "".join(c if c.isalnum() else "_" for c in sem_acento.upper())
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def resolve_output_dir(dados: dict, base_dir: Path = Path("reports")) -> Path:
    """
    Retorna diretório de saída com estrutura:
    {base_dir}/{tipo_pasta}/{YYYY_MM_DD__HH_MM}__{SLUG}/

    Exemplo: reports/dashboards/2026_06_26__15_46__PAINEL_ATENDIMENTOS/
    """
    meta = dados.get("meta", {})
    tipo = meta.get("tipo_documento", "relatorio")
    titulo = meta.get("titulo", "sem_titulo")
    pasta = _TIPO_PASTA.get(tipo, "relatorios")
    ts = datetime.now().strftime("%Y_%m_%d__%H_%M")
    slug = slugify(titulo)
    return base_dir / pasta / f"{ts}__{slug}"
