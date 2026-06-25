import json
import os
from pathlib import Path

import requests

_DEFAULT_MANIFEST_PATH = Path("data/manifest/manifest.json")


def load_manifest(path: str | None = None, url: str | None = None) -> dict:
    """Carrega manifest de path local, URL HTTP ou fallback de desenvolvimento."""
    source = path or os.getenv("DBT_MANIFEST_PATH") or url or os.getenv("DBT_MANIFEST_URL")

    if not source:
        if _DEFAULT_MANIFEST_PATH.exists():
            return _unwrap(json.loads(_DEFAULT_MANIFEST_PATH.read_text()))
        fallback = Path("../airflow-astro/dbt/target/manifest.json")
        if fallback.exists():
            return _unwrap(json.loads(fallback.read_text()))
        raise RuntimeError(
            "Configure DBT_MANIFEST_PATH ou execute 'just manifest-update' para baixar da API."
        )

    if source.startswith("http"):
        token = os.getenv("DBT_MANIFEST_TOKEN", "")
        headers = {"Authorization": f"Token {token}"} if token else {}
        r = requests.get(source, headers=headers, timeout=30)
        r.raise_for_status()
        return _unwrap(r.json())

    return _unwrap(json.loads(Path(source).read_text()))


def _unwrap(data: dict) -> dict:
    """Desembrulha manifest_content se a API retornou o objeto envelope."""
    if "manifest_content" in data and "nodes" not in data:
        return data["manifest_content"]
    return data


def build_registry(manifest: dict) -> dict[str, dict]:
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
