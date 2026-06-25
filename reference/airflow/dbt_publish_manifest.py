"""
DAG: dbt_publish_manifest

Gera manifest.json via `dbt parse` e publica na API de registry somente se o
conteúdo mudou. Roda a cada 30 minutos.

Fingerprint usa SHA-256 do manifest normalizado — exclui campos voláteis
(generated_at, invocation_id) que mudam a cada parse mesmo sem alterações reais.

Credenciais (prioridade: Airflow Variable > env var):
    DBT_MANIFEST_API_BASE_URL
    DBT_MANIFEST_API_USERNAME
    DBT_MANIFEST_API_PASSWORD
    DBT_MANIFEST_TAG  (default: airflow_astro)
    DBT_MANIFEST_API_LOCAL_ROUTE  (true/1 → roteia HTTPS para 127.0.0.1, preservando SNI/TLS)

Roteamento local (DBT_MANIFEST_API_LOCAL_ROUTE=true):
    Quando o domínio configurado resolve para o IP público do próprio servidor,
    o UFW (INPUT DROP) bloqueia conexões de loopback via IP público. Com esta
    opção, as requisições são conectadas a 127.0.0.1:443 mantendo SNI e
    validação de certificado intactos (sem verify=False).

Nota: manifest pendente é escrito em MANIFEST_PENDING_PATH entre as tasks.
Em ambiente single-node (local Astro) isso funciona sem configuração adicional.
Em K8s executor com múltiplos workers, o path precisa estar em PVC compartilhado.
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from airflow.sdk import dag, task
from pendulum import datetime as pendulum_datetime

log = logging.getLogger(__name__)

DBT_PROJECT_PATH = Path("/usr/local/airflow/dbt")
MANIFEST_PENDING_PATH = Path("/usr/local/airflow/artifacts/manifest_pending.json")
_DEFAULT_TAG = "airflow_astro"


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _resolve_dbt_executable() -> Path:
    candidates = [
        os.getenv("DBT_EXECUTABLE_PATH"),
        "/usr/local/airflow/dbt_venv/bin/dbt",
        shutil.which("dbt"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    return Path("dbt")


def _get_conf(key: str) -> str:
    """Lê configuração priorizando Airflow Variable sobre env var."""
    try:
        from airflow.models import Variable
        val = Variable.get(key, default_var=None)
        if val:
            return val
    except Exception:
        pass
    return os.getenv(key, "")


def _build_session(base_url: str) -> requests.Session:
    """
    Retorna uma Session configurada para roteamento local quando
    DBT_MANIFEST_API_LOCAL_ROUTE=true.

    Quando ativado, conecta em 127.0.0.1:<porta> em vez de resolver o DNS
    público (que aponta para o próprio servidor, bloqueado pelo UFW).
    O SNI e a verificação de certificado continuam usando o hostname original,
    garantindo segurança TLS completa.
    """
    session = requests.Session()

    if _get_conf("DBT_MANIFEST_API_LOCAL_ROUTE").lower() not in ("1", "true", "yes"):
        return session

    parsed = urlparse(base_url)
    hostname = parsed.hostname
    if not hostname:
        return session

    _hostname = hostname  # captura para closure

    class _LocalSNIAdapter(HTTPAdapter):
        """Redireciona TCP para 127.0.0.1 preservando SNI e validação de cert."""

        def send(self, request, **kwargs):
            p = urlparse(request.url)
            if p.hostname == _hostname:
                port = p.port or (443 if p.scheme == "https" else 80)
                request.url = urlunparse(p._replace(netloc=f"127.0.0.1:{port}"))
            return super().send(request, **kwargs)

        def _get_connection(self, url, proxies=None):
            conn = super()._get_connection(url, proxies)
            # Força verificação do cert e SNI contra o hostname original
            if hasattr(conn, "assert_hostname"):
                conn.assert_hostname = _hostname
            if hasattr(conn, "conn_kw"):
                conn.conn_kw["server_hostname"] = _hostname
            return conn

    adapter = _LocalSNIAdapter()
    session.mount(f"https://{hostname}", adapter)
    session.mount(f"http://{hostname}", adapter)
    log.info("Roteamento local ativo: %s → 127.0.0.1", hostname)
    return session


def _compute_fingerprint(manifest: dict) -> str:
    """
    SHA-256 estável do manifest.

    Exclui recursivamente chaves voláteis em qualquer nível da estrutura:
      - generated_at, invocation_id, invocation_started_at, run_started_at
        (campos de metadata do manifest)
      - created_at (presente em cada node; regenerado a cada dbt parse
        com --no-partial-parse mesmo sem mudanças no projeto)

    O restante (checksum SQL dos nodes, config, meta.version, sources, macros)
    é estável entre execuções quando o projeto não mudou.
    """
    _VOLATILE = frozenset({
        "generated_at",
        "invocation_id",
        "invocation_started_at",
        "run_started_at",
        "created_at",
        # path fields que referenciam --target-path (tempdir absoluto muda a cada run)
        "compiled_path",
        "build_path",
        "deferred_to_manifest_id",
        # telemetria dbt: UUID de sessão regenerado a cada parse
        "user_id",
    })

    def _strip(obj: object) -> object:
        if isinstance(obj, dict):
            return {k: _strip(v) for k, v in obj.items() if k not in _VOLATILE}
        if isinstance(obj, list):
            stripped = [_strip(i) for i in obj]
            # Ordena listas para eliminar não-determinismo de `sources` e `depends_on`
            # (dbt 1.11 não garante ordem estável entre parse runs)
            try:
                return sorted(
                    stripped,
                    key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False),
                )
            except TypeError:
                return stripped
        return obj

    return hashlib.sha256(
        json.dumps(_strip(manifest), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _get_token(
    base_url: str,
    username: str,
    password: str,
    session: requests.Session | None = None,
) -> str:
    http = session or requests
    resp = http.post(
        f"{base_url}/autenticacao/token/",
        json={"username": username, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["token"]


# ─── DAG ─────────────────────────────────────────────────────────────────────

@dag(
    dag_id="dbt_publish_manifest",
    description=(
        "Gera manifest.json via dbt parse e publica na API de registry "
        "somente se o conteúdo mudou desde a última publicação."
    ),
    default_args={
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=3),
        "retry_exponential_backoff": False,
        "email_on_failure": False,
    },
    start_date=pendulum_datetime(2024, 1, 1, tz="America/Sao_Paulo"),
    schedule="*/30 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["dbt", "registry", "manifest"],
)
def dbt_publish_manifest() -> None:

    @task(task_id="gerar_manifest")
    def gerar_manifest() -> str:
        """
        Executa `dbt parse`, persiste manifest em MANIFEST_PENDING_PATH
        e retorna o fingerprint estável para comparação na próxima task.

        dbt parse não conecta ao banco — usa apenas os arquivos YAML/SQL
        do projeto para montar o manifest.

        Usa profiles.yml dummy em tmp_dir: o profiles.yml real referencia
        env_var() do banco que não estão disponíveis no worker em produção,
        e dbt parse valida o arquivo mesmo sem conectar.
        """
        dbt_exe = _resolve_dbt_executable()

        _DUMMY_PROFILES = """\
timed_transforms:
  target: dev
  outputs:
    dev:
      type: postgres
      host: localhost
      port: 5432
      dbname: dummy
      user: dummy
      password: dummy
      schema: public
      threads: 1
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            profiles_path = Path(tmp_dir) / "profiles.yml"
            profiles_path.write_text(_DUMMY_PROFILES, encoding="utf-8")

            cmd = [
                str(dbt_exe), "parse",
                "--project-dir", str(DBT_PROJECT_PATH),
                "--profiles-dir", tmp_dir,
                "--target-path", tmp_dir,
                "--log-path", tmp_dir,
                "--no-partial-parse",
            ]
            log.info("Executando dbt parse: %s", " ".join(cmd))
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)

            if result.stdout:
                log.info("dbt parse stdout:\n%s", result.stdout)
            if result.stderr:
                log.warning("dbt parse stderr:\n%s", result.stderr)

            if result.returncode != 0:
                raise RuntimeError(
                    f"dbt parse falhou com código {result.returncode}.\n"
                    f"stdout: {result.stdout[:800]}\n"
                    f"stderr: {result.stderr[:800]}"
                )

            manifest_path = Path(tmp_dir) / "manifest.json"
            if not manifest_path.exists():
                raise FileNotFoundError(
                    f"manifest.json não encontrado em {tmp_dir} após dbt parse. "
                    "Verifique --target-path e permissões."
                )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        model_count = sum(
            1 for v in manifest.get("nodes", {}).values()
            if v.get("resource_type") == "model"
        )
        fingerprint = _compute_fingerprint(manifest)

        MANIFEST_PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PENDING_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False),
            encoding="utf-8",
        )

        section_fps = {
            section: _compute_fingerprint({section: manifest[section]})[:12]
            for section in manifest
        }
        log.info(
            "Manifest gerado | dbt_version=%s | models=%d | fingerprint=%.12s… | sections=%s",
            manifest.get("metadata", {}).get("dbt_version", "?"),
            model_count,
            fingerprint,
            section_fps,
        )

        # Diagnóstico: loga metadata stripped para identificar campo volátil
        _VOLATILE_DEBUG = frozenset({
            "generated_at", "invocation_id", "invocation_started_at",
            "run_started_at", "created_at", "compiled_path", "build_path",
            "deferred_to_manifest_id",
        })
        meta_stripped = {
            k: v for k, v in manifest.get("metadata", {}).items()
            if k not in _VOLATILE_DEBUG
        }
        log.info("metadata stripped: %s", json.dumps(meta_stripped, sort_keys=True))

        # Diagnóstico: fingerprint por node para achar qual varia
        node_fps = {
            uid: _compute_fingerprint(node)[:12]
            for uid, node in manifest.get("nodes", {}).items()
        }
        log.info("node fingerprints: %s", node_fps)

        # Diagnóstico: per-field fingerprint dos nodes conhecidos como voláteis
        _WATCH_NODES = {
            "model.timed_transforms.vw_monitoramento_acp_timed",
            "model.timed_transforms.mvw_censo_leito_ativo_qualificado_timed",
            "model.timed_transforms.vw_classificado_atendimento_azul_agg_mes_timed",
            "model.timed_transforms.vw_produto_saldo_timed",
        }
        for uid in _WATCH_NODES:
            node = manifest.get("nodes", {}).get(uid)
            if node:
                field_fps = {
                    k: _compute_fingerprint({k: v})[:12]
                    for k, v in node.items()
                }
                log.info("node field fingerprints [%s]: %s", uid.split(".")[-1], field_fps)

        return fingerprint

    @task(task_id="sincronizar_manifest")
    def sincronizar_manifest(fingerprint_local: str) -> None:
        """
        Fluxo de sincronização:
          1. Compara fingerprint_local com o último fingerprint publicado,
             armazenado em Airflow Variable DBT_MANIFEST_LAST_FINGERPRINT.
             - Iguais  → conteúdo não mudou, ignora (sem chamada à API de conteúdo).
             - Ausente ou diferentes → continua para publicação.
          2. Obtém token da API.
          3. Publica manifest atualizado via POST /api/dbt-manifest/.
          4. Atualiza Variable com o novo fingerprint.

        Comparação via Variable (não via download do conteúdo remoto) evita
        falsos positivos causados por reformatação/enriquecimento do JSON pela API
        ao armazenar, que alteraria o fingerprint recomputado mesmo sem mudanças reais.
        """
        from airflow.sdk import Variable  # noqa: PLC0415

        _VAR_FINGERPRINT = "DBT_MANIFEST_LAST_FINGERPRINT"

        # ── 1. Comparar com último fingerprint publicado ───────────────────────
        fingerprint_anterior = Variable.get(_VAR_FINGERPRINT, default=None)
        log.info(
            "Fingerprint local: %.12s… | Último publicado: %s",
            fingerprint_local,
            f"{fingerprint_anterior[:12]}…" if fingerprint_anterior else "ausente",
        )

        if fingerprint_anterior == fingerprint_local:
            log.info("Conteúdo idêntico — publicação ignorada.")
            return

        # ── 2. Autenticação ───────────────────────────────────────────────────
        base_url = _get_conf("DBT_MANIFEST_API_BASE_URL").rstrip("/")
        username  = _get_conf("DBT_MANIFEST_API_USERNAME")
        password  = _get_conf("DBT_MANIFEST_API_PASSWORD")
        tag       = _get_conf("DBT_MANIFEST_TAG") or _DEFAULT_TAG

        if not all([base_url, username, password]):
            raise ValueError(
                "Credenciais incompletas. Configure DBT_MANIFEST_API_BASE_URL, "
                "DBT_MANIFEST_API_USERNAME e DBT_MANIFEST_API_PASSWORD "
                "(Airflow Variables ou variáveis de ambiente)."
            )

        session = _build_session(base_url)
        token = _get_token(base_url, username, password, session)
        headers = {"Authorization": f"Token {token}"}
        log.info("Token obtido para usuário '%s'.", username)

        # ── 3. Publicar manifest ──────────────────────────────────────────────
        log.info("Conteúdo diferente — publicando manifest atualizado.")
        _publicar(base_url, headers, tag, fingerprint_local, session)

        # ── 4. Persistir fingerprint publicado ────────────────────────────────
        Variable.set(_VAR_FINGERPRINT, fingerprint_local)
        log.info("Fingerprint atualizado na Variable '%s'.", _VAR_FINGERPRINT)

    def _publicar(
        base_url: str,
        headers: dict,
        tag: str,
        fingerprint: str,
        session: requests.Session | None = None,
    ) -> None:
        if not MANIFEST_PENDING_PATH.exists():
            raise FileNotFoundError(
                f"Manifest pendente não encontrado em {MANIFEST_PENDING_PATH}. "
                "A task gerar_manifest pode ter falhado silenciosamente."
            )

        manifest = json.loads(MANIFEST_PENDING_PATH.read_text(encoding="utf-8"))

        http = session or requests
        resp = http.post(
            f"{base_url}/api/dbt-manifest/",
            headers={**headers, "Content-Type": "application/json"},
            json={"tag": tag, "manifest_content": manifest},
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        log.info(
            "Manifest publicado com sucesso | tag=%s | updated_at=%s | fingerprint=%.12s…",
            result.get("tag"),
            result.get("updated_at"),
            fingerprint,
        )

    fingerprint = gerar_manifest()
    sincronizar_manifest(fingerprint)


dbt_publish_manifest()
