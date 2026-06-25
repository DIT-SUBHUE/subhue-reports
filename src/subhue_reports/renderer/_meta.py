"""Utilitários de timestamp para meta de relatórios e documentações."""

from datetime import datetime
from typing import Any


def current_timestamp_iso() -> str:
    """Timestamp local ISO-8601 com offset, precisão de segundos."""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def get_generation_timestamp(meta: dict[str, Any]) -> str:
    """Retorna timestamp de geração, preferindo data_hora_geracao."""
    for key in ("data_hora_geracao", "data_geracao"):
        value = str(meta.get(key, "")).strip()
        if value:
            return value
    return current_timestamp_iso()


def ensure_generation_timestamp(payload: dict[str, Any]) -> bool:
    """Garante meta.data_hora_geracao no payload. Retorna True se alterado."""
    meta = payload.setdefault("meta", {})
    if not isinstance(meta, dict):
        raise ValueError(
            f"Campo 'meta' deve ser um objeto JSON. "
            f"Recebido: {type(meta).__name__}"
        )
    if str(meta.get("data_hora_geracao", "")).strip():
        return False
    meta["data_hora_geracao"] = current_timestamp_iso()
    return True
