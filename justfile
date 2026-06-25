set dotenv-load := true
export PYTHONPATH := "src"
export PATH := ".venv/bin:" + env_var_or_default("PATH", "/usr/bin:/bin")

# ── Manifest ──────────────────────────────────────────────────────────────────

# Verifica metadados e atualiza manifest local se API tiver versão mais recente
manifest-update:
    python -m subhue_reports.registry.updater

# Força atualização do manifest mesmo se já estiver na versão atual
manifest-update-force:
    python -m subhue_reports.registry.updater --force

# Verifica status do manifest local vs API sem baixar
manifest-status:
    python -m subhue_reports.registry.updater --check-only

# Baixa manifest diretamente (sem verificação de versão)
manifest-fetch:
    python -m subhue_reports.registry.updater --force

# Exibe versões de todos os models do manifest local
manifest-versions:
    #!/usr/bin/env python3
    import json
    manifest = json.load(open("data/manifest.json"))
    models = {
        v["name"]: v.get("meta", {}).get("version", "-")
        for v in manifest["nodes"].values()
        if v.get("resource_type") == "model"
    }
    for name, ver in sorted(models.items()):
        print(f"{ver:12} {name}")

# Verifica se fontes de um relatório estão na versão atual
manifest-check report:
    python -m subhue_reports.registry.checker {{report}}

# ── Cache ──────────────────────────────────────────────────────────────────────

# Lista parquets em cache com status (source, version, data extração)
cache-status:
    #!/usr/bin/env python3
    from pathlib import Path
    import json
    metas = sorted(Path("data/cache").glob("*.meta.json"))
    if not metas:
        print("cache vazio")
    else:
        for meta_file in metas:
            meta = json.loads(meta_file.read_text())
            print(f"{meta['source']:50} v{meta['model_version']:8} extraído {meta['extracted_at'][:10]}")

# Remove todos os parquets do cache
cache-clear:
    find data/cache -name "*.parquet" -o -name "*.meta.json" | xargs rm -f
    @echo "cache limpo"

# Remove parquets com versão desatualizada (compara com manifest local)
cache-prune:
    python -m subhue_reports.cache.resolver --prune

# ── Consulta (DuckDB) ─────────────────────────────────────────────────────────

# Executa SQL sobre parquets do cache
query sql:
    #!/usr/bin/env python3
    from subhue_reports.cache.query import query
    import json
    rows = query("{{sql}}")
    print(json.dumps(rows[:20], ensure_ascii=False, indent=2))

# Shell DuckDB interativo sobre o cache
duckdb-shell:
    duckdb

# ── Relatórios ────────────────────────────────────────────────────────────────

# Gera HTML a partir de JSON já construído
report-render json:
    python -m subhue_reports.renderer.relatorio {{json}} \
        -o data/reports/$(basename {{json}} .json).html

# Valida JSON de relatório contra schema e fontes
report-validate json:
    python -m subhue_reports.registry.checker {{json}}

# ── Documentações ─────────────────────────────────────────────────────────────

# Gera HTML de documentação a partir de JSON
doc-render json:
    python -m subhue_reports.renderer.documentacao {{json}} \
        -o data/reports/$(basename {{json}} .json).html

# ── Sync ──────────────────────────────────────────────────────────────────────

# Lista documentos em data/reports prontos para sync
sync-list:
    python -m subhue_reports.sync.client --list

# Envia novos HTMLs para API Django (skip duplicatas)
sync-push:
    python -m subhue_reports.sync.client \
        --base-url $DADOS_DOCS_API_BASE_URL \
        --username $DADOS_DOCS_API_USERNAME \
        --password $DADOS_DOCS_API_PASSWORD

# Envia todos (sobrescreve existentes)
sync-push-force:
    python -m subhue_reports.sync.client \
        --base-url $DADOS_DOCS_API_BASE_URL \
        --username $DADOS_DOCS_API_USERNAME \
        --password $DADOS_DOCS_API_PASSWORD \
        --force

# Simula sync sem enviar
sync-dry-run:
    python -m subhue_reports.sync.client \
        --base-url $DADOS_DOCS_API_BASE_URL \
        --username $DADOS_DOCS_API_USERNAME \
        --password $DADOS_DOCS_API_PASSWORD \
        --dry-run

# ── Testes ────────────────────────────────────────────────────────────────────

# Roda unit tests (sem integração)
test:
    pytest tests/unit/ -v

# Roda integration tests (requer .env configurado)
test-integration:
    pytest -m integration -v

# Roda todos os testes incluindo integração
test-all:
    pytest -v

# ── Lint & Format ─────────────────────────────────────────────────────────────

# Verifica código com ruff
lint:
    ruff check .

# Formata código com ruff
format:
    ruff format .

# Lint + auto-fix
lint-fix:
    ruff check --fix .

# ── Setup ─────────────────────────────────────────────────────────────────────

# Instala dependências
install:
    pip install -r requirements.txt

# Cria diretórios de dados
dirs:
    mkdir -p data/manifest data/cache data/reports

# Copia .env.example para .env
env-setup:
    cp .env.example .env
    @echo "edite .env com suas credenciais"
