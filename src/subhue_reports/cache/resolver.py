"""
Cache hit/miss para fontes dbt.

Invalidação em três camadas (todas devem passar para hit):
    1. versão do model (meta.model_version == registry version)
    2. checksum do SQL (meta.sql_checksum == registry checksum)
    3. TTL (extracted_at dentro de CACHE_TTL_HOURS, default 4h)

Filtros: dict com campos opcionais:
    periodo      → sufixo do nome do arquivo (ex: "2026-06")
    <col>=<val>  → cláusulas WHERE no SQL extraído
    periodo é excluído das cláusulas WHERE.

Filtros são sempre construídos internamente — nunca de input do usuário.
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from subhue_reports.cache.extractor import extract_to_parquet
from subhue_reports.registry.loader import RegistryEntry

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path("data/cache")
_DEFAULT_TTL_HOURS = 4


def resolve_source(
    source: str,
    filters: dict,
    registry: dict[str, RegistryEntry],
    cache_dir: Path = _DEFAULT_CACHE_DIR,
) -> Path:
    """
    Retorna path do parquet válido (cache hit) ou extrai do banco (cache miss).

    Cache hit: arquivo existe AND versão atual AND checksum atual AND dentro do TTL.
    Cache miss: extrai do Postgres via extractor e salva localmente.
    """
    model_name = source.split(".")[-1]
    model_meta = registry.get(model_name, {})
    current_version = model_meta.get("version", "")
    current_checksum = model_meta.get("_sql_checksum", "")

    parquet_path = cache_dir / f"{_cache_key(source, filters)}.parquet"
    meta_path = parquet_path.with_suffix(".meta.json")

    if _is_cache_valid(parquet_path, meta_path, current_version, current_checksum):
        logger.info("cache hit %s", parquet_path.name)
        return parquet_path

    logger.info("cache miss %s — extraindo do banco", parquet_path.name)
    sql = _build_sql(source, filters)
    return extract_to_parquet(
        source=source,
        sql=sql,
        parquet_path=parquet_path,
        meta_path=meta_path,
        model_version=current_version,
        sql_checksum=current_checksum,
        filters=filters,
    )


def _is_cache_valid(
    parquet_path: Path,
    meta_path: Path,
    current_version: str,
    current_checksum: str,
) -> bool:
    if not parquet_path.exists() or not meta_path.exists():
        return False
    meta = json.loads(meta_path.read_text())
    if meta.get("model_version") != current_version:
        old = meta.get("model_version")
        logger.debug("cache inválido: versão mudou %s → %s", old, current_version)
        return False
    if meta.get("sql_checksum") != current_checksum:
        logger.debug("cache inválido: checksum mudou")
        return False
    if _is_expired(meta.get("extracted_at", "")):
        logger.debug("cache expirado: %s", meta.get("extracted_at"))
        return False
    return True


def _is_expired(extracted_at: str) -> bool:
    if not extracted_at:
        return True
    ttl_hours = int(os.getenv("CACHE_TTL_HOURS", str(_DEFAULT_TTL_HOURS)))
    try:
        extracted = datetime.fromisoformat(extracted_at)
        age = datetime.now(tz=UTC) - extracted.astimezone(UTC)
        return age > timedelta(hours=ttl_hours)
    except ValueError:
        return True


def _cache_key(source: str, filters: dict) -> str:
    periodo = filters.get("periodo", "sem-periodo")
    return f"{source}_{periodo}"


def _build_sql(source: str, filters: dict) -> str:
    """Constrói SELECT com filtros de igualdade. Filtros são internos — nunca de input externo."""
    schema, table = source.rsplit(".", 1)
    sql_filters = {k: v for k, v in filters.items() if k != "periodo"}
    where = " AND ".join(f"{col} = '{val}'" for col, val in sql_filters.items())
    return f"SELECT * FROM {schema}.{table}" + (f" WHERE {where}" if where else "")
