# TRQ-BEC LiberRotas API — Referência de Integração

**Versão:** `0.5.0-alpha.2`  
**Contrato:** OpenAPI 3.1  
**Estado:** laboratório controlado; ML-KEM-768 e ML-DSA-65 bloqueados até provider auditado.

## Objetivo

A API é a fronteira autoritativa para:

1. vincular uma chave pública ao dispositivo autenticado;
2. emitir cupons vinculados ao empreendedor, dispositivo e política;
3. iniciar o resgate com desafio de uso único;
4. validar prova de posse, replay, contexto e política;
5. registrar evidências em ledger append-only;
6. produzir checkpoints assinados do ledger em contrato administrativo separado.

A regra estrutural é **fail-closed**: falha criptográfica, ausência de evidência obrigatória ou indisponibilidade de dependência crítica nunca produz `ALLOW`.

## Contratos separados

### Contrato público

| Interface | Caminho | Finalidade |
|---|---|---|
| Swagger UI | `/docs` | Teste interativo das rotas públicas |
| ReDoc | `/redoc` | Leitura técnica e apresentação pública |
| OpenAPI JSON | `/openapi.json` | Geração de clientes e validação do app |

O contrato público contém apenas:

- saúde e prontidão;
- cadastro de dispositivos;
- emissão de cupons;
- início e autorização de resgate.

### Contrato administrativo

| Interface | Caminho | Finalidade |
|---|---|---|
| Swagger administrativo | `/internal/docs` | Teste interativo das rotas internas |
| ReDoc administrativo | `/internal/redoc` | Leitura do contrato operacional interno |
| OpenAPI administrativo | `/internal/openapi.json` | Auditoria e automação administrativa |

O contrato administrativo contém somente rotas iniciadas por `/internal/`. Ele não aparece na documentação pública.

Todas as interfaces de documentação são habilitadas apenas fora de produção quando `TRQ_BEC_DOCS_ENABLED=true`.

## Autenticação

As rotas protegidas usam **HTTP Bearer** com um Firebase ID token:

```http
Authorization: Bearer <firebase-id-token>
```

No Swagger UI, clique em **Authorize** e cole somente o token. A interface acrescenta o prefixo `Bearer`.

Claims principais:

| Claim | Uso |
|---|---|
| `sub` ou `uid` | identidade autoritativa do usuário |
| `role=entrepreneur` | permissão para emissão de cupom |
| `admin=true` | permissão para checkpoint interno |

## Fluxo autoritativo

```text
Firebase ID token
       |
       v
Cadastro do dispositivo
       |
       v
Emissão do cupom --> QR compacto
       |
       v
Início do resgate --> operação + sessão + desafio
       |
       v
Assinatura local da proof_message
       |
       v
Autorização --> replay + criptografia + risco + política
       |
       v
Decisão + evento no ledger
```

## Endpoints públicos

### Saúde e prontidão

| Método | Caminho | Autenticação | Descrição |
|---|---|---|---|
| `GET` | `/health/` | não | PostgreSQL, Redis e prontidão PQC |
| `GET` | `/health/crypto` | não | provider, aprovação, autoteste e algoritmos |

### Dispositivos

| Método | Caminho | Autenticação | Descrição |
|---|---|---|---|
| `POST` | `/v1/trq-bec/devices/enroll` | sim | vincula a chave pública ao Firebase UID |

### Cupons

| Método | Caminho | Autenticação | Descrição |
|---|---|---|---|
| `POST` | `/v1/trq-bec/coupons/issue` | empreendedor | emite QR compacto e envelope protegido |

### Resgate

| Método | Caminho | Autenticação | Descrição |
|---|---|---|---|
| `POST` | `/v1/trq-bec/coupons/redeem/begin` | sim | cria sessão e desafio de uso único |
| `POST` | `/v1/trq-bec/coupons/redeem/authorize` | sim | valida prova de posse e aplica política |

## Endpoint administrativo

| Método | Caminho | Autenticação | Descrição |
|---|---|---|---|
| `POST` | `/internal/v1/ledger/checkpoint` | `admin=true` | produz checkpoint assinado do ledger |

## Exemplo de emissão

```json
{
  "coupon_id": "FEITUR-021",
  "issuer_id": "firebase-uid-feirante-001",
  "city": "Pinhais - PR",
  "device_key_id": "device:expo:feirante:01"
}
```

Resposta:

```json
{
  "qr_payload": {
    "type": "trq-bec-coupon-v1",
    "v": 1,
    "token_ref": "y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un",
    "issuer_ref": "issuer:4f1c5f4a93f2",
    "expires_at": 1783811490
  },
  "expires_at": 1783811490
}
```

## Contrato de erro

Erros de autenticação e domínio usam envelope estável:

```json
{
  "code": "AUTH_TOKEN_INVALID",
  "message": "AUTH_TOKEN_INVALID"
}
```

Os exemplos da documentação são específicos para cada rota e correspondem aos códigos realmente emitidos pelo serviço.

| HTTP | Exemplos de código | Significado operacional |
|---|---|---|
| `400` | `QR_BINDING_MISMATCH`, `TOKEN_CRYPTO_INVALID` | QR ou envelope semanticamente inválido |
| `401` | `AUTH_BEARER_REQUIRED`, `AUTH_TOKEN_INVALID` | autenticação ausente ou inválida |
| `403` | `ENTREPRENEUR_CLAIM_REQUIRED`, `DEVICE_NOT_ENROLLED`, `ADMIN_CLAIM_REQUIRED` | claim, dispositivo ou vínculo insuficiente |
| `404` | `COUPON_NOT_ACTIVE_OR_NOT_OWNED`, `TOKEN_REFERENCE_UNKNOWN`, `OPERATION_UNKNOWN` | recurso não encontrado |
| `409` | `DEVICE_KEY_BINDING_CONFLICT`, `TOKEN_NOT_REDEEMABLE`, `LEDGER_EMPTY` | conflito ou estado incompatível |
| `410` | `TOKEN_EXPIRED` | token expirado |
| `422` | validação Pydantic | corpo fora do schema estrito |
| `503` | `PQC_PROVIDER_NOT_READY`, `REPLAY_STORE_UNAVAILABLE` | dependência crítica indisponível |

## Decisão de autorização

A resposta de autorização contém:

- `decision`: `ALLOW`, `DENY`, `STEP_UP` ou `HOLD_OR_REVIEW`;
- `crypto_ok`: resultado dos gates criptográficos obrigatórios;
- `reason_codes`: justificativas auditáveis;
- `event_ref`: referência ao evento append-only;
- `idempotent`: repetição segura da mesma operação.

`crypto_ok=false` jamais deve ser interpretado como autorização.

## Exportar os contratos

Contrato público:

```powershell
trq-bec-openapi --scope public --output .\docs\openapi-liberrotas-public-v0.5.0a2.json
```

Contrato administrativo:

```powershell
trq-bec-openapi --scope internal --output .\docs\openapi-liberrotas-internal-v0.5.0a2.json
```

Os arquivos gerados podem ser versionados, comparados em revisão e usados para geração de clientes ou auditoria.
