# Backend TRQ-BEC para app_LiberRotas

**Versão:** 0.5.0-alpha.2  
**Estado:** implementação executável de laboratório; produção permanece bloqueada

## Componentes

| Componente | Função |
| --- | --- |
| FastAPI/Uvicorn | endpoints autenticados e contratos estritos |
| Firebase Admin | valida ID token e revogação no servidor |
| PostgreSQL | dispositivos, cupons, envelopes, operações e ledger durável |
| Redis + Lua | desafio, replay, idempotência e sinal de taxa entre workers |
| FileEd25519Provider | assinatura do perfil de laboratório com chaves montadas como segredo |
| Future PQC Provider | interface ML-KEM-768/ML-DSA-65 bloqueada até aprovação |

## Endpoints implementados

```text
GET  /health/
GET  /health/crypto
POST /v1/trq-bec/devices/enroll
POST /v1/trq-bec/coupons/issue
POST /v1/trq-bec/coupons/redeem/begin
POST /v1/trq-bec/coupons/redeem/authorize
POST /internal/v1/ledger/checkpoint
```

Os quatro endpoints móveis correspondem aos contratos já usados por `src/security/trq-bec/service.ts` no aplicativo.

## Primeiro início com Docker Compose

1. Copie `.env.backend.example` para `.env.backend`.
2. Defina `TRQ_BEC_POSTGRES_PASSWORD` no arquivo `.env` usado pelo Docker Compose.
3. Gere as chaves de laboratório fora do contêiner:

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
trq-bec-keygen --output secrets
```

4. Coloque a credencial Firebase Admin em:

```text
secrets/firebase-service-account.json
```

Não envie esse arquivo para Git, aplicativo, chat ou frontend. Em infraestrutura Google, prefira Application Default Credentials/Workload Identity em vez de uma chave JSON permanente.

5. No Linux, permita leitura somente ao UID do contêiner:

```bash
sudo chown -R 10001:10001 secrets
sudo chmod 700 secrets
sudo chmod 600 secrets/*
```

6. Inicie:

```bash
docker compose up --build -d
curl http://127.0.0.1:8787/health/
```

## Papel de empreendedor

O backend não confia no campo `role` de `public_profiles`, pois o documento do perfil pertence ao usuário. A emissão exige custom claim Firebase:

```bash
trq-bec-set-role FIREBASE_UID entrepreneur
```

Depois de alterar claims, o usuário deve renovar o ID token — normalmente saindo e entrando novamente.

## Replay distribuído

Redis executa Lua atômico para:

- reservar `(issuer, jti)`;
- distinguir `NEW`, `SAME_OP` e `REPLAY`;
- guardar resultado idempotente;
- consumir desafio uma única vez;
- contar tentativas por janela.

PostgreSQL mantém a segunda barreira: `jti` é único e um token só muda de `ISSUED` para `REDEEMED` uma vez dentro de transação. Se o Redis perder dados, o banco ainda impede segundo efeito.

## Ledger

Cada inserção adquire `pg_advisory_xact_lock`, lê o hash anterior, calcula SHA3-256 canônico e grava sequência/hash. Triggers rejeitam `UPDATE` e `DELETE` em eventos e checkpoints.

Isso detecta adulteração, mas não prova sozinho ausência de truncamento do banco inteiro. Checkpoints devem ser exportados e ancorados fora do mesmo PostgreSQL.

## Provider pós-quântico futuro

O contrato `PostQuantumProvider` exige:

- status verificável;
- self-test;
- ML-DSA-65 sign/verify com contexto;
- ML-KEM-768 encapsulate/decapsulate;
- identidade e versão do provider.

`UnavailablePQCProvider` falha fechado. Marcar `TRQ_BEC_PQC_PROVIDER_APPROVED=true` sem instalar um adapter real impede o backend de iniciar.

Para aprovar um provider serão exigidos: versão imutável, hashes, licença, relatório de auditoria, vetores FIPS 203/204, testes negativos, SBOM, lifecycle de chaves e ambiente/plataforma cobertos pela alegação.

## Produção

Antes de produção:

- trocar FileEd25519Provider por KMS/HSM/provider aprovado;
- instalar e validar o adapter PQC;
- desativar `TRQ_BEC_LAB_SUITE_ENABLED`;
- usar TLS em proxy reverso;
- restringir `FORWARDED_ALLOW_IPS` ao proxy;
- autenticar Redis e PostgreSQL em rede privada;
- exportar checkpoints para ancoragem independente;
- executar testes com PostgreSQL/Redis reais, falhas parciais e múltiplos workers;
- realizar revisão externa.
