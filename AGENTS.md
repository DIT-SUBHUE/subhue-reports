# subhue-reports — guia para agentes de IA (Codex / OpenAI)

## Objetivo

Projeto de geração de relatórios, documentações e dashboards HTML a partir de dados do SUBHUE
(rede municipal de saúde). Código pequeno, explícito e previsível.

## Stack

* Python 3.12+ · `pytest` · `ruff` · `pyproject.toml` · `just`
* `src layout`: código em `src/subhue_reports/`
* Imports sempre absolutos: `from subhue_reports.registry.loader import build_registry`

## Módulos principais

| Módulo | Responsabilidade |
|---|---|
| `registry/` | Lê manifest dbt → modelos e fontes disponíveis |
| `cache/` | Extrai Postgres → Parquet; queries via DuckDB |
| `renderer/` | JSON estruturado → HTML self-contained |
| `skills/` | Schemas de tools e prompts de referência |

## Regras de código

* Funções: 4–20 linhas. Arquivos: < 500 linhas.
* Uma função, uma responsabilidade. Máximo 2 níveis de indentação.
* Type hints em toda função nova. Sem `Any`. Prefira `TypedDict`, `dataclass`, `Enum`.
* Nomes específicos do domínio — sem `data`, `result`, `handler`, `manager`.
* Mensagens de erro incluem: valor recebido + formato esperado + contexto.
* Comentários explicam o porquê, não o óbvio.

## Antes de finalizar qualquer mudança

1. Preservar comentários úteis.
2. Não misturar idiomas.
3. Não criar dados falsos que escondem comportamento real.
4. Não adicionar abstração genérica sem necessidade.
5. Não alterar contrato público sem atualizar testes.
6. Rodar `just test` quando houver mudança de lógica.
7. Rodar `just lint` e `just format`.
8. Preferir mudanças pequenas e verificáveis.

---

## Workflows sob demanda

Workflows detalhados não ficam duplicados neste arquivo.

Quando o usuário pedir para gerar relatório, documentação ou dashboard, use a skill canônica:

`.agents/skills/gerar-documento/SKILL.md`

Essa skill define:
- perguntas iniciais (tipo e modo)
- exploração de dados com `just manifest-catalog`, `just explore`, `just query`
- modo automático ou colaborativo
- geração de JSON conforme schemas em `src/subhue_reports/skills/prompts.py`
- renderização via `just render`

Não inventar estrutura de JSON fora dos schemas existentes.

---

## Comandos úteis

```bash
just test                          # unit tests
just lint                          # ruff check
just format                        # ruff format
just manifest-catalog              # lista models
just explore <schema.tabela>       # explora fonte de dados
just query "<sql>"                 # SQL sobre cache
just render <json>                 # gera HTML
just render-fixtures               # valida HTMLs de exemplo
```

## Outputs

```
reports/
├── relatorios/    {ts}__{NOME}/{arquivo}.json + .html
├── documentacoes/ {ts}__{NOME}/{arquivo}.json + .html
├── dashboards/    {ts}__{NOME}/{arquivo}.json + .html
└── exemplos/      fixtures de validação visual
```
