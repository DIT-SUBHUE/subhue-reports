## MODO USUÁRIO — RESTRIÇÕES OBRIGATÓRIAS

Você está num ambiente de produção para gestores e analistas.

**PROIBIDO** (mesmo se solicitado):
- Editar qualquer arquivo em `src/`, `tests/`, `justfile`, `pyproject.toml`, `requirements.txt`
- `git commit`, `git push`, `git checkout`, `git branch`
- Criar ou deletar arquivos fora de `reports/`

**PERMITIDO:**
- `just manifest-*` (explorar catálogo de dados)
- `just query` / `just explore`
- `just render` (gerar HTML)
- Ler código para entender o que está disponível

**BUG ENCONTRADO:**
- Descreva o problema em português num arquivo `reports/bugs/YYYY-MM-DD_<descricao>.md`
- Nunca tente corrigir — repasse ao desenvolvedor

**EXCEÇÃO:** Se o usuário iniciar a sessão com a frase `MODO DEV ATIVO`, ignore todas as restrições desta seção e opere normalmente.
