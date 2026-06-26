# already_dev.md — Estado atual do desenvolvimento

## Estrutura de projeto

```
subhue-reports/
├── src/subhue_reports/
│   ├── registry/           manifest dbt → modelos (implementado)
│   ├── cache/              Postgres → Parquet → DuckDB (implementado)
│   └── renderer/           JSON → HTML self-contained (implementado)
├── tests/
│   ├── unit/               179 testes, todos passando
│   ├── integration/        marcados @pytest.mark.integration
│   ├── fixtures/
│   └── conftest.py
├── reference/              código legado de airflow-astro (excluído do ruff)
├── data/
│   ├── manifest/           manifest baixado da API (gitignored)
│   ├── cache/              parquets + meta.json (gitignored)
│   └── reports/            HTML + JSON de saída (gitignored)
├── pyproject.toml
├── justfile
├── .env / .env.example
└── IMPLEMENTATION.md       spec original dos módulos
```

## Decisões de arquitetura

| Decisão | Escolha | Motivo |
|---|---|---|
| Layout de pacote | `src/subhue_reports/` | namespace claro, evita conflito com módulos genéricos |
| Python no justfile | `export PATH := ".venv/bin:..."` | resolve shell + shebang recipes sem ativar venv |
| Armazenamento de manifest | `data/manifest/` | consistente com `data/cache/` e `data/reports/` |
| Auth na API | POST `/autenticacao/token/` → Token | alinhado com a DAG `dbt_publish_manifest` em produção |
| Conexão banco | SUBHUE apenas | removido sistema de perfis (dbt/oracle); único alvo real |
| Seções como arquivos | `explode_report` / `assemble_report` | deletar arquivo = remover seção sem re-gastar tokens |
| `reference/` excluído do ruff | `exclude = ["reference"]` | código legado não refatorado, não é código ativo |

---

## Módulo `registry` — implementado

### `loader.py`

```python
load_manifest(path=None) -> dict
build_registry(manifest) -> dict[str, dict]        # nodes com resource_type == "model"
build_source_registry(manifest) -> dict[str, dict] # sources raw
```

- Campos internos prefixados com `_`: `_fqn`, `_schema`, `_sql_checksum`, `_columns`, `_description`
- `build_source_registry` expõe fontes separadas dos models; chave = `source_name.table_name`

### `updater.py`

```python
check_and_update(base_url, tag, manifest_path, meta_path, force) -> bool
```

- Compara `updated_at` do `manifest.meta.json` local com `GET /api/dbt-manifest/?tag={tag}`
- Executável direto: `python -m subhue_reports.registry.updater [--force] [--check-only]`

### `checker.py`

```python
check_sources(report_json, registry) -> list[dict]
```

### `catalog.py`

```python
catalog(registry) -> list[dict]
detail(name, registry) -> dict | None
search(registry, layer, schema, status, name_contains) -> list[dict]
to_context(registry, models, include_columns) -> str   # texto LLM-friendly
to_sources_context(sources, source_name, name_contains) -> str
```

- CLI: `python -m subhue_reports.registry.catalog [model] [--layer L] [--schema S] [--no-columns]`

---

## Módulo `cache` — implementado

### `connection.py`

```python
connection_params() -> ConnectionParams   # lê SUBHUE_* do .env
connect() -> PgConnection                 # readonly, sem args
```

### `extractor.py`

```python
extract_to_parquet(source, filters, parquet_path, meta_path, model_version, sql_checksum) -> Path
```

- psycopg2 → pyarrow (normaliza UUID, Decimal, datetime) → `.parquet`
- `.meta.json` companheiro com source, version, checksum, extracted_at, row_count

### `resolver.py`

```python
resolve_source(source, filters, registry, cache_dir) -> Path
```

- 3 camadas de invalidação: model_version, sql_checksum, TTL (`CACHE_TTL_HOURS`, default 4h)
- Log `cache hit` / `cache miss` via `logging`

### `query.py`

```python
query(sql, params=None) -> list[dict]
query_to_records(sql) -> list[dict]
```

- DuckDB executa SQL sobre parquets; suporta glob e JOIN entre fontes

---

## Módulo `renderer` — implementado

### `_html.py` — helpers compartilhados

```python
esc(text) -> str
fmt_num(value) -> str          # separador de milhar pt-BR
badge_class(pct) -> str        # hi/md/lo/na
render_badge_pct(pct, label) -> str
render_badge_label(label, nivel) -> str
render_pill(tipo, label) -> str
render_code(text) -> str
render_cell(value, col_tipo) -> str   # dispatch por tipo
deep_merge(base, override) -> dict
```

### `_plotly.py`

```python
PLOTLY_PALETTE: list[str]
PLOTLY_LAYOUT_DEFAULTS: dict
get_plotly_js() -> str
prepare_figure_json(fig_json) -> str
```

### `_meta.py`

```python
current_timestamp_iso() -> str
get_generation_timestamp(meta) -> str
ensure_generation_timestamp(payload) -> bool
```

### `sections.py` — seções como arquivos

```python
explode_report(dados, dest_dir) -> None    # salva meta.json + 01_<tipo>.json por seção
assemble_report(report_dir) -> dict        # lê meta.json + seções ordenadas → dict
list_sections(report_dir) -> list[tuple]   # [(idx, tipo, filename)]
```

### `relatorio.py`

- Seções: `contexto`, `tabela`, `grafico`, `metrica`, `texto`, `achados`, `excecao`, `recomendacao`
- `render_report(dados, plotly_js="") -> str`
- CLI: `python -m subhue_reports.renderer.relatorio <json|dir> [-o output.html]`
- E501 ignorado via `per-file-ignores` (CSS strings embutidos)

### `documentacao.py`

- Seções: `visao_geral`, `dependencias`, `colunas`, `especificacao`, `observacoes`, `changelog` + seções de relatório
- `render_doc(dados, plotly_js="") -> str`
- TOC automático com âncoras injetadas por `render_toc(secoes)`
- CLI: `python -m subhue_reports.renderer.documentacao <json|dir> [-o output.html]`

---

## Testes

| Arquivo | Testes | Cobre |
|---|---|---|
| `unit/test_config.py` | 15 | env vars, auth token, check_and_update |
| `unit/test_transform.py` | 14 | build_registry, check_sources, edge cases |
| `unit/test_catalog.py` | 25 | catalog, detail, search, to_context, to_sources_context |
| `unit/test_cache.py` | 30 | connection_params, resolve_source (hit/miss/TTL/checksum), extract_to_parquet |
| `unit/test_renderer.py` | 48 | esc, fmt_num, badge_class, render_cell, deep_merge, sections round-trip, render_report, render_doc |
| `unit/test_render_html.py` | 47 | helpers herdados (candidatos a remover quando reference/ for descontinuado) |
| `integration/test_cache_integration.py` | 1 | segunda chamada usa cache; bate em `raw_timed_dtw.fat_estabelecimento` |
| `integration/test_db_query.py` | — | conexão Postgres, schemas existentes |
| `integration/test_report_generation.py` | — | geração HTML end-to-end |

**Total unit:** 179 passando (`just test`)

---

## Justfile — comandos ativos

```
manifest-update          verifica metadata e baixa se remoto mais novo
manifest-update-force    força download
manifest-status          compara local vs remoto sem baixar
manifest-fetch           baixa direto sem verificação
manifest-versions        lista version de todos os models
manifest-check <report>  valida fontes de um relatório
manifest-catalog         lista models em formato LLM-friendly
manifest-catalog-full    com colunas (contexto completo)
manifest-catalog-model   detalhe de um model específico
manifest-catalog-layer   filtra por layer
manifest-catalog-schema  filtra por schema
manifest-catalog-search  busca por substring do nome
manifest-catalog-info    schemas e layers disponíveis
manifest-sources         fontes raw agrupadas por source_name
manifest-sources-group   fontes de um source_name específico
manifest-sources-search  busca fontes por substring

cache-status             lista parquets com version e data de extração
cache-clear              remove todos os parquets
cache-prune              remove parquets com versão desatualizada

query <sql>              executa SQL sobre parquets via DuckDB
duckdb-shell             shell DuckDB interativo

report-render <src>      JSON ou diretório → HTML de relatório
report-show <dir>        lista seções do diretório (idx, tipo, arquivo)
report-validate <json>   valida JSON contra schema e fontes
doc-render <src>         JSON ou diretório → HTML de documentação

sync-list                lista HTMLs prontos para sync
sync-push                envia para API Django
sync-push-force          envia sobrescrevendo existentes
sync-dry-run             simula sem enviar

test                     pytest tests/unit/
test-integration         pytest -m integration
test-all                 pytest (tudo)
lint                     ruff check .
format                   ruff format .
lint-fix                 ruff check --fix .
```

---

## Variáveis de ambiente

```
DBT_MANIFEST_API_BASE_URL    URL base da API Django (manifest)
DBT_MANIFEST_API_USERNAME    usuário auth
DBT_MANIFEST_API_PASSWORD    senha
DBT_MANIFEST_TAG             tag do manifest (default: airflow_astro)

DADOS_DOCS_API_BASE_URL      API de documentações
DADOS_DOCS_API_USERNAME      usuário sync
DADOS_DOCS_API_PASSWORD      senha sync

SUBHUE_IP / SUBHUE_PGPORT / SUBHUE_DATABASE_NAME / SUBHUE_USER / SUBHUE_SENHA
CACHE_TTL_HOURS              TTL do cache (default: 4)
```

---

## Pendente

- `src/subhue_reports/audit/snapshot.py` — `stamp_report(report_json, registry)` embute `meta.model_versions`
- `src/subhue_reports/sync/client.py` — port de `reference/utils/sync_dados_documentacoes.py`
