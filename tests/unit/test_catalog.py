"""Tests for subhue_reports.registry.catalog."""

import pytest

from subhue_reports.registry.catalog import catalog, detail, search, to_context


# ── catalog ──────────────────────────────────────────────────────────────────


def test_catalog_retorna_apenas_models(registry):
    result = catalog(registry)
    names = [m["name"] for m in result]
    assert "fat_alta" not in names  # source node ignorado


def test_catalog_campos_obrigatorios(registry):
    result = catalog(registry)
    required = {"name", "table", "schema", "layer", "status", "version", "grain", "description", "primary_key"}
    for model in result:
        assert required <= model.keys()


def test_catalog_table_formato_schema_ponto_nome(registry):
    result = catalog(registry)
    leito = next(m for m in result if m["name"] == "fat_censo_leito_ativo")
    assert leito["table"] == "silver_timed.fat_censo_leito_ativo"


def test_catalog_ordenado_por_nome(registry):
    result = catalog(registry)
    names = [m["name"] for m in result]
    assert names == sorted(names)


def test_catalog_versao_mapeada(registry):
    result = catalog(registry)
    agg = next(m for m in result if m["name"] == "atendimento_emergencia_agg")
    assert agg["version"] == "2.1.0"
    assert agg["layer"] == "gold"
    assert agg["status"] == "stable"


# ── detail ───────────────────────────────────────────────────────────────────


def test_detail_retorna_none_para_model_inexistente(registry):
    assert detail("nao_existe", registry) is None


def test_detail_inclui_columns(registry):
    result = detail("fat_censo_leito_ativo", registry)
    assert result is not None
    assert "columns" in result
    col_names = [c["name"] for c in result["columns"]]
    assert "gid" in col_names
    assert "periodo" in col_names


def test_detail_columns_tem_descricao(registry):
    result = detail("fat_censo_leito_ativo", registry)
    gid_col = next(c for c in result["columns"] if c["name"] == "gid")
    assert gid_col["description"] == "Identificador único"


def test_detail_model_sem_columns_retorna_lista_vazia(registry):
    result = detail("atendimento_emergencia_agg", registry)
    assert result["columns"] == []


def test_detail_inclui_sql_checksum(registry):
    result = detail("fat_censo_leito_ativo", registry)
    assert result["sql_checksum"] == "abc123def456"


def test_detail_inclui_fqn(registry):
    result = detail("fat_censo_leito_ativo", registry)
    assert "timed_transforms" in result["fqn"]


# ── search ───────────────────────────────────────────────────────────────────


def test_search_por_layer(registry):
    results = search(registry, layer="gold")
    assert all(m["layer"] == "gold" for m in results)
    assert any(m["name"] == "atendimento_emergencia_agg" for m in results)


def test_search_por_layer_sem_resultados(registry):
    results = search(registry, layer="bronze")
    assert results == []


def test_search_por_schema(registry):
    results = search(registry, schema="silver_timed")
    assert all(m["schema"] == "silver_timed" for m in results)


def test_search_por_name_contains(registry):
    results = search(registry, name_contains="censo")
    assert all("censo" in m["name"] for m in results)


def test_search_filtros_combinados(registry):
    results = search(registry, layer="silver", name_contains="censo")
    assert len(results) == 1
    assert results[0]["name"] == "fat_censo_leito_ativo"


def test_search_sem_filtros_retorna_todos(registry):
    results = search(registry)
    assert len(results) == len(catalog(registry))


# ── to_context ───────────────────────────────────────────────────────────────


def test_to_context_contem_nome_do_model(registry):
    ctx = to_context(registry)
    assert "fat_censo_leito_ativo" in ctx
    assert "atendimento_emergencia_agg" in ctx


def test_to_context_contem_versao_e_layer(registry):
    ctx = to_context(registry)
    assert "v1.0.2" in ctx
    assert "silver" in ctx


def test_to_context_contem_colunas(registry):
    ctx = to_context(registry)
    assert "gid" in ctx


def test_to_context_sem_colunas(registry):
    ctx = to_context(registry, include_columns=False)
    assert "gid" not in ctx


def test_to_context_registry_vazio():
    ctx = to_context({})
    assert ctx == "No models found."


def test_to_context_subset_de_models(registry):
    ctx = to_context(registry, models=["fat_censo_leito_ativo"])
    assert "fat_censo_leito_ativo" in ctx
    assert "atendimento_emergencia_agg" not in ctx


def test_to_context_cabecalho_com_total(registry):
    ctx = to_context(registry)
    assert "MANIFEST MODELS (2 total)" in ctx


def test_to_context_tabela_ponto_nome_no_header(registry):
    ctx = to_context(registry)
    assert "[silver_timed.fat_censo_leito_ativo]" in ctx
