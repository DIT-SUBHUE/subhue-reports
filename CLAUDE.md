# subhue-reports — guia de desenvolvimento com IA

## Stack

- Python 3.12+
- pytest + fixtures para testes
- ruff para lint e formatação
- pyproject.toml como fonte única de config
- just para atalhos de operação

## Estrutura de pacote

Src layout: pacote em `src/subhue_reports/`. Nunca colocar código de aplicação na raiz.
Cada submódulo tem `__init__.py` vazio. Imports absolutos sempre: `from subhue_reports.registry.loader import build_registry`.

pytest lê `pythonpath = ["src"]` do `pyproject.toml`. justfile define `export PYTHONPATH := "src"`.
Para instalar em modo editável: `pip install -e .` (usa `[tool.setuptools.packages.find] where = ["src"]`).

## Testes

### Organização

```
tests/
├── unit/           lógica pura, sem I/O externo
├── integration/    requerem banco/API/disco — marcados @pytest.mark.integration
├── fixtures/       dados estáticos conhecidos
└── conftest.py     fixtures compartilhadas
```

### Unit tests

Para lógica pura: normalização, cálculo, montagem de dict, geração de paths, validação.
Nunca mockar o que não é necessário. Se a função tem dependência externa, mova a lógica pura para uma função separada e teste essa.

```python
# bom: testa comportamento, não implementação
def test_badge_class_hi():
    assert badge_class(95) == "badge hi"

# ruim: testa detalhe de implementação
def test_badge_class_calls_float_conversion():
    ...
```

### Fixtures

Fixtures são contexto confiável. Defina em `conftest.py` os dicts/objetos que múltiplos testes usam.
Fixtures de arquivo (CSV, YAML, HTML) ficam em `tests/fixtures/` e são carregadas via `@pytest.fixture` com `Path`.

```python
@pytest.fixture
def sample_manifest():
    return {"nodes": {...}, "metadata": {...}}

@pytest.fixture
def registry(sample_manifest):
    return build_registry(sample_manifest)
```

### Integration tests

Marcados com `@pytest.mark.integration`. Não rodam no CI padrão.
Rodar localmente com `pytest -m integration` ou `just test-integration`.

```python
@pytest.mark.integration
def test_db_connection():
    ...
```

Requerem `.env` configurado. Nunca usam dados de produção diretamente — usam tabela/schema de teste quando possível.

## Nomenclatura de testes

`test_<função>_<cenário>` ou `test_<função>_quando_<condição>`.

```
test_build_registry_ignora_nodes_nao_model
test_check_sources_retorna_warning_versao_desatualizada
test_badge_class_retorna_na_quando_none
```

## Linting e formatação

Ruff como único linter/formatter. Configurado em `pyproject.toml`.

```bash
ruff check .       # lint
ruff format .      # format
ruff check --fix . # auto-fix
```

Regras ativas: E (pycodestyle), F (pyflakes), I (imports), UP (pyupgrade), B (bugbear), SIM (simplificações).

## Práticas específicas para desenvolvimento com IA

### Não gerar dados falsos que mascaram comportamento real

Ruim: fixture com dados inventados que nunca falham.
Bom: fixture derivada de schema real (`reference/`) com casos edge reais (None, string vazia, valores limítrofes).

### Testar os contratos, não os internos

IA tende a gerar testes que verificam detalhes de implementação. Testes devem verificar o contrato público da função (input → output), não como ela calcula internamente.

### Fixtures como documentação

Uma fixture bem nomeada explica a estrutura esperada. `sample_manifest_com_dois_models` é melhor que um dict inline de 30 linhas.

### Um assert por teste (quando possível)

Facilita diagnóstico. IA frequentemente empilha asserts — quebre em funções separadas quando cenários são distintos.

### Não testar o Python, testar o negócio

Ruim: `assert isinstance(result, dict)`.
Bom: `assert result["silver_timed.fat_censo_leito_ativo"]["version"] == "1.0.2"`.

## Comandos úteis

```bash
just test               # unit tests
just test-integration   # integration tests
just lint               # ruff check
just format             # ruff format
just manifest-update    # atualiza manifest local da API
just manifest-status    # verifica se manifest está atualizado
```

## Variáveis de ambiente

Sempre via `.env` (carregado pelo justfile). Nunca hardcodar credenciais.
Arquivo `.env.example` é a documentação das variáveis — mantê-lo atualizado.

Para testes de integração, criar `.env.test` com credenciais de ambiente de desenvolvimento.
