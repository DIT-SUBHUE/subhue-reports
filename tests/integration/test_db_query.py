"""
Testes de integração — conexão com Postgres via perfil dbt.
Requerem .env configurado com credenciais reais.

Rodar com:
    pytest -m integration
    just test-integration
"""

import os

import pytest


@pytest.mark.integration
class TestDbConnection:
    def test_conecta_postgres_com_credenciais_env(self):
        """Verifica que as credenciais do .env permitem conexão."""
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ["DBT_IP"],
            port=int(os.environ.get("DBT_PGPORT", "5432")),
            dbname=os.environ["DBT_DATABASE_NAME"],
            user=os.environ["DBT_USER"],
            password=os.environ["DBT_SENHA"],
            connect_timeout=10,
        )
        assert conn.closed == 0
        conn.close()

    def test_schema_silver_timed_existe(self):
        """Schema silver_timed deve existir no banco configurado."""
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ["DBT_IP"],
            port=int(os.environ.get("DBT_PGPORT", "5432")),
            dbname=os.environ["DBT_DATABASE_NAME"],
            user=os.environ["DBT_USER"],
            password=os.environ["DBT_SENHA"],
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
            ("silver_timed",),
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None, "schema silver_timed não encontrado"

    def test_schema_gold_timed_existe(self):
        """Schema gold_timed deve existir no banco configurado."""
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ["DBT_IP"],
            port=int(os.environ.get("DBT_PGPORT", "5432")),
            dbname=os.environ["DBT_DATABASE_NAME"],
            user=os.environ["DBT_USER"],
            password=os.environ["DBT_SENHA"],
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
            ("gold_timed",),
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None, "schema gold_timed não encontrado"


@pytest.mark.integration
class TestManifestApi:
    def test_fetch_remote_meta_retorna_tag_correta(self):
        """GET /api/dbt-manifest/?tag=airflow_astro deve retornar a tag."""
        from subhue_reports.registry.updater import fetch_remote_meta

        base_url = os.environ["SUBHUE_MANIFEST_BASE_URL"].rstrip("/")
        tag = os.environ.get("SUBHUE_MANIFEST_TAG", "airflow_astro")

        meta = fetch_remote_meta(base_url, tag)
        assert meta["tag"] == tag
        assert "updated_at" in meta

    def test_fetch_manifest_content_retorna_nodes(self):
        """GET /api/dbt-manifest/{tag}/content/ deve retornar nodes."""
        from subhue_reports.registry.updater import fetch_manifest_content

        base_url = os.environ["SUBHUE_MANIFEST_BASE_URL"].rstrip("/")
        tag = os.environ.get("SUBHUE_MANIFEST_TAG", "airflow_astro")

        manifest = fetch_manifest_content(base_url, tag)
        assert "nodes" in manifest
        model_count = sum(
            1 for v in manifest["nodes"].values() if v.get("resource_type") == "model"
        )
        assert model_count > 0, "manifest retornou zero models"
