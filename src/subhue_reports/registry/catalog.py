"""
LLM-friendly views of the dbt manifest registry.

Typical usage:
    registry = build_registry(load_manifest())
    print(to_context(registry))                    # inject into prompt
    detail("fat_censo_leito_ativo", registry)      # single model detail
    search(registry, layer="gold", status="stable") # filtered list

__main__: python -m subhue_reports.registry.catalog [model_name] [--layer L] [--schema S] [--status ST]
"""

from __future__ import annotations

import json
import textwrap
from typing import Any


# ── Public API ──────────────────────────────────────────────────────────────


def catalog(registry: dict[str, dict]) -> list[dict]:
    """Compact list of all models. One dict per model, only LLM-relevant fields."""
    return [_compact(name, meta) for name, meta in sorted(registry.items())]


def detail(name: str, registry: dict[str, dict]) -> dict | None:
    """Full model info including columns. Returns None if model not found."""
    meta = registry.get(name)
    if meta is None:
        return None
    base = _compact(name, meta)
    base["columns"] = _columns_summary(meta.get("_columns", {}))
    base["changelog"] = meta.get("changelog", [])
    base["consumers"] = meta.get("consumers", [])
    base["owner"] = meta.get("owner", "")
    base["slo"] = meta.get("slo", "")
    base["importance"] = meta.get("importance", "")
    base["sql_checksum"] = meta.get("_sql_checksum", "")
    base["fqn"] = meta.get("_fqn", [])
    return base


def search(
    registry: dict[str, dict],
    layer: str | None = None,
    schema: str | None = None,
    status: str | None = None,
    name_contains: str | None = None,
) -> list[dict]:
    """Filtered catalog. All filters are AND-combined; None = no filter."""
    results = []
    for name, meta in sorted(registry.items()):
        if layer and meta.get("layer") != layer:
            continue
        if schema and meta.get("_schema") != schema:
            continue
        if status and meta.get("status") != status:
            continue
        if name_contains and name_contains.lower() not in name.lower():
            continue
        results.append(_compact(name, meta))
    return results


def to_context(
    registry: dict[str, dict],
    models: list[str] | None = None,
    include_columns: bool = True,
) -> str:
    """
    Compact text block for LLM prompt injection.

    models: restrict to these model names (None = all).
    include_columns: include column names and descriptions.

    Format is plain text optimized for token efficiency, not markdown.
    """
    subset = {k: v for k, v in registry.items() if models is None or k in models}
    if not subset:
        return "No models found."

    schemas = sorted({v.get("_schema", "?") for v in subset.values()})
    layers = sorted({v.get("layer", "?") for v in subset.values()})
    lines: list[str] = [
        f"MANIFEST MODELS ({len(subset)} total)",
        f"schemas: {', '.join(schemas)} | layers: {', '.join(layers)}",
        "",
    ]

    for name, meta in sorted(subset.items()):
        schema = meta.get("_schema", "?")
        version = meta.get("version", "?")
        layer = meta.get("layer", "?")
        status = meta.get("status", "?")
        grain = meta.get("grain", "")
        desc = meta.get("_description", "")
        pk = meta.get("primary_key", [])

        lines.append(f"[{schema}.{name}] v{version} | {layer} | {status}")
        if grain:
            lines.append(f"  grain: {grain}")
        if desc:
            lines.append(f"  desc: {_truncate(desc, 120)}")
        if pk:
            pk_str = ", ".join(pk) if isinstance(pk, list) else str(pk)
            lines.append(f"  pk: {pk_str}")

        if include_columns:
            cols = meta.get("_columns", {})
            if cols:
                col_parts = [_col_inline(col_name, col_meta) for col_name, col_meta in cols.items()]
                col_block = "; ".join(col_parts)
                wrapped = textwrap.wrap(col_block, width=100, subsequent_indent="       ")
                lines.append(f"  cols: {wrapped[0]}")
                for wl in wrapped[1:]:
                    lines.append(f"  {wl}")

        lines.append("")

    return "\n".join(lines).rstrip()


# ── Internals ───────────────────────────────────────────────────────────────


def _compact(name: str, meta: dict) -> dict:
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


def _columns_summary(columns: dict[str, Any]) -> list[dict]:
    return [
        {
            "name": col_name,
            "description": col_meta.get("description", ""),
            "data_type": col_meta.get("data_type") or "",
        }
        for col_name, col_meta in columns.items()
    ]


def _col_inline(name: str, meta: dict) -> str:
    desc = meta.get("description", "")
    return f"{name} ({_truncate(desc, 60)})" if desc else name


def _truncate(text: str, max_len: int) -> str:
    text = text.strip()
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    from subhue_reports.registry.loader import build_registry, load_manifest

    parser = argparse.ArgumentParser(description="LLM-friendly manifest viewer")
    parser.add_argument("model", nargs="?", help="Model name for detailed view")
    parser.add_argument("--layer", help="Filter by layer (silver/gold)")
    parser.add_argument("--schema", help="Filter by schema")
    parser.add_argument("--status", help="Filter by status (stable/experimental)")
    parser.add_argument("--name", help="Filter by name substring")
    parser.add_argument("--no-columns", action="store_true", help="Omit columns from context")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()

    registry = build_registry(load_manifest())

    if args.model:
        result = detail(args.model, registry)
        if result is None:
            print(f"Model '{args.model}' not found.")
            raise SystemExit(1)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            d = result
            print(f"[{d['table']}] v{d['version']} | {d['layer']} | {d['status']}")
            if d["grain"]:
                print(f"grain: {d['grain']}")
            if d["description"]:
                print(f"desc:  {d['description']}")
            if d["primary_key"]:
                print(f"pk:    {', '.join(d['primary_key'])}")
            if d["owner"]:
                print(f"owner: {d['owner']}")
            if d["consumers"]:
                print(f"consumers: {', '.join(d['consumers'])}")
            if d["columns"]:
                print(f"\ncolumns ({len(d['columns'])}):")
                for col in d["columns"]:
                    desc = f" — {col['description']}" if col["description"] else ""
                    dtype = f" [{col['data_type']}]" if col["data_type"] else ""
                    print(f"  {col['name']}{dtype}{desc}")
            if d["changelog"]:
                print("\nchangelog:")
                for entry in d["changelog"]:
                    print(f"  {entry.get('date')} {entry.get('version')} ({entry.get('type')}): {entry.get('summary')}")
    elif any([args.layer, args.schema, args.status, args.name]):
        results = search(registry, layer=args.layer, schema=args.schema, status=args.status, name_contains=args.name)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            filtered_registry = {r["name"]: registry[r["name"]] for r in results}
            print(to_context(filtered_registry, include_columns=not args.no_columns))
    else:
        print(to_context(registry, include_columns=not args.no_columns))
