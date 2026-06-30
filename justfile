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

# ── Catalog ────────────────────────────────────────────────────────────────────

# Lista todos os models do manifest em formato LLM-friendly
manifest-catalog:
    python -m subhue_reports.registry.catalog --no-columns

# Lista models com colunas (contexto completo para LLM)
manifest-catalog-full:
    python -m subhue_reports.registry.catalog

# Detalhe de um model específico
manifest-catalog-model model:
    python -m subhue_reports.registry.catalog {{model}}

# Filtra models por layer (silver, gold)
manifest-catalog-layer layer:
    python -m subhue_reports.registry.catalog --layer {{layer}} --no-columns

# Filtra models por schema (silver_timed, gold_timed, raw_sarah)
manifest-catalog-schema schema:
    python -m subhue_reports.registry.catalog --schema {{schema}} --no-columns

# Busca models por substring do nome
manifest-catalog-search name:
    python -m subhue_reports.registry.catalog --name {{name}} --no-columns

# Lista schemas e layers disponíveis no manifest
manifest-catalog-info:
    #!/usr/bin/env python3
    from subhue_reports.registry.loader import build_registry, build_source_registry, load_manifest
    manifest = load_manifest()
    registry = build_registry(manifest)
    sources = build_source_registry(manifest)
    schemas = sorted({m.get("_schema", "") for m in registry.values()})
    layers = sorted({m.get("layer", "") for m in registry.values()})
    source_names = sorted({s.get("source_name", "") for s in sources.values()})
    source_schemas = sorted({s.get("schema", "") for s in sources.values()})
    print(f"=== models ({len(registry)}) ===")
    print(f"schemas ({len(schemas)}): {', '.join(schemas)}")
    print(f"layers  ({len(layers)}): {', '.join(layers)}")
    print(f"\n=== sources ({len(sources)} tabelas) ===")
    print(f"source_names ({len(source_names)}): {', '.join(source_names)}")
    print(f"schemas      ({len(source_schemas)}): {', '.join(source_schemas)}")

# ── Sources ────────────────────────────────────────────────────────────────────

# Lista todas as fontes raw agrupadas por source_name
manifest-sources:
    #!/usr/bin/env python3
    from subhue_reports.registry.loader import build_source_registry, load_manifest
    from subhue_reports.registry.catalog import to_sources_context
    print(to_sources_context(build_source_registry(load_manifest())))

# Lista fontes de um source_name específico (ex: raw_timed_dtw)
manifest-sources-group group:
    #!/usr/bin/env python3
    from subhue_reports.registry.loader import build_source_registry, load_manifest
    from subhue_reports.registry.catalog import to_sources_context
    print(to_sources_context(build_source_registry(load_manifest()), source_name="{{group}}"))

# Busca fontes por substring do nome da tabela
manifest-sources-search name:
    #!/usr/bin/env python3
    from subhue_reports.registry.loader import build_source_registry, load_manifest
    from subhue_reports.registry.catalog import to_sources_context
    print(to_sources_context(build_source_registry(load_manifest()), name_contains="{{name}}"))

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

# ── Render ────────────────────────────────────────────────────────────────────

# Gera HTML a partir de JSON ou diretório — salva em reports/{tipo}/{ts}__{NOME}/
render src:
    python -m subhue_reports.renderer {{src}}

# Gera HTML em caminho explícito (anula estrutura automática de diretórios)
render-to src out:
    python -m subhue_reports.renderer {{src}} -o {{out}}

# Lista seções de um diretório (idx, tipo, arquivo)
render-show dir:
    #!/usr/bin/env python3
    from pathlib import Path
    from subhue_reports.renderer.sections import list_sections
    secs = list_sections(Path("{{dir}}"))
    if not secs:
        print("nenhuma seção encontrada")
    else:
        for idx, tipo, fname in secs:
            print(f"  {idx:02d}  {tipo:<20}  {fname}")

# Valida JSON contra fontes do manifest
render-validate json:
    python -m subhue_reports.registry.checker {{json}}

# Atalhos explícitos (forçam o renderer sem ler meta.tipo_documento)
report-render src:
    python -m subhue_reports.renderer.relatorio {{src}}

doc-render src:
    python -m subhue_reports.renderer.documentacao {{src}}

dash-render src:
    python -m subhue_reports.renderer.dashboard {{src}}

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

# ── Skills (backends chamáveis por Claude Code) ───────────────────────────────

# Explora uma fonte: colunas, volume e amostra (ex: just explore silver_timed.fat_censo)
explore source:
    #!/usr/bin/env python3
    import json, sys
    from pathlib import Path
    sys.path.insert(0, "src")
    from subhue_reports.skills.tools import dispatch_tool
    from subhue_reports.registry.loader import build_registry, build_source_registry, load_manifest
    manifest = load_manifest()
    registry = {**build_registry(manifest), **build_source_registry(manifest)}
    result = dispatch_tool("explore_source", {"source": "{{source}}", "limit": 20}, registry)
    print(result)

# Detalhe completo de um model dbt (ex: just model-detail fat_censo_leito_ativo)
model-detail name:
    #!/usr/bin/env python3
    import json, sys
    sys.path.insert(0, "src")
    from subhue_reports.skills.tools import dispatch_tool
    from subhue_reports.registry.loader import build_registry, load_manifest
    registry = build_registry(load_manifest())
    print(dispatch_tool("get_model_detail", {"name": "{{name}}"}, registry))

# ── Git / Deploy ──────────────────────────────────────────────────────────────

# Propaga main para stable com force push e reaplica restrições de agente no CLAUDE.md
# NUNCA usar "git push main:stable" diretamente — apaga as restrições de stable
push-stable:
    #!/usr/bin/env bash
    set -euo pipefail
    RESTRICTIONS=$(cat .claude/stable-restrictions.md)
    ORIGINAL=$(cat CLAUDE.md)
    git push origin main:stable --force
    git fetch origin stable
    # Remove worktree stale se existir de execução anterior interrompida
    git worktree remove /tmp/subhue-stable --force 2>/dev/null || true
    git worktree add /tmp/subhue-stable origin/stable
    printf '%s\n\n---\n\n%s' "$RESTRICTIONS" "$ORIGINAL" > /tmp/subhue-stable/CLAUDE.md
    git -C /tmp/subhue-stable add CLAUDE.md
    git -C /tmp/subhue-stable commit -m "chore: reaplica restrições de agente em stable"
    git -C /tmp/subhue-stable push origin HEAD:stable
    git worktree remove /tmp/subhue-stable --force
    # Sincroniza ref local de stable com origin/stable
    git fetch origin stable
    git update-ref refs/heads/stable refs/remotes/origin/stable
    echo "stable atualizado com restrições de agente aplicadas"

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

# Regenera HTMLs de validação visual a partir dos fixtures em tests/fixtures/
# Útil para inspecionar impacto visual após mudanças no renderer
render-fixtures:
    mkdir -p reports/exemplos
    python -m subhue_reports.renderer tests/fixtures/exemplo_relatorio.json \
        -o reports/exemplos/exemplo_relatorio.html
    python -m subhue_reports.renderer tests/fixtures/exemplo_documentacao.json \
        -o reports/exemplos/exemplo_documentacao.html
    python -m subhue_reports.renderer tests/fixtures/exemplo_dashboard.json \
        -o reports/exemplos/exemplo_dashboard.html
    @echo "abrir: reports/exemplos/exemplo_relatorio.html"
    @echo "abrir: reports/exemplos/exemplo_documentacao.html"
    @echo "abrir: reports/exemplos/exemplo_dashboard.html"

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

# Cria diretórios de dados e saída
dirs:
    mkdir -p data/manifest data/cache
    mkdir -p reports/relatorios reports/documentacoes reports/dashboards reports/exemplos

# Copia .env.example para .env
env-setup:
    cp .env.example .env
    @echo "edite .env com suas credenciais"
