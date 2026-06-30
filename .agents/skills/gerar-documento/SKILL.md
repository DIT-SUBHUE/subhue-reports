# Skill: gerar-documento

## Quando usar

Use esta skill quando o usuário pedir para gerar um relatório, documentação ou dashboard HTML a partir dos dados do SUBHUE.

Exemplos de gatilho:
- "Gera um relatório de atendimentos do HMSF em junho"
- "Documenta o model fat_censo_leito_ativo"
- "Cria um dashboard de ocupação hospitalar"

---

## Fluxo obrigatório

### 1. Perguntar o tipo de documento

```
Qual tipo de documento deseja gerar?
1. Relatório      — métricas e achados para gestores
2. Documentação   — especificação técnica de model dbt
3. Dashboard      — painel interativo com filtros
```

### 2. Perguntar o modo de geração

```
Modo de geração:
1. Automático   — você toma todas as decisões com base nos dados encontrados
2. Colaborativo — você apresenta proposta e aguarda aprovação antes de gerar
```

### 3. Receber a instrução

Solicitar ao usuário uma descrição clara do que deve ser gerado.

Exemplos:
- "Relatório de atendimentos do HMSF em junho de 2026"
- "Documentação do model fat_censo_leito_ativo"
- "Dashboard de ocupação de leitos com filtro por unidade e período"

### 4. Aplicar regras de negócio

As regras abaixo são obrigatórias em todo documento gerado:

**RN-01 — Agrupamento por tipo de estabelecimento**
Em gráficos que comparam indicadores de todas as unidades, incluir também visualização agrupada por tipo de estabelecimento. Extrair o tipo do início do nome do estabelecimento (ex: "Hospital", "UPA", "CER").

**RN-02 — Fonte preferencial para análises**
Análises devem ser feitas preferencialmente a partir das silvers (`fat_boletim_categorizado`). Ler a documentação das colunas via `just manifest-catalog-model` antes de montar queries.

**RN-03 — Filtro de boletins de emergência**
Em análises de quantitativos (atendimentos, internações ou outros), quando o tipo de atendimento ou tipo de entrada **não for informado** pelo usuário, perguntar:

> "Devo filtrar apenas boletins de emergência? (`silver_timed.fat_boletim_categorizado.is_boletim_emergencia = TRUE`)"

Aguardar resposta antes de montar a query.

---

### 5. Explorar os dados

Use os comandos abaixo para entender as fontes disponíveis antes de gerar qualquer JSON:

```bash
just manifest-catalog                    # lista models dbt disponíveis
just manifest-catalog-model <nome>       # detalhe de um model com colunas
just manifest-sources                    # fontes raw agrupadas por source_name
just explore <schema.tabela>             # colunas, volume e amostra da fonte
just query "<sql>"                       # SQL DuckDB sobre parquets em cache
```

Regras de exploração:
- Use `list_models` / `manifest-catalog` se não souber quais fontes existem.
- Use `explore` antes de `query` para entender a estrutura.
- Não invente nomes de colunas ou tabelas — confirme nos dados reais.

### 6. Modo Colaborativo — apresentar proposta

Antes de gerar o JSON, apresente ao usuário:

- O que foi encontrado: fontes consultadas, colunas relevantes, volume de dados
- O que é possível gerar: seções ou painéis viáveis com os dados encontrados
- Perguntas de confirmação: período a priorizar, comparações desejadas, o que incluir ou excluir

**Aguardar resposta do usuário antes de continuar.**

No modo automático, pule esta etapa.

### 7. Gerar o JSON

Siga **rigorosamente** o schema correspondente ao tipo escolhido, definido em:

```
src/subhue_reports/skills/prompts.py
```

Campos obrigatórios em `meta`: `titulo`, `tipo_documento`.

| `tipo_documento` | Estrutura principal                        |
|------------------|--------------------------------------------|
| `relatorio`      | `meta` + `secoes[]`                        |
| `documentacao`   | `meta` + `secoes[]`                        |
| `dashboard`      | `meta` + `filtros[]` + `dados{}` + `paineis[]` |

**Não inventar tipos de seção, campos ou estruturas fora dos schemas existentes.**

Para relatório e documentação, tipos de seção válidos estão listados nos system prompts de `prompts.py`.
Para dashboard, painéis válidos são: `metrica`, `grafico`, `tabela`, `texto`.

### 8. Renderizar

```bash
just render <arquivo.json>
# Detecta tipo_documento automaticamente e salva em:
# reports/{tipo}/{YYYY_MM_DD__HH_MM}__{NOME}/{arquivo}.html
```

---

## Restrições

- Não inventar dados que não existem nas fontes exploradas.
- Não usar estrutura de JSON fora do schema de `prompts.py`.
- Não alterar código Python, justfile ou arquivos de configuração durante a geração.
- Se os dados não forem suficientes para gerar o documento pedido, informar ao usuário antes de continuar.
