"""Testa transformações puras: build_registry, check_sources, cálculos de path/versão."""

import pytest


class TestBuildRegistry:
    def test_extrai_apenas_model_nodes(self, sample_manifest, registry):
        # source node não deve aparecer
        assert "fat_alta" not in registry
        assert len(registry) == 2

    def test_model_contem_meta_fields(self, registry):
        model = registry["fat_censo_leito_ativo"]
        assert model["version"] == "1.0.2"
        assert model["layer"] == "silver"
        assert model["status"] == "stable"

    def test_model_contem_fields_internos(self, registry):
        model = registry["fat_censo_leito_ativo"]
        assert model["_schema"] == "silver_timed"
        assert model["_sql_checksum"] == "abc123def456"
        assert model["_description"] == "Censo de leitos ativos por período."
        assert isinstance(model["_fqn"], list)
        assert isinstance(model["_columns"], dict)

    def test_manifest_sem_nodes_retorna_vazio(self):
        from subhue_reports.registry.loader import build_registry

        result = build_registry({"nodes": {}})
        assert result == {}

    def test_checksum_ausente_vira_string_vazia(self):
        from subhue_reports.registry.loader import build_registry

        manifest = {
            "nodes": {
                "model.x.sem_checksum": {
                    "resource_type": "model",
                    "name": "sem_checksum",
                    "fqn": ["x"],
                    "schema": "public",
                    "meta": {},
                }
            }
        }
        registry = build_registry(manifest)
        assert registry["sem_checksum"]["_sql_checksum"] == ""

    def test_meta_ausente_nao_levanta_erro(self):
        from subhue_reports.registry.loader import build_registry

        manifest = {
            "nodes": {
                "model.x.sem_meta": {
                    "resource_type": "model",
                    "name": "sem_meta",
                    "fqn": ["x"],
                    "schema": "public",
                    # sem campo "meta"
                }
            }
        }
        registry = build_registry(manifest)
        assert "sem_meta" in registry


class TestCheckSources:
    def test_retorna_vazio_quando_tudo_ok(self, sample_report_json, registry):
        from subhue_reports.registry.checker import check_sources

        warnings = check_sources(sample_report_json, registry)
        assert warnings == []

    def test_detecta_versao_desatualizada(self, sample_report_json, registry):
        from subhue_reports.registry.checker import check_sources

        report = {
            **sample_report_json,
            "meta": {
                **sample_report_json["meta"],
                "model_versions": {
                    "silver_timed.fat_censo_leito_ativo": "1.0.0",  # desatualizado
                    "gold_timed.atendimento_emergencia_agg": "2.1.0",
                },
            },
        }
        warnings = check_sources(report, registry)
        assert len(warnings) == 1
        w = warnings[0]
        assert w["fonte"] == "silver_timed.fat_censo_leito_ativo"
        assert w["issue"] == "versão desatualizada"
        assert w["no_relatorio"] == "1.0.0"
        assert w["atual"] == "1.0.2"

    def test_detecta_model_ausente_no_registry(self, registry):
        from subhue_reports.registry.checker import check_sources

        report = {
            "meta": {
                "fontes": ["silver_timed.modelo_inexistente"],
                "model_versions": {},
            }
        }
        warnings = check_sources(report, registry)
        assert len(warnings) == 1
        assert warnings[0]["issue"] == "model não encontrado no registry"

    def test_sem_model_versions_nao_gera_warning_de_versao(self, registry):
        from subhue_reports.registry.checker import check_sources

        report = {
            "meta": {
                "fontes": ["silver_timed.fat_censo_leito_ativo"],
                # sem model_versions — nenhuma versão auditada
            }
        }
        warnings = check_sources(report, registry)
        assert warnings == []

    def test_meta_vazio_retorna_vazio(self, registry):
        from subhue_reports.registry.checker import check_sources

        warnings = check_sources({}, registry)
        assert warnings == []

    def test_multiplas_fontes_com_problemas(self, registry):
        from subhue_reports.registry.checker import check_sources

        report = {
            "meta": {
                "fontes": [
                    "silver_timed.fat_censo_leito_ativo",
                    "silver_timed.nao_existe",
                ],
                "model_versions": {
                    "silver_timed.fat_censo_leito_ativo": "0.9.0",
                },
            }
        }
        warnings = check_sources(report, registry)
        assert len(warnings) == 2
        issues = {w["fonte"]: w["issue"] for w in warnings}
        assert issues["silver_timed.fat_censo_leito_ativo"] == "versão desatualizada"
        assert issues["silver_timed.nao_existe"] == "model não encontrado no registry"


class TestModelNameExtraction:
    """build_registry e check_sources usam model_name = fqn[-1] / fonte.split('.')[-1]."""

    def test_fonte_schema_ponto_model_extrai_model_name(self, registry):
        from subhue_reports.registry.checker import check_sources

        report = {
            "meta": {
                "fontes": ["silver_timed.fat_censo_leito_ativo"],
                "model_versions": {"silver_timed.fat_censo_leito_ativo": "1.0.2"},
            }
        }
        warnings = check_sources(report, registry)
        assert warnings == []

    def test_fqn_usado_na_registry_e_nao_na_chave(self, registry):
        assert "fat_censo_leito_ativo" in registry
        assert "silver_timed.fat_censo_leito_ativo" not in registry
