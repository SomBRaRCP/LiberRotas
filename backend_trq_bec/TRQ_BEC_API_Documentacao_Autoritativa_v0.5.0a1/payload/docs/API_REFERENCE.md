# TRQ-BEC LiberRotas API — Referência de Integração

**Versão:** `0.5.0-alpha.1`  
**Contrato:** OpenAPI 3.1  
**Estado:** laboratório controlado; ML-KEM-768 e ML-DSA-65 bloqueados até provider auditado.

## Objetivo

A API é a fronteira autoritativa para:

1. vincular uma chave pública ao dispositivo autenticado;
2. emitir cupons vinculados ao empreendedor, dispositivo e política;
3. iniciar o resgate com desafio de uso único;
4. validar prova de posse, replay, contexto e política;
5. registrar evidências em ledger append-only;
6. produzir checkpoints assinados do ledger.

A regra estrutural é **fail-closed**: falha criptográfica, ausência de evidência obrigatória ou indisponibilidade de dependência crítica nunca produz `ALLOW`.

## Interfaces de documentação

| Interface | Caminho | Finalidade |
|---|---|---|
| Swagger UI | `/docs` | Teste interativo e inspeção dos contratos |
| ReDoc | `/redoc` | Leitura técnica contínua e apresentação |
| OpenAPI JSON | `/openapi.json` | Geração de clientes, validação e auditoria |

Essas interfaces são habilitadas somente fora de produção quando `TRQ_BEC_DOCS_ENABLED=true`.

## Autenticação

As rotas protegidas usam **HTTP Bearer** com um Firebase ID token:

```http
Authorization: Bearer <firebase-id-token>
```

No Swagger UI, clique em **Authorize** e cole somente o token. A interface acrescenta o prefixo `Bearer`.

Principais claims:

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

## Endpoints

### Saúde e prontidão

| Método | Caminho | Autenticação | Descrição |
|---|---|---|---|
| `GET` | `/health/` | não | PostgreSQL, Redis e prontidão PQC |
| `GET` | `/health/crypto` | não | provider, aprovação, self-test e algoritmos |

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

### Operações internas

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

| HTTP | Significado operacional |
|---|---|
| `400` | QR, vínculo ou contrato semanticamente inválido |
| `401` | token Firebase ausente ou inválido |
| `403` | claim, dispositivo ou vínculo sem autorização |
| `404` | cupom, token ou operação não encontrado |
| `409` | conflito, replay ou recurso já utilizado |
| `410` | token expirado |
| `422` | corpo fora do schema estrito |
| `503` | Redis/provider/dependência crítica indisponível |

## Decisão de autorização

A resposta de autorização contém:

- `decision`: `ALLOW`, `DENY`, `STEP_UP` ou `HOLD_OR_REVIEW`;
- `crypto_ok`: resultado dos gates criptográficos obrigatórios;
- `reason_codes`: justificativas auditáveis;
- `event_ref`: referência ao evento append-only;
- `idempotent`: repetição segura da mesma operação.

`crypto_ok=false` jamais deve ser interpretado como autorização.

## Exportar o contrato

Após instalar o pacote em modo editável:

```powershell
trq-bec-openapi --output .\docs\openapi-liberrotas-v0.5.0a1.json
```

O arquivo gerado pode ser versionado, comparado em revisão e usado para geração de clientes.
