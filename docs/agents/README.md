# Arquitetura de instruções para agentes

Este repositório separa instruções de agentes em camadas para evitar duplicação e reduzir ruído de contexto.

## Camadas

1. **Arquivos base** (carregados automaticamente pelo agente):
   - `AGENTS.md` — Codex / OpenAI
   - `CLAUDE.md` — Claude Code
   - `OPENCODE.md` — OpenCode

   Devem conter apenas contexto estável do projeto, regras gerais de código, comandos úteis e referências curtas para workflows sob demanda.

2. **Skills canônicas compartilháveis**:
   - `.agents/skills/<nome>/SKILL.md`

   Devem conter workflows completos e reutilizáveis entre agentes. Esta é a fonte única de verdade para cada workflow.

3. **Adaptadores específicos por ferramenta**:
   - `.opencode/skills/<nome>/SKILL.md`
   - `.claude/skills/<nome>/SKILL.md`

   Devem ser curtos e apenas apontar para a skill canônica. Só devem existir quando a ferramenta exige um arquivo naquele diretório para carregar a skill.

## Skills disponíveis

| Skill | Canônica | Descrição |
|---|---|---|
| `gerar-documento` | `.agents/skills/gerar-documento/SKILL.md` | Gera relatório, documentação ou dashboard HTML |

## Regra de manutenção

Não duplicar workflows completos em `AGENTS.md`, `CLAUDE.md` ou `OPENCODE.md`.

Quando um workflow crescer ou passar a ser usado sob demanda, mover para `.agents/skills/<nome>/SKILL.md` e deixar apenas uma referência curta nos arquivos base.

Skills específicas de ferramenta só devem existir quando houver diferença real de comportamento entre agentes. Caso contrário, o adaptador aponta para a skill canônica.

## Fonte única de verdade

Para workflows compartilhados, a fonte única de verdade é sempre:

`.agents/skills/<nome>/SKILL.md`

Arquivos em `.opencode/skills/` e `.claude/skills/` não devem copiar o conteúdo completo da skill canônica.
