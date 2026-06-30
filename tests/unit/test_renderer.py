"""Testes unitários do módulo renderer (sem I/O externo exceto fixtures)."""

from pathlib import Path

# ── _output helpers ───────────────────────────────────────────────────────────

class TestSlugify:
    def test_titulo_simples(self):
        from subhue_reports.renderer._output import slugify
        assert slugify("Painel Geral") == "PAINEL_GERAL"

    def test_remove_acentos(self):
        from subhue_reports.renderer._output import slugify
        assert slugify("Ocupação Média") == "OCUPACAO_MEDIA"

    def test_colapsa_multiplos_underscores(self):
        from subhue_reports.renderer._output import slugify
        assert slugify("A  B") == "A_B"

    def test_caracteres_especiais(self):
        from subhue_reports.renderer._output import slugify
        assert slugify("fat_censo_leito_ativo") == "FAT_CENSO_LEITO_ATIVO"


class TestResolveOutputDir:
    def test_tipo_dashboard(self):
        from subhue_reports.renderer._output import resolve_output_dir
        dados = {"meta": {"titulo": "Painel", "tipo_documento": "dashboard"}}
        path = resolve_output_dir(dados, Path("/tmp/reports"))
        assert "dashboards" in str(path)
        assert "PAINEL" in str(path)

    def test_tipo_relatorio(self):
        from subhue_reports.renderer._output import resolve_output_dir
        dados = {"meta": {"titulo": "Rel", "tipo_documento": "relatorio"}}
        path = resolve_output_dir(dados, Path("/tmp/reports"))
        assert "relatorios" in str(path)

    def test_tipo_documentacao(self):
        from subhue_reports.renderer._output import resolve_output_dir
        dados = {"meta": {"titulo": "Doc", "tipo_documento": "documentacao"}}
        path = resolve_output_dir(dados, Path("/tmp/reports"))
        assert "documentacoes" in str(path)

    def test_tipo_ausente_usa_relatorios(self):
        from subhue_reports.renderer._output import resolve_output_dir
        dados = {"meta": {"titulo": "X"}}
        path = resolve_output_dir(dados, Path("/tmp/reports"))
        assert "relatorios" in str(path)

    def test_formato_timestamp(self):
        from subhue_reports.renderer._output import resolve_output_dir
        dados = {"meta": {"titulo": "T", "tipo_documento": "relatorio"}}
        path = resolve_output_dir(dados, Path("/tmp/reports"))
        nome_dir = path.name  # 2026_06_26__15_52__T
        parts = nome_dir.split("__")
        assert len(parts) == 3
        assert len(parts[0]) == 10  # YYYY_MM_DD


# ── _html helpers ─────────────────────────────────────────────────────────────

class TestEsc:
    def test_escapa_html(self):
        from subhue_reports.renderer._html import esc
        assert esc("<script>") == "&lt;script&gt;"

    def test_none_vira_string_vazia(self):
        from subhue_reports.renderer._html import esc
        assert esc(None) == ""

    def test_preserva_texto_normal(self):
        from subhue_reports.renderer._html import esc
        assert esc("texto simples") == "texto simples"


class TestFmtNum:
    def test_milhar_com_ponto(self):
        from subhue_reports.renderer._html import fmt_num
        assert fmt_num(1000) == "1.000"

    def test_milhao(self):
        from subhue_reports.renderer._html import fmt_num
        assert fmt_num(1_000_000) == "1.000.000"

    def test_valor_invalido_retorna_string(self):
        from subhue_reports.renderer._html import fmt_num
        assert fmt_num("abc") == "abc"

    def test_none_retorna_none_string(self):
        from subhue_reports.renderer._html import fmt_num
        assert fmt_num(None) == "None"


class TestBadgeClass:
    def test_none_retorna_na(self):
        from subhue_reports.renderer._html import badge_class
        assert badge_class(None) == "badge na"

    def test_100_retorna_hi(self):
        from subhue_reports.renderer._html import badge_class
        assert badge_class(100) == "badge hi"

    def test_90_retorna_hi(self):
        from subhue_reports.renderer._html import badge_class
        assert badge_class(90) == "badge hi"

    def test_89_retorna_md(self):
        from subhue_reports.renderer._html import badge_class
        assert badge_class(89) == "badge md"

    def test_70_retorna_md(self):
        from subhue_reports.renderer._html import badge_class
        assert badge_class(70) == "badge md"

    def test_69_retorna_lo(self):
        from subhue_reports.renderer._html import badge_class
        assert badge_class(69) == "badge lo"

    def test_zero_retorna_lo(self):
        from subhue_reports.renderer._html import badge_class
        assert badge_class(0) == "badge lo"


class TestRenderCell:
    def test_none_mostra_traco(self):
        from subhue_reports.renderer._html import render_cell
        assert "—" in render_cell(None, "texto")

    def test_numero_com_separador(self):
        from subhue_reports.renderer._html import render_cell
        html = render_cell(1000, "numero")
        assert "1.000" in html
        assert 'class="n"' in html

    def test_badge_pct_float(self):
        from subhue_reports.renderer._html import render_cell
        html = render_cell(95.0, "badge_pct")
        assert "badge hi" in html

    def test_badge_pct_dict(self):
        from subhue_reports.renderer._html import render_cell
        html = render_cell({"pct": 95, "label": "95%"}, "badge_pct")
        assert "95%" in html

    def test_badge_label_str(self):
        from subhue_reports.renderer._html import render_cell
        html = render_cell("OK", "badge_label")
        assert "OK" in html
        assert "badge" in html

    def test_badge_label_dict(self):
        from subhue_reports.renderer._html import render_cell
        html = render_cell({"label": "Ativo", "nivel": "hi"}, "badge_label")
        assert "Ativo" in html
        assert "badge hi" in html

    def test_codigo_envolve_em_code(self):
        from subhue_reports.renderer._html import render_cell
        html = render_cell("fat_censo", "codigo")
        assert "<code>" in html
        assert "fat_censo" in html

    def test_pill_dict(self):
        from subhue_reports.renderer._html import render_cell
        html = render_cell({"tipo": "hospital", "label": "HMSF"}, "pill")
        assert "pill-h" in html
        assert "HMSF" in html

    def test_texto_default(self):
        from subhue_reports.renderer._html import render_cell
        html = render_cell("valor", "texto")
        assert "valor" in html


class TestDeepMerge:
    def test_base_preenchida_por_override(self):
        from subhue_reports.renderer._html import deep_merge
        result = deep_merge({"a": 1, "b": 2}, {"b": 99, "c": 3})
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_merge_recursivo(self):
        from subhue_reports.renderer._html import deep_merge
        result = deep_merge({"x": {"a": 1, "b": 2}}, {"x": {"b": 99}})
        assert result["x"] == {"a": 1, "b": 99}

    def test_nao_modifica_base(self):
        from subhue_reports.renderer._html import deep_merge
        base = {"a": 1}
        deep_merge(base, {"a": 2})
        assert base == {"a": 1}


# ── _meta ─────────────────────────────────────────────────────────────────────

class TestGetGenerationTimestamp:
    def test_usa_data_hora_geracao(self):
        from subhue_reports.renderer._meta import get_generation_timestamp
        meta = {"data_hora_geracao": "2026-06-25T10:00:00-03:00"}
        assert get_generation_timestamp(meta) == "2026-06-25T10:00:00-03:00"

    def test_fallback_para_data_geracao(self):
        from subhue_reports.renderer._meta import get_generation_timestamp
        meta = {"data_geracao": "2026-06-25"}
        assert get_generation_timestamp(meta) == "2026-06-25"

    def test_sem_campo_retorna_timestamp_atual(self):
        from subhue_reports.renderer._meta import get_generation_timestamp
        result = get_generation_timestamp({})
        assert "2026" in result or "202" in result


class TestEnsureGenerationTimestamp:
    def test_adiciona_timestamp_quando_ausente(self):
        from subhue_reports.renderer._meta import ensure_generation_timestamp
        payload = {"meta": {}}
        changed = ensure_generation_timestamp(payload)
        assert changed is True
        assert "data_hora_geracao" in payload["meta"]

    def test_nao_sobrescreve_existente(self):
        from subhue_reports.renderer._meta import ensure_generation_timestamp
        payload = {"meta": {"data_hora_geracao": "2026-01-01T00:00:00"}}
        changed = ensure_generation_timestamp(payload)
        assert changed is False
        assert payload["meta"]["data_hora_geracao"] == "2026-01-01T00:00:00"

    def test_cria_meta_se_ausente(self):
        from subhue_reports.renderer._meta import ensure_generation_timestamp
        payload = {}
        ensure_generation_timestamp(payload)
        assert "meta" in payload
        assert "data_hora_geracao" in payload["meta"]


# ── sections ──────────────────────────────────────────────────────────────────

_DADOS_EXEMPLO = {
    "meta": {"titulo": "Teste", "periodo": "Jun/2026"},
    "secoes": [
        {"tipo": "contexto", "objetivo": "Obj", "descricao": "Desc"},
        {"tipo": "texto", "titulo": "Metodologia", "paragrafos": ["P1", "P2"]},
    ],
}


class TestExplodeAssemble:
    def test_round_trip_sem_perda(self, tmp_path):
        from subhue_reports.renderer.sections import assemble_report, explode_report

        dest = tmp_path / "relatorio"
        explode_report(_DADOS_EXEMPLO, dest)
        resultado = assemble_report(dest)

        assert resultado["meta"]["titulo"] == "Teste"
        assert len(resultado["secoes"]) == 2
        assert resultado["secoes"][0]["tipo"] == "contexto"
        assert resultado["secoes"][1]["tipo"] == "texto"

    def test_arquivos_criados(self, tmp_path):
        from subhue_reports.renderer.sections import explode_report

        dest = tmp_path / "relatorio"
        explode_report(_DADOS_EXEMPLO, dest)

        assert (dest / "meta.json").exists()
        assert (dest / "01_contexto.json").exists()
        assert (dest / "02_texto.json").exists()

    def test_assemble_sem_meta_levanta(self, tmp_path):
        import pytest

        from subhue_reports.renderer.sections import assemble_report

        with pytest.raises(FileNotFoundError, match="meta.json"):
            assemble_report(tmp_path / "inexistente")

    def test_deletar_arquivo_remove_secao(self, tmp_path):
        from subhue_reports.renderer.sections import assemble_report, explode_report

        dest = tmp_path / "relatorio"
        explode_report(_DADOS_EXEMPLO, dest)
        (dest / "01_contexto.json").unlink()
        resultado = assemble_report(dest)

        assert len(resultado["secoes"]) == 1
        assert resultado["secoes"][0]["tipo"] == "texto"


class TestListSections:
    def test_retorna_lista_com_idx_tipo_filename(self, tmp_path):
        from subhue_reports.renderer.sections import explode_report, list_sections

        dest = tmp_path / "relatorio"
        explode_report(_DADOS_EXEMPLO, dest)
        secs = list_sections(dest)

        assert len(secs) == 2
        assert secs[0] == (1, "contexto", "01_contexto.json")
        assert secs[1] == (2, "texto", "02_texto.json")


# ── render dispatcher ────────────────────────────────────────────────────────

class TestRender:
    def test_sem_tipo_documento_usa_relatorio(self):
        from subhue_reports.renderer import render

        dados = {
            "meta": {"titulo": "Sem tipo"},
            "secoes": [{"tipo": "contexto", "objetivo": "O", "descricao": "D"}],
        }
        html = render(dados)
        assert "Sem tipo" in html

    def test_tipo_relatorio_usa_render_report(self):
        from subhue_reports.renderer import render

        dados = {
            "meta": {"titulo": "Rel", "tipo_documento": "relatorio"},
            "secoes": [{"tipo": "contexto", "objetivo": "O", "descricao": "D"}],
        }
        html = render(dados)
        assert "Rel" in html

    def test_tipo_documentacao_usa_render_doc(self):
        from subhue_reports.renderer import render

        dados = {
            "meta": {"titulo": "Doc técnica", "tipo_documento": "documentacao"},
            "secoes": [{"tipo": "visao_geral", "descricao": "Desc", "detalhes": []}],
        }
        html = render(dados)
        assert "Doc técnica" in html
        assert 'class="toc"' in html

    def test_tipo_invalido_cai_em_relatorio(self):
        from subhue_reports.renderer import render

        dados = {
            "meta": {"titulo": "Fallback", "tipo_documento": "desconhecido"},
            "secoes": [],
        }
        html = render(dados)
        assert "Fallback" in html


# ── render_report smoke test ──────────────────────────────────────────────────

_DADOS_SEM_GRAFICO = {
    "meta": {"titulo": "Relatório Teste", "periodo": "Jun/2026", "fontes": ["raw.fat_censo"]},
    "secoes": [
        {"tipo": "contexto", "objetivo": "Obj", "descricao": "Desc"},
        {"tipo": "metrica", "titulo": "Números", "items": [{"valor": "99%", "label": "Match"}]},
        {"tipo": "texto", "titulo": "Notas", "paragrafos": ["Texto"]},
    ],
}


class TestRenderReport:
    def test_html_contem_titulo(self):
        from subhue_reports.renderer.relatorio import render_report

        html = render_report(_DADOS_SEM_GRAFICO)
        assert "Relatório Teste" in html

    def test_html_contem_secoes(self):
        from subhue_reports.renderer.relatorio import render_report

        html = render_report(_DADOS_SEM_GRAFICO)
        assert "Contexto" in html
        assert "99%" in html
        assert "Notas" in html

    def test_html_sem_grafico_nao_inclui_plotly(self):
        from subhue_reports.renderer.relatorio import render_report

        html = render_report(_DADOS_SEM_GRAFICO, plotly_js="")
        assert "Plotly.newPlot" not in html

    def test_tipo_desconhecido_mostra_erro_inline(self):
        from subhue_reports.renderer.relatorio import render_report

        dados = {**_DADOS_SEM_GRAFICO, "secoes": [{"tipo": "inexistente"}]}
        html = render_report(dados)
        assert "inexistente" in html


# ── render_doc smoke test ─────────────────────────────────────────────────────

_DADOS_DOC = {
    "meta": {
        "titulo": "fat_censo_leito_ativo",
        "subtitulo": "Model silver_timed",
        "versao": "v1.0",
    },
    "secoes": [
        {
            "tipo": "visao_geral",
            "titulo": "Visão Geral",
            "descricao": "Censo de leitos ativos.",
            "detalhes": ["Grain: dia × leito."],
        },
        {
            "tipo": "colunas",
            "items": [
                {
                    "nome": "gid", "tipo_dado": "UUID",
                    "pk": True, "obrigatorio": True, "descricao": "Chave",
                },
                {
                    "nome": "periodo", "tipo_dado": "DATE",
                    "obrigatorio": False, "descricao": "Período",
                },
            ],
        },
        {
            "tipo": "changelog",
            "items": [
                {"versao": "v1.0", "data": "01/06/2026", "tipo": "feat", "descricao": "Criação"},
            ],
        },
    ],
}


class TestRenderDoc:
    def test_html_contem_titulo(self):
        from subhue_reports.renderer.documentacao import render_doc

        html = render_doc(_DADOS_DOC)
        assert "fat_censo_leito_ativo" in html

    def test_html_contem_toc(self):
        from subhue_reports.renderer.documentacao import render_doc

        html = render_doc(_DADOS_DOC)
        assert 'class="toc"' in html

    def test_html_contem_colunas(self):
        from subhue_reports.renderer.documentacao import render_doc

        html = render_doc(_DADOS_DOC)
        assert "gid" in html
        assert "PK" in html

    def test_html_contem_changelog(self):
        from subhue_reports.renderer.documentacao import render_doc

        html = render_doc(_DADOS_DOC)
        assert "FEAT" in html
        assert "Criação" in html

    def test_html_sem_grafico_nao_inclui_plotly(self):
        from subhue_reports.renderer.documentacao import render_doc

        html = render_doc(_DADOS_DOC)
        assert "Plotly.newPlot" not in html


# ── render_doc seções específicas ─────────────────────────────────────────────

class TestRenderDependencias:
    def test_upstream_downstream(self):
        from subhue_reports.renderer.documentacao import render_dependencias

        sec = {
            "tipo": "dependencias",
            "upstream": [{"nome": "raw.fat_alta", "descricao": "Fonte"}],
            "downstream": ["gold.agg"],
        }
        html = render_dependencias(sec)
        assert "raw.fat_alta" in html
        assert "gold.agg" in html
        assert "Upstream" in html
        assert "Downstream" in html


class TestRenderChangelog:
    def test_tipos_de_badge(self):
        from subhue_reports.renderer.documentacao import render_changelog

        sec = {
            "tipo": "changelog",
            "items": [
                {"versao": "v1", "data": "01/01/2026", "tipo": "feat", "descricao": "Nova feature"},
                {"versao": "v0", "data": "01/12/2025", "tipo": "fix", "descricao": "Correção"},
            ],
        }
        html = render_changelog(sec)
        assert "FEAT" in html
        assert "FIX" in html


# ── render dispatcher: dashboard ─────────────────────────────────────────────

_DADOS_DASHBOARD = {
    "meta": {"titulo": "Painel Teste", "tipo_documento": "dashboard"},
    "filtros": [
        {
            "id": "periodo",
            "label": "Período",
            "campo": "periodo",
            "todos_label": "Todos",
            "opcoes": ["2026-06"],
        }
    ],
    "dados": {
        "vendas": [
            {"produto": "A", "periodo": "2026-06", "valor": 100.0},
            {"produto": "B", "periodo": "2026-06", "valor": 200.0},
        ]
    },
    "paineis": [
        {
            "id": "m1",
            "tipo": "metrica",
            "titulo": "Valor Total",
            "dataset": "vendas",
            "campo": "valor",
            "agregacao": "soma",
            "formato": "numero",
            "largura": "quarto",
            "filtros_ativos": ["periodo"],
        },
        {
            "id": "g1",
            "tipo": "grafico",
            "titulo": "Por Produto",
            "dataset": "vendas",
            "chart_type": "bar",
            "x": "produto",
            "y": "valor",
            "largura": "metade",
            "filtros_ativos": ["periodo"],
        },
        {
            "id": "t1",
            "tipo": "tabela",
            "titulo": "Detalhamento",
            "dataset": "vendas",
            "colunas": [
                {"campo": "produto", "label": "Produto"},
                {"campo": "valor", "label": "Valor", "formato": "numero"},
            ],
            "largura": "completo",
            "filtros_ativos": ["periodo"],
        },
    ],
}


class TestRenderDashboard:
    def test_html_contem_titulo(self):
        from subhue_reports.renderer.dashboard import render_dashboard

        html = render_dashboard(_DADOS_DASHBOARD)
        assert "Painel Teste" in html

    def test_html_contem_filtro(self):
        from subhue_reports.renderer.dashboard import render_dashboard

        html = render_dashboard(_DADOS_DASHBOARD)
        assert 'id="filtro_periodo"' in html
        assert "Período" in html

    def test_html_contem_paineis(self):
        from subhue_reports.renderer.dashboard import render_dashboard

        html = render_dashboard(_DADOS_DASHBOARD)
        assert 'id="val_m1"' in html
        assert 'id="chart_g1"' in html
        assert 'id="tbody_t1"' in html

    def test_html_embute_dados(self):
        from subhue_reports.renderer.dashboard import render_dashboard

        html = render_dashboard(_DADOS_DASHBOARD)
        assert '"vendas"' in html
        assert '"produto"' in html

    def test_html_contem_js_reativo(self):
        from subhue_reports.renderer.dashboard import render_dashboard

        html = render_dashboard(_DADOS_DASHBOARD)
        assert "Plotly.react" in html
        assert "atualizar" in html

    def test_render_dispatcher_tipo_dashboard(self):
        from subhue_reports.renderer import render

        html = render(_DADOS_DASHBOARD)
        assert "Painel Teste" in html
        assert "dash-grid" in html

    def test_painel_tipo_desconhecido_nao_quebra(self):
        from subhue_reports.renderer.dashboard import render_dashboard

        dados = {**_DADOS_DASHBOARD, "paineis": [{"id": "x", "tipo": "radar", "dataset": "vendas"}]}
        html = render_dashboard(dados)
        assert "radar" in html
