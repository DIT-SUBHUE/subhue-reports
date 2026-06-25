"""
Teste de integração: resolve_source bate no banco na 1ª chamada, usa cache na 2ª.

Requer .env.test com variáveis SUBHUE_*.
Rodar: just test-integration
"""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

FONTE = "raw_timed_dtw.fat_estabelecimento"
FILTERS: dict = {}


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.mark.integration
def test_segunda_chamada_usa_cache(cache_dir: Path, caplog):
    from subhue_reports.cache.resolver import resolve_source

    with caplog.at_level(logging.INFO, logger="subhue_reports.cache.resolver"):
        # 1ª chamada: cache miss → bate no banco
        path_1 = resolve_source(FONTE, FILTERS, registry={}, cache_dir=cache_dir)

    assert path_1.exists(), "parquet não foi criado"
    assert path_1.with_suffix(".meta.json").exists(), "meta.json não foi criado"
    assert any("cache miss" in r.message for r in caplog.records), "1ª chamada deveria ser miss"

    caplog.clear()

    with (
        caplog.at_level(logging.INFO, logger="subhue_reports.cache.resolver"),
        patch("subhue_reports.cache.resolver.extract_to_parquet") as mock_extract,
    ):
        # 2ª chamada: cache hit → não chama extractor
        path_2 = resolve_source(FONTE, FILTERS, registry={}, cache_dir=cache_dir)

    mock_extract.assert_not_called()
    assert path_2 == path_1
    assert any("cache hit" in r.message for r in caplog.records), "2ª chamada deveria ser hit"
