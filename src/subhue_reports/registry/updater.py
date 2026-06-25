"""
Compara metadados do manifest local com a rota de metadata da API.
Baixa conteúdo completo apenas se a origem tiver versão mais recente.

Auth: POST /autenticacao/token/ com username/password → Bearer token.
Variáveis de ambiente (alinhadas com a DAG dbt_publish_manifest):
    DBT_MANIFEST_API_BASE_URL   URL base da API Django (ex: https://diid.subhue.org)
    DBT_MANIFEST_API_USERNAME   usuário para obtenção do token
    DBT_MANIFEST_API_PASSWORD   senha para obtenção do token
    DBT_MANIFEST_TAG            tag do manifest (default: airflow_astro)

Uso direto:
    python -m subhue_reports.registry.updater
    python -m subhue_reports.registry.updater --force
    python -m subhue_reports.registry.updater --check-only
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

_DEFAULT_TAG = "airflow_astro"
_MANIFEST_DIR = Path("data/manifest")
_MANIFEST_PATH = _MANIFEST_DIR / "manifest.json"
_META_PATH = _MANIFEST_DIR / "manifest.meta.json"


def _get_token(base_url: str) -> str:
    """POST /autenticacao/token/ → token string."""
    username = os.getenv("DBT_MANIFEST_API_USERNAME", "")
    password = os.getenv("DBT_MANIFEST_API_PASSWORD", "")
    if not username or not password:
        raise RuntimeError(
            "Configure DBT_MANIFEST_API_USERNAME e DBT_MANIFEST_API_PASSWORD no .env"
        )
    r = requests.post(
        f"{base_url}/autenticacao/token/",
        json={"username": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


def _auth_headers(base_url: str) -> dict:
    """Retorna header Authorization com token obtido da API."""
    token = _get_token(base_url)
    return {"Authorization": f"Token {token}"}


def fetch_remote_meta(base_url: str, tag: str) -> dict:
    """GET /api/dbt-manifest/?tag={tag} → metadados sem conteúdo."""
    r = requests.get(
        f"{base_url}/api/dbt-manifest/",
        params={"tag": tag},
        headers=_auth_headers(base_url),
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list):
        hits = [d for d in data if d.get("tag") == tag]
        if not hits:
            raise ValueError(f"tag '{tag}' não encontrada na API")
        return hits[0]
    if isinstance(data, dict) and "results" in data:
        hits = [d for d in data["results"] if d.get("tag") == tag]
        if not hits:
            raise ValueError(f"tag '{tag}' não encontrada na API")
        return hits[0]
    return data


def fetch_manifest_content(base_url: str, tag: str) -> dict:
    """GET /api/dbt-manifest/{tag}/content/ → manifest completo (campo manifest_content)."""
    r = requests.get(
        f"{base_url}/api/dbt-manifest/{tag}/content/",
        headers=_auth_headers(base_url),
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    # API envolve o manifest em {"manifest_content": {...}}
    if "manifest_content" in data:
        return data["manifest_content"]
    return data


def load_local_meta(meta_path: Path = _META_PATH) -> dict | None:
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text())


def check_and_update(
    base_url: str | None = None,
    tag: str | None = None,
    manifest_path: Path = _MANIFEST_PATH,
    meta_path: Path = _META_PATH,
    force: bool = False,
) -> bool:
    """
    Compara updated_at do manifest local com a API.
    Se API tiver versão mais recente (ou force=True), baixa e salva localmente.
    Retorna True se manifest foi atualizado.
    """
    base_url = (base_url or os.getenv("DBT_MANIFEST_API_BASE_URL", "")).rstrip("/")
    tag = tag or os.getenv("DBT_MANIFEST_TAG", _DEFAULT_TAG)

    if not base_url:
        raise RuntimeError(
            "Configure DBT_MANIFEST_API_BASE_URL no .env "
            "(ex: https://diid.subhue.org)"
        )

    remote_meta = fetch_remote_meta(base_url, tag)
    remote_updated = remote_meta.get("updated_at", "")

    local_meta = load_local_meta(meta_path)
    local_updated = (local_meta or {}).get("updated_at", "")

    if not force and local_updated and local_updated >= remote_updated:
        print(
            f"manifest já atualizado  "
            f"local={local_updated[:19]}  remoto={remote_updated[:19]}"
        )
        return False

    action = "forçando atualização" if force and local_updated else "nova versão disponível"
    print(f"{action}  remoto={remote_updated[:19]}")
    print("baixando manifest...")

    manifest = fetch_manifest_content(base_url, tag)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    meta_path.write_text(json.dumps(
        {
            **remote_meta,
            "local_path": str(manifest_path),
            "fetched_at": datetime.now().astimezone().isoformat(),
        },
        ensure_ascii=False,
        indent=2,
    ))

    model_count = sum(
        1 for v in manifest.get("nodes", {}).values()
        if v.get("resource_type") == "model"
    )
    print(f"manifest salvo  path={manifest_path}  models={model_count}")
    return True


def print_status(base_url: str, tag: str) -> None:
    """Exibe comparação de metadados local vs remoto sem baixar."""
    remote_meta = fetch_remote_meta(base_url, tag)
    local_meta = load_local_meta()

    remote_updated = remote_meta.get("updated_at", "—")
    local_updated = (local_meta or {}).get("updated_at", "ausente")
    fetched_at = (local_meta or {}).get("fetched_at", "—")

    print(f"tag:             {remote_meta.get('tag', tag)}")
    print(f"remoto updated:  {remote_updated[:19] if remote_updated != '—' else '—'}")
    print(f"local  updated:  {local_updated[:19] if local_updated != 'ausente' else 'ausente'}")
    print(f"baixado em:      {fetched_at[:19] if fetched_at != '—' else '—'}")

    if local_updated == "ausente":
        print("status:          sem manifest local")
    elif local_updated >= remote_updated:
        print("status:          atualizado")
    else:
        print("status:          desatualizado — execute 'just manifest-update'")


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Verifica e atualiza manifest local a partir da API"
    )
    p.add_argument("--force", action="store_true", help="baixa mesmo se já atualizado")
    p.add_argument("--check-only", action="store_true", help="verifica sem baixar")
    p.add_argument("--tag", default=None, help="tag do manifest (default: airflow_astro)")
    p.add_argument("--base-url", default=None, help="URL base da API Django")
    args = p.parse_args()

    base_url = (args.base_url or os.getenv("DBT_MANIFEST_API_BASE_URL", "")).rstrip("/")
    tag = args.tag or os.getenv("DBT_MANIFEST_TAG", _DEFAULT_TAG)

    if not base_url:
        print("erro: DBT_MANIFEST_API_BASE_URL não configurado", file=sys.stderr)
        sys.exit(1)

    if args.check_only:
        print_status(base_url, tag)
        sys.exit(0)

    try:
        check_and_update(base_url=base_url, tag=tag, force=args.force)
    except Exception as e:
        print(f"erro: {e}", file=sys.stderr)
        sys.exit(1)
