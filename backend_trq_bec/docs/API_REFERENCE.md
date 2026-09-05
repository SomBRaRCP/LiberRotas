# TRQ-BEC LiberRotas API — Referência de Integração

**Versão:** `0.6.0-alpha.1`  
**Contrato:** OpenAPI 3.1  
**Escopo:** núcleo comercial da Fase 1 e serviços atuais da plataforma LiberRotas  
**Estado:** laboratório controlado; pagamentos e criptografia pós-quântica permanecem fora deste escopo.

## Objetivo da Fase 1

A API é a fronteira autoritativa para:

1. aprovar ou suspender a conta comercial de um empreendedor;
2. manter produto, preço e estoque no PostgreSQL;
3. emitir oferta com desconto calculado pelo backend e QR com referência opaca;
4. consultar a oferta antes do resgate sem produzir efeito comercial;
5. iniciar um desafio de uso único e validar a prova de posse do dispositivo;
6. confirmar o resgate em transação, respeitando estoque, limite global e um uso por pessoa;
7. aplicar a quantidade assinada da venda sem confiar em alterações do cliente;
8. autorizar diretório, Feed, comentários, mensagens, mídia privada e painéis por função;
9. registrar evidências em ledger append-only e produzir checkpoints administrativos.

O aplicativo não é fonte de verdade para preço, estoque, limite ou resultado do resgate. Redis coordena desafio, anti-replay e idempotência. PostgreSQL confirma o efeito comercial. Indisponibilidade de uma dependência crítica deve falhar fechada, e não existe resgate comercial final offline.

> **Ruptura deliberada da etapa anterior:** `v0.6.0a1` substitui o contrato experimental de cupom `v0.5.0a2` pelo contrato de oferta ao vivo `trq-bec-offer-v1`. Não misture os JSON antigos com o app atual. Antes de implantar, encerre operações `v0.5.0a2` pendentes e atualize o mobile e o backend juntos.

## Contratos separados

### Contrato público

| Interface | Caminho | Finalidade |
|---|---|---|
| Swagger UI | `/docs` | Teste interativo das rotas públicas |
| ReDoc | `/redoc` | Leitura técnica do contrato público |
| OpenAPI JSON | `/openapi.json` | Geração de cliente e validação do aplicativo |

### Contrato administrativo

| Interface | Caminho | Finalidade |
|---|---|---|
| Swagger administrativo | `/internal/docs` | Teste das operações internas |
| ReDoc administrativo | `/internal/redoc` | Leitura do contrato operacional |
| OpenAPI administrativo | `/internal/openapi.json` | Auditoria e automação administrativa |

O OpenAPI público não contém caminhos `/internal/`. O OpenAPI administrativo contém somente caminhos internos. Essas interfaces existem apenas fora de produção e quando `TRQ_BEC_DOCS_ENABLED=true`.

## Autenticação e autorização

Rotas protegidas usam um Firebase ID token:

```http
Authorization: Bearer <firebase-id-token>
```

No Swagger UI, clique em **Authorize** e informe somente o token; a interface acrescenta `Bearer`.

| Claim ou cadastro | Uso |
|---|---|
| `sub` ou `uid` | identidade autoritativa do usuário |
| `role=entrepreneur` | permite solicitar operações de empreendedor |
| conta comercial `ACTIVE` | segunda autorização obrigatória para catálogo e ofertas |
| `role=admin`, `support`, `security` ou `institution` | seleciona o conjunto inicial de permissões; a permissão detalhada e o status ainda são consultados no PostgreSQL |
| `admin=true` | permite as duas operações estritamente internas: aprovar comerciantes e gerar checkpoint |

A claim `role=entrepreneur` sozinha não ativa comércio. Um administrador precisa cadastrar a conta em `/internal/v1/marketplace/merchants/status`.

## Identidade de dispositivo por plataforma

O backend recebe somente a chave pública, o identificador derivado e o perfil de
armazenamento. A chave privada permanece no cliente:

| Cliente | `storage_profile` | Proteção local |
|---|---|---|
| Android/iOS | `EXPO_SECURE_STORE_LAB` | seed Ed25519 protegida pelo SecureStore e separada por Firebase UID |
| Web | `WEB_CRYPTO_INDEXEDDB_LAB` | chave privada Ed25519 como `CryptoKey` não exportável persistido no IndexedDB |

O cliente Web exige WebCrypto Ed25519, IndexedDB e contexto seguro. A aplicação
deve ser aberta por HTTPS ou, no laboratório no próprio computador, por
`http://127.0.0.1`. HTTP por IP da rede local não atende esse requisito.

Para cadastrar qualquer chave nova em `POST /v1/trq-bec/devices/enroll`, o
`auth_time` do Firebase ID token deve ter no máximo 300 segundos. O recadastro da
mesma chave é idempotente. Para visitante, toda chave nova fica `ACTIVE`
imediatamente. Para empreendedor e instituição, toda chave nova, inclusive a
primeira, fica `PENDING_APPROVAL` e não participa de operações TRQ-BEC protegidas
durante os 10 minutos de segurança. Depois desse período, o backend promove a
chave automaticamente para `ACTIVE`.

Para todo aparelho novo de visitante, empreendedor ou instituição, o backend obtém o destinatário exclusivamente por
`firebase_admin.auth.get_user(uid).email` e envia um alerta com o botão **Não fui
eu!** para `/account/devices`. Se o acesso for legítimo, o usuário apenas
desconsidera a mensagem. Se não reconhecer, revisa os dispositivos e troca a
senha. O e-mail não contém token nem autoriza o aparelho.

O IndexedDB é isolado pela origem completa — protocolo, host e porta. Trocar de
origem ou limpar os dados do site perde o acesso à chave privada não exportável,
mas não apaga o registro autoritativo. A nova chave pode ser cadastrada e
liberada após o cooldown; o registro anterior continua visível até a
revogação. Esse perfil é de laboratório e não representa atestação de hardware.
Além disso, a não exportabilidade não impede que um XSS na mesma origem solicite
assinaturas enquanto o código malicioso estiver em execução.

## Sequência completa

Uma explicação didática de cada etapa, incluindo conteúdo do QR, prova de posse,
anti-replay, transação e limites do perfil acadêmico, está em
[`FLUXO_TRQ_BEC.md`](FLUXO_TRQ_BEC.md).

```text
Administrador: ativa conta comercial
        |
        v
Empreendedor: cadastra dispositivo e produto autoritativo
        |
        v
Backend: calcula desconto e cria oferta
        |
        v
Vitrine do vendedor: solicita QR opaco com quantidade assinada
        |
        v
Visitante: cadastra dispositivo e consulta preview
        |
        v
Begin: cria operação + sessão + desafio + proof_message_b64u
        |
        v
Dispositivo: assina exatamente proof_message_b64u
        |
        v
Authorize: Redis anti-replay + gates criptográficos + transação PostgreSQL
        |
        v
Decisão autoritativa + estoque/limite atualizados pela quantidade + evento no ledger
```

O aplicativo pode agrupar de 2 a 5 payloads individuais já emitidos em
`trq-bec-offer-bundle-v1`. Esse agrupamento é apenas um formato de transporte para
uma leitura: cada oferta conserva `token_ref`, quantidade, desconto, operação e
decisão independentes.

## Endpoints públicos

### Saúde

| Método | Caminho | Autenticação | Descrição |
|---|---|---|---|
| `GET` | `/health/` | não | PostgreSQL, Redis e prontidão criptográfica |
| `GET` | `/health/crypto` | não | provider, aprovação, autoteste e algoritmos |
| `GET` | `/v1/time` | não | relógio UTC autoritativo para contagens visuais |

### Conta, acesso e painéis

| Método | Caminho | Autorização | Descrição |
|---|---|---|---|
| `GET` | `/v1/access/me` | Firebase | resolve função, status e permissões efetivas |
| `DELETE` | `/v1/account` | Firebase recente | prepara a exclusão definitiva da própria conta |
| `GET` | `/v1/admin/accounts` | Administrador | lista projeção autorizada de contas |
| `GET` | `/v1/admin/institutions` | Administrador | lista instituições |
| `POST` | `/v1/admin/institutions` | Administrador recente | cria instituição com função fixa |
| `GET` | `/v1/admin/operations/summary` | Administrador | indicadores operacionais sem segredos |
| `GET` | `/v1/support/accounts` | Suporte | consulta mínima de contas |
| `POST` | `/v1/support/institutions` | Suporte recente | cria instituição com função fixa |
| `GET` | `/v1/security/accounts` | Segurança | consulta contas e eventos recentes |
| `POST` | `/v1/security/accounts/{uid}/status` | Segurança recente | suspende ou reativa conta não protegida |
| `GET` | `/v1/security/monitoring/summary` | Segurança | indicadores agregados de monitoramento |

### Dispositivos

| Método | Caminho | Autenticação | Descrição |
|---|---|---|---|
| `POST` | `/v1/trq-bec/devices/enroll` | Firebase recente para uma chave nova | visitante fica ativo com alerta; todo novo aparelho de empreendedor ou instituição aguarda 10 minutos |
| `GET` | `/v1/account/devices` | Firebase | lista somente os dispositivos `ACTIVE`, `PENDING_APPROVAL` e `REVOKED` do UID autenticado |
| `POST` | `/v1/account/devices/approve` | Firebase + token legado | compatibilidade temporária com alertas antigos; novos e-mails não usam esta rota |
| `POST` | `/v1/account/devices/resend-approval` | Firebase recente | reenvia o alerta após 60 segundos sem reiniciar o cooldown |
| `POST` | `/v1/account/devices/revoke-all` | Firebase recente | revoga dispositivos ativos e pendentes e os refresh tokens Firebase |

O estado de notificação pode ser `NOT_REQUIRED`, `PENDING`, `SENT`,
`NOT_CONFIGURED` ou `FAILED`. `SENT` só é persistido depois que o servidor SMTP
aceita `send_message`. Falha de e-mail não encerra a sessão autenticada. Para
empreendedor e instituição, o dispositivo permanece `PENDING_APPROVAL` apenas até
o fim do cooldown; visitante permanece `ACTIVE`.

Enquanto o registro permanece `PENDING_APPROVAL`, `resend-approval` exige
autenticação recente e respeita o intervalo mínimo, mas preserva o horário
original. Ao vencer `approval_expires_at`, o backend limpa o token interno legado,
registra `DEVICE_AUTO_ACTIVATION` e muda o aparelho para `ACTIVE`.

### Diretório, pesquisa, mensagens e Suporte

| Método | Caminho | Autorização | Descrição |
|---|---|---|---|
| `PUT` | `/v1/profile/public` | Firebase | salva o perfil público autoritativo |
| `PUT` | `/v1/directory/profile` | Firebase | alias do salvamento de perfil |
| `GET` | `/v1/profile/public/{uid}` | Firebase | consulta perfil público ativo |
| `GET` | `/v1/directory/profile/me` | Firebase | consulta o próprio perfil |
| `GET` | `/v1/search` | Firebase | pesquisa perfis, produtos, ofertas e publicações |
| `GET` | `/v1/messages/conversations` | Firebase | lista conversas da conta |
| `GET` | `/v1/messages/conversations/{conversation_id}` | participante | consulta mensagens e mídia autorizada |
| `POST` | `/v1/messages` | Firebase | inicia ou reutiliza conversa direta |
| `POST` | `/v1/messages/conversations/{conversation_id}/messages` | participante | envia texto e imagem opcional |
| `POST` | `/v1/messages/conversations/{conversation_id}/read` | participante | marca a conversa como lida |
| `GET` | `/v1/messages/blocks` | Firebase | lista bloqueios próprios |
| `POST` ou `PUT` | `/v1/messages/blocks/{uid}` | Firebase | bloqueia um perfil |
| `DELETE` | `/v1/messages/blocks/{uid}` | Firebase | remove o bloqueio |
| `POST` | `/v1/support/requests` | Firebase | abre chamado privado |
| `GET` | `/v1/support/requests` | Suporte | lista a caixa de atendimento |
| `GET` | `/v1/support/requests/{conversation_id}` | solicitante ou Suporte | consulta o chamado |
| `POST` | `/v1/support/requests/{conversation_id}/messages` | solicitante ou Suporte | responde ao chamado |
| `POST` | `/v1/support/requests/{conversation_id}/resolve` | Suporte | conclui o chamado |

### Feed, comentários e mídia

| Método | Caminho | Autorização | Descrição |
|---|---|---|---|
| `POST` | `/v1/community/posts` | `feed.publish` | publica texto e imagem opcional no Feed |
| `PATCH` | `/v1/community/posts/{post_id}` | autor | edita a própria publicação |
| `DELETE` | `/v1/community/posts/{post_id}` | autor | exclui a própria publicação das consultas públicas |
| `POST` | `/v1/community/places` | Empreendedor + `locations.publish` | publica ponto no mapa |
| `DELETE` | `/v1/community/places/{place_id}` | autor + `locations.publish` | exclui o próprio ponto e libera uma nova publicação |
| `POST` | `/v1/community/live-fairs` | Empreendedor ou Instituição + `locations.publish` | inicia feira ao vivo |
| `POST` | `/v1/community/live-fairs/{fair_id}/end` | autor | encerra a própria feira |
| `DELETE` | `/v1/community/live-fairs/{fair_id}` | autor + `locations.publish` | exclui definitivamente a própria feira |

O ID Token determina o autor; o cliente não envia uma função confiável nem escolhe `ownerId`. Para pontos, o backend permite somente um documento aprovado por empreendedor; uma segunda tentativa responde `409 CURATED_PLACE_ALREADY_EXISTS`. Na exclusão, a API primeiro valida conta, função e permissão no PostgreSQL. Em seguida, uma transação do Firestore lê o ponto ou a feira e só remove o documento quando `ownerId` (ou o campo legado `createdBy`) corresponde ao UID autenticado. Outro autor recebe `403`; um documento inexistente recebe `404`. A remoção atualiza automaticamente as consultas públicas usadas pelo perfil e pelo mapa.
| `GET` | `/v1/feed/posts/{post_id}/comments` | Firebase | lista comentários e respostas |
| `POST` | `/v1/feed/posts/{post_id}/comments` | Firebase | comenta ou responde |
| `PATCH` | `/v1/feed/comments/{comment_id}` | autor | edita comentário próprio |
| `DELETE` | `/v1/feed/comments/{comment_id}` | autor | exclui comentário próprio |
| `PUT` | `/v1/feed/comments/{comment_id}/like` | Firebase | curte comentário ou resposta |
| `DELETE` | `/v1/feed/comments/{comment_id}/like` | Firebase | remove a curtida |
| `POST` | `/v1/media/uploads` | Firebase | autoriza upload direto de imagem |
| `POST` | `/v1/media/uploads/{media_id}/confirm` | proprietário | valida bytes e conclui o processamento |
| `GET` | `/v1/media` | autorizado para a entidade | lista imagens prontas |
| `GET` | `/v1/media/{media_id}` | autorizado | devolve metadados e URL temporária |
| `GET` | `/v1/public/media/{media_id}?variant=...` | público | redireciona o ativo estável para `thumbnail`, `display` ou objeto compatível |
| `GET` | `/v1/public/media/entities/{tipo}/{id}/{papel}?variant=...` | público | seleciona em uma consulta a imagem processada atual de produto, feira ou instituição |
| `GET` | `/v1/public/profile/{uid}/avatar?variant=...` | público | abre o avatar público atual do perfil |
| `DELETE` | `/v1/media/{media_id}` | proprietário | exclui logicamente e remove o objeto privado |
| `POST` | `/v1/admin/media/cleanup` | Administrador | limpa uploads pendentes expirados |

Novos uploads aceitam somente JPEG, PNG ou WebP de até 5 MB. O bucket é
privado; o cliente recebe autorização temporária de upload ou download, nunca a
credencial do Google Cloud.

Os pares aceitos no caminho por entidade são estritos: `product/product_image`,
`fair/fair_cover` e `institution/institution_logo`. Um papel incompatível, ativo
privado, pendente ou sem variante retorna o mesmo `404`, sem revelar metadados.

### Catálogo e painel do empreendedor

| Método | Caminho | Autorização | Descrição |
|---|---|---|---|
| `POST` | `/v1/marketplace/products` | empreendedor ativo | cadastra preço em centavos e estoque |
| `GET` | `/v1/marketplace/products/mine` | empreendedor ativo | lista os próprios produtos |
| `POST` | `/v1/marketplace/products/batch/archive` | empreendedor ativo | exclui produtos da operação/vitrine e preserva histórico |
| `POST` | `/v1/marketplace/products/batch/activate` | empreendedor ativo | ativa até 25 produtos com estoques individuais |
| `POST` | `/v1/marketplace/products/{product_id}/stock` | empreendedor ativo | substitui o estoque autoritativo |
| `GET` | `/v1/marketplace/offers/mine` | empreendedor ativo | lista ofertas e disponibilidade atual |
| `GET` | `/v1/marketplace/offers/{offer_id}/qr` | empreendedor proprietário | gera o QR atual com `quantity` |
| `DELETE` | `/v1/marketplace/offers/{offer_id}` | empreendedor proprietário | revoga o QR e remove a oferta da vitrine |
| `POST` | `/v1/marketplace/offers/batch/actions` | empreendedor ativo | exclui, aumenta desconto ou amplia validade em lote |
| `POST` | `/v1/marketplace/offers/{offer_id}/status` | empreendedor ativo | pausa, reativa ou cancela a própria oferta |

### Oferta e resgate

| Método | Caminho | Autorização | Descrição |
|---|---|---|---|
| `POST` | `/v1/trq-bec/coupons/issue` | empreendedor ativo + dispositivo | emite oferta e QR opaco |
| `POST` | `/v1/trq-bec/coupons/preview` | Firebase | consulta preço, desconto, validade e saldo |
| `POST` | `/v1/trq-bec/coupons/redeem/begin` | Firebase + dispositivo | cria operação e desafio de uso único |
| `POST` | `/v1/trq-bec/coupons/redeem/authorize` | Firebase + prova de posse | confirma ou nega o resgate |

### Instituições, grupos, relatórios e eventos financiados

| Método | Caminho | Autorização | Descrição |
|---|---|---|---|
| `GET` ou `PATCH` | `/v1/institution/profile` | Instituição | consulta ou atualiza campos públicos próprios |
| `GET` | `/v1/institution/reports/summary` | Instituição | resume os próprios grupos |
| `POST` ou `GET` | `/v1/institution/groups` | Instituição | cria ou lista grupos próprios |
| `POST` | `/v1/institution/groups/{group_id}/close` | proprietária | encerra grupo |
| `POST` | `/v1/institution/groups/{group_id}/invitations` | proprietária | convida vendedor por nome público único |
| `GET` | `/v1/institution/groups/{group_id}/members` | proprietária | lista convites e membros |
| `POST` | `/v1/institution/groups/{group_id}/members/{membership_id}/remove` | proprietária | cancela convite ou remove membro |
| `GET` | `/v1/entrepreneur/institution-invitations` | Empreendedor | lista convites e filiação |
| `POST` | `/v1/entrepreneur/institution-invitations/{membership_id}/accept` | Empreendedor | aceita convite |
| `POST` | `/v1/entrepreneur/institution-invitations/{membership_id}/decline` | Empreendedor | recusa convite |
| `POST` | `/v1/entrepreneur/institution-memberships/{membership_id}/leave` | Empreendedor | sai da filiação |
| `GET` | `/v1/institution/reports/sales` | Instituição | relatório de vendas nas janelas de filiação |
| `POST` ou `GET` | `/v1/institution/funded-events` | Instituição | cria ou lista eventos com verba |
| `PUT` | `/v1/institution/funded-events/{event_id}/seller-allocations` | proprietária | ajusta cotas dos afiliados |
| `POST` | `/v1/institution/funded-events/{event_id}/activate` | proprietária | ativa e congela alocações |
| `POST` | `/v1/institution/funded-events/{event_id}/end` | proprietária | encerra evento ativo |
| `GET` | `/v1/institution/funded-events/{event_id}/report` | proprietária | relatório financeiro do evento |
| `GET` | `/v1/entrepreneur/funded-events` | Empreendedor | lista eventos em que recebeu verba |
| `GET` | `/v1/entrepreneur/funded-events/{event_id}/report` | Empreendedor participante | consulta somente a própria cota |
| `PUT` | `/v1/entrepreneur/funded-events/{event_id}/product-allocations` | Empreendedor participante | distribui a própria cota por produto |

Sem configuração manual, o backend divide igualmente o valor entre afiliados e,
depois, entre os produtos elegíveis de cada vendedor. A ativação exige que as
somas fechem o orçamento e congela as alocações usadas pelo relatório.

## Endpoints administrativos

| Método | Caminho | Autorização | Descrição |
|---|---|---|---|
| `POST` | `/internal/v1/marketplace/merchants/status` | `admin=true` | cria, ativa ou suspende conta comercial |
| `POST` | `/internal/v1/ledger/checkpoint` | `admin=true` | produz checkpoint assinado do ledger |

## Exemplo: preparar e emitir uma oferta

Todos os corpos usam schemas fechados; campos adicionais resultam em HTTP `422`.

### 1. Ativar o comerciante

```json
{
  "firebase_uid": "firebase-uid-feirante-001",
  "display_name": "Ana da Feira",
  "establishment_id": "EST-FEIRA-001",
  "establishment_name": "Sabores da Ana",
  "status": "ACTIVE"
}
```

### 2. Cadastrar produto

```json
{
  "title": "Cesta colonial",
  "description": "Cesta de produtos artesanais",
  "price_minor": 5000,
  "currency": "BRL",
  "stock_quantity": 10
}
```

`price_minor=5000` significa R$ 50,00. Valores monetários nunca usam `float`.

### 3. Emitir oferta

No teste real, substitua `valid_until` por um horário com fuso explícito, entre 30 segundos e 8 horas no futuro. A data abaixo documenta o snapshot desta versão.

```json
{
  "product_id": "PROD-A1B2C3D4E5F6",
  "discount_type": "PERCENT",
  "discount_value": 20,
  "maximum_redemptions": 10,
  "valid_until": "2026-07-12T18:00:00-03:00",
  "purpose": "LIVE_FAIR_DISCOUNT",
  "device_key_id": "device:expo:feirante:01"
}
```

O cliente não envia preço final. Para o produto de 5000 centavos, o backend calcula desconto de 1000 e preço final de 4000 centavos.

Resposta resumida:

```json
{
  "offer_id": "OFFER-A1B2C3D4E5F60708",
  "qr_payload": {
    "type": "trq-bec-offer-v1",
    "v": 1,
    "token_ref": "y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un",
    "issuer_ref": "issuer:4f1c5f4a93f2",
    "expires_at": 1783890000,
    "quantity": 1
  },
  "expires_at": 1783890000,
  "offer": {
    "offer_id": "OFFER-A1B2C3D4E5F60708",
    "product_id": "PROD-A1B2C3D4E5F6",
    "product_title": "Cesta colonial",
    "merchant_name": "Ana da Feira",
    "establishment_name": "Sabores da Ana",
    "original_amount_minor": 5000,
    "discount_amount_minor": 1000,
    "final_amount_minor": 4000,
    "currency": "BRL",
    "maximum_redemptions": 10,
    "redeemed_count": 0,
    "remaining_redemptions": 10,
    "expires_at": 1783890000,
    "purpose": "LIVE_FAIR_DISCOUNT",
    "status": "ACTIVE",
    "purchase_quantity": 1
  }
}
```

Depois de emitir a oferta, a Vitrine solicita
`GET /v1/marketplace/offers/{offer_id}/qr?quantity=N`. O backend limita `N` ao
saldo autoritativo e, para quantidade maior que `1`, devolve
`quantity_proof_b64u`. Essa assinatura vincula `token_ref`, emissor, expiração e
quantidade; remover ou alterar qualquer desses campos faz o preview falhar.

## Resgate e idempotência

O retorno de `redeem/begin` inclui `proof_message_b64u`. O aplicativo deve decodificar Base64URL, assinar exatamente esses bytes com a chave privada correspondente ao `device_key_id` e enviar a assinatura em `device_proof_b64u`.

Uma resposta `ALLOW` pode incluir:

- `offer_id` e `product_id`;
- `amount_saved_minor` e `final_amount_minor`;
- `remaining_redemptions` após o commit;
- `quantity` de unidades confirmadas;
- `event_ref` do ledger;
- `idempotent=true` quando a mesma operação concluída é repetida com segurança.

Uma nova operação do mesmo usuário para a mesma oferta é negada. Repetir a mesma operação não produz segundo decremento de estoque. Quando `quantity` é maior que `1`, valores financeiros da autorização são totais da venda e o estoque e `redeemed_count` diminuem/aumentam pela quantidade na mesma transação.

## Contrato de erro

Erros HTTP de autenticação e domínio usam envelope estável:

```json
{
  "code": "MERCHANT_ACCOUNT_INACTIVE",
  "message": "MERCHANT_ACCOUNT_INACTIVE"
}
```

| HTTP | Códigos frequentes | Significado |
|---|---|---|
| `400` | `QR_BINDING_MISMATCH`, `QR_QUANTITY_BINDING_REQUIRED`, `QR_QUANTITY_BINDING_INVALID`, `TOKEN_CRYPTO_INVALID`, `OFFER_VALIDITY_TOO_SHORT`, `OFFER_VALIDITY_TOO_LONG`, `DISCOUNT_INVALID_FOR_AUTHORITATIVE_PRICE` | entrada semanticamente inválida ou quantidade adulterada |
| `401` | `AUTH_BEARER_REQUIRED`, `AUTH_TOKEN_INVALID` | autenticação ausente ou inválida |
| `403` | `ENTREPRENEUR_CLAIM_REQUIRED`, `VISITOR_CLAIM_REQUIRED`, `RECENT_AUTHENTICATION_REQUIRED`, `SELF_REDEMPTION_FORBIDDEN`, `MERCHANT_ACCOUNT_INACTIVE`, `DEVICE_NOT_ENROLLED`, `ADMIN_CLAIM_REQUIRED`, `CURATED_PLACE_NOT_OWNED` | identidade sem autorização necessária |
| `404` | `PRODUCT_NOT_ACTIVE_OR_NOT_OWNED`, `TOKEN_REFERENCE_UNKNOWN`, `OFFER_NOT_FOUND`, `OPERATION_UNKNOWN`, `CURATED_PLACE_NOT_FOUND` | recurso indisponível ou não pertencente ao sujeito |
| `409` | `DEVICE_APPROVAL_NOT_PENDING`, `OFFER_LIMIT_EXCEEDS_STOCK`, `OFFER_QR_QUANTITY_EXCEEDS_AVAILABLE`, `TOKEN_NOT_REDEEMABLE`, `OFFER_NOT_ACTIVE`, `OFFER_REDEMPTION_LIMIT_REACHED`, `OPERATION_IN_PROGRESS`, `LEDGER_EMPTY`, `CURATED_PLACE_ALREADY_EXISTS` | concorrência, saldo insuficiente ou estado incompatível |
| `410` | `TOKEN_EXPIRED`, `OFFER_EXPIRED` | validade encerrada |
| `422` | validação Pydantic | corpo fora do schema estrito |
| `429` | `APPROVAL_RESEND_COOLDOWN` | reenvio solicitado antes do intervalo mínimo |
| `503` | `SESSION_REVOCATION_FAILED`, `PQC_PROVIDER_NOT_READY`, `REPLAY_STORE_UNAVAILABLE`, `CHALLENGE_STORE_UNAVAILABLE`, `OFFER_EXPIRATION_COMMIT_FAILED`, `AUTHORIZATION_DENIAL_COMMIT_FAILED` | dependência crítica indisponível; falha fechada |

Algumas negativas comerciais válidas são retornadas com HTTP `200` e `decision="DENY"`, acompanhadas de `reason_codes`, por exemplo limite ou estoque perdido em uma corrida concorrente.
O código `RATE_LIMIT_EXCEEDED` também é uma negativa terminal durável. Se o cache Redis falhar depois do commit PostgreSQL, a resposta preserva o resultado comercial e acrescenta `REPLAY_CACHE_COMMIT_DEGRADED`.

Para `RECENT_AUTHENTICATION_REQUIRED`, o usuário deve sair, entrar novamente e
cadastrar a chave nova em até 5 minutos. `DEVICE_APPROVAL_NOT_PENDING` pertence
somente à rota legada de aprovação e indica que o registro não está mais em
estado compatível. No fluxo atual, o reenvio exige autenticação recente, apenas
repete o alerta de segurança e não reinicia o cooldown; ao completar 10 minutos,
o backend ativa automaticamente o dispositivo pendente.

O botão **Alterar senha** deve avisar antes da confirmação que todos os aparelhos,
inclusive o atual e os pendentes, serão desconectados. A revogação só é anunciada
como concluída depois que o backend revoga os registros e os refresh tokens do
Firebase; `SESSION_REVOCATION_FAILED` não deve ser mostrado como sucesso parcial.

## Gerar os contratos versionados

Na pasta `backend_trq_bec`, com o ambiente virtual ativado:

```powershell
trq-bec-openapi --scope public
trq-bec-openapi --scope internal
```

Saídas padrão:

- `docs/openapi-liberrotas-public-v0.6.0a1.json`;
- `docs/openapi-liberrotas-internal-v0.6.0a1.json`.

Os arquivos gerados devem ser atualizados sempre que rota, schema, exemplo, código de erro ou versão da API mudar.

## Fora da Fase 1

- pedidos sem pagamento entram somente na Fase 2;
- pagamentos, webhooks e estornos entram somente na Fase 3;
- ML-KEM-768 e ML-DSA-65 dependem de provider auditado e aprovado;
- IA permanece em modo observador, sem poder de autorizar ou executar;
- não existe confirmação comercial offline.
