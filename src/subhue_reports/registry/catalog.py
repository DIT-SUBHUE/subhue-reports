"""
LLM-friendly views of the dbt manifest registry.

Typical usage:
    registry = build_registry(load_manifest())
    print(to_context(registry))                     # inject into prompt
    detail("fat_censo_leito_ativo", registry)       # single model detail
    search(registry, layer="gold", status="stable") # filtered list

CLI: python -m subhue_reports.registry.catalog [model_name] [--layer L] [--schema S] [--status ST]
"""

from __future__ import annotations

import json
import textwrap
from typing import TypedDict

from subhue_reports.registry.loader import RegistryEntry


class ColumnSummary(TypedDict):
    name: str
    description: str
    data_type: str


class ModelCatalogEntry(TypedDict):
    name: str
    table: str
    schema: str
    layer: str
    status: str
    version: str
    grain: str
    description: str
    primary_key: list[str]
    last_change_type: str


class ModelDetail(ModelCatalogEntry, total=False):
    columns: list[ColumnSummary]
    changelog: list[dict]
    consumers: list[str]
    owner: str
    slo: str
    importance: str
    sql_checksum: str
    fqn: list[str]


# ── Public API ──────────────────────────────────────────────────────────────


def catalog(registry: dict[str, RegistryEntry]) -> list[ModelCatalogEntry]:
    """Lista compacta de todos os models, somente campos LLM-relevantes."""
    return [_to_catalog_entry(name, meta) for name, meta in sorted(registry.items())]


def detail(name: str, registry: dict[str, RegistryEntry]) -> ModelDetail | None:
    """Detalhe completo de um model incluindo columns e changelog. None se não encontrado."""
    meta = registry.get(name)
    if meta is None:
        return None
    return {
        **_to_catalog_entry(name, meta),
        "columns": _columns_summary(meta.get("_columns", {})),
        "changelog": meta.get("changelog", []),
        "consumers": meta.get("consumers", []),
        "owner": meta.get("owner", ""),
        "slo": meta.get("slo", ""),
        "importance": meta.get("importance", ""),
        "sql_checksum": meta.get("_sql_checksum", ""),
        "fqn": meta.get("_fqn", []),
    }


def search(
    registry: dict[str, RegistryEntry],
    layer: str | None = None,
    schema: str | None = None,
    status: str | None = None,
    name_contains: str | None = None,
) -> list[ModelCatalogEntry]:
    """Catálogo filtrado. Todos os filtros são AND; None = sem filtro."""
    return [
        _to_catalog_entry(name, meta)
        for name, meta in sorted(registry.items())
        if _matches_filters(name, meta, layer, schema, status, name_contains)
    ]


def to_context(
    registry: dict[str, RegistryEntry],
    models: list[str] | None = None,
    include_columns: bool = True,
) -> str:
    """Bloco de texto compacto para injeção em prompt LLM.

    models: restringe a esses model names (None = todos).
    include_columns: inclui nomes e descrições de colunas.

    Formato plain text otimizado para eficiência de tokens.
    """
    subset = {k: v for k, v in registry.items() if models is None or k in models}
    if not subset:
        return "No models found."

    schemas = sorted({v.get("_schema", "?") for v in subset.values()})
    layers = sorted({v.get("layer", "?") for v in subset.values()})
    header = [
        f"MANIFEST MODELS ({len(subset)} total)",
        f"schemas: {', '.join(schemas)} | layers: {', '.join(layers)}",
        "",
    ]
    model_blocks = [
        line
        for name, meta in sorted(subset.items())
        for line in _model_context_block(name, meta, include_columns)
    ]
    return "\n".join(header + model_blocks).rstrip()


# ── Internals ───────────────────────────────────────────────────────────────


def _to_catalog_entry(name: str, meta: RegistryEntry) -> ModelCatalogEntry:
    return {
        "name": name,
        "table": f"{meta.get('_schema', '')}.{name}",
        "schema": meta.get("_schema", ""),
        "layer": meta.get("layer", ""),
        "status": meta.get("status", ""),
        "version": meta.get("version", ""),
        "grain": meta.get("grain", ""),
        "description": meta.get("_description", ""),
        "primary_key": meta.get("primary_key", []),
        "last_change_type": meta.get("last_change_type", ""),
    }


def _matches_filters(
    name: str,
    meta: RegistryEntry,
    layer: str | None,
    schema: str | None,
    status: str | None,
    name_contains: str | None,
) -> bool:
    if layer and meta.get("layer") != layer:
        return False
    if schema and meta.get("_schema") != schema:
        return False
    if status and meta.get("status") != status:
        return False
    return not name_contains or name_contains.lower() in name.lower()


def _columns_summary(columns: dict[str, dict]) -> list[ColumnSummary]:
    return [
        {
            "name": col_name,
            "description": col_meta.get("description", ""),
            "data_type": col_meta.get("data_type") or "",
        }
        for col_name, col_meta in columns.items()
    ]


def _model_context_block(name: str, meta: RegistryEntry, include_columns: bool) -> list[str]:
    schema = meta.get("_schema", "?")
    version = meta.get("version", "?")
    layer = meta.get("layer", "?")
    status = meta.get("status", "?")
    pk = meta.get("primary_key", [])

    lines = [f"[{schema}.{name}] v{version} | {layer} | {status}"]
    if meta.get("grain"):
        lines.append(f"  grain: {meta['grain']}")
    if meta.get("_description"):
        lines.append(f"  desc: {_truncate(meta['_description'], 120)}")
    if pk:
        pk_str = ", ".join(pk) if isinstance(pk, list) else str(pk)
        lines.append(f"  pk: {pk_str}")
    if include_columns and meta.get("_columns"):
        lines.extend(_column_context_lines(meta["_columns"]))
    lines.append("")
    return lines


def _column_context_lines(columns: dict[str, dict]) -> list[str]:
    col_parts = [_col_inline(col_name, col_meta) for col_name, col_meta in columns.items()]
    col_block = "; ".join(col_parts)
    wrapped = textwrap.wrap(col_block, width=100, subsequent_indent="       ")
    return [f"  cols: {wrapped[0]}"] + [f"  {wl}" for wl in wrapped[1:]]


def _col_inline(col_name: str, col_meta: dict) -> str:
    desc = col_meta.get("description", "")
    return f"{col_name} ({_truncate(desc, 60)})" if desc else col_name


def _truncate(text: str, max_len: int) -> str:
    text = text.strip()
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


# ── CLI ─────────────────────────────────────────────────────────────────────


def _run_cli() -> None:
    import argparse

    from subhue_reports.registry.loader import build_registry, load_manifest

    parser = argparse.ArgumentParser(description="LLM-friendly manifest viewer")
    parser.add_argument("model", nargs="?", help="Model name for detailed view")
    parser.add_argument("--layer", help="Filter by layer (silver/gold)")
    parser.add_argument("--schema", help="Filter by schema")
    parser.add_argument("--status", help="Filter by status (stable/experimental)")
    parser.add_argument("--name", help="Filter by name substring")
    parser.add_argument("--no-columns", action="store_true", help="Omit columns from context")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    args = parser.parse_args()

    registry = build_registry(load_manifest())

    if args.model:
        _print_model_detail(args.model, registry, as_json=args.as_json)
    elif any([args.layer, args.schema, args.status, args.name]):
        _print_filtered_catalog(registry, args, include_columns=not args.no_columns)
    else:
        print(to_context(registry, include_columns=not args.no_columns))


def _print_model_detail(
    model_name: str, registry: dict[str, RegistryEntry], *, as_json: bool
) -> None:
    model_info = detail(model_name, registry)
    if model_info is None:
        print(f"Model '{model_name}' não encontrado no registry.")
        raise SystemExit(1)
    if as_json:
        print(json.dumps(model_info, ensure_ascii=False, indent=2))
        return
    _print_model_info_text(model_info)


def _print_model_info_text(model_info: ModelDetail) -> None:
    table = model_info["table"]
    version, layer, status = model_info["version"], model_info["layer"], model_info["status"]
    print(f"[{table}] v{version} | {layer} | {status}")
    if model_info["grain"]:
        print(f"grain: {model_info['grain']}")
    if model_info["description"]:
        print(f"desc:  {model_info['description']}")
    if model_info["primary_key"]:
        print(f"pk:    {', '.join(model_info['primary_key'])}")
    if model_info.get("owner"):
        print(f"owner: {model_info['owner']}")
    if model_info.get("consumers"):
        print(f"consumers: {', '.join(model_info['consumers'])}")
    if model_info.get("columns"):
        print(f"\ncolumns ({len(model_info['columns'])}):")
        for col in model_info["columns"]:
            desc = f" — {col['description']}" if col["description"] else ""
            dtype = f" [{col['data_type']}]" if col["data_type"] else ""
            print(f"  {col['name']}{dtype}{desc}")
    if model_info.get("changelog"):
        print("\nchangelog:")
        for entry in model_info["changelog"]:
            date, ver, kind = entry.get("date"), entry.get("version"), entry.get("type")
            print(f"  {date} {ver} ({kind}): {entry.get('summary')}")


def _print_filtered_catalog(
    registry: dict[str, RegistryEntry],
    args: object,
    *,
    include_columns: bool,
) -> None:
    matching_models = search(
        registry,
        layer=getattr(args, "layer", None),
        schema=getattr(args, "schema", None),
        status=getattr(args, "status", None),
        name_contains=getattr(args, "name", None),
    )
    if getattr(args, "as_json", False):
        print(json.dumps(matching_models, ensure_ascii=False, indent=2))
        return
    filtered_registry = {m["name"]: registry[m["name"]] for m in matching_models}
    print(to_context(filtered_registry, include_columns=include_columns))


if __name__ == "__main__":
    _run_cli()
