"""
Fábrica de conexões psycopg2 para o banco Subhue.

Variáveis de ambiente:
    SUBHUE_IP, SUBHUE_PGPORT, SUBHUE_DATABASE_NAME, SUBHUE_USER, SUBHUE_SENHA

Todas as conexões abertas aqui são somente-leitura.
"""

import logging
import os
from typing import TypedDict

import psycopg2
from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)

_ENV_MAP = {
    "host": "SUBHUE_IP",
    "port": "SUBHUE_PGPORT",
    "dbname": "SUBHUE_DATABASE_NAME",
    "user": "SUBHUE_USER",
    "password": "SUBHUE_SENHA",
}


class ConnectionParams(TypedDict):
    host: str
    port: int
    dbname: str
    user: str
    password: str


def connection_params() -> ConnectionParams:
    """Constrói parâmetros de conexão para o banco Subhue."""
    missing = [env for env in _ENV_MAP.values() if not os.environ.get(env)]
    if missing:
        raise RuntimeError(
            f"Variáveis de ambiente ausentes: {', '.join(sorted(missing))}"
        )
    raw = {key: os.environ[env] for key, env in _ENV_MAP.items()}
    return {**raw, "port": int(raw["port"])}  # type: ignore[return-value]


def connect() -> PgConnection:
    """Abre conexão somente-leitura para o banco Subhue."""
    params = connection_params()
    logger.debug("conectando host=%s db=%s", params["host"], params["dbname"])
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True)
    return conn
