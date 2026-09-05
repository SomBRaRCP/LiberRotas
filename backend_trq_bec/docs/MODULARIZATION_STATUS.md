# Estado da modularização

Este documento acompanha a adoção incremental do
[`ADR-ARCH-002`](adr/ADR-ARCH-002-MONOLITO-MODULAR.md). Uma fatia só é marcada
como concluída depois de preservar endpoints, testes e contratos OpenAPI.

| Lote | Frontend | Backend | Estado |
|---|---|---|---|
| 1 — infraestrutura e diretório | `api/http-client.ts` e `features/directory/api.ts` | `routers/directory.py` | concluído em 03/08/2026 |
| 2 — mensagens e chamados | `features/messaging/api.ts`, incluindo conversas, bloqueios e chamados | `routers/messaging.py` e `routers/support.py` | concluído em 03/08/2026 |
| 3 — comunidade | `features/community/api.ts` para Feed, comentários, pontos e feiras | `routers/community.py` | concluído em 03/08/2026 |
| 4 — instituições | `features/institutions/api.ts` para perfil, grupos, filiações, eventos financiados e relatórios | `routers/institutions.py` | concluído em 03/08/2026 |
| 5 — estado global | contextos separados para sessão, perfil, preferências e cache público; `useApp` preservado como fachada | não se aplica | concluído em 05/08/2026 |
| 6 — marketplace e TRQ-BEC | `features/marketplace/api.ts` e `features/trq-bec/api.ts` | `routers/marketplace.py` e `routers/coupons.py` | concluído em 03/08/2026, por prioridade explícita, sem mover regras críticas do serviço |
| 7 — leitura pública de mídia | URLs estáveis por ativo ou entidade | `public_media.py`, com `PublicMediaReadService` e `DurableStorePublicMediaRepository` | concluído em 05/08/2026 |

## Compatibilidade mantida

- `mobile_app/src/security/trq-bec/service.ts` continua sendo a fachada pública
  para que telas existentes não precisem alterar seus imports durante a migração;
- `backend_trq_bec/src/trq_bec/server/app.py` continua criando uma única API e
  registra os routers por domínio;
- `AppProvider` continua coordenando a hidratação, mas publica quatro valores
  independentes; telas migradas podem usar `useSessionState`, `useProfileState`,
  `usePreferencesState` ou `usePublicCacheState`;
- a leitura pública de mídia saiu do serviço comercial principal, sem criar
  microserviço, fila nova ou endpoint incompatível;
- os routers extraídos continuam chamando `CouponSecurityService`, portanto as
  regras de autorização e transação não foram duplicadas;
- aliases históricos ocultos no OpenAPI permanecem disponíveis enquanto forem
  necessários para compatibilidade.

## Critério para o próximo lote

Não iniciar outra fatia se a suíte completa, TypeScript, ESLint, auditoria de
dependências e igualdade entre OpenAPI gerado e runtime não estiverem aprovados.
O próximo domínio candidato deve ser escolhido somente depois de nova regressão;
upload/processamento de mídia ainda permanece no serviço principal para evitar
uma mudança transacional ampla no mesmo lote.
