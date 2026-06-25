# subhue-reports

Sistema de consulta e geração de relatórios sobre dados hospitalares.
Consome artefatos dbt via API, expõe metadados do manifest e gera HTMLs self-contained.

---

## Arquitetura

```
Django API (diid.subhue.org)
  /api/dbt-manifest/          → manifest dbt com metadados de modelos
  /api/dados-documentacoes/   → endpoint de publicação de relatórios

subhue-reports
  registry/   manifest → catálogo de modelos e fontes
  cache/      Postgres → Parquet (pendente)
  renderer/   JSON → HTML self-contained (pendente)
  audit/      stamp de versões no JSON do relatório (pendente)
  sync/       HTML → API Django (pendente)
```

---

## Módulos implementados

### `registry/loader.py`

Carrega o manifest dbt e constrói registries de modelos e fontes.

```python
from subhue_reports.registry.loader import load_manifest, build_registry, build_source_registry

manifest = load_manifest()                    # resolve source automaticamente
registry = build_registry(manifest)           # dict[model_name, RegistryEntry]
sources  = build_source_registry(manifest)    # dict["source.table", SourceEntry]
```

**`load_manifest(path, url)`** — ordem de resolução:
1. `path` arg
2. `DBT_MANIFEST_PATH` env
3. `url` arg
4. `DBT_MANIFEST_URL` env
5. `data/manifest/manifest.json`
6. `../airflow-astro/dbt/target/manifest.json`

**`RegistryEntry`** (TypedDict) — campos relevantes:

| Campo | Tipo | Origem |
|---|---|---|
| `version` | str | `meta.version` no YAML dbt |
| `layer` | str | `meta.layer` (`silver`, `gold`) |
| `status` | str | `meta.status` (`stable`, `experimental`) |
| `grain` | str | `meta.grain` |
| `primary_key` | list[str] | `meta.primary_key` |
| `_schema` | str | schema do modelo no banco |
| `_sql_checksum` | str | SHA256 do arquivo `.sql` |
| `_columns` | dict | colunas com descrições |
| `_description` | str | descrição do modelo |

**`SourceEntry`** (TypedDict) — campos relevantes:

| Campo | Tipo | Significado |
|---|---|---|
| `source_name` | str | grupo lógico (ex: `raw_timed_dtw`) |
| `name` | str | nome da tabela |
| `schema` | str | schema real no banco |
| `description` | str | descrição da tabela |
| `source_description` | str | descrição do grupo |
| `_columns` | dict | colunas com descrições |
| `_relation_name` | str | nome qualificado no banco |

---

### `registry/updater.py`

Compara `updated_at` do manifest local com a API. Baixa só se remoto for mais novo.

```python
from subhue_reports.registry.updater import check_and_update, print_status

updated = check_and_update(force=False)   # bool — True se baixou
print_status(base_url, tag)               # exibe local vs remoto sem baixar
```

Arquivos gerados:
- `data/manifest/manifest.json` — manifest completo
- `data/manifest/manifest.meta.json` — metadados da API + `fetched_at` local

---

### `registry/checker.py`

Valida se fontes declaradas em um relatório estão na versão atual do registry.

```python
from subhue_reports.registry.checker import check_sources

warnings = check_sources(report_json, registry)
# [] = tudo ok
# [{"fonte": "silver_timed.fat_censo_leito_ativo", "issue": "versão desatualizada",
#   "no_relatorio": "1.0.0", "atual": "1.0.2"}]
```

---

### `registry/catalog.py`

Vistas LLM-friendly do manifest. Funções de modelos e fontes são **separadas** por design.

#### Modelos

```python
from subhue_reports.registry.catalog import catalog, detail, search, to_context

catalog(registry)                               # list[ModelCatalogEntry] — todos os modelos
detail("fat_censo_leito_ativo", registry)       # ModelDetail | None — com colunas e changelog
search(registry, layer="gold", status="stable") # list[ModelCatalogEntry] — filtrado
to_context(registry, include_columns=False)     # str — pronto para injetar em prompt
```

**`to_context()`** — formato de saída:
```
MANIFEST MODELS (37 total)
schemas: gold_timed, raw_sarah, silver_timed | layers: gold, silver

[silver_timed.fat_censo_leito_ativo_timed] v1.0.1 | silver | stable
  grain: 1 linha por leito_gid
  desc: Tabela Silver do estado atual dos leitos hospitalares...
  pk: leito_gid
  cols: leito_gid (Grain da tabela...); secao_gid (...); ...
```

#### Fontes

```python
from subhue_reports.registry.catalog import source_catalog, to_sources_context

source_catalog(sources, source_name="raw_timed_dtw")   # list[SourceEntry]
to_sources_context(sources, source_name="raw_sarah")   # str — pronto para prompt
```

**`to_sources_context()`** — formato de saída:
```
MANIFEST SOURCES (68 tabelas | 5 grupos)

[raw_timed_dtw] schema=raw_timed_dtw (57 tabelas)
  Dados brutos ingeridos pelo Airbyte
  - fat_censo_ativo (20 cols): Tabela de fatos com o estado atual dos leitos...
  - fat_paciente_rede (15 cols): ...
```

---

## Variáveis de ambiente

| Variável | Uso |
|---|---|
| `DBT_MANIFEST_API_BASE_URL` | URL base da API Django (ex: `https://diid.subhue.org`) |
| `DBT_MANIFEST_API_USERNAME` | usuário para auth |
| `DBT_MANIFEST_API_PASSWORD` | senha para auth |
| `DBT_MANIFEST_TAG` | tag do manifest (default: `airflow_astro`) |
| `DBT_MANIFEST_PATH` | path local do manifest (alternativa à API) |
| `DBT_MANIFEST_URL` | URL direta do manifest (alternativa à API) |
| `DADOS_DOCS_API_BASE_URL` | API de publicação de relatórios |
| `DADOS_DOCS_API_USERNAME` | usuário sync |
| `DADOS_DOCS_API_PASSWORD` | senha sync |
| `DBT_IP` / `DBT_PGPORT` / `DBT_DATABASE_NAME` / `DBT_USER` / `DBT_SENHA` | banco dbt |
| `SUBHUE_IP` / `SUBHUE_PGPORT` / `SUBHUE_DATABASE_NAME` / `SUBHUE_USER` / `SUBHUE_SENHA` | banco subhue |

---

## Comandos just

### Manifest

```bash
just manifest-update          # verifica e baixa se remoto mais novo
just manifest-update-force    # força download
just manifest-status          # compara local vs remoto sem baixar
just manifest-versions        # lista versões de todos os modelos
just manifest-check <report>  # valida fontes de um relatório JSON
```

### Catalog — modelos

```bash
just manifest-catalog                   # todos os modelos (sem colunas)
just manifest-catalog-full              # todos os modelos com colunas
just manifest-catalog-model <name>      # detalhe de um modelo
just manifest-catalog-layer <layer>     # filtra por layer (silver, gold)
just manifest-catalog-schema <schema>   # filtra por schema
just manifest-catalog-search <name>     # busca por substring do nome
just manifest-catalog-info              # overview: schemas, layers, source_names
```

### Catalog — fontes

```bash
just manifest-sources                   # todas as fontes agrupadas por source_name
just manifest-sources-group <group>     # fontes de um grupo (ex: raw_timed_dtw)
just manifest-sources-search <name>     # busca por substring do nome da tabela
```

### Cache / Relatórios

```bash
just cache-status             # lista parquets em data/cache/
just cache-clear              # remove todos os parquets
just report-render <json>     # gera HTML a partir de JSON
just sync-push                # envia relatórios para API Django
just sync-dry-run             # simula sync sem enviar
```

### Dev

```bash
just test                     # pytest tests/unit/
just test-integration         # pytest -m integration
just lint                     # ruff check
just format                   # ruff format
just dirs                     # cria data/manifest data/cache data/reports
```

---

## Manifest dbt — estrutura relevante

```
manifest.json
  nodes.<unique_id>
    resource_type: "model"
    name: "fat_censo_leito_ativo_timed"
    schema: "silver_timed"
    fqn: ["timed_transforms", "silver_timed", "fat_censo_leito_ativo_timed"]
    description: "..."
    checksum.checksum: "<sha256 do .sql>"
    meta:
      version: "1.0.1"
      layer: "silver"
      status: "stable"
      grain: "1 linha por leito_gid"
      primary_key: ["leito_gid"]
      changelog: [{date, version, type, summary}]
    columns.<col_name>:
      description: "..."
      data_type: null | "uuid" | ...

  sources.<unique_id>
    resource_type: "source"
    source_name: "raw_timed_dtw"
    name: "fat_censo_ativo"
    schema: "raw_timed_dtw"
    description: "..."
    source_description: "Dados brutos ingeridos pelo Airbyte"
    relation_name: '"db"."raw_timed_dtw"."fat_censo_ativo"'
    columns.<col_name>:
      description: "..."
```

**Manifest atual (2026-06-24):** 37 modelos · 68 fontes · dbt 1.11.11 · tag `airflow_astro`

---

## Fluxo de geração de relatório

```
1. manifest-update
   └── GET /api/dbt-manifest/airflow_astro/content/ → data/manifest/manifest.json

2. build_registry(manifest)       → {model_name: RegistryEntry}
   build_source_registry(manifest) → {"source.table": SourceEntry}

3. Para cada fonte:
   cache.resolver.resolve_source(fonte, filtros, registry)
   ├── cache hit  → data/cache/<fonte>_<periodo>.parquet
   └── cache miss → Postgres → .parquet + .meta.json

4. cache.query.query(sql sobre parquets) → rows

5. Monta report_json
   audit.snapshot.stamp_report(report_json, registry)
   └── adiciona meta.model_versions

6. registry.checker.check_sources(report_json, registry)
   └── warnings se fontes desatualizadas

7. renderer.relatorio.gerar_relatorio(json_path, output_path)
   └── data/reports/<nome>.html

8. sync.client.sync() → POST /api/dados-documentacoes/documentacoes/
```

---

## Pendente

| Módulo | Status |
|---|---|
| `cache/resolver.py` | não implementado |
| `cache/extractor.py` | não implementado |
| `cache/query.py` | não implementado |
| `renderer/relatorio.py` | não implementado (base em `reference/utils/gerador_relatorio_subhue.py`) |
| `renderer/documentacao.py` | não implementado (base em `reference/utils/gerador_documentacao_subhue.py`) |
| `audit/snapshot.py` | não implementado |
| `sync/client.py` | não implementado (base em `reference/utils/sync_dados_documentacoes.py`) |
