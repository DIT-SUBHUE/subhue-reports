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

### 4. Explorar os dados

**Fluxo eficiente — siga esta ordem:**

#### 4a. Descobrir o model (sem banco)

```bash
just manifest-catalog-search <termo>     # acha nome exato do model (sem colunas)
just manifest-catalog-model <nome>       # colunas + descrições do manifest (sem DB)
just manifest-sources-search <termo>     # busca em fontes raw
```

> `manifest-catalog-model` usa o **nome curto** do model, sem schema.
> Ex: `fat_boletim_categorizado_timed`, não `silver_timed.fat_boletim_categorizado_timed`.
> Retorna todas as colunas com descrições — use isso para identificar colunas relevantes
> antes de qualquer consulta ao banco.

#### 4b. Verificar cache antes de consultar

```bash
just cache-status                        # lista parquets disponíveis localmente
```

- **Cache com dados** → use `just query "<SQL DuckDB>"` com `FROM 'data/cache/<fonte>_*.parquet'`
- **Cache vazio** → use Python direto no Postgres para agregações:

```python
# Script direto — para agregações quando cache está vazio
import sys, os
sys.path.insert(0, 'src')
for line in open('.env'):
    line = line.strip()
    if line and '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ[k] = v
from subhue_reports.cache.connection import connect
import json
conn = connect()
with conn.cursor() as cur:
    cur.execute("<SQL Postgres agregado>")
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()
    print(json.dumps([dict(zip(cols, r)) for r in rows], default=str))
conn.close()
```

#### 4c. `just explore` — usar apenas quando necessário

`just explore <schema.tabela>` retorna 20 linhas completas × todas as colunas.
**Caro em tokens.** Use somente quando:
- o manifest não tiver metadados suficientes de colunas, **ou**
- precisar confirmar volume total da tabela.

Nunca use `just explore` apenas para descobrir nomes de colunas — o manifest já tem isso.

#### Regras gerais

- Não invente nomes de colunas ou tabelas — confirme no manifest antes de consultar.
- Prefira múltiplas queries agregadas em paralelo a uma única query grande.
- Use o schema completo `schema.tabela` no SQL Postgres (ex: `silver_timed.fat_boletim_categorizado_timed`).

### 5. Modo Colaborativo — apresentar proposta

Antes de gerar o JSON, apresente ao usuário:

- O que foi encontrado: fontes consultadas, colunas relevantes, volume de dados
- O que é possível gerar: seções ou painéis viáveis com os dados encontrados
- Perguntas de confirmação: período a priorizar, comparações desejadas, o que incluir ou excluir

**Aguardar resposta do usuário antes de continuar.**

No modo automático, pule esta etapa.

### 6. Gerar o JSON

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

### 7. Renderizar

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
