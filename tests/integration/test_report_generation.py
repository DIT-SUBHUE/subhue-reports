"""
Testes de integração — geração completa de relatório em disco.
Requerem manifest local (data/manifest.json) e dependências instaladas (plotly).

Rodar com:
    pytest -m integration
    just test-integration
"""

import json
from pathlib import Path

import pytest


@pytest.mark.integration
class TestManifestUpdateEndToEnd:
    def test_check_and_update_cria_manifest_e_meta(self, tmp_path):
        """
        Testa o fluxo completo: fetch_remote_meta → fetch_manifest_content → salva arquivos.
        Requer SUBHUE_MANIFEST_BASE_URL configurado.
        """
        import os

        from subhue_reports.registry.updater import check_and_update

        base_url = os.environ.get("SUBHUE_MANIFEST_BASE_URL", "").rstrip("/")
        if not base_url:
            pytest.skip("SUBHUE_MANIFEST_BASE_URL não configurado")

        manifest_path = tmp_path / "manifest.json"
        meta_path = tmp_path / "manifest.meta.json"

        updated = check_and_update(
            base_url=base_url,
            manifest_path=manifest_path,
            meta_path=meta_path,
            force=True,
        )

        assert updated is True
        assert manifest_path.exists()
        assert meta_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert "nodes" in manifest

        meta = json.loads(meta_path.read_text())
        assert "updated_at" in meta
        assert "fetched_at" in meta

    def test_build_registry_com_manifest_real(self):
        """Testa build_registry com manifest baixado da API."""
        from subhue_reports.registry.loader import build_registry, load_manifest

        manifest = load_manifest()
        registry = build_registry(manifest)

        assert len(registry) > 0
        for name, meta in registry.items():
            assert "_schema" in meta
            assert "_fqn" in meta


@pytest.mark.integration
class TestRendererEndToEnd:
    def test_gerar_html_a_partir_de_json_fixture(self, tmp_path, sample_report_json):
        """
        Gera HTML completo a partir do sample_report_json.
        Testa que o arquivo é criado e contém elementos essenciais.
        Requer plotly instalado.
        """
        import sys

        # renderer ainda não portado para subhue_reports — importa da referência
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "reference" / "utils"))
        try:
            from gerador_relatorio_subhue import gerar_html
        except ImportError:
            pytest.skip("gerador_relatorio_subhue não disponível")

        html = gerar_html(sample_report_json, plotly_js="")

        output = tmp_path / "test_report.html"
        output.write_text(html, encoding="utf-8")

        assert output.exists()
        content = output.read_text()
        assert "<!DOCTYPE html>" in content
        assert "Teste de Altas" in content
        assert "Validar cobertura." in content

    def test_html_gerado_contem_secao_contexto(self, sample_report_json):
        """Seção contexto do sample_report_json deve aparecer no HTML."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "reference" / "utils"))
        try:
            from gerador_relatorio_subhue import gerar_html
        except ImportError:
            pytest.skip("gerador_relatorio_subhue não disponível")

        html = gerar_html(sample_report_json, plotly_js="")
        assert "callout" in html
        assert "Análise de cobertura" in html

    def test_html_sem_graficos_nao_inclui_plotly(self, sample_report_json):
        """Sem seções de gráfico, o bloco plotly não deve aparecer no HTML."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "reference" / "utils"))
        try:
            from gerador_relatorio_subhue import gerar_html
        except ImportError:
            pytest.skip("gerador_relatorio_subhue não disponível")

        html = gerar_html(sample_report_json, plotly_js="PLOTLY_SENTINEL")
        assert "PLOTLY_SENTINEL" not in html
