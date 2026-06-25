#!/usr/bin/env python3
"""Sincroniza documentacoes geradas com a API Django de dados-documentacoes."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

from report_metadata import normalize_api_generation_timestamp


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT_DIR / "data" / "reports"

DOC_SECTION_TYPES = {
    "visao_geral",
    "dependencias",
    "colunas",
    "especificacao",
    "observacoes",
    "changelog",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_payload(payload: dict) -> str:
    section_types = {section.get("tipo") for section in payload.get("secoes", [])}
    if section_types & DOC_SECTION_TYPES:
        return "documentacao"
    return "relatorio"


def discover_documents(reports_dir: Path) -> list[dict]:
    """Descobre pares HTML+JSON em reports_dir e extrai metadados do JSON companion."""
    documents = []
    for html_path in sorted(reports_dir.rglob("*.html")):
        json_path = html_path.with_suffix(".json")
        if not json_path.exists():
            continue

        payload = load_json(json_path)
        meta = payload.get("meta", {})

        documents.append(
            {
                "titulo": meta.get("titulo") or html_path.stem,
                "subtitulo": meta.get("subtitulo", ""),
                "tipo_documento": classify_payload(payload),
                "versao": meta.get("versao", ""),
                "periodo": meta.get("periodo", ""),
                "data_geracao": normalize_api_generation_timestamp(meta),
                "fontes": meta.get("fontes", []),
                "html_path": html_path,
                "json_path": json_path,
            }
        )
    return documents


def env_or_arg(value: str | None, env_name: str) -> str | None:
    return value or os.getenv(env_name)


def normalize_base_url(base_url: str) -> str:
    base_url = base_url.strip()
    if "://" not in base_url:
        local_hosts = ("localhost", "127.", "0.0.0.0")
        scheme = "http" if base_url.startswith(local_hosts) else "https"
        base_url = f"{scheme}://{base_url}"
    return base_url.rstrip("/") + "/"


def get_token(base_url: str, username: str | None, password: str | None, token: str | None) -> str:
    if token:
        return token
    if not username or not password:
        raise ValueError(
            "Informe DADOS_DOCS_API_TOKEN ou DADOS_DOCS_API_USERNAME e DADOS_DOCS_API_PASSWORD."
        )

    response = requests.post(
        urljoin(base_url, "autenticacao/token/"),
        json={"username": username, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["token"]


def upload_doc(
    base_url: str,
    token: str,
    path: Path,
    *,
    titulo: str,
    subtitulo: str = "",
    tipo_documento: str = "",
    versao: str = "",
    periodo: str = "",
    data_geracao: str = "",
    fontes: list[str] | None = None,
    force: bool = False,
) -> dict:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = {
        "titulo": titulo,
        "subtitulo": subtitulo,
        "tipo_documento": tipo_documento,
        "versao": versao,
        "periodo": periodo,
        "data_geracao": data_geracao,
        "fontes": json.dumps(fontes or []),
        "force": str(force).lower(),
    }
    with path.open("rb") as file_obj:
        response = requests.post(
            urljoin(base_url, "api/dados-documentacoes/documentacoes/"),
            headers={"Authorization": f"Token {token}"},
            data=data,
            files={"arquivo": (path.name, file_obj, content_type)},
            timeout=120,
        )
    response.raise_for_status()
    return response.json()


def list_remote_documents(base_url: str, token: str) -> list[dict]:
    response = requests.get(
        urljoin(base_url, "api/dados-documentacoes/documentacoes/listar/"),
        headers={"Authorization": f"Token {token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def remote_key(item: dict) -> tuple[str, str]:
    return str(item.get("tipo", "")), str(item.get("nome_original", ""))


def sync_documents(
    base_url: str,
    token: str,
    documents: list[dict],
    *,
    force: bool,
    include_source_json: bool,
    dry_run: bool,
) -> int:
    remote_items = list_remote_documents(base_url, token)
    remote_keys = {remote_key(item) for item in remote_items}

    sent = 0
    skipped = 0

    for doc in documents:
        html_path: Path = doc["html_path"]
        meta = {k: doc[k] for k in ("titulo", "subtitulo", "tipo_documento", "versao", "periodo", "data_geracao", "fontes")}

        print(f"\nProcessando: {html_path.relative_to(ROOT_DIR)}")
        print("Metadados:", meta)
        exists_remote = ("html", html_path.name) in remote_keys
        if exists_remote and not force:
            skipped += 1
            print(f"Ignorado, ja existe: {html_path.relative_to(ROOT_DIR)}")
        elif dry_run:
            action = "sobrescreveria" if exists_remote else "enviaria"
            print(f"DRY-RUN {action}: {html_path.relative_to(ROOT_DIR)}")
        else:
            payload = upload_doc(base_url, token, html_path, force=force, **meta)
            sent += 1
            _log_resultado(payload, html_path)

        if include_source_json:
            json_path: Path = doc["json_path"]
            exists_json_remote = ("json", json_path.name) in remote_keys
            if exists_json_remote and not force:
                skipped += 1
                print(f"Ignorado, ja existe: {json_path.relative_to(ROOT_DIR)}")
            elif dry_run:
                action = "sobrescreveria" if exists_json_remote else "enviaria"
                print(f"DRY-RUN {action}: {json_path.relative_to(ROOT_DIR)}")
            else:
                payload = upload_doc(base_url, token, json_path, force=force, **meta)
                sent += 1
                _log_resultado(payload, json_path)

    total = len(documents) * (2 if include_source_json else 1)
    print(f"Resumo: {sent} enviados, {skipped} ignorados, {total} avaliados.")
    return sent


def _log_resultado(payload: dict, path: Path) -> None:
    sha = payload.get("sha256", "")
    if payload.get("ignorado"):
        print(f"Ignorado pela API: {path.name} -> {sha}")
    elif payload.get("sobrescrito"):
        print(f"Sobrescrito: {path.name} -> {sha}")
    else:
        print(f"Enviado: {path.name} -> {sha}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sincroniza documentacoes HTML com a API Django, enviando metadados junto ao arquivo."
    )
    parser.add_argument("--base-url", help="URL base da API Django. Env: DADOS_DOCS_API_BASE_URL")
    parser.add_argument("--token", help="Token ja emitido. Env: DADOS_DOCS_API_TOKEN")
    parser.add_argument("--username", help="Usuario para login. Env: DADOS_DOCS_API_USERNAME")
    parser.add_argument("--password", help="Senha para login. Env: DADOS_DOCS_API_PASSWORD")
    parser.add_argument("--force", action="store_true", help="Reenvia todos os arquivos e sobrescreve duplicados.")
    parser.add_argument(
        "--include-source-json",
        action="store_true",
        help="Tambem envia os JSONs fonte de cada HTML.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria enviado sem fazer upload.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    documents = discover_documents(REPORTS_DIR)
    print(f"Documentos encontrados em {REPORTS_DIR.relative_to(ROOT_DIR)}: {len(documents)}")
    for doc in documents:
        print(f"  {doc['html_path'].name} — {doc['titulo']}")

    base_url = env_or_arg(args.base_url, "DADOS_DOCS_API_BASE_URL")
    if not base_url:
        raise SystemExit("Informe --base-url ou DADOS_DOCS_API_BASE_URL.")
    base_url = normalize_base_url(base_url)
    print(f"Base URL da API: {base_url}")

    username = env_or_arg(args.username, "DADOS_DOCS_API_USERNAME")
    password = env_or_arg(args.password, "DADOS_DOCS_API_PASSWORD")
    token = get_token(base_url, username, password, env_or_arg(args.token, "DADOS_DOCS_API_TOKEN"))

    sync_documents(
        base_url,
        token,
        documents,
        force=args.force,
        include_source_json=args.include_source_json,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        response = exc.response
        detail = response.text if response is not None else str(exc)
        print(f"Erro HTTP ao sincronizar documentacoes: {detail}", file=sys.stderr)
        raise SystemExit(1) from exc
