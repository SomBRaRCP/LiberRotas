# LiberRotas: contexto progressivo

Responda em português do Brasil. Explique o que mudou, onde e como verificar.

## Entrada

1. Leia [PROJECT_STATE.md](docs/ai/PROJECT_STATE.md).
2. Leia [NEXT.md](docs/ai/NEXT.md); a tarefa do usuário define o escopo atual.
3. Identifique a área: frontend, backend, infraestrutura ou documentação.
4. Leia o `AGENTS.md` mais próximo do código: [frontend](mobile_app/AGENTS.md) ou [backend](backend_trq_bec/AGENTS.md). Tarefas transversais podem precisar de ambos.
5. Localize arquivos com `rg --files <área>` e `rg -n <termo> <área>`.
6. Abra somente os trechos necessários; não releia o que já está no contexto.
7. Consulte documentação extensa apenas para resolver uma necessidade concreta.

## Trabalho

- Não carregue toda a documentação nem faça varreduras globais por padrão. Amplie a busca só quando a área consultada não bastar.
- Prefira patches pequenos e diffs a arquivos inteiros. Preserve alterações locais, código e documentação existentes.
- Rode testes relacionados primeiro; amplie para mudanças transversais, riscos não cobertos ou entrega funcional. Só documentação: confira links, fatos e diff.
- Antes de mudar arquitetura, consulte [ARCHITECTURE.md](docs/ai/ARCHITECTURE.md); antes de rever decisões, [DECISIONS.md](docs/ai/DECISIONS.md).
- Nunca imprima, copie ou commite credenciais. Firebase Admin só no backend; nenhum segredo em `EXPO_PUBLIC_*`. Não enfraqueça autenticação ou autorização para passar testes.

## Encerramento

Atualize `docs/ai/PROJECT_STATE.md` só se o estado real mudar, `DECISIONS.md` só para decisão arquitetural duradoura e `NEXT.md` só se a prioridade mudar. Mantenha referências, não diários; diferencie teste automatizado de uso real.

Procedimento reutilizável: [skill LiberRotas](.agents/skills/liberrotas/SKILL.md), quando aplicável.
