"""Schemas de tools Claude e dispatcher para os backends SUBHUE."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "list_models",
        "description": (
            "Lista models dbt disponíveis no manifest. "
            "Use para descobrir nomes, schemas e layers antes de explorar dados."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "description": "Filtro por layer (silver, gold, ...)",
                },
                "schema": {
                    "type": "string",
                    "description": "Filtro por schema (silver_timed, gold_timed, raw_sarah, ...)",
                },
                "name_contains": {
                    "type": "string",
                    "description": "Substring do nome do model",
                },
            },
        },
    },
    {
        "name": "get_model_detail",
        "description": (
            "Retorna detalhes completos de um model dbt: "
            "colunas (com tipo e descrição), grain, primary_key, changelog e dependências."
        ),
        "input_schema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nome exato do model (ex: fat_censo_leito_ativo)",
                },
            },
        },
    },
    {
        "name": "explore_source",
        "description": (
            "Busca dados de uma fonte via cache ou banco e retorna colunas, "
            "contagem de linhas e amostra. Use antes de query_parquet para "
            "entender a estrutura. O campo parquet_path retornado é usado no FROM do SQL."
        ),
        "input_schema": {
            "type": "object",
            "required": ["source"],
            "properties": {
                "source": {
                    "type": "string",
                    "description": 'Schema.tabela no formato "schema.nome" (ex: silver_timed.fat_censo_leito_ativo)',
                },
                "filters": {
                    "type": "object",
                    "description": 'Filtros WHERE opcionais. Ex: {"periodo": "2026-06"}',
                    "additionalProperties": {"type": "string"},
                },
                "limit": {
                    "type": "integer",
                    "description": "Máximo de linhas na amostra (default: 20)",
                },
            },
        },
    },
    {
        "name": "query_parquet",
        "description": (
            "Executa SQL DuckDB sobre parquets em cache. "
            "Use o parquet_path retornado por explore_source no FROM. "
            "Suporta JOIN entre fontes, window functions e agregações analíticas. "
            "Retorna até 200 linhas."
        ),
        "input_schema": {
            "type": "object",
            "required": ["sql"],
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL DuckDB com parquet_path no FROM (ex: SELECT * FROM '/path/arquivo.parquet')",
                },
            },
        },
    },
]

_SEARCH_KEYS = {"layer", "schema", "name_contains"}


def dispatch_tool(
    tool_name: str,
    tool_input: dict,
    registry: dict,
    cache_dir: Path = Path("data/cache"),
) -> str:
    """Executa o tool e retorna resultado como string para o modelo."""
    logger.info("dispatch: %s %s", tool_name, list(tool_input.keys()))
    try:
        return _run_tool(tool_name, tool_input, registry, cache_dir)
    except Exception as exc:
        logger.warning("tool %s falhou: %s", tool_name, exc)
        return json.dumps({"erro": str(exc), "tool": tool_name}, ensure_ascii=False)


def _run_tool(tool_name: str, tool_input: dict, registry: dict, cache_dir: Path) -> str:
    if tool_name == "list_models":
        from subhue_reports.registry.catalog import search, to_context

        filtered = {k: v for k, v in tool_input.items() if k in _SEARCH_KEYS}
        results = search(registry, **filtered)
        names = [r["name"] for r in results]
        return to_context(registry, names, include_columns=False)

    if tool_name == "get_model_detail":
        from subhue_reports.registry.catalog import detail

        result = detail(tool_input["name"], registry)
        return json.dumps(result, ensure_ascii=False, default=str)

    if tool_name == "explore_source":
        from subhue_reports.cache.query import explore_source

        exp = explore_source(
            source=tool_input["source"],
            filters=tool_input.get("filters", {}),
            registry=registry,
            limit=tool_input.get("limit", 20),
            cache_dir=cache_dir,
        )
        return json.dumps(exp.to_dict(), ensure_ascii=False, default=str)

    if tool_name == "query_parquet":
        from subhue_reports.cache.query import query

        rows = query(tool_input["sql"])
        return json.dumps(rows[:200], ensure_ascii=False, default=str)

    raise ValueError(
        f"Tool desconhecido: {tool_name!r}. "
        f"Disponíveis: {[t['name'] for t in TOOL_SCHEMAS]}"
    )
