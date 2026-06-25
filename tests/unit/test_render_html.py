"""
Testa funções puras do renderer de HTML.
Importa de reference/utils/ enquanto subhue_reports.renderer não está implementado.
Quando renderer for portado, trocar imports para subhue_reports.renderer.relatorio.
"""

import pytest


# ── Helpers de formatação ─────────────────────────────────────────────────────

class TestFmtNum:
    def setup_method(self):
        from gerador_relatorio_subhue import fmt_num
        self.fmt_num = fmt_num

    def test_inteiro_com_separador_milhar(self):
        assert self.fmt_num(1000) == "1.000"

    def test_numero_grande(self):
        assert self.fmt_num(45231) == "45.231"

    def test_zero(self):
        assert self.fmt_num(0) == "0"

    def test_string_numerica(self):
        assert self.fmt_num("2500") == "2.500"

    def test_valor_nao_numerico_retorna_string(self):
        result = self.fmt_num("N/A")
        assert result == "N/A"

    def test_none_retorna_none_string(self):
        result = self.fmt_num(None)
        assert result == "None"


class TestBadgeClass:
    def setup_method(self):
        from gerador_relatorio_subhue import badge_class
        self.badge_class = badge_class

    def test_acima_de_90_retorna_hi(self):
        assert self.badge_class(90) == "badge hi"
        assert self.badge_class(100) == "badge hi"

    def test_entre_70_e_89_retorna_md(self):
        assert self.badge_class(70) == "badge md"
        assert self.badge_class(89) == "badge md"

    def test_abaixo_de_70_retorna_lo(self):
        assert self.badge_class(69) == "badge lo"
        assert self.badge_class(0) == "badge lo"

    def test_none_retorna_na(self):
        assert self.badge_class(None) == "badge na"


class TestRenderBadgePct:
    def setup_method(self):
        from gerador_relatorio_subhue import render_badge_pct
        self.render = render_badge_pct

    def test_none_retorna_span_vazio(self):
        result = self.render(None)
        assert 'class="badge na"' in result
        assert "—" in result

    def test_valor_alto_usa_hi(self):
        result = self.render(95)
        assert "hi" in result
        assert "95%" in result

    def test_label_customizado_substitui_porcentagem(self):
        result = self.render(83, "83%")
        assert "83%" in result

    def test_html_escapa_label(self):
        result = self.render(50, "<script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestRenderBadgeLabel:
    def setup_method(self):
        from gerador_relatorio_subhue import render_badge_label
        self.render = render_badge_label

    def test_nivel_hi(self):
        result = self.render("Ativo", "hi")
        assert 'class="badge hi"' in result
        assert "Ativo" in result

    def test_nivel_invalido_usa_na(self):
        result = self.render("Teste", "invalido")
        assert 'class="badge na"' in result

    def test_nivel_default_e_na(self):
        result = self.render("Label")
        assert 'class="badge na"' in result


class TestRenderPill:
    def setup_method(self):
        from gerador_relatorio_subhue import render_pill
        self.render = render_pill

    def test_hospital_usa_pill_h(self):
        result = self.render("hospital", "HMSF")
        assert "pill-h" in result
        assert "HMSF" in result

    def test_upa_usa_pill_u(self):
        result = self.render("upa", "UPA João XXIII")
        assert "pill-u" in result

    def test_cer_usa_pill_c(self):
        result = self.render("cer", "CER Barra")
        assert "pill-c" in result

    def test_tipo_desconhecido_usa_pill_o(self):
        result = self.render("outro_tipo", "X")
        assert "pill-o" in result

    def test_case_insensitive(self):
        result = self.render("HOSPITAL", "X")
        assert "pill-h" in result


class TestRenderCell:
    def setup_method(self):
        from gerador_relatorio_subhue import render_cell
        self.render = render_cell

    def test_none_retorna_celula_vazia(self):
        result = self.render(None, "texto")
        assert "<td>" in result
        assert "—" in result

    def test_tipo_numero_alinha_direita(self):
        result = self.render(1500, "numero")
        assert 'class="n"' in result
        assert "1.500" in result

    def test_tipo_texto_escapa_html(self):
        result = self.render("<b>bold</b>", "texto")
        assert "<b>" not in result
        assert "&lt;b&gt;" in result

    def test_tipo_badge_pct_float(self):
        result = self.render(85.0, "badge_pct")
        assert "badge" in result

    def test_tipo_badge_pct_dict(self):
        result = self.render({"pct": 85, "label": "85%"}, "badge_pct")
        assert "badge" in result
        assert "85%" in result

    def test_tipo_badge_label_dict(self):
        result = self.render({"label": "Ativo", "nivel": "hi"}, "badge_label")
        assert "Ativo" in result
        assert "hi" in result

    def test_tipo_codigo_usa_code_tag(self):
        result = self.render("SELECT 1", "codigo")
        assert "<code>" in result
        assert "SELECT 1" in result

    def test_tipo_pill_dict(self):
        result = self.render({"tipo": "hospital", "label": "HMSF"}, "pill")
        assert "pill-h" in result


class TestDeepMerge:
    def setup_method(self):
        from gerador_relatorio_subhue import _deep_merge
        self.merge = _deep_merge

    def test_override_substitui_valor_simples(self):
        result = self.merge({"a": 1}, {"a": 2})
        assert result["a"] == 2

    def test_base_preenche_chave_ausente_no_override(self):
        result = self.merge({"a": 1, "b": 2}, {"a": 99})
        assert result["b"] == 2

    def test_merge_recursivo_em_dicts_aninhados(self):
        base = {"layout": {"height": 260, "font": {"size": 11, "color": "#333"}}}
        override = {"layout": {"height": 320}}
        result = self.merge(base, override)
        assert result["layout"]["height"] == 320
        assert result["layout"]["font"]["size"] == 11  # preservado do base

    def test_lista_nao_e_merged_recursivamente(self):
        result = self.merge({"x": [1, 2]}, {"x": [3]})
        assert result["x"] == [3]


# ── Renderizadores de seção ───────────────────────────────────────────────────

class TestRenderContexto:
    def setup_method(self):
        from gerador_relatorio_subhue import render_contexto
        self.render = render_contexto

    def test_contem_objetivo(self):
        sec = {"objetivo": "Validar cobertura.", "descricao": "Análise detalhada."}
        result = self.render(sec)
        assert "Validar cobertura." in result

    def test_contem_descricao(self):
        sec = {"objetivo": "X", "descricao": "Texto da descrição."}
        result = self.render(sec)
        assert "Texto da descrição." in result

    def test_escapa_html_no_objetivo(self):
        sec = {"objetivo": "<script>xss</script>", "descricao": ""}
        result = self.render(sec)
        assert "<script>" not in result


class TestRenderMetrica:
    def setup_method(self):
        from gerador_relatorio_subhue import render_metrica
        self.render = render_metrica

    def test_contem_titulo(self):
        sec = {"titulo": "Resumo", "items": []}
        result = self.render(sec)
        assert "Resumo" in result

    def test_renderiza_items(self):
        sec = {
            "titulo": "T",
            "items": [
                {"valor": "99%", "label": "Match Alta", "cor": "var(--green)"},
            ],
        }
        result = self.render(sec)
        assert "99%" in result
        assert "Match Alta" in result

    def test_item_com_sub(self):
        sec = {
            "titulo": "T",
            "items": [{"valor": "50%", "label": "Label", "sub": "HMSF · Jun"}],
        }
        result = self.render(sec)
        assert "HMSF · Jun" in result

    def test_items_vazio_nao_levanta_erro(self):
        result = self.render({"titulo": "T", "items": []})
        assert "metrics-grid" in result


class TestRenderTabela:
    def setup_method(self):
        from gerador_relatorio_subhue import render_tabela
        self.render = render_tabela

    def test_renderiza_cabecalho_das_colunas(self):
        sec = {
            "titulo": "Tabela",
            "colunas": [{"label": "Unidade", "tipo": "texto"}, {"label": "Total", "tipo": "numero"}],
            "linhas": [],
        }
        result = self.render(sec)
        assert "Unidade" in result
        assert "Total" in result

    def test_renderiza_linhas(self):
        sec = {
            "titulo": "T",
            "colunas": [{"label": "Nome", "tipo": "texto"}, {"label": "N", "tipo": "numero"}],
            "linhas": [["HMSF", 1234]],
        }
        result = self.render(sec)
        assert "HMSF" in result
        assert "1.234" in result

    def test_nota_opcional_aparece(self):
        sec = {
            "titulo": "T",
            "colunas": [],
            "linhas": [],
            "nota": "Nota de rodapé.",
        }
        result = self.render(sec)
        assert "Nota de rodapé." in result

    def test_sem_nota_nao_aparece_elemento_vazio(self):
        sec = {"titulo": "T", "colunas": [], "linhas": []}
        result = self.render(sec)
        assert "Nota" not in result


class TestRenderTexto:
    def setup_method(self):
        from gerador_relatorio_subhue import render_texto
        self.render = render_texto

    def test_renderiza_paragrafos(self):
        sec = {"titulo": "Metodologia", "paragrafos": ["Parágrafo 1.", "Parágrafo 2."]}
        result = self.render(sec)
        assert "Parágrafo 1." in result
        assert "Parágrafo 2." in result
        assert result.count("<p>") == 2

    def test_paragrafos_vazios_nao_levanta_erro(self):
        result = self.render({"titulo": "T", "paragrafos": []})
        assert "prose" in result
