# TRQ-BEC

Implementação de referência modular da **TRQ-BEC — Boundary Entropic Cryptography / Criptografia Entrópica de Borda TRQ**, preparada para integração experimental com o `app_LiberRotas`.

> Status: backend experimental `0.6.0-alpha.1`, com a **Fase 1 — oferta ao vivo em feira** implementada. Não é certificação FIPS 140-3, homologação Pix, protocolo pronto para produção nem implementação pós-quântica validada.

A segurança nasce de primitivas e verificações determinísticas. Contexto e IA permanecem auxiliares, calibráveis e auditáveis. A regra estrutural é absoluta: `CryptoOK = 0` implica `DENY`.

## O que já funciona

- conta comercial aprovada ou suspensa por administrador;
- catálogo autoritativo no PostgreSQL, com preço inteiro em centavos e estoque;
- emissão de oferta ao vivo vinculada a produto, limite global, validade e dispositivo;
- QR compacto contendo referência opaca e quantidade assinada, sem preço ou estoque confiado ao cliente;
- consulta prévia de preço, desconto, validade e saldo calculados pelo backend;
- resgate transacional por quantidade, com decremento de estoque, limite global e um resgate por usuário em cada oferta;
- concorrência protegida no PostgreSQL e anti-replay distribuído no Redis;
- contrato estrito de intenção e envelope;
- codificação canônica sem `float` no domínio assinado;
- suíte de laboratório Ed25519 + SHA3-256;
- registro explícito da suíte futura ML-KEM-768 + ML-DSA-65, indisponível e bloqueada;
- emissão e verificação de token com assinatura, emissor, audiência, propósito, política, TTL e vínculo de intenção;
- desafio aleatório de uso único e prova de posse de chave de dispositivo;
- autenticação recente para toda chave nova; visitantes são liberados imediatamente com alerta por e-mail, enquanto todo novo dispositivo de empreendedor ou instituição aguarda 10 minutos antes da ativação automática;
- replay, desafio e idempotência distribuídos em Redis com Lua atômico;
- limite de tentativas efetivo: excesso produz `DENY`, não apenas aumento de score;
- motor contextual com proveniência, frescor, cobertura e índice heurístico;
- política determinística `DENY / ALLOW / STEP_UP / HOLD_OR_REVIEW`;
- ledger PostgreSQL append-only, encadeado por SHA3-256 e checkpoint assinado;
- API FastAPI com Firebase ID-token, custom claims e contratos fechados;
- estado durável de comerciantes, produtos, ofertas, dispositivos, envelopes, operações e resgates;
- diretório de perfis com nome público único normalizado, pesquisa global e sincronização pública controlada;
- mensagens privadas, bloqueio entre perfis e chamados recebidos pela caixa autorizada do Suporte;
- imagens privadas em mensagens, comentários e respostas de publicações, curtidas, edição e exclusão pelo autor;
- armazenamento privado de imagens JPEG/PNG/WebP no GCS, com autorização, confirmação e URLs temporárias;
- arquivamento de produtos e alteração de ofertas em massa, com transação única e repetição idempotente;
- ativação em massa de produtos com estoque individual e exclusão de oferta com revogação imediata do QR;
- convites institucionais por nome público único, aceite/recusa/saída e no máximo uma filiação ativa global por empreendedor;
- relatório institucional de resgates/vendas registrados, limitado aos próprios grupos e às janelas em que cada filiação esteve ativa;
- eventos institucionais financiados, divisão igual por padrão, ajustes por vendedor/produto e relatório final;
- `AI Assurance Layer` somente leitura, sem acesso ao núcleo ou poder de execução;
- adaptador TypeScript para React Native/Expo do `app_LiberRotas`;
- testes de adulteração, replay, concorrência com 100 compradores, downgrade, intenção, ledger e limites da IA.

Nesta fase, o aplicativo apenas coleta comandos e exibe respostas. PostgreSQL é a fonte de verdade para conta comercial, preço, estoque, oferta e resgate; Redis é a fonte operacional para desafio, replay e idempotência. Um resgate comercial final nunca é autorizado offline.

## Arquitetura

```text
app_LiberRotas (Expo: entrada e exibição)
        |
        | Firebase ID token + comando + prova de posse
        v
FastAPI / regras comerciais autoritativas
        |                    |
        |                    +--> Redis: desafio, replay e idempotência
        v
PostgreSQL: comerciantes, produtos, ofertas, estoque e resgates
        |
        v
Protocol Engine ---> Crypto Core ---> Policy Engine
        |                                  |
        v                                  v
Evidence Ledger -----------------> decisão autoritativa
        |
        v
AI Assurance Layer -- somente recomendação --> revisão humana/política
```

A IA não possui referência para `Crypto Core`, `ReplayStore` ou `PolicyEngine`. Essa ausência não é estética: é separação de capacidade.

## Estrutura

```text
src/trq_bec/
  crypto/        primitivas, chaves opacas e registry de suítes
  protocol/      envelope, desafio, prova de posse e replay
  risk/          validação de sinais, cobertura e índice
  policy/        decisão determinística e versionada
  ledger/        evidência sanitizada, cadeia e checkpoint
  assurance/     observador/recomendador sem execução
  application/   orquestração dos cinco gates
  server/        FastAPI, Firebase, PostgreSQL, Redis e provider boundary
    routers/     endpoints extraídos: comunidade, cupons, diretório, instituições, marketplace, mensagens e suporte
integrations/app_liberrotas/
  mobile/        contratos e cliente TypeScript
config/          política de laboratório e papel interno da IA
schemas/         JSON Schemas canônicos
docs/            ADRs, arquitetura, ameaça e implantação
tests/           bateria de regressão e ataques
migrations/      schema, constraints e triggers append-only
```

## Executar

No Windows PowerShell, execute a partir de `backend_trq_bec`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python -m pytest tests -q
```

No Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
trq-bec demo
python -m pytest tests -q
```

Também é possível executar sem instalar:

```bash
PYTHONPATH=src python examples/demo_liberrotas.py
```

## Perfis criptográficos

| Perfil | Estado | Uso |
|---|---|---|
| `TRQ-BEC-LAB-ED25519-AES256GCM-SHA3` | disponível | fluxo funcional e testes locais |
| `TRQ-BEC-PQ-MLKEM768-MLDSA65-AES256GCM-SHA3` | bloqueado | exige provedor auditado, vetores oficiais e ADR aprovado |

O nome da suíte de laboratório inclui AES-256-GCM como perfil previsto, embora esta fase exercite assinatura, hash, prova de posse e autorização; estabelecimento de sessão KEM/KDF/AEAD permanece no gate P1.

## Backend

### Fluxo da Fase 1

```text
POST /v1/trq-bec/devices/enroll
GET  /v1/account/devices
POST /v1/account/devices/approve
POST /v1/account/devices/resend-approval
POST /v1/account/devices/revoke-all
POST /v1/marketplace/products
GET  /v1/marketplace/products/mine
POST /v1/marketplace/products/batch/archive
POST /v1/marketplace/products/batch/activate
POST /v1/marketplace/products/{product_id}/stock
GET  /v1/marketplace/offers/mine
GET  /v1/marketplace/offers/{offer_id}/qr
DELETE /v1/marketplace/offers/{offer_id}
POST /v1/marketplace/offers/batch/actions
POST /v1/marketplace/offers/{offer_id}/status
POST /v1/trq-bec/coupons/issue
POST /v1/trq-bec/coupons/preview
POST /v1/trq-bec/coupons/redeem/begin
POST /v1/trq-bec/coupons/redeem/authorize
```

### Segurança de múltiplos dispositivos

Toda chave nova exige autenticação Firebase recente. Para visitante, a chave fica imediatamente `ACTIVE` em qualquer aparelho e o e-mail serve apenas para avisar e permitir a reação em caso de acesso desconhecido. Para empreendedor e instituição, inclusive no primeiro aparelho, a chave fica `PENDING_APPROVAL` por 10 minutos e depois é ativada automaticamente pelo backend. Contas administrativas mantêm a política privilegiada própria.

O alerta é enviado para todo novo aparelho de visitante, empreendedor ou instituição ao endereço obtido exclusivamente por `firebase_admin.auth.get_user(uid).email`. Ele informa que o usuário pode desconsiderar a mensagem quando reconhecer o acesso e oferece o botão **Não fui eu!**, que abre `/account/devices` para revisão e troca de senha. O e-mail não autoriza o dispositivo e não contém token.

`POST /v1/account/devices/resend-approval` é mantido por compatibilidade de rota, exige autenticação Firebase recente e reapresenta o alerta após intervalo mínimo de 60 segundos sem reiniciar os 10 minutos. Ao terminar o cooldown, a próxima consulta ou operação protegida promove o aparelho para `ACTIVE`. `POST /v1/account/devices/revoke-all` revoga dispositivos `ACTIVE` e `PENDING_APPROVAL`, além dos refresh tokens Firebase. A alteração de senha deve exibir previamente que todos os aparelhos, inclusive o atual, serão desconectados.

O SMTP usa senha montada em `/run/secrets/smtp-password`, nunca valor secreto no frontend ou no corpo da requisição. Em desenvolvimento, falha ou ausência de SMTP não derruba o login nem impede a ativação automática: a resposta informa `NOT_CONFIGURED` ou `FAILED`, nunca um falso `SENT`. Em produção, host SMTP e remetente são requisitos de inicialização para preservar o alerta. Consulte [`docs/BACKEND_DEPLOYMENT.md`](docs/BACKEND_DEPLOYMENT.md) para a configuração completa.

Diretório, pesquisa global, mensagens e atendimento:

```text
PUT    /v1/profile/public
PUT    /v1/directory/profile
GET    /v1/profile/public/{uid}
GET    /v1/directory/profile/me
GET    /v1/search
GET    /v1/messages/conversations
GET    /v1/messages/conversations/{conversation_id}
POST   /v1/messages
POST   /v1/messages/conversations/{conversation_id}/messages
GET    /v1/feed/posts/{post_id}/comments
POST   /v1/feed/posts/{post_id}/comments
PATCH  /v1/feed/comments/{comment_id}
DELETE /v1/feed/comments/{comment_id}
PUT    /v1/feed/comments/{comment_id}/like
DELETE /v1/feed/comments/{comment_id}/like
POST   /v1/messages/conversations/{conversation_id}/read
GET    /v1/messages/blocks
POST   /v1/messages/blocks/{uid}
PUT    /v1/messages/blocks/{uid}
DELETE /v1/messages/blocks/{uid}
POST   /v1/support/requests
GET    /v1/support/requests
GET    /v1/support/requests/{conversation_id}
POST   /v1/support/requests/{conversation_id}/messages
POST   /v1/support/requests/{conversation_id}/resolve
POST   /v1/media/uploads
POST   /v1/media/uploads/{media_id}/confirm
GET    /v1/media
GET    /v1/media/{media_id}
DELETE /v1/media/{media_id}
```

O backend deriva remetente, função, estado, permissões, propriedade dos itens e participantes da conversa a partir do ID Token e do PostgreSQL. O frontend não escolhe esses campos. O nome público é normalizado para garantir unicidade mesmo com variações de caixa, acentos, espaços ou pontuação. A caixa de chamados exige função `support` e permissão `support.requests.manage`.

As rotas em massa aceitam no máximo 25 identificadores únicos por comando. `POST /v1/marketplace/products/batch/archive` arquiva os produtos e revoga suas ofertas ativas; eles deixam de aparecer na lista operacional e na vitrine, mas o histórico de auditoria permanece. `POST /v1/marketplace/products/batch/activate` recebe um estoque positivo individual para cada produto selecionado. `POST /v1/marketplace/offers/batch/actions` aceita `DELETE`, `INCREASE_DISCOUNT` ou `EXTEND_VALIDITY`; aumento de desconto e extensão emitem uma referência QR atualizada sem apagar o histórico. O lote é atômico e exige `client_request_id`: a repetição do mesmo corpo retorna a resposta persistida, enquanto o reaproveitamento do identificador com outro corpo retorna conflito.

`GET /v1/marketplace/offers/{offer_id}/qr?quantity=N` gera novamente o QR da própria oferta com quantidade entre 1 e o saldo disponível. Para `N > 1`, o payload contém `quantity_proof_b64u`, assinatura que impede alterar a quantidade fora do backend. O aplicativo pode agrupar de 2 a 5 payloads individuais em `trq-bec-offer-bundle-v1`; cada item ainda passa por `preview`, `begin` e `authorize` separadamente. Um `ALLOW` reduz o estoque e aumenta `redeemed_count` pela quantidade confirmada na mesma transação.

Controle de acesso, relógio e painéis autorizados:

```text
GET  /v1/time
GET  /v1/access/me
POST /v1/admin/institutions
GET  /v1/admin/institutions
GET  /v1/admin/accounts
GET  /v1/admin/operations/summary
POST /v1/support/institutions
POST /v1/public/institution-applications
GET  /v1/support/institution-applications
PATCH /v1/support/institution-applications/{application_id}
GET  /v1/support/accounts
GET  /v1/security/accounts
GET  /v1/security/monitoring/summary
POST /v1/security/accounts/{uid}/status
GET  /v1/institution/profile
PATCH /v1/institution/profile
GET  /v1/institution/reports/summary
POST /v1/institution/groups
GET  /v1/institution/groups
POST /v1/institution/groups/{group_id}/close
POST /v1/institution/groups/{group_id}/invitations
GET  /v1/institution/groups/{group_id}/members
POST /v1/institution/groups/{group_id}/members/{membership_id}/remove
GET  /v1/entrepreneur/institution-invitations
POST /v1/entrepreneur/institution-invitations/{membership_id}/accept
POST /v1/entrepreneur/institution-invitations/{membership_id}/decline
POST /v1/entrepreneur/institution-memberships/{membership_id}/leave
GET  /v1/institution/reports/sales
POST /v1/institution/funded-events
GET  /v1/institution/funded-events
PUT  /v1/institution/funded-events/{event_id}/seller-allocations
POST /v1/institution/funded-events/{event_id}/activate
POST /v1/institution/funded-events/{event_id}/end
GET  /v1/institution/funded-events/{event_id}/report
GET  /v1/entrepreneur/funded-events
GET  /v1/entrepreneur/funded-events/{event_id}/report
PUT  /v1/entrepreneur/funded-events/{event_id}/product-allocations
```

O formulário público de instituição grava uma solicitação separada e não cria identidade, função ou permissão. Somente o Suporte com `support.requests.manage` consulta a fila. Ao aprovar, também são exigidos `support.institutions.create` e autenticação recente; a operação cria exclusivamente `institution`, envia pelo SMTP autenticado o link Firebase de primeiro acesso e grava a aprovação vinculada ao UID provisionado. Falha no envio reverte a identidade e mantém a solicitação sem aprovação.

Administrador e Suporte podem provisionar somente `institution`, cada um com sua própria permissão e autenticação recente. O corpo não aceita função, senha nem permissões. A instituição altera somente os campos permitidos do próprio perfil, cria e encerra grupos derivados do próprio UID e recebe relatórios agregados somente desses grupos; o frontend não envia `owner_uid`. Suporte consulta uma projeção mínima de contas. Segurança não pode mudar a própria conta nem contas com função `admin` ou `security`; suspensão e reativação exigem motivo de 10 a 500 caracteres, persistido na auditoria append-only.

Contas `admin`, `support` e `security` exigem também uma validação de autoridade `APPROVED` em `privileged_account_validations`. As contas oficiais existentes usam proteção `SYSTEM`; novas contas criadas em `POST /v1/admin/staff-accounts` nascem `PENDING`, com permissões derivadas exclusivamente da função e confirmação de e-mail enfileirada. `POST /v1/admin/staff-accounts/{uid}/validate` exige autenticação recente, e-mail confirmado no Firebase e motivo; somente então aplica `staff_validated=true`, ativa a conta, revoga sessões anteriores e registra `STAFF_ACCOUNT_VALIDATED`.

`GET /v1/security/trq-bec/status` exige `security.trq_bec.monitor` e retorna somente telemetria sanitizada de política, ledger, contas privilegiadas, dispositivos, filas, PostgreSQL, Redis e disponibilidade PQC. Senhas, tokens, chaves, assinaturas privadas, mensagens e dados financeiros não fazem parte desse contrato.

A instituição convida pelo nome público único, e o backend resolve o empreendedor autorizado sem aceitar UID arbitrário do frontend. O empreendedor aceita ou recusa o convite e pode encerrar a própria filiação; a instituição pode cancelar um convite pendente ou remover um membro dos próprios grupos. O PostgreSQL permite somente uma filiação `ACTIVE` global por empreendedor e também impede janelas históricas sobrepostas, inclusive diante de concorrência.

`GET /v1/institution/reports/sales` aceita período e filtro opcional de grupo, limita a consulta aos grupos da instituição autenticada e inclui somente resgates confirmados dentro das janelas ativas de filiação. As linhas e os totais usam uma única fotografia `REPEATABLE READ`, e os valores são separados por moeda. `amounts_unavailable_count` informa quantos registros legados não possuem snapshot financeiro completo; esses registros não entram nos totais em dinheiro. O relatório representa resgates/vendas registrados no LiberRotas e **não comprova pagamento, Pix, liquidação, estorno ou faturamento contábil**. A resposta não expõe comprador, UID do vendedor, identificadores internos de filiação, chave Pix, QR, token ou mensagem privada.

Eventos financiados distribuem o orçamento igualmente entre afiliados quando não há ajuste manual. A instituição pode ajustar a cota por vendedor antes da ativação; cada vendedor pode ajustar a própria cota por produto. As somas precisam fechar exatamente o orçamento correspondente. A ativação congela as alocações, e o relatório usa somente vendas e cupons elegíveis dentro da janela do evento.

`GET /v1/time` é público e serve para sincronizar relógios visuais. Todas as decisões de validade permanecem no servidor: o horário enviado pelo cliente nunca autoriza cupom, feira ou operação de segurança.

Operações administrativas ficam em contrato separado:

```text
POST /internal/v1/marketplace/merchants/status
POST /internal/v1/ledger/checkpoint
```

Ordem mínima para testar: administrador ativa a conta comercial; empreendedor cadastra o dispositivo e o produto; backend emite a oferta e o QR opaco; visitante cadastra seu dispositivo, consulta a oferta, inicia o desafio e assina `proof_message_b64u`; somente então o backend autoriza e confirma o resgate.

O fluxo completo, com a responsabilidade de cada componente, conteúdo do QR,
cinco portas de autorização, idempotência e limites criptográficos, está em
[`docs/FLUXO_TRQ_BEC.md`](docs/FLUXO_TRQ_BEC.md).

### Documentação autoritativa da API

Com o backend em execução fora de produção, os contratos ficam separados:

```text
Público
  Swagger UI  http://127.0.0.1:8787/docs
  ReDoc       http://127.0.0.1:8787/redoc
  OpenAPI     http://127.0.0.1:8787/openapi.json

Administrativo
  Swagger UI  http://127.0.0.1:8787/internal/docs
  ReDoc       http://127.0.0.1:8787/internal/redoc
  OpenAPI     http://127.0.0.1:8787/internal/openapi.json
```

O contrato público não contém rotas `/internal/`. O contrato administrativo contém somente as operações internas e exige `admin=true` para execução. Os exemplos de erro são específicos por rota e correspondem aos códigos emitidos pelo serviço. As descrições dos schemas são mantidas em português. Todas as interfaces de documentação são desativadas em produção.

Referências:

- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md): fluxo, autenticação, separação de contratos e erros;
- [`docs/README.md`](docs/README.md): índice da documentação atual e limites da Fase 1;
- [`docs/openapi-liberrotas-public-v0.6.0a1.json`](docs/openapi-liberrotas-public-v0.6.0a1.json): contrato público OpenAPI 3.1;
- [`docs/openapi-liberrotas-internal-v0.6.0a1.json`](docs/openapi-liberrotas-internal-v0.6.0a1.json): contrato administrativo OpenAPI 3.1;
- [`docs/BACKEND_DEPLOYMENT.md`](docs/BACKEND_DEPLOYMENT.md): Docker Compose, Firebase custom claims, segredos, migrações e implantação.
- [`docs/GCS_MEDIA_STORAGE.md`](docs/GCS_MEDIA_STORAGE.md): upload privado, variantes, cache e exclusão de mídia.
- [`docs/MEDIA_COST_AUDIT_2026-08-03.md`](docs/MEDIA_COST_AUDIT_2026-08-03.md): auditoria real de Base64, duplicações, consultas e limites de custo.

Para regenerar os contratos:

```powershell
trq-bec-openapi --scope public
trq-bec-openapi --scope internal
```

Na validação de **04/09/2026**, o contrato OpenAPI operacional contém `94` caminhos e `106` operações.

## Limites conhecidos

- As migrations `001_initial.sql` até `021_institution_live_fairs.sql` formam a sequência atual e foram confirmadas no PostgreSQL operacional em 05/08/2026. Antes de um piloto em outro ambiente, a sequência deve ser repetida com backup e plano de reversão.
- A suíte local foi aprovada em 04/09/2026 com `197 testes` e `63 subtestes`. Ela não substitui ensaios manuais com duas contas, câmera, entrega SMTP, navegador e dispositivo físico.
- Pedidos, pagamentos, webhooks, estornos e baixa financeira não fazem parte da Fase 1.
- Resgate comercial final offline é proibido; indisponibilidade do Redis ou do PostgreSQL deve falhar fechado.
- O provider de laboratório usa arquivos PEM montados como segredo; produção exige KMS/HSM e lifecycle completo.
- O índice contextual é heurístico, em pontos-base, e não é probabilidade.
- A política de laboratório é versionada e possui digest, mas ainda não é assinada.
- Não há ML-KEM/ML-DSA implementado neste pacote; escolher a suíte PQ falha fechado.
- O adapter PQC está deliberadamente bloqueado; aprovar uma flag sem instalar um provider real impede a inicialização.
- A camada de IA permanece somente leitura e não decide nem confirma operações comerciais.

## Próximo gate operacional

Repetir a implantação no ambiente-alvo, configurar as claims de administrador/empreendedor e executar a bateria com PostgreSQL/Redis reais, múltiplos workers, carga e recuperação de falhas. Pedidos entram apenas na Fase 2; pagamentos, na Fase 3; o provider pós-quântico só entra depois de auditoria específica.
