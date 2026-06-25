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

import duckdb

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
