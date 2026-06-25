"""Helpers HTML puros compartilhados entre relatório e documentação."""

import html as html_module

PILL_CSS = {
    "hospital": "pill-h",
    "upa": "pill-u",
    "cer": "pill-c",
    "outro": "pill-o",
}


def esc(text: object) -> str:
    return html_module.escape(str(text)) if text is not None else ""


def fmt_num(value: object) -> str:
    try:
        return f"{int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(value)


def badge_class(pct: float | None) -> str:
    if pct is None:
        return "badge na"
    if pct >= 90:
        return "badge hi"
    if pct >= 70:
        return "badge md"
    return "badge lo"


def render_badge_pct(pct: float | None, label: str | None = None) -> str:
    if pct is None:
        return '<span class="badge na">—</span>'
    display = label or f"{pct:.0f}%"
    return f'<span class="{badge_class(pct)}">{esc(display)}</span>'


def render_badge_label(label: str, nivel: str = "na") -> str:
    cls = f"badge {nivel}" if nivel in ("hi", "md", "lo", "na", "ex") else "badge na"
    return f'<span class="{cls}">{esc(label)}</span>'


def render_pill(tipo: str, label: str) -> str:
    css = PILL_CSS.get(tipo.lower(), "pill-o")
    return f'<span class="pill {css}">{esc(label)}</span>'


def render_code(text: str) -> str:
    return f"<code>{esc(text)}</code>"


def render_cell(value: object, col_tipo: str) -> str:
    """Renderiza célula de tabela genérica pelo tipo da coluna."""
    if value is None:
        return '<td><span style="color:var(--ink-5)">—</span></td>'
    if col_tipo == "numero":
        return f'<td class="n">{esc(fmt_num(value))}</td>'
    if col_tipo == "badge_pct":
        if isinstance(value, dict):
            return f'<td class="n">{render_badge_pct(value.get("pct"), value.get("label"))}</td>'
        return f'<td class="n">{render_badge_pct(float(value))}</td>'
    if col_tipo == "badge_label":
        if isinstance(value, dict):
            lbl = value.get("label", "")
            nivel = value.get("nivel", "na")
            return f'<td>{render_badge_label(lbl, nivel)}</td>'
        return f'<td>{render_badge_label(str(value))}</td>'
    if col_tipo == "codigo":
        return f'<td>{render_code(str(value))}</td>'
    if col_tipo == "pill":
        if isinstance(value, dict):
            return f'<td>{render_pill(value.get("tipo", "outro"), value.get("label", ""))}</td>'
        return f'<td>{esc(str(value))}</td>'
    return f'<td>{esc(str(value))}</td>'


def deep_merge(base: dict, override: dict) -> dict:
    """Merge recursivo: override tem precedência, base preenche o que falta."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result
