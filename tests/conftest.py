"""Fixtures compartilhadas entre unit e integration tests."""

import sys
from pathlib import Path

import pytest
import yaml

# Permite importar helpers do reference/ nos testes de renderer
sys.path.insert(0, str(Path(__file__).parent.parent / "reference" / "utils"))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Manifest & Registry ───────────────────────────────────────────────────────

@pytest.fixture
def sample_manifest() -> dict:
    """Manifest mínimo com dois model nodes e metadata estável."""
    return {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v10/manifest.json",
            "dbt_version": "1.7.0",
        },
        "nodes": {
            "model.timed_transforms.fat_censo_leito_ativo": {
                "resource_type": "model",
                "name": "fat_censo_leito_ativo",
                "fqn": ["timed_transforms", "silver_timed", "fat_censo_leito_ativo"],
                "schema": "silver_timed",
                "description": "Censo de leitos ativos por período.",
                "checksum": {"checksum": "abc123def456"},
                "meta": {"version": "1.0.2", "layer": "silver", "status": "stable"},
                "columns": {
                    "gid": {"name": "gid", "description": "Identificador único"},
                    "periodo": {"name": "periodo", "description": "Período de referência"},
                },
            },
            "model.timed_transforms.atendimento_emergencia_agg": {
                "resource_type": "model",
                "name": "atendimento_emergencia_agg",
                "fqn": ["timed_transforms", "gold_timed", "atendimento_emergencia_agg"],
                "schema": "gold_timed",
                "description": "Agregado de atendimentos de emergência.",
                "checksum": {"checksum": "fed321cba654"},
                "meta": {"version": "2.1.0", "layer": "gold", "status": "stable"},
                "columns": {},
            },
            # node que NÃO é model — deve ser ignorado pelo build_registry
            "source.timed_transforms.raw.fat_alta": {
                "resource_type": "source",
                "name": "fat_alta",
                "fqn": ["timed_transforms", "raw"],
                "schema": "raw_timed_dtw",
                "meta": {},
            },
        },
    }


@pytest.fixture
def registry(sample_manifest) -> dict:
    from subhue_reports.registry.loader import build_registry

    return build_registry(sample_manifest)


@pytest.fixture
def sample_report_json() -> dict:
    """JSON de relatório com fontes e versões auditadas."""
    return {
        "meta": {
            "titulo": "Teste de Altas",
            "periodo": "2026-06",
            "fontes": [
                "silver_timed.fat_censo_leito_ativo",
                "gold_timed.atendimento_emergencia_agg",
            ],
            "model_versions": {
                "silver_timed.fat_censo_leito_ativo": "1.0.2",
                "gold_timed.atendimento_emergencia_agg": "2.1.0",
            },
            "data_hora_geracao": "2026-06-24T10:00:00-03:00",
        },
        "secoes": [
            {
                "tipo": "contexto",
                "objetivo": "Validar cobertura de fontes.",
                "descricao": "Análise de cobertura para o período de junho/2026.",
            }
        ],
    }


# ── Fixtures de arquivo ───────────────────────────────────────────────────────

@pytest.fixture
def sample_config() -> dict:
    config_path = FIXTURES_DIR / "sample_config.yaml"
    return yaml.safe_load(config_path.read_text())


@pytest.fixture
def sample_data_csv_path() -> Path:
    return FIXTURES_DIR / "sample_data.csv"


@pytest.fixture
def expected_report_html() -> str:
    return (FIXTURES_DIR / "expected_report.html").read_text()
