"""Testa carregamento de configuração via env vars e paths."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestLoadManifest:
    def test_carrega_de_path_local(self, tmp_path, sample_manifest):
        from subhue_reports.registry.loader import load_manifest

        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(sample_manifest))

        result = load_manifest(path=str(manifest_file))
        assert result["metadata"]["dbt_version"] == "1.7.0"

    def test_carrega_via_env_manifest_path(self, tmp_path, sample_manifest):
        from subhue_reports.registry.loader import load_manifest

        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(sample_manifest))

        with patch.dict(os.environ, {"DBT_MANIFEST_PATH": str(manifest_file)}):
            result = load_manifest()
        assert "nodes" in result

    def test_levanta_erro_sem_source_configurado(self, tmp_path):
        import subhue_reports.registry.loader as loader_module
        from subhue_reports.registry.loader import load_manifest

        env_limpo = {
            k: v for k, v in os.environ.items()
            if k not in ("DBT_MANIFEST_PATH", "DBT_MANIFEST_URL")
        }
        path_inexistente = tmp_path / "nao_existe.json"
        with patch.dict(os.environ, env_limpo, clear=True):
            with patch.object(loader_module, "_DEFAULT_MANIFEST_PATH", path_inexistente):
                with patch("subhue_reports.registry.loader.Path") as mock_path_cls:
                    mock_path_cls.return_value.exists.return_value = False
                    with pytest.raises(RuntimeError, match="DBT_MANIFEST_PATH"):
                        load_manifest()

    def test_path_arg_tem_precedencia_sobre_env(self, tmp_path, sample_manifest):
        from subhue_reports.registry.loader import load_manifest

        f1 = tmp_path / "m1.json"
        f2 = tmp_path / "m2.json"
        f1.write_text(json.dumps({**sample_manifest, "metadata": {"dbt_version": "1.0.0"}}))
        f2.write_text(json.dumps({**sample_manifest, "metadata": {"dbt_version": "2.0.0"}}))

        with patch.dict(os.environ, {"DBT_MANIFEST_PATH": str(f2)}):
            result = load_manifest(path=str(f1))
        assert result["metadata"]["dbt_version"] == "1.0.0"


class TestUpdaterAuth:
    def test_get_token_levanta_sem_credenciais(self):
        from subhue_reports.registry.updater import _get_token

        env_limpo = {
            k: v for k, v in os.environ.items()
            if k not in ("DBT_MANIFEST_API_USERNAME", "DBT_MANIFEST_API_PASSWORD")
        }
        with patch.dict(os.environ, env_limpo, clear=True):
            with pytest.raises(RuntimeError, match="DBT_MANIFEST_API_USERNAME"):
                _get_token("https://api.exemplo.gov.br")

    def test_get_token_retorna_token_da_api(self):
        from subhue_reports.registry.updater import _get_token

        mock_response = {"token": "tok-abc123"}
        with (
            patch("subhue_reports.registry.updater.requests.post") as mock_post,
            patch.dict(os.environ, {
                "DBT_MANIFEST_API_USERNAME": "user",
                "DBT_MANIFEST_API_PASSWORD": "pass",
            }),
        ):
            mock_post.return_value.json.return_value = mock_response
            mock_post.return_value.raise_for_status = lambda: None
            token = _get_token("https://api.exemplo.gov.br")

        assert token == "tok-abc123"
        mock_post.assert_called_once_with(
            "https://api.exemplo.gov.br/autenticacao/token/",
            json={"username": "user", "password": "pass"},
            timeout=30,
        )

    def test_auth_headers_incluem_bearer_token(self):
        from subhue_reports.registry.updater import _auth_headers

        with patch("subhue_reports.registry.updater._get_token", return_value="tok-xyz"):
            headers = _auth_headers("https://api.exemplo.gov.br")

        assert headers == {"Authorization": "Token tok-xyz"}


class TestUpdaterConfig:
    def test_load_local_meta_retorna_none_quando_ausente(self, tmp_path):
        from subhue_reports.registry.updater import load_local_meta

        result = load_local_meta(tmp_path / "nao_existe.json")
        assert result is None

    def test_load_local_meta_carrega_json(self, tmp_path):
        from subhue_reports.registry.updater import load_local_meta

        meta = {"tag": "airflow_astro", "updated_at": "2026-06-24T10:00:00Z"}
        meta_file = tmp_path / "manifest.meta.json"
        meta_file.write_text(json.dumps(meta))

        result = load_local_meta(meta_file)
        assert result["tag"] == "airflow_astro"
        assert result["updated_at"] == "2026-06-24T10:00:00Z"

    def test_check_and_update_levanta_sem_base_url(self):
        from subhue_reports.registry.updater import check_and_update

        env_limpo = {k: v for k, v in os.environ.items() if k != "DBT_MANIFEST_API_BASE_URL"}
        with patch.dict(os.environ, env_limpo, clear=True):
            with pytest.raises(RuntimeError, match="DBT_MANIFEST_API_BASE_URL"):
                check_and_update()

    def test_check_and_update_skip_quando_atualizado(self, tmp_path):
        from subhue_reports.registry.updater import check_and_update

        remote_meta = {"tag": "airflow_astro", "updated_at": "2026-06-20T10:00:00Z"}
        local_meta = {"tag": "airflow_astro", "updated_at": "2026-06-24T10:00:00Z"}

        meta_file = tmp_path / "manifest.meta.json"
        meta_file.write_text(json.dumps(local_meta))

        with (
            patch("subhue_reports.registry.updater.fetch_remote_meta", return_value=remote_meta),
            patch.dict(os.environ, {"DBT_MANIFEST_API_BASE_URL": "https://api.exemplo.gov.br"}),
        ):
            updated = check_and_update(meta_path=meta_file, manifest_path=tmp_path / "m.json")

        assert updated is False

    def test_check_and_update_baixa_quando_remoto_mais_novo(self, tmp_path, sample_manifest):
        from subhue_reports.registry.updater import check_and_update

        remote_meta = {"tag": "airflow_astro", "updated_at": "2026-06-25T10:00:00Z"}
        local_meta = {"tag": "airflow_astro", "updated_at": "2026-06-20T10:00:00Z"}

        meta_file = tmp_path / "manifest.meta.json"
        meta_file.write_text(json.dumps(local_meta))
        manifest_path = tmp_path / "manifest.json"

        with (
            patch("subhue_reports.registry.updater.fetch_remote_meta", return_value=remote_meta),
            patch("subhue_reports.registry.updater.fetch_manifest_content", return_value=sample_manifest),
            patch.dict(os.environ, {"DBT_MANIFEST_API_BASE_URL": "https://api.exemplo.gov.br"}),
        ):
            updated = check_and_update(meta_path=meta_file, manifest_path=manifest_path)

        assert updated is True
        assert manifest_path.exists()
        saved = json.loads(manifest_path.read_text())
        assert "nodes" in saved

    def test_check_and_update_salva_meta_com_fetched_at(self, tmp_path, sample_manifest):
        from subhue_reports.registry.updater import check_and_update

        remote_meta = {"tag": "airflow_astro", "updated_at": "2026-06-25T10:00:00Z"}
        meta_file = tmp_path / "manifest.meta.json"

        with (
            patch("subhue_reports.registry.updater.fetch_remote_meta", return_value=remote_meta),
            patch("subhue_reports.registry.updater.fetch_manifest_content", return_value=sample_manifest),
            patch.dict(os.environ, {"DBT_MANIFEST_API_BASE_URL": "https://api.exemplo.gov.br"}),
        ):
            check_and_update(meta_path=meta_file, manifest_path=tmp_path / "m.json")

        saved_meta = json.loads(meta_file.read_text())
        assert "fetched_at" in saved_meta
        assert saved_meta["tag"] == "airflow_astro"

    def test_check_and_update_force_baixa_mesmo_atualizado(self, tmp_path, sample_manifest):
        from subhue_reports.registry.updater import check_and_update

        remote_meta = {"tag": "airflow_astro", "updated_at": "2026-06-20T10:00:00Z"}
        local_meta = {"tag": "airflow_astro", "updated_at": "2026-06-24T10:00:00Z"}

        meta_file = tmp_path / "manifest.meta.json"
        meta_file.write_text(json.dumps(local_meta))

        with (
            patch("subhue_reports.registry.updater.fetch_remote_meta", return_value=remote_meta),
            patch("subhue_reports.registry.updater.fetch_manifest_content", return_value=sample_manifest),
            patch.dict(os.environ, {"DBT_MANIFEST_API_BASE_URL": "https://api.exemplo.gov.br"}),
        ):
            updated = check_and_update(
                meta_path=meta_file,
                manifest_path=tmp_path / "m.json",
                force=True,
            )

        assert updated is True

    def test_check_and_update_cria_subdir_se_necessario(self, tmp_path, sample_manifest):
        from subhue_reports.registry.updater import check_and_update

        remote_meta = {"tag": "airflow_astro", "updated_at": "2026-06-25T10:00:00Z"}
        manifest_path = tmp_path / "data" / "manifest" / "manifest.json"
        meta_path = tmp_path / "data" / "manifest" / "manifest.meta.json"

        with (
            patch("subhue_reports.registry.updater.fetch_remote_meta", return_value=remote_meta),
            patch("subhue_reports.registry.updater.fetch_manifest_content", return_value=sample_manifest),
            patch.dict(os.environ, {"DBT_MANIFEST_API_BASE_URL": "https://api.exemplo.gov.br"}),
        ):
            check_and_update(manifest_path=manifest_path, meta_path=meta_path)

        assert manifest_path.exists()
