# Mapa técnico

O aplicativo obtém identidade no Firebase Authentication e envia o token à API. O backend valida identidade, permissões e regras comerciais antes de alterar dados.

| Componente | Responsabilidade |
|---|---|
| `mobile_app/` | Telas Expo Router, navegação, interface e chamadas à API; não decide preço, estoque, permissão ou resgate. |
| `backend_trq_bec/` | Uma API FastAPI; routers por domínio, serviços e persistência. Firebase Admin somente aqui. |
| PostgreSQL | Fonte autoritativa de permissões e fatos comerciais; metadados e propriedade de mídia. |
| Redis | Desafios, replay e idempotência; estado temporário operacional. |
| Firestore | Feed e perfis projetados, além dos usos pessoais permitidos nas regras; não substitui a autoridade comercial. |
| Google Cloud Storage | Bytes de imagens privadas, acesso autorizado pelo backend. |
| Docker / Cloudflare | Infraestrutura local e exposição pública por Tunnel, respectivamente. |

TRQ-BEC integra segurança/protocolo/ledger experimental. Separar produto e pesquisa não implica remover controles nem afirmar desacoplamento técnico completo.

## Quando consultar documentação completa

- Escrita, cache ou autorização de dados: [matriz de autoridade](../../backend_trq_bec/docs/DATA_AUTHORITY_MATRIX.md).
- Limites entre módulos e contratos: [ADR do monólito modular](../../backend_trq_bec/docs/adr/ADR-ARCH-002-MONOLITO-MODULAR.md).
- API, segurança e contratos: [índice técnico](../../backend_trq_bec/docs/README.md).
- Mídia e permissões de armazenamento: [GCS](../../backend_trq_bec/docs/GCS_MEDIA_STORAGE.md).
- Inicialização e operação: localize a seção necessária no [README](../../README.md) ou no [mapa de comandos](../../MAPA_DE_COMANDOS.md); não os leia inteiros por padrão.
