# subhue-reports — Implementação

Sistema autônomo de consulta, geração de relatórios e documentações técnicas.
Desacoplado do repositório `airflow-astro`; consome artefatos dbt via API,
cacheia dados em Parquet e usa DuckDB como camada unificada de consulta.

---

## Arquitetura

```
airflow-astro (produtor)
  └── DAG dbt_publish_manifest
        └── dbt parse → fingerprint → POST /api/dbt-manifest/
                                              │
                                              ▼
                                  Django API (diid_django)
                                  /api/dbt-manifest/
                                  /api/dados-documentacoes/
                                              │
                         ┌────────────────────┘
                         ▼
              subhue-reports (este repo)
              ┌─────────────────────────────────┐
              │  registry/   manifest → modelos  │
              │  cache/      Postgres → Parquet  │
              │  query/      DuckDB unificado    │
              │  renderer/   JSON → HTML         │
              │  sync/       HTML → API Django   │
              └─────────────────────────────────┘
```

---

## Estrutura do Repositório

```
subhue-reports/
├── src/
│   └── subhue_reports/
│       ├── registry/          # consome manifest da API
│       │   ├── loader.py      # GET /api/dbt-manifest/ → dict de modelos
│       │   ├── updater.py     # compara metadados e atualiza manifest local
│       │   └── checker.py     # valida fontes do relatório vs versões atuais
│       ├── cache/             # Postgres → Parquet → DuckDB
│       │   ├── resolver.py    # cache hit/miss com .meta.json por arquivo
│       │   ├── extractor.py   # Postgres → .parquet via db_query
│       │   └── query.py       # DuckDB executor (parquet ou live)
│       ├── renderer/          # gerador HTML self-contained
│       │   ├── relatorio.py   # extraído de reference/utils/gerador_relatorio_subhue.py
│       │   └── documentacao.py
│       ├── audit/
│       │   └── snapshot.py    # embute {source: version} no meta do JSON ao gerar
│       └── sync/
│           └── client.py      # extraído de reference/utils/sync_dados_documentacoes.py
├── tests/
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_transform.py
│   │   └── test_render_html.py
│   ├── integration/
│   │   ├── test_db_query.py
│   │   └── test_report_generation.py
│   ├── fixtures/
│   │   ├── sample_data.csv
│   │   ├── expected_report.html
│   │   └── sample_config.yaml
│   └── conftest.py
├── reference/             # artefatos copiados de airflow-astro como base
│   ├── airflow/
│   │   └── dbt_publish_manifest.py   # DAG Airflow já em produção
│   └── utils/
│       ├── gerador_relatorio_subhue.py
│       ├── gerador_documentacao_subhue.py
│       ├── report_metadata.py
│       ├── sync_dados_documentacoes.py
│       ├── db_query.py
│       └── diid_vertical_fix.svg
├── data/
│   ├── cache/             # .parquet + .meta.json (gitignored)
│   └── reports/           # HTML + JSON de saída (gitignored)
├── pyproject.toml         # config do projeto, pytest, ruff
├── justfile               # comandos de operação
├── CLAUDE.md              # boas práticas para dev com IA
├── IMPLEMENTATION.md      # este arquivo
└── .env.example
```

---

## 1. Registry — Manifest dbt

### Fluxo de publicação (Airflow → Django)

DAG `dbt_publish_manifest` em `airflow-astro` roda a cada 30 minutos:

1. `dbt parse` com profiles dummy (sem conexão ao banco)
2. Calcula fingerprint estável do manifest (exclui timestamps/invocation_id)
3. `GET /api/dbt-manifest/?tag=airflow_astro` — verifica existência
4. Se 404 → publica direto
5. Se 200 → `GET /api/dbt-manifest/airflow_astro/content/` → compara fingerprint
6. Se diferente → `POST /api/dbt-manifest/` com manifest completo
7. Se igual → ignora

Referência: `reference/airflow/dbt_publish_manifest.py`

### Fingerprint estável

```python
# Campos excluídos (mudam a cada dbt parse sem alteração real):
VOLATILE = {"generated_at", "invocation_id", "invocation_started_at", "run_started_at"}

def _compute_fingerprint(manifest: dict) -> str:
    stable = dict(manifest)
    stable["metadata"] = {k: v for k, v in stable["metadata"].items() if k not in VOLATILE}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
```

Campos estáveis relevantes por node:
- `checksum.checksum` — SHA256 do arquivo `.sql` (nativo dbt)
- `meta.version` — versão semântica do YAML (`meta.version: "1.0.2"`)
- `meta.layer`, `meta.status`, `meta.grain`, `meta.changelog`

### Loader no subhue-reports

```python
# subhue_reports/registry/loader.py

def load_manifest(path: str | None = None, url: str | None = None) -> dict:
    """Carrega manifest de path local, URL HTTP ou fallback de desenvolvimento."""
    source = path or os.getenv("SUBHUE_MANIFEST_PATH") or url or os.getenv("SUBHUE_MANIFEST_URL")

    if not source:
        # fallback dev: manifest local do airflow-astro
        default = Path("../airflow-astro/dbt/target/manifest.json")
        if default.exists():
            return json.loads(default.read_text())
        raise RuntimeError("Configure SUBHUE_MANIFEST_PATH ou SUBHUE_MANIFEST_URL")

    if source.startswith("http"):
        token = os.getenv("SUBHUE_MANIFEST_TOKEN", "")
        headers = {"Authorization": f"Token {token}"} if token else {}
        r = requests.get(source, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()

    return json.loads(Path(source).read_text())


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
```

### Checker de fontes

```python
# subhue_reports/registry/checker.py

def check_sources(report_json: dict, registry: dict) -> list[dict]:
    """
    Cruza fontes declaradas no JSON do relatório com versões atuais do registry.
    Retorna lista de warnings; lista vazia = tudo ok.
    """
    warnings = []
    for fonte in report_json.get("meta", {}).get("fontes", []):
        model_name = fonte.split(".")[-1]
        current = registry.get(model_name)
        if not current:
            warnings.append({"fonte": fonte, "issue": "model não encontrado no registry"})
            continue
        snapshotted = report_json["meta"].get("model_versions", {}).get(fonte)
        if snapshotted and snapshotted != current.get("version"):
            warnings.append({
                "fonte": fonte,
                "issue": "versão desatualizada",
                "no_relatorio": snapshotted,
                "atual": current.get("version"),
            })
    return warnings
```

---

## 2. Cache — Parquet + DuckDB

### Conceito

Cada fonte consultada é salva como `.parquet` com um `.meta.json` companheiro.
DuckDB executa SQL unificado tanto sobre parquet local quanto sobre Postgres ao vivo.

```
data/cache/
  silver_timed.fat_censo_leito_ativo_2026-06.parquet
  silver_timed.fat_censo_leito_ativo_2026-06.meta.json
  gold_timed.atendimento_emergencia_agg_2026-06.parquet
  gold_timed.atendimento_emergencia_agg_2026-06.meta.json
```

### Formato do .meta.json

```json
{
  "source": "silver_timed.fat_censo_leito_ativo",
  "model_version": "1.0.2",
  "sql_checksum": "96108a60...",
  "extracted_at": "2026-06-24T10:30:00-03:00",
  "query_hash": "sha256:abc123...",
  "filters": {"periodo": "2026-06"},
  "row_count": 45231
}
```

### Resolver — lógica de cache hit/miss

```python
# subhue_reports/cache/resolver.py

def resolve_source(
    source: str,
    filters: dict,
    registry: dict,
    cache_dir: Path = Path("data/cache"),
) -> Path:
    """
    Retorna path do parquet válido (cache hit) ou extrai do banco (cache miss).

    Cache hit: parquet existe E model_version == versão atual no registry.
    Cache miss: extrai via db_query → salva parquet + meta.json.
    """
    model_name = source.split(".")[-1]
    periodo = filters.get("periodo", "sem-periodo")
    parquet_path = cache_dir / f"{source}_{periodo}.parquet"
    meta_path = parquet_path.with_suffix(".meta.json")

    current_version = registry.get(model_name, {}).get("version", "")
    current_checksum = registry.get(model_name, {}).get("_sql_checksum", "")

    if parquet_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("model_version") == current_version and meta.get("sql_checksum") == current_checksum:
            return parquet_path  # cache hit

    # cache miss → extrai
    return extract_to_parquet(source, filters, parquet_path, meta_path, current_version, current_checksum)
```

### Extrator — Postgres → Parquet

```python
# subhue_reports/cache/extractor.py
# Usa db_query.py via subprocess (referência: reference/utils/db_query.py)
# Futuramente: migrar para DuckDB postgres_scanner direto

import subprocess, json, hashlib
from pathlib import Path
import duckdb

def extract_to_parquet(
    source: str,
    filters: dict,
    parquet_path: Path,
    meta_path: Path,
    model_version: str,
    sql_checksum: str,
) -> Path:
    schema, table = source.rsplit(".", 1)
    where_clauses = _build_where(filters)
    sql = f"SELECT * FROM {schema}.{table}{' WHERE ' + where_clauses if where_clauses else ''}"

    query_hash = hashlib.sha256(sql.encode()).hexdigest()

    # executa via db_query.py (perfil dbt) — stdout é CSV/JSON
    result = subprocess.run(
        [".venv/bin/python", "utils/db_query.py", "--profile", "dbt", "--format", "parquet",
         "--output", str(parquet_path)],
        input=sql, text=True, capture_output=True, check=True,
    )

    meta = {
        "source": source,
        "model_version": model_version,
        "sql_checksum": sql_checksum,
        "extracted_at": datetime.now().astimezone().isoformat(),
        "query_hash": f"sha256:{query_hash[:16]}",
        "filters": filters,
        "row_count": duckdb.sql(f"SELECT count(*) FROM '{parquet_path}'").fetchone()[0],
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return parquet_path
```

### Query — DuckDB unificado

```python
# subhue_reports/cache/query.py

import duckdb

def query(sql: str, params: dict | None = None) -> list[dict]:
    """
    Executa SQL sobre parquets em data/cache/ via DuckDB.

    Uso no SQL:
        FROM 'data/cache/silver_timed.fat_censo_leito_ativo_2026-06.parquet'
        -- ou glob para múltiplos períodos:
        FROM 'data/cache/silver_timed.fat_censo_leito_ativo_*.parquet'
        -- ou join entre fontes:
        FROM 'data/cache/silver_timed.fat_censo_leito_ativo_2026-06.parquet' c
        JOIN 'data/cache/gold_timed.atendimento_emergencia_agg_2026-06.parquet' a
          ON c.estabelecimento_gid = a.estabelecimento_gid
    """
    con = duckdb.connect()
    rel = con.sql(sql)
    columns = [desc[0] for desc in rel.description]
    return [dict(zip(columns, row)) for row in rel.fetchall()]


def query_to_records(sql: str) -> list[dict]:
    """Atalho para scripts de geração de relatório."""
    return query(sql)
```

---

## 3. Renderer — HTML Self-Contained

Extraído diretamente de `reference/utils/gerador_relatorio_subhue.py` e
`reference/utils/gerador_documentacao_subhue.py`.

### Tipos de seção disponíveis (relatório)

| Tipo | Campos principais |
|---|---|
| `contexto` | `objetivo`, `descricao` |
| `metrica` | `titulo`, `items[]{valor, label, sub, cor}` |
| `tabela` | `titulo`, `colunas[]{label, tipo}`, `linhas` |
| `grafico` | `titulo`, `figura` (Plotly Figure JSON) |
| `achados` | `items[]{tipo, titulo, texto}` |
| `excecao` | `titulo`, `descricao`, `colunas`, `linhas`, `stats` |
| `recomendacao` | `titulo`, `campos[]{label, valor}` |
| `texto` | `titulo`, `paragrafos` |

### Tipos de coluna de tabela

`texto` · `numero` · `badge_pct` · `badge_label` · `codigo` · `pill`

### Uso

```python
from subhue_reports.renderer.relatorio import gerar_relatorio

gerar_relatorio(
    json_path="data/reports/meu_relatorio.json",
    output_path="data/reports/meu_relatorio.html",
)
```

---

## 4. Audit Snapshot

Ao gerar um relatório, o sistema registra quais versões de modelo estavam ativas:

```python
# subhue_reports/audit/snapshot.py

def stamp_report(report_json: dict, registry: dict) -> dict:
    """
    Adiciona meta.model_versions ao JSON do relatório antes de renderizar.
    Permite auditoria retroativa: qual versão do model estava vigente.
    """
    fontes = report_json.get("meta", {}).get("fontes", [])
    model_versions = {}
    for fonte in fontes:
        model_name = fonte.split(".")[-1]
        if model_name in registry:
            model_versions[fonte] = registry[model_name].get("version", "")
    report_json["meta"]["model_versions"] = model_versions
    return report_json
```

JSON resultante:
```json
{
  "meta": {
    "titulo": "Relatório de Altas",
    "fontes": ["silver_timed.fat_censo_leito_ativo"],
    "model_versions": {
      "silver_timed.fat_censo_leito_ativo": "1.0.2"
    }
  }
}
```

---

## 5. Sync — Publicar na API Django

Extraído de `reference/utils/sync_dados_documentacoes.py`.

```python
# subhue_reports/sync/client.py

def sync(
    reports_dir: Path = Path("data/reports"),
    base_url: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Descobre pares HTML+JSON em reports_dir e envia para a API Django.
    Pula arquivos já existentes (a menos que force=True).
    """
    ...
```

Endpoint: `POST /api/dados-documentacoes/documentacoes/`

---

## 6. Justfile — Comandos de Operação

```justfile
# justfile

set dotenv-load := true

# ── Manifest ──────────────────────────────────────────────────────────────────

# Baixa manifest mais recente da API e salva localmente
manifest-fetch:
    python -c "
import requests, json, os
r = requests.get(
    os.environ['SUBHUE_MANIFEST_URL'],
    headers={'Authorization': 'Token ' + os.environ['SUBHUE_MANIFEST_TOKEN']},
    timeout=30
)
r.raise_for_status()
open('data/manifest.json', 'w').write(r.text)
print('manifest.json atualizado')
"

# Mostra versões de todos os models do manifest local
manifest-versions:
    python -c "
import json
manifest = json.load(open('data/manifest.json'))
models = {
    v['name']: v.get('meta', {}).get('version', '-')
    for v in manifest['nodes'].values()
    if v.get('resource_type') == 'model'
}
for name, ver in sorted(models.items()):
    print(f'{ver:12} {name}')
"

# Verifica se fontes de um relatório estão na versão atual
manifest-check report:
    python -m subhue_reports.registry.checker {{report}}

# ── Cache ──────────────────────────────────────────────────────────────────────

# Lista parquets em cache com status (ok/stale)
cache-status:
    python -c "
from pathlib import Path
import json
for meta_file in sorted(Path('data/cache').glob('*.meta.json')):
    meta = json.loads(meta_file.read_text())
    print(f\"{meta['source']:50} v{meta['model_version']:8} extraído {meta['extracted_at'][:10]}\")
"

# Remove todos os parquets do cache
cache-clear:
    find data/cache -name '*.parquet' -o -name '*.meta.json' | xargs rm -f
    @echo "cache limpo"

# Remove parquets com versão desatualizada (compara com manifest local)
cache-prune:
    python -m subhue_reports.cache.resolver --prune

# ── Consulta (DuckDB) ─────────────────────────────────────────────────────────

# Executa SQL sobre parquets do cache
query sql:
    python -c "
from subhue_reports.cache.query import query
import json
rows = query('{{sql}}')
print(json.dumps(rows[:20], ensure_ascii=False, indent=2))
"

# Shell DuckDB interativo sobre o cache
duckdb-shell:
    duckdb -c "PRAGMA database_list;" && duckdb

# ── Relatórios ────────────────────────────────────────────────────────────────

# Gera HTML a partir de JSON já construído
report-render json:
    python -m subhue_reports.renderer.relatorio {{json}} \
        -o data/reports/$(basename {{json}} .json).html

# Valida JSON de relatório contra schema e fontes
report-validate json:
    python -m subhue_reports.registry.checker {{json}}

# ── Documentações ─────────────────────────────────────────────────────────────

# Gera HTML de documentação a partir de JSON
doc-render json:
    python -m subhue_reports.renderer.documentacao {{json}} \
        -o data/reports/$(basename {{json}} .json).html

# ── Sync ──────────────────────────────────────────────────────────────────────

# Lista documentos em data/reports prontos para sync
sync-list:
    python -m subhue_reports.sync.client --list

# Envia novos HTMLs para API Django (skip duplicatas)
sync-push:
    python -m subhue_reports.sync.client \
        --base-url $DADOS_DOCS_API_BASE_URL \
        --username $DADOS_DOCS_API_USERNAME \
        --password $DADOS_DOCS_API_PASSWORD

# Envia todos (sobrescreve existentes)
sync-push-force:
    python -m subhue_reports.sync.client \
        --base-url $DADOS_DOCS_API_BASE_URL \
        --username $DADOS_DOCS_API_USERNAME \
        --password $DADOS_DOCS_API_PASSWORD \
        --force

# Simula sync sem enviar
sync-dry-run:
    python -m subhue_reports.sync.client \
        --base-url $DADOS_DOCS_API_BASE_URL \
        --username $DADOS_DOCS_API_USERNAME \
        --password $DADOS_DOCS_API_PASSWORD \
        --dry-run

# ── Setup ─────────────────────────────────────────────────────────────────────

# Instala dependências
install:
    pip install -r requirements.txt

# Cria diretórios de dados
dirs:
    mkdir -p data/cache data/reports data

# Copia .env.example para .env
env-setup:
    cp .env.example .env
    @echo "edite .env com suas credenciais"
```

---

## 7. Variáveis de Ambiente

```bash
# .env.example

# ── Manifest API ──────────────────────────────────────────────────────────────
SUBHUE_MANIFEST_URL=https://diid.exemplo.gov.br/api/dbt-manifest/airflow_astro/content/
SUBHUE_MANIFEST_TOKEN=seu-token-aqui
# alternativa: path local (desenvolvimento)
# SUBHUE_MANIFEST_PATH=../airflow-astro/dbt/target/manifest.json

# ── Dados Documentações API ───────────────────────────────────────────────────
DADOS_DOCS_API_BASE_URL=https://diid.exemplo.gov.br
DADOS_DOCS_API_USERNAME=usuario_api
DADOS_DOCS_API_PASSWORD=senha-segura

# ── Banco de dados (perfil dbt) ───────────────────────────────────────────────
DBT_IP=host-do-banco
DBT_PGPORT=5432
DBT_DATABASE_NAME=nome-do-banco
DBT_USER=usuario
DBT_SENHA=senha

# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_DIR=data/cache
REPORTS_DIR=data/reports
```

---

## 8. Dependências (requirements.txt)

```
# renderer
plotly>=5.0

# cache e query
duckdb>=0.10
pyarrow>=14.0

# registry / sync / http
requests>=2.31

# banco (extração)
psycopg2-binary>=2.9

# utilitários
pyyaml>=6.0
```

---

## 9. Fluxo Completo de Geração de Relatório

```
1. manifest-fetch
   └── GET /api/dbt-manifest/airflow_astro/content/ → data/manifest.json

2. registry.loader.build_registry(manifest)
   └── dict {model_name: {version, sql_checksum, ...}}

3. Para cada fonte necessária:
   cache.resolver.resolve_source(fonte, filtros, registry)
   ├── cache hit  → retorna path do .parquet existente
   └── cache miss → Postgres → .parquet + .meta.json → retorna path

4. cache.query.query(sql sobre parquets)
   └── DuckDB executa SQL unificado → rows

5. Monta report_json (meta + secoes)
   audit.snapshot.stamp_report(report_json, registry)
   └── adiciona meta.model_versions

6. registry.checker.check_sources(report_json, registry)
   └── warnings se fontes desatualizadas

7. renderer.relatorio.gerar_relatorio(json_path, output_path)
   └── HTML self-contained em data/reports/

8. sync.client.sync(dry_run=False)
   └── POST /api/dados-documentacoes/documentacoes/
```

---

## 10. API Django — Endpoints Necessários

### Manifest (app `dbt_manifest`)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/dbt-manifest/` | Publica manifest (cria ou sobrescreve por tag) |
| `GET` | `/api/dbt-manifest/?tag=airflow_astro` | Metadados do manifest (sem conteúdo) |
| `GET` | `/api/dbt-manifest/{tag}/content/` | Conteúdo completo do manifest |

Campos retornados pelo GET metadata:
```json
{"id": 1, "tag": "airflow_astro", "created_at": "...", "updated_at": "..."}
```

### Documentações (app `dados_documentacoes`)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/dados-documentacoes/documentacoes/` | Upload de HTML + metadados |
| `GET` | `/api/dados-documentacoes/documentacoes/listar/` | Lista arquivos existentes |

### Autenticação

```
POST /autenticacao/token/
body: {"username": "...", "password": "..."}
retorno: {"token": "..."}
header: Authorization: Token <token>
```

---

## 11. Referências

| Arquivo | Origem | Uso |
|---|---|---|
| `reference/utils/gerador_relatorio_subhue.py` | `airflow-astro/utils/` | Base do `renderer/relatorio.py` |
| `reference/utils/gerador_documentacao_subhue.py` | `airflow-astro/utils/` | Base do `renderer/documentacao.py` |
| `reference/utils/report_metadata.py` | `airflow-astro/utils/` | Helpers de timestamp — reusar direto |
| `reference/utils/sync_dados_documentacoes.py` | `airflow-astro/utils/` | Base do `sync/client.py` |
| `reference/utils/db_query.py` | `airflow-astro/utils/` | Extração Postgres — reusar ou adaptar |
| `reference/utils/diid_vertical_fix.svg` | `airflow-astro/utils/` | Logo DIID — copiar para assets |
| `reference/airflow/dbt_publish_manifest.py` | `airflow-astro/dags/` | DAG já em produção — não modificar aqui |
