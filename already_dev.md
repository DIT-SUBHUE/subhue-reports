# already_dev.md — Estado atual do desenvolvimento

## Estrutura de projeto

```
subhue-reports/
├── src/subhue_reports/     pacote principal (src layout)
│   └── registry/           único módulo implementado
├── tests/
│   ├── unit/               76 testes, todos passando
│   ├── integration/        marcados @pytest.mark.integration
│   ├── fixtures/           sample_data.csv, expected_report.html, sample_config.yaml
│   └── conftest.py
├── reference/              código de produção do airflow-astro (leitura, não modificar)
├── data/
│   └── manifest/           manifest baixado da API (gitignored)
├── pyproject.toml
├── justfile
├── .env / .env.example
└── IMPLEMENTATION.md       spec completa dos módulos pendentes
```

## Decisões de arquitetura

| Decisão | Escolha | Motivo |
|---|---|---|
| Layout de pacote | `src/subhue_reports/` | namespace claro, evita conflito com módulos genéricos |
| Python no justfile | `export PATH := ".venv/bin:..."` | resolve tanto shell quanto shebang recipes sem ativar venv |
| Armazenamento de manifest | `data/manifest/` (subdir) | consistente com `data/cache/` e `data/reports/`; escala para múltiplas tags |
| Auth na API | POST `/autenticacao/token/` → Token | alinhado com a DAG `dbt_publish_manifest` em produção |
| Nomes de env vars | prefixo `DBT_MANIFEST_API_*` | alinhado com variáveis já configuradas no ambiente |
| Loader unwrap | `_unwrap()` em todos os retornos | API envolve manifest em `{"manifest_content": {...}}`; desembrulha transparente |

## Módulo `registry` — implementado

### `loader.py`

```python
load_manifest(path=None, url=None) -> dict
build_registry(manifest) -> dict[str, dict]
_unwrap(data) -> dict   # interno
```

- `load_manifest` resolve source na ordem: `path arg → DBT_MANIFEST_PATH → url arg → DBT_MANIFEST_URL → data/manifest/manifest.json → ../airflow-astro/dbt/target/manifest.json`
- `_unwrap` desembrulha `manifest_content` do envelope da API em todos os caminhos de retorno
- `build_registry` extrai apenas nodes com `resource_type == "model"`; ignora sources, tests, snapshots
- Campos internos prefixados com `_`: `_fqn`, `_schema`, `_sql_checksum`, `_columns`, `_description`

### `updater.py`

```python
check_and_update(base_url, tag, manifest_path, meta_path, force) -> bool
fetch_remote_meta(base_url, tag) -> dict
fetch_manifest_content(base_url, tag) -> dict
load_local_meta(meta_path) -> dict | None
print_status(base_url, tag) -> None
_get_token(base_url) -> str
_auth_headers(base_url) -> dict
```

- Compara `updated_at` do `manifest.meta.json` local com `GET /api/dbt-manifest/?tag={tag}`
- Só baixa conteúdo completo se remoto for mais novo (ou `force=True`)
- `data/manifest/manifest.meta.json` armazena metadados da API + `fetched_at` local
- Executável direto: `python -m subhue_reports.registry.updater [--force] [--check-only]`

### `checker.py`

```python
check_sources(report_json, registry) -> list[dict]
```

### `catalog.py`

```python
catalog(registry) -> list[dict]             # visão compacta de todos os models
detail(name, registry) -> dict | None       # detalhe completo com columns e changelog
search(registry, layer, schema, status, name_contains) -> list[dict]  # busca filtrada
to_context(registry, models, include_columns) -> str  # texto compacto para injetar em prompt LLM
```

- `catalog` retorna campos LLM-relevantes: name, table, schema, layer, status, version, grain, description, primary_key
- `detail` adiciona: columns (name+desc+type), changelog, consumers, owner, slo, sql_checksum, fqn
- `to_context` produz plain text token-eficiente — formato `[schema.model] vX | layer | status` com grain/desc/pk/cols
- CLI direto: `python -m subhue_reports.registry.catalog [model_name] [--layer L] [--schema S] [--no-columns] [--json]`

- Cruza `meta.fontes` do JSON do relatório com versões atuais do registry
- Retorna lista de warnings: `versão desatualizada` ou `model não encontrado no registry`
- Executável direto: `python -m subhue_reports.registry.checker <report.json>`

## Manifest real (validado)

- **API:** `https://diid.subhue.org`
- **Tag:** `airflow_astro`
- **dbt version:** 1.11.11
- **Models:** 37
- **Último updated_at:** 2026-06-24T12:54:23-03:00
- **Arquivo local:** `data/manifest/manifest.json` (envelope da API desembrulhado via `_unwrap`)

## Testes

| Arquivo | Testes | Cobre |
|---|---|---|
| `unit/test_config.py` | 13 | env vars, auth token, check_and_update (skip/force/download/meta salvo/mkdir) |
| `unit/test_transform.py` | 14 | build_registry, check_sources, edge cases (checksum ausente, meta ausente, múltiplos problemas) |
| `unit/test_render_html.py` | 49 | helpers puros do renderer (importados de `reference/utils/`) |
| `unit/test_catalog.py` | 25 | catalog, detail, search, to_context — todas as funções públicas do catalog.py |
| `integration/test_db_query.py` | 5 | conexão Postgres, schemas existentes, endpoints da API |
| `integration/test_report_generation.py` | 3 | geração HTML end-to-end |

Testes de renderer importam de `reference/utils/gerador_relatorio_subhue.py` via `sys.path` no `conftest.py`. Quando `subhue_reports.renderer` for implementado, trocar os imports.

## Justfile — comandos ativos

```
manifest-update          verifica metadata e baixa se remoto mais novo
manifest-update-force    força download
manifest-status          compara local vs remoto sem baixar
manifest-versions        lista version de todos os models do manifest local
manifest-check <report>  valida fontes de um relatório

test                     pytest tests/unit/
test-integration         pytest -m integration
test-all                 pytest (tudo)
lint                     ruff check .
format                   ruff format .

cache-status             lista parquets em data/cache/
cache-clear              remove todos os parquets
dirs                     cria data/manifest data/cache data/reports
install                  pip install -r requirements.txt
env-setup                cp .env.example .env
```

## Variáveis de ambiente configuradas

```
DBT_MANIFEST_API_BASE_URL    URL base da API Django
DBT_MANIFEST_API_USERNAME    usuário para auth
DBT_MANIFEST_API_PASSWORD    senha (aspas simples no .env se tiver caracteres especiais)
DBT_MANIFEST_TAG             tag do manifest (default: airflow_astro)
DADOS_DOCS_API_BASE_URL      API de documentações
DADOS_DOCS_API_USERNAME      usuário sync
DADOS_DOCS_API_PASSWORD      senha sync
DBT_IP / DBT_PGPORT / DBT_DATABASE_NAME / DBT_USER / DBT_SENHA   banco dbt
SUBHUE_IP / SUBHUE_PGPORT / SUBHUE_DATABASE_NAME / SUBHUE_USER / SUBHUE_SENHA   banco subhue
```

## Pendente (ver IMPLEMENTATION.md para spec)

- `src/subhue_reports/cache/` — resolver.py, extractor.py, query.py
- `src/subhue_reports/renderer/` — relatorio.py, documentacao.py (portar de `reference/utils/`)
- `src/subhue_reports/audit/` — snapshot.py
- `src/subhue_reports/sync/` — client.py (portar de `reference/utils/sync_dados_documentacoes.py`)
