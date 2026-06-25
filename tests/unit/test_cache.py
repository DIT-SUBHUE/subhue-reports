"""Testes unitários do módulo cache (sem conexão ao banco)."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# ── connection ────────────────────────────────────────────────────────────────

_SUBHUE_ENV = {
    "SUBHUE_IP": "subhue.host",
    "SUBHUE_PGPORT": "5432",
    "SUBHUE_DATABASE_NAME": "subhuedb",
    "SUBHUE_USER": "su",
    "SUBHUE_SENHA": "sp",
}


class TestConnectionParams:
    def test_retorna_params_corretos(self):
        from subhue_reports.cache.connection import connection_params

        with patch.dict(os.environ, _SUBHUE_ENV):
            params = connection_params()

        assert params["host"] == "subhue.host"
        assert params["port"] == 5432
        assert params["dbname"] == "subhuedb"
        assert params["user"] == "su"
        assert params["password"] == "sp"

    def test_porta_convertida_para_int(self):
        from subhue_reports.cache.connection import connection_params

        with patch.dict(os.environ, _SUBHUE_ENV):
            params = connection_params()

        assert isinstance(params["port"], int)

    def test_levanta_com_variaveis_ausentes(self):
        import pytest

        from subhue_reports.cache.connection import connection_params

        env_sem_subhue = {k: v for k, v in os.environ.items() if not k.startswith("SUBHUE_")}
        with (
            patch.dict(os.environ, env_sem_subhue, clear=True),
            pytest.raises(RuntimeError, match="ausentes"),
        ):
            connection_params()


# ── extractor — helpers puros ─────────────────────────────────────────────────

class TestNormalize:
    def test_none_retorna_none(self):
        from subhue_reports.cache.extractor import _normalize
        assert _normalize(None) is None

    def test_int_retorna_int(self):
        from subhue_reports.cache.extractor import _normalize
        assert _normalize(42) == 42

    def test_float_retorna_float(self):
        from subhue_reports.cache.extractor import _normalize
        assert _normalize(3.14) == 3.14

    def test_decimal_vira_float(self):
        from decimal import Decimal

        from subhue_reports.cache.extractor import _normalize
        assert _normalize(Decimal("1.5")) == 1.5

    def test_datetime_vira_isoformat(self):
        from subhue_reports.cache.extractor import _normalize
        dt = datetime(2026, 6, 24, 10, 0, 0)
        result = _normalize(dt)
        assert result == "2026-06-24T10:00:00"

    def test_uuid_vira_string(self):
        import uuid

        from subhue_reports.cache.extractor import _normalize
        uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = _normalize(uid)
        assert result == "12345678-1234-5678-1234-567812345678"


class TestWriteMeta:
    def test_salva_campos_obrigatorios(self, tmp_path):
        from subhue_reports.cache.extractor import _write_meta

        meta_path = tmp_path / "test.meta.json"
        _write_meta(
            meta_path=meta_path,
            source="silver_timed.fat_censo",
            sql="SELECT * FROM silver_timed.fat_censo",
            model_version="1.0.2",
            sql_checksum="abc123",
            filters={"periodo": "2026-06"},
            row_count=100,
        )

        meta = json.loads(meta_path.read_text())
        assert meta["source"] == "silver_timed.fat_censo"
        assert meta["model_version"] == "1.0.2"
        assert meta["sql_checksum"] == "abc123"
        assert meta["row_count"] == 100
        assert meta["filters"] == {"periodo": "2026-06"}
        assert "extracted_at" in meta
        assert meta["query_hash"].startswith("sha256:")


# ── resolver — lógica de cache ────────────────────────────────────────────────

class TestCacheKey:
    def test_inclui_source_e_periodo(self):
        from subhue_reports.cache.resolver import _cache_key
        assert _cache_key("silver_timed.fat_censo", {"periodo": "2026-06"}) == \
               "silver_timed.fat_censo_2026-06"

    def test_sem_periodo_usa_fallback(self):
        from subhue_reports.cache.resolver import _cache_key
        assert _cache_key("silver_timed.fat_censo", {}) == \
               "silver_timed.fat_censo_sem-periodo"


class TestBuildSql:
    def test_sem_filtros_retorna_select_star(self):
        from subhue_reports.cache.resolver import _build_sql
        sql = _build_sql("silver_timed.fat_censo", {})
        assert sql == "SELECT * FROM silver_timed.fat_censo"

    def test_filtros_viram_where(self):
        from subhue_reports.cache.resolver import _build_sql
        sql = _build_sql("silver_timed.fat_censo", {"mes": "2026-06"})
        assert "WHERE mes = '2026-06'" in sql

    def test_periodo_excluido_do_where(self):
        from subhue_reports.cache.resolver import _build_sql
        sql = _build_sql("silver_timed.fat_censo", {"periodo": "2026-06"})
        assert "WHERE" not in sql

    def test_multiplos_filtros_combinados_com_and(self):
        from subhue_reports.cache.resolver import _build_sql
        sql = _build_sql("gold_timed.agg", {"mes": "2026-06", "ubs": "1"})
        assert "AND" in sql


class TestIsExpired:
    def test_extracted_at_recente_nao_expirou(self):
        from subhue_reports.cache.resolver import _is_expired
        recente = datetime.now(tz=UTC) - timedelta(hours=1)
        assert _is_expired(recente.isoformat()) is False

    def test_extracted_at_antigo_expirou(self):
        from subhue_reports.cache.resolver import _is_expired
        antigo = datetime.now(tz=UTC) - timedelta(hours=10)
        assert _is_expired(antigo.isoformat()) is True

    def test_extracted_at_vazio_expirou(self):
        from subhue_reports.cache.resolver import _is_expired
        assert _is_expired("") is True

    def test_extracted_at_invalido_expirou(self):
        from subhue_reports.cache.resolver import _is_expired
        assert _is_expired("nao-e-uma-data") is True

    def test_cache_ttl_hours_env_respeitado(self):
        from subhue_reports.cache.resolver import _is_expired
        # 2h atrás; TTL de 1h → expirou
        dois_h_atras = datetime.now(tz=UTC) - timedelta(hours=2)
        with patch.dict(os.environ, {"CACHE_TTL_HOURS": "1"}):
            assert _is_expired(dois_h_atras.isoformat()) is True

    def test_cache_ttl_hours_env_maior_nao_expirou(self):
        from subhue_reports.cache.resolver import _is_expired
        # 2h atrás; TTL de 8h → não expirou
        dois_h_atras = datetime.now(tz=UTC) - timedelta(hours=2)
        with patch.dict(os.environ, {"CACHE_TTL_HOURS": "8"}):
            assert _is_expired(dois_h_atras.isoformat()) is False


class TestIsCacheValid:
    def _write_meta(self, meta_path: Path, **overrides) -> None:
        meta = {
            "model_version": "1.0.0",
            "sql_checksum": "abc123",
            "extracted_at": datetime.now(tz=UTC).isoformat(),
            **overrides,
        }
        meta_path.write_text(json.dumps(meta))

    def test_hit_quando_tudo_valido(self, tmp_path):
        from subhue_reports.cache.resolver import _is_cache_valid

        parquet = tmp_path / "fonte.parquet"
        meta = tmp_path / "fonte.meta.json"
        parquet.write_text("fake")
        self._write_meta(meta)

        assert _is_cache_valid(parquet, meta, "1.0.0", "abc123") is True

    def test_miss_quando_parquet_ausente(self, tmp_path):
        from subhue_reports.cache.resolver import _is_cache_valid

        meta = tmp_path / "fonte.meta.json"
        self._write_meta(meta)

        assert _is_cache_valid(tmp_path / "nao_existe.parquet", meta, "1.0.0", "abc123") is False

    def test_miss_quando_versao_diferente(self, tmp_path):
        from subhue_reports.cache.resolver import _is_cache_valid

        parquet = tmp_path / "fonte.parquet"
        meta = tmp_path / "fonte.meta.json"
        parquet.write_text("fake")
        self._write_meta(meta, model_version="1.0.0")

        assert _is_cache_valid(parquet, meta, "1.0.1", "abc123") is False

    def test_miss_quando_checksum_diferente(self, tmp_path):
        from subhue_reports.cache.resolver import _is_cache_valid

        parquet = tmp_path / "fonte.parquet"
        meta = tmp_path / "fonte.meta.json"
        parquet.write_text("fake")
        self._write_meta(meta, sql_checksum="abc123")

        assert _is_cache_valid(parquet, meta, "1.0.0", "diferente") is False

    def test_miss_quando_expirado(self, tmp_path):
        from subhue_reports.cache.resolver import _is_cache_valid

        parquet = tmp_path / "fonte.parquet"
        meta = tmp_path / "fonte.meta.json"
        parquet.write_text("fake")
        antigo = datetime.now(tz=UTC) - timedelta(hours=10)
        self._write_meta(meta, extracted_at=antigo.isoformat())

        assert _is_cache_valid(parquet, meta, "1.0.0", "abc123") is False


# ── query ─────────────────────────────────────────────────────────────────────

class TestParquetPathHelpers:
    def test_parquet_path_for_formato(self):
        from subhue_reports.cache.query import parquet_path_for
        path = parquet_path_for("silver_timed.fat_censo", "2026-06")
        assert path == "data/cache/silver_timed.fat_censo_2026-06.parquet"

    def test_parquet_glob_for_formato(self):
        from subhue_reports.cache.query import parquet_glob_for
        glob = parquet_glob_for("silver_timed.fat_censo")
        assert glob == "data/cache/silver_timed.fat_censo_*.parquet"

    def test_parquet_path_for_cache_dir_customizado(self):
        from subhue_reports.cache.query import parquet_path_for
        path = parquet_path_for("gold_timed.agg", "2026-06", cache_dir="/tmp/cache")
        assert path == "/tmp/cache/gold_timed.agg_2026-06.parquet"
