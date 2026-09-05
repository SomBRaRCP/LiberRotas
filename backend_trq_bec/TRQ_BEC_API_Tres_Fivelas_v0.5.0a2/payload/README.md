# TRQ-BEC

Implementação de referência modular da **TRQ-BEC — Boundary Entropic Cryptography / Criptografia Entrópica de Borda TRQ**, preparada para integração experimental com o `app_LiberRotas`.

> Status: backend experimental `0.5.0-alpha.2`. Não é certificação FIPS 140-3, homologação Pix, protocolo pronto para produção nem implementação pós-quântica validada.

A segurança nasce de primitivas e verificações determinísticas. Contexto e IA permanecem auxiliares, calibráveis e auditáveis. A regra estrutural é absoluta: `CryptoOK = 0` implica `DENY`.

## O que já funciona

- contrato estrito de intenção e envelope;
- codificação canônica sem `float` no domínio assinado;
- suíte de laboratório Ed25519 + SHA3-256;
- registro explícito da suíte futura ML-KEM-768 + ML-DSA-65, indisponível e bloqueada;
- emissão e verificação de token com assinatura, emissor, audiência, propósito, política, TTL e vínculo de intenção;
- desafio aleatório de uso único e prova de posse de chave de dispositivo;
- replay, desafio e idempotência distribuídos em Redis com Lua atômico;
- motor contextual com proveniência, frescor, cobertura e índice heurístico;
- política determinística `DENY / ALLOW / STEP_UP / HOLD_OR_REVIEW`;
- ledger PostgreSQL append-only, encadeado por SHA3-256 e checkpoint assinado;
- API FastAPI com Firebase ID-token, custom claims e contratos fechados;
- estado durável de dispositivos, cupons, envelopes e operações;
- `AI Assurance Layer` somente leitura, sem acesso ao núcleo ou poder de execução;
- adaptador TypeScript para React Native/Expo do `app_LiberRotas`;
- testes de adulteração, replay, concorrência, downgrade, intenção, ledger e limites da IA.

## Arquitetura

```text
app_LiberRotas (Expo)
        |
        | Firebase ID token + prova de posse
        v
Protocol Engine ---> Crypto Core ---> CryptoOK
        |                                 |
        v                                 v
Boundary / Risk -----------------> Policy Engine
        |                                 |
        v                                 v
Evidence Ledger ----------------> decisão autoritativa
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
integrations/app_liberrotas/
  mobile/        contratos e cliente TypeScript
config/          política de laboratório e papel interno da IA
schemas/         JSON Schemas canônicos
docs/            ADRs, arquitetura, ameaça e implantação
tests/           bateria de regressão e ataques
migrations/      schema, constraints e triggers append-only
```

## Executar

No Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
trq-bec demo
python -m unittest discover -s tests -v
```

No Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e .
trq-bec demo
py -m unittest discover -s tests -v
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

O aplicativo usa estes endpoints:

```text
POST /v1/trq-bec/devices/enroll
POST /v1/trq-bec/coupons/issue
POST /v1/trq-bec/coupons/redeem/begin
POST /v1/trq-bec/coupons/redeem/authorize
```

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
- [`docs/openapi-liberrotas-public-v0.5.0a2.json`](docs/openapi-liberrotas-public-v0.5.0a2.json): contrato público OpenAPI 3.1;
- [`docs/openapi-liberrotas-internal-v0.5.0a2.json`](docs/openapi-liberrotas-internal-v0.5.0a2.json): contrato administrativo OpenAPI 3.1;
- [`docs/BACKEND_DEPLOYMENT.md`](docs/BACKEND_DEPLOYMENT.md): Docker Compose, Firebase custom claims, segredos, migrações e implantação.

Para regenerar os contratos:

```powershell
trq-bec-openapi --scope public --output .\docs\openapi-liberrotas-public-v0.5.0a2.json
trq-bec-openapi --scope internal --output .\docs\openapi-liberrotas-internal-v0.5.0a2.json
```

## Limites conhecidos

- Redis/PostgreSQL reais não puderam ser iniciados no ambiente de construção; o Compose deve ser validado no servidor antes de qualquer piloto.
- O provider de laboratório usa arquivos PEM montados como segredo; produção exige KMS/HSM e lifecycle completo.
- O índice contextual é heurístico, em pontos-base, e não é probabilidade.
- A política de laboratório é versionada e possui digest, mas ainda não é assinada.
- Não há ML-KEM/ML-DSA implementado neste pacote; escolher a suíte PQ falha fechado.
- O adapter PQC está deliberadamente bloqueado; aprovar uma flag sem instalar um provider real impede a inicialização.

## Próximo gate

Subir o Docker Compose no servidor, aplicar custom claims aos empreendedores, conectar o IP HTTPS ao aplicativo e executar a bateria com PostgreSQL/Redis reais e múltiplos workers. O provider pós-quântico só entra depois dessa base ficar verde.
