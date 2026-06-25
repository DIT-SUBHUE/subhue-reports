"""
Extrai dados do Postgres e salva como Parquet + meta.json.

Não usa subprocess. Conecta via psycopg2 (connection.py) e serializa com pyarrow.
Tipos não nativos do pyarrow (UUID, Decimal, etc.) são convertidos para str.
"""

import hashlib
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from subhue_reports.cache.connection import PgConnection, connect

logger = logging.getLogger(__name__)


def extract_to_parquet(
    source: str,
    sql: str,
    parquet_path: Path,
    meta_path: Path,
    model_version: str,
    sql_checksum: str,
    filters: dict,
) -> Path:
    """Executa SQL no Postgres e salva resultado como parquet + meta.json."""
    logger.info("extraindo %s → %s", source, parquet_path.name)

    conn = connect()
    try:
        arrow_table = _fetch_as_arrow(conn, sql)
    finally:
        conn.rollback()
        conn.close()

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(arrow_table, parquet_path)

    _write_meta(meta_path, source, sql, model_version, sql_checksum, filters, len(arrow_table))
    logger.info("salvo %d linhas → %s", len(arrow_table), parquet_path.name)
    return parquet_path


def _fetch_as_arrow(conn: PgConnection, sql: str) -> pa.Table:
    with conn.cursor() as cur:
        cur.execute(sql)
        columns = [desc.name for desc in cur.description]
        rows = cur.fetchall()
    arrays = [
        pa.array([_normalize(row[i]) for row in rows])
        for i in range(len(columns))
    ]
    return pa.table(dict(zip(columns, arrays, strict=True)))


def _normalize(value: Any) -> Any:
    """Converte tipos do psycopg2 não suportados nativamente pelo pyarrow."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _write_meta(
    meta_path: Path,
    source: str,
    sql: str,
    model_version: str,
    sql_checksum: str,
    filters: dict,
    row_count: int,
) -> None:
    query_hash = hashlib.sha256(sql.encode()).hexdigest()[:16]
    meta_path.write_text(json.dumps(
        {
            "source": source,
            "model_version": model_version,
            "sql_checksum": sql_checksum,
            "extracted_at": datetime.now().astimezone().isoformat(),
            "query_hash": f"sha256:{query_hash}",
            "filters": filters,
            "row_count": row_count,
        },
        ensure_ascii=False,
        indent=2,
    ))
