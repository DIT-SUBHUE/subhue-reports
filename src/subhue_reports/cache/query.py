"""
Executor DuckDB sobre parquets em data/cache/.

O SQL deve referenciar paths de parquets diretamente:

    FROM 'data/cache/silver_timed.fat_censo_leito_ativo_2026-06.parquet'

    -- glob para múltiplos períodos:
    FROM 'data/cache/silver_timed.fat_censo_leito_ativo_*.parquet'

    -- join entre fontes:
    FROM 'data/cache/silver_timed.fat_censo_leito_ativo_2026-06.parquet' c
    JOIN 'data/cache/gold_timed.atendimento_emergencia_agg_2026-06.parquet' a
      ON c.estabelecimento_gid = a.estabelecimento_gid
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb

if TYPE_CHECKING:
    from subhue_reports.registry.loader import RegistryEntry

logger = logging.getLogger(__name__)


def query(sql: str) -> list[dict]:
    """Executa SQL sobre parquets via DuckDB. Retorna lista de dicts."""
    logger.debug("duckdb query: %.120s", sql)
    con = duckdb.connect()
    rel = con.sql(sql)
    columns = [desc[0] for desc in rel.description]
    return [dict(zip(columns, row, strict=True)) for row in rel.fetchall()]


def parquet_path_for(source: str, periodo: str, cache_dir: str = "data/cache") -> str:
    """Retorna o path do parquet para uso direto no SQL DuckDB."""
    return f"{cache_dir}/{source}_{periodo}.parquet"


def parquet_glob_for(source: str, cache_dir: str = "data/cache") -> str:
    """Retorna glob para todos os períodos de uma fonte."""
    return f"{cache_dir}/{source}_*.parquet"


class SourceExploration:
    """Resultado de explore_source: colunas, amostra e contagem."""

    columns: list[str]
    sample: list[dict[str, Any]]
    row_count: int
    parquet_path: str

    def __init__(
        self,
        columns: list[str],
        sample: list[dict[str, Any]],
        row_count: int,
        parquet_path: str,
    ) -> None:
        self.columns = columns
        self.sample = sample
        self.row_count = row_count
        self.parquet_path = parquet_path

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "row_count": self.row_count,
            "sample": self.sample,
            "parquet_path": self.parquet_path,
        }


def explore_source(
    source: str,
    filters: dict,
    registry: "dict[str, RegistryEntry]",
    limit: int = 20,
    cache_dir: Path = Path("data/cache"),
) -> SourceExploration:
    """
    Resolve fonte (cache hit/miss) e retorna amostra + metadados em uma chamada.

    Uso típico em skills: substituir dois round-trips (resolve + query) por um.

    Exemplo:
        exp = explore_source("silver_timed.fat_censo", {}, registry)
        exp.columns   # ["gid", "periodo", "leitos_ativos", ...]
        exp.row_count # 45231
        exp.sample    # [{"gid": "...", "periodo": "2026-06", ...}, ...]
    """
    from subhue_reports.cache.resolver import resolve_source

    path = resolve_source(source, filters, registry, cache_dir)
    path_str = str(path)

    con = duckdb.connect()
    row_count = con.sql(f"SELECT count(*) FROM '{path_str}'").fetchone()[0]
    rel = con.sql(f"SELECT * FROM '{path_str}' LIMIT {limit}")
    columns = [desc[0] for desc in rel.description]
    sample = [dict(zip(columns, row, strict=True)) for row in rel.fetchall()]

    logger.debug(
        "explore_source %s: %d colunas, %d linhas, amostra %d",
        source, len(columns), row_count, len(sample),
    )
    return SourceExploration(
        columns=columns, sample=sample, row_count=row_count, parquet_path=path_str
    )
