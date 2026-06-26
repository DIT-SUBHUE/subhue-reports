# subhue-reports

Sistema de geração de relatórios, documentações e dashboards HTML a partir dos dados do SUBHUE (rede municipal de saúde).

Consome o manifest dbt via API, acessa o banco de dados via Postgres, armazena em Parquet local e gera HTMLs self-contained prontos para publicação.

Projetado para ser operado por agentes de IA (Claude Code, Codex, OpenCode) via linguagem natural.

---

## Branches

| Branch   | Público-alvo              | Comportamento do agente                         |
|----------|---------------------------|-------------------------------------------------|
| `main`   | Desenvolvedores           | Sem restrições — pode editar código, commits, testes |
| `stable` | Gestores e analistas      | Restrito — apenas geração e exploração de dados |

**`main`** é a branch de desenvolvimento ativa. Código validado é propagado para `stable` via force push.

### Fluxo de atualização de `stable`

**NUNCA** mergear `stable` em `main`. O fluxo é unidirecional:

```bash
# Após commit e push em main:
just push-stable
```

`just push-stable` faz force push de `main` em `stable` e reaplica automaticamente o bloco de restrições de agente no `CLAUDE.md` de `stable`. As restrições são geridas em `.claude/stable-restrictions.md`.

**NUNCA** usar `git push origin main:stable` diretamente — apaga as restrições.
**NUNCA** `git merge origin/stable` em `main` — contamina `main` com restrições de gestores.

### Restrições do agente em `stable`

O `CLAUDE.md` da branch `stable` contém restrições rígidas no topo:

```
PROIBIDO (mesmo se solicitado):
- Editar qualquer arquivo em src/, tests/, justfile, pyproject.toml, requirements.txt
- git commit, git push, git checkout, git branch
- Criar ou deletar arquivos fora de reports/

PERMITIDO:
- just manifest-* (explorar catálogo de dados)
- just query / just explore
- just render (gerar HTML)
- Ler código para entender o que está disponível

BUG ENCONTRADO:
- Descreva em reports/bugs/YYYY-MM-DD_<descricao>.md
- Nunca tente corrigir — repasse ao desenvolvedor
```

---

## Como usar

### Para gestores e analistas

```bash
# 1. Clone a branch estável
git clone -b stable <url-do-repositorio>
cd subhue-reports

# 2. Configure as variáveis de ambiente
cp .env.example .env
# Preencha as credenciais no .env

# 3. Instale as dependências
pip install -e .

# 4. Abra o projeto no seu agente de IA (Claude Code, Codex, OpenCode)
# 5. Solicite em linguagem natural:
#    "Gera um relatório de atendimentos do HMSF em junho de 2026"
#    "Cria um dashboard de ocupação de leitos com filtro por unidade"
#    "Documenta o model fat_censo_leito_ativo"
```

O agente segue o fluxo definido em `.agents/skills/gerar-documento/SKILL.md`:
pergunta o tipo, explora os dados, apresenta proposta (modo colaborativo) e gera o HTML.

### Para desenvolvedores

```bash
git clone -b main <url-do-repositorio>
cd subhue-reports
pip install -e .
cp .env.example .env
just test   # valida o ambiente
```

---

## Arquitetura

```
Django API (SUBHUE)
  /api/dbt-manifest/         → manifest dbt com metadados dos modelos
  /api/dados-documentacoes/  → publicação de relatórios gerados

subhue-reports
  registry/   manifest → catálogo de modelos e fontes (37 modelos · 68 fontes)
  cache/      Postgres → Parquet local → DuckDB
  renderer/   JSON estruturado → HTML self-contained
  skills/     schemas de tools e system prompts para agentes
```

---

## Módulos

| Módulo | Responsabilidade |
|---|---|
| `registry/loader.py` | Carrega manifest dbt, constrói registries de modelos e fontes |
| `registry/updater.py` | Compara manifest local com API e baixa se houver versão nova |
| `registry/catalog.py` | Vistas LLM-friendly do manifest (busca, detalhe, contexto) |
| `registry/checker.py` | Valida se fontes de um relatório estão na versão atual |
| `cache/connection.py` | Conexão Postgres (lê variáveis `SUBHUE_*` do `.env`) |
| `cache/extractor.py` | Extrai tabela do Postgres → Parquet com meta.json companheiro |
| `cache/resolver.py` | Cache hit/miss com invalidação por versão, checksum e TTL |
| `cache/query.py` | Executa SQL DuckDB sobre parquets; suporta JOIN e window functions |
| `renderer/relatorio.py` | Renderiza relatório HTML (métricas, gráficos, tabelas, achados) |
| `renderer/documentacao.py` | Renderiza documentação HTML de model dbt com TOC automático |
| `renderer/dashboard.py` | Renderiza dashboard interativo com filtros JS reativos |
| `renderer/sections.py` | Serializa/deserializa relatório como diretório de seções |
| `skills/tools.py` | Schemas de tools e dispatcher para backends de dados |
| `skills/prompts.py` | System prompts por tipo de documento e modo de geração |

---

## Variáveis de ambiente

Copie `.env.example` para `.env` e preencha:

| Variável | Uso |
|---|---|
| `DBT_MANIFEST_API_BASE_URL` | URL base da API Django |
| `DBT_MANIFEST_API_USERNAME` | usuário para auth |
| `DBT_MANIFEST_API_PASSWORD` | senha para auth |
| `DBT_MANIFEST_TAG` | tag do manifest (default: `airflow_astro`) |
| `SUBHUE_IP` / `SUBHUE_PGPORT` / `SUBHUE_DATABASE_NAME` / `SUBHUE_USER` / `SUBHUE_SENHA` | banco de dados |
| `CACHE_TTL_HOURS` | TTL do cache Parquet (default: `4`) |
| `DADOS_DOCS_API_BASE_URL` | API de publicação de relatórios |
| `DADOS_DOCS_API_USERNAME` | usuário sync |
| `DADOS_DOCS_API_PASSWORD` | senha sync |

---

## Comandos principais

```bash
# Manifest
just manifest-update          # baixa manifest se houver versão nova
just manifest-status          # compara local vs remoto sem baixar
just manifest-catalog         # lista modelos disponíveis
just manifest-catalog-model <nome>  # detalhe de um modelo com colunas
just manifest-sources         # fontes raw agrupadas por source_name

# Dados
just explore <schema.tabela>  # colunas, volume e amostra da fonte
just query "<sql>"            # SQL DuckDB sobre parquets em cache
just cache-status             # lista parquets armazenados
just cache-clear              # remove todos os parquets

# Geração
just render <arquivo.json>    # JSON → HTML (detecta tipo automaticamente)
just render-fixtures          # regenera HTMLs de validação visual

# Publicação
just sync-push                # envia HTMLs para API Django
just sync-dry-run             # simula sem enviar

# Dev
just test                     # pytest tests/unit/
just lint                     # ruff check
just format                   # ruff format
```

---

## Outputs

```
reports/
├── relatorios/     {YYYY_MM_DD__HH_MM}__{NOME}/  ← relatórios HTML
├── documentacoes/  {YYYY_MM_DD__HH_MM}__{NOME}/  ← documentações HTML
├── dashboards/     {YYYY_MM_DD__HH_MM}__{NOME}/  ← dashboards HTML
└── bugs/           YYYY-MM-DD_<descricao>.md      ← bugs reportados (stable)
```

---

## Instruções para agentes

Arquitetura de instruções em camadas — ver `docs/agents/README.md`.

| Arquivo | Agente | Conteúdo |
|---|---|---|
| `CLAUDE.md` | Claude Code | contexto do projeto + regras de código |
| `AGENTS.md` | Codex / OpenAI | idem |
| `OPENCODE.md` | OpenCode | idem |
| `.agents/skills/gerar-documento/SKILL.md` | todos | fluxo completo de geração de documentos |
