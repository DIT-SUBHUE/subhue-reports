import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())


def render(dados: dict, plotly_js: str = "") -> str:
    """
    Dispatcher unificado: lê meta.tipo_documento e chama o renderer correto.

    Valores válidos: "relatorio" (default) | "documentacao"
    """
    tipo = dados.get("meta", {}).get("tipo_documento", "relatorio")
    if tipo == "documentacao":
        from subhue_reports.renderer.documentacao import render_doc

        return render_doc(dados, plotly_js)
    from subhue_reports.renderer.relatorio import render_report

    return render_report(dados, plotly_js)
