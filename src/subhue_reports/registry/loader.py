import json
import logging
import os
from pathlib import Path
from typing import TypedDict

import requests

logger = logging.getLogger(__name__)

_DEFAULT_MANIFEST_PATH = Path("data/manifest/manifest.json")
_AIRFLOW_FALLBACK_PATH = Path("../airflow-astro/dbt/target/manifest.json")


class RegistryEntry(TypedDict, total=False):
    # Campos internos — sempre presentes após build_registry
    _fqn: list[str]
    _schema: str
    _sql_checksum: str
    _columns: dict[str, dict]
    _description: str
    # Campos de meta dbt — domínio-específicos, opcionais por modelo
    version: str
    layer: str
    status: str
    grain: str
    primary_key: list[str]
    changelog: list[dict]
    consumers: list[str]
    owner: str
    slo: str
    importance: str
    last_change_type: str
    versioning_policy: str


def load_manifest(path: str | None = None, url: str | None = None) -> dict:
    """Carrega manifest de path local, URL HTTP ou fallbacks de desenvolvimento.

    Ordem de resolução: path arg → DBT_MANIFEST_PATH → url arg → DBT_MANIFEST_URL
    → data/manifest/manifest.json → ../airflow-astro/dbt/target/manifest.json
    """
    manifest_source = path or os.getenv("DBT_MANIFEST_PATH") or url or os.getenv("DBT_MANIFEST_URL")

    if not manifest_source:
        return _load_from_fallback_paths()

    if manifest_source.startswith("http"):
        return _load_from_url(manifest_source)

    return _unwrap(json.loads(Path(manifest_source).read_text()))


class SourceEntry(TypedDict, total=False):
    # Campos sempre presentes após build_source_registry
    source_name: str      # grupo lógico (ex: raw_timed_dtw)
    name: str             # nome da tabela
    schema: str           # schema real no banco
    description: str
    source_description: str
    _columns: dict[str, dict]
    _relation_name: str   # nome totalmente qualificado no banco


def build_registry(manifest: dict) -> dict[str, RegistryEntry]:
    """Extrai {model_name: meta} de todos os model nodes."""
    return {
        node["name"]: {
            **node.get("meta", {}),
            "_fqn": node["fqn"],
            "_schema": node["schema"],
            "_sql_checksum": node.get("checksum", {}).get("checksum", ""),
            "_columns": node.get("columns", {}),
            "_description": node.get("description", ""),
        }
        for node in manifest.get("nodes", {}).values()
        if node.get("resource_type") == "model"
    }


def build_source_registry(manifest: dict) -> dict[str, SourceEntry]:
    """Extrai {source_name.table_name: meta} de todos os source nodes."""
    return {
        f"{source['source_name']}.{source['name']}": {
            "source_name": source["source_name"],
            "name": source["name"],
            "schema": source.get("schema", ""),
            "description": source.get("description", ""),
            "source_description": source.get("source_description", ""),
            "_columns": source.get("columns", {}),
            "_relation_name": source.get("relation_name", ""),
        }
        for source in manifest.get("sources", {}).values()
        if source.get("resource_type") == "source"
    }


def _load_from_fallback_paths() -> dict:
    if _DEFAULT_MANIFEST_PATH.exists():
        logger.debug("manifest carregado de %s", _DEFAULT_MANIFEST_PATH)
        return _unwrap(json.loads(_DEFAULT_MANIFEST_PATH.read_text()))
    if _AIRFLOW_FALLBACK_PATH.exists():
        logger.debug("manifest carregado de fallback airflow: %s", _AIRFLOW_FALLBACK_PATH)
        return _unwrap(json.loads(_AIRFLOW_FALLBACK_PATH.read_text()))
    raise RuntimeError(
        "Manifest não encontrado. "
        f"Tentativas: {_DEFAULT_MANIFEST_PATH}, {_AIRFLOW_FALLBACK_PATH}. "
        "Configure DBT_MANIFEST_PATH ou execute 'just manifest-update' para baixar da API."
    )


def _load_from_url(url: str) -> dict:
    token = os.getenv("DBT_MANIFEST_TOKEN", "")
    headers = {"Authorization": f"Token {token}"} if token else {}
    logger.debug("carregando manifest de URL: %s", url)
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return _unwrap(r.json())


def _unwrap(manifest_envelope: dict) -> dict:
    """Desembrulha manifest_content se a API retornou o objeto envelope."""
    if "manifest_content" in manifest_envelope and "nodes" not in manifest_envelope:
        return manifest_envelope["manifest_content"]
    return manifest_envelope
