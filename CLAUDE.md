# subhue-reports — guia para desenvolvimento com IA

## Objetivo

Este projeto deve ser simples de navegar, testar e modificar por humanos e agentes de IA.

Prioridades:

1. Código pequeno e explícito.
2. Estrutura previsível.
3. Testes rápidos e úteis.
4. Pouca mágica.
5. Nomes fáceis de buscar com `rg`.

## Stack

* Python 3.12+
* `pytest`
* `ruff`
* `pyproject.toml`
* `just`

## Estrutura

Usar `src layout`.

```text
src/subhue_reports/
tests/
├── unit/
├── integration/
├── fixtures/
└── conftest.py
```

Regras:

* Código de aplicação nunca fica na raiz.
* Imports sempre absolutos.

```python
from subhue_reports.registry.loader import build_registry
```

* `pytest` usa `pythonpath = ["src"]`.
* `justfile` exporta `PYTHONPATH := "src"`.
* Instalação local:

```bash
pip install -e .
```

## Estilo de código

* Funções pequenas: idealmente 4 a 20 linhas.
* Arquivos abaixo de 500 linhas.
* Uma função faz uma coisa.
* Um módulo tem uma responsabilidade clara.
* Prefira retornos antecipados a `if` aninhado.
* Máximo de 2 níveis de indentação.
* Evite duplicação; extraia lógica compartilhada.

### Nomes

Evite nomes genéricos:

```text
data, result, handler, manager, service, process
```

Prefira nomes específicos do domínio:

```text
manifest_model_nodes
source_freshness_warning
registry_build_result
```

Regra prática: o nome deve ser fácil de encontrar com `rg` sem retornar muitos falsos positivos.

### Tipos

* Toda função nova deve ter type hints.
* Evite `Any`.
* Evite `dict` genérico quando o formato é conhecido.
* Prefira `TypedDict`, `dataclass`, `Enum` ou `Protocol`.

## Erros

Mensagens de erro devem incluir:

* valor recebido;
* formato esperado;
* contexto.

```python
raise ValueError(
    f"Manifest inválido: metadata ausente. "
    f"Recebido: {manifest.keys()}. Esperado: chave 'metadata'."
)
```

## Comentários

* Não remova comentários existentes sem entender o motivo.
* Comentários devem explicar o **porquê**, não o óbvio.
* Funções públicas devem ter docstring curta com intenção e exemplo quando útil.

Bom:

```python
# Manifest antigo pode vir sem group_map; manter fallback por compatibilidade.
```

Ruim:

```python
# incrementa contador
count += 1
```

## Dependências

* Injete dependências por parâmetro ou construtor.
* Evite variáveis globais escondendo dependências.
* I/O externo deve ficar isolado.
* Bibliotecas de terceiros devem ser acessadas por interfaces finas do projeto quando forem centrais para a lógica.

## Testes

Comandos:

```bash
just test
just test-integration
```

Organização:

* `tests/unit/`: lógica pura, sem I/O externo.
* `tests/integration/`: banco, API, disco ou serviços externos.
* `tests/fixtures/`: arquivos estáticos.
* `conftest.py`: fixtures compartilhadas.

### Regras

* Toda função nova relevante deve ter teste.
* Todo bug corrigido deve ter teste de regressão.
* Teste comportamento público, não implementação interna.
* Não mockar o que não precisa.
* Para I/O externo, prefira fake classes nomeadas.
* Fixtures devem representar casos reais, incluindo `None`, string vazia, campos ausentes e versões antigas.

Bom:

```python
def test_badge_class_retorna_hi_quando_score_alto():
    assert badge_class(95) == "badge hi"
```

Ruim:

```python
def test_badge_class_chama_float_conversion():
    ...
```

### Nomes de testes

```text
test_<funcao>_<cenario>
test_<funcao>_quando_<condicao>
```

Exemplos:

```text
test_build_registry_ignora_nodes_nao_model
test_check_sources_retorna_warning_versao_desatualizada
test_badge_class_retorna_na_quando_none
```

### Integração

* Marcar com `@pytest.mark.integration`.
* Não rodar no CI padrão.
* Usar `.env.test`.
* Nunca depender diretamente de produção.

## Ruff

Ruff é o único linter e formatter.

```bash
ruff check .
ruff format .
ruff check --fix .
```

Regras principais:

* `E`
* `F`
* `I`
* `UP`
* `B`
* `SIM`

Não discutir estilo fora do formatter.

## Variáveis de ambiente

* Sempre via `.env`.
* Nunca hardcodar credenciais.
* `.env.example` deve documentar as variáveis.
* Integração usa `.env.test`.

## Logging

* Logs técnicos devem ser estruturados, preferencialmente JSON.
* Saída de CLI para usuário deve ser texto simples.
* Nunca logar segredos.

## Comandos úteis

```bash
just test
just test-integration
just lint
just format
just manifest-update
just manifest-status
```

## Regras para agentes de IA

Antes de finalizar qualquer mudança:

1. Preservar comentários úteis.
2. Não misturar idiomas.
3. Não criar dados falsos que escondem comportamento real.
4. Não adicionar abstração genérica sem necessidade.
5. Não alterar contrato público sem atualizar testes.
6. Rodar `just test` quando houver mudança de lógica.
7. Rodar `just lint` e `just format`.
8. Preferir mudanças pequenas e verificáveis.

## Anti-padrões

Evite:

* funções longas;
* arquivos gigantes;
* nomes genéricos;
* fixtures enormes inline;
* testes de detalhes internos;
* mocks desnecessários;
* dependências globais escondidas;
* credenciais hardcoded;
* comentários óbvios;
* duplicação de regra de negócio.

## Regra final

Código bom neste projeto é código que dá para encontrar com `rg`, entender rápido, modificar com baixo risco e validar com um comando.
