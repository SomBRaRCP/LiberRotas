# Backend TRQ-BEC para app_LiberRotas

**Versão:** 0.6.0-alpha.1  
**Escopo:** Fase 1 — oferta ao vivo em feira  
**Estado:** implementação executável de laboratório; produção permanece bloqueada

## Componentes

| Componente | Função |
| --- | --- |
| FastAPI/Uvicorn | endpoints autenticados e contratos estritos |
| Firebase Admin | valida ID token e revogação no servidor |
| PostgreSQL | contas, permissões, catálogo, ofertas, dispositivos, operações, resgates, mensagens, comentários, eventos e ledger |
| Redis + Lua | desafio, replay, idempotência e sinal de taxa entre workers |
| Google Cloud Storage | bytes privados de imagens; PostgreSQL mantém metadados e propriedade |
| FileEd25519Provider | assinatura do perfil de laboratório com chaves montadas como segredo |
| Future PQC Provider | interface ML-KEM-768/ML-DSA-65 bloqueada até aprovação |

## Endpoints implementados

```text
GET  /health/
GET  /health/crypto
GET  /v1/time
GET  /v1/access/me
POST /v1/trq-bec/devices/enroll
GET  /v1/account/devices
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
POST /v1/marketplace/offers/{offer_id}/status
POST /v1/trq-bec/coupons/issue
POST /v1/trq-bec/coupons/preview
POST /v1/trq-bec/coupons/redeem/begin
POST /v1/trq-bec/coupons/redeem/authorize
POST /internal/v1/marketplace/merchants/status
POST /internal/v1/ledger/checkpoint
```

Esse bloco mostra somente saúde, dispositivos e núcleo comercial. Diretório,
Feed, comentários, mídia, mensagens, painéis e eventos institucionais estão
listados em [`API_REFERENCE.md`](API_REFERENCE.md) e no OpenAPI público gerado.

O backend é autoritativo para valores e efeitos comerciais. O aplicativo não deve confirmar oferta, estoque ou resgate por conta própria.

## Primeiro início com Docker Compose

Execute os comandos abaixo no Windows PowerShell, dentro da pasta `backend_trq_bec`.

1. Crie a configuração local a partir do exemplo, caso ela ainda não exista:

```powershell
if (-not (Test-Path .env.backend)) {
    Copy-Item .env.backend.example .env.backend
}
```

2. Defina `TRQ_BEC_POSTGRES_PASSWORD` no arquivo `.env` usado pelo Docker Compose. Use uma senha local forte e não a publique.

3. Gere as chaves de laboratório fora do contêiner:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
trq-bec-keygen --output secrets
```

4. Coloque a credencial Firebase Admin em:

```text
secrets/firebase-service-account.json
```

Não envie esse arquivo para Git, aplicativo, chat ou frontend. Em infraestrutura Google, prefira Application Default Credentials/Workload Identity em vez de uma chave JSON permanente.

4.1. Configure o e-mail de segurança em `.env.backend`. Dados de conexão podem ficar nesse arquivo local ignorado pelo Git; a senha deve permanecer em Docker secret:

```env
TRQ_BEC_PUBLIC_APP_URL=https://app.liberrotas.com.br
TRQ_BEC_DEVICE_AUTO_ACTIVATION_DELAY_SECONDS=600
TRQ_BEC_DEVICE_APPROVAL_TTL_SECONDS=1800
TRQ_BEC_DEVICE_APPROVAL_RESEND_COOLDOWN_SECONDS=60
TRQ_BEC_SMTP_HOST=smtp.exemplo.com
TRQ_BEC_SMTP_PORT=587
TRQ_BEC_SMTP_USERNAME=seguranca@liberrotas.com.br
TRQ_BEC_SMTP_PASSWORD_PATH=/run/secrets/smtp-password
TRQ_BEC_SMTP_STARTTLS=true
TRQ_BEC_SMTP_SSL=false
TRQ_BEC_SMTP_TIMEOUT_SECONDS=10
TRQ_BEC_EMAIL_FROM=seguranca@liberrotas.com.br
```

Na pasta `backend_trq_bec`, crie o segredo sem colocar a senha no histórico do PowerShell:

```powershell
New-Item -ItemType Directory -Force ".\secrets" | Out-Null
notepad ".\secrets\smtp-password"
```

Salve somente a senha SMTP ou senha de aplicativo. Para SMTP implícito na porta `465`, use `TRQ_BEC_SMTP_SSL=true` e `TRQ_BEC_SMTP_STARTTLS=false`. Nunca habilite os dois modos ao mesmo tempo. O `secrets-init` copia o arquivo para `/run/secrets/smtp-password` quando ele existe, aplica proprietário `10001`, modo `600`, e a API monta o volume como somente leitura. Em produção, provisione a credencial exigida pelo provedor antes de iniciar a pilha.

O destinatário do alerta é sempre consultado por `firebase_admin.auth.get_user(uid).email`; não aceite e-mail informado pelo aplicativo. O remetente precisa estar autorizado pelo provedor. Em domínio público, configure SPF, DKIM e DMARC. Em desenvolvimento, falha SMTP não derruba o login nem impede a liberação após 10 minutos e deve produzir `NOT_CONFIGURED` ou `FAILED`, nunca `SENT`. Em `TRQ_BEC_ENVIRONMENT=production`, `TRQ_BEC_SMTP_HOST` e `TRQ_BEC_EMAIL_FROM` são obrigatórios para preservar o alerta de segurança.

5. No Windows, o serviço `secrets-init` copia os arquivos da pasta NTFS para o volume Linux `trq_bec_secrets`, ajusta o proprietário para UID `10001` e aplica modo `600`. Não tente usar `chmod` no PowerShell.

No Linux, a restrição equivalente no diretório de origem pode ser feita com:

```bash
sudo chown -R 10001:10001 secrets
sudo chmod 700 secrets
sudo chmod 600 secrets/*
```

6. Inicie:

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8787/health/
```

O comando do serviço `api` executa `trq-bec-migrate` antes do Uvicorn. A sequência atual vai de `001_initial.sql` até `016_community_content_management.sql` e é aplicada em ordem. Para conferir:

```powershell
docker compose exec postgres psql -U trq_bec -d trq_bec -c "SELECT version, applied_at FROM schema_migrations ORDER BY version;"
```

O resultado esperado termina em `016_community_content_management`. Se a API não subir, rode `docker compose logs api --tail 200` e diagnostique a mensagem exata antes de alterar arquivos. Confira apenas os metadados do segredo SMTP, nunca seu conteúdo:

```powershell
docker compose exec api stat -c "%a %u:%g %n" /run/secrets/smtp-password
```

O resultado esperado é `600 10001:10001 /run/secrets/smtp-password` quando o SMTP foi configurado.

## Claims e conta comercial

O backend não confia no campo `role` de `public_profiles`, pois o documento do perfil pertence ao usuário. Defina as custom claims somente em ambiente administrativo:

```powershell
trq-bec-set-role FIREBASE_UID_DO_ADMIN admin
trq-bec-set-role FIREBASE_UID entrepreneur
```

Depois de alterar claims, o usuário deve renovar o ID token — normalmente saindo e entrando novamente. Atenção: o helper aplica um papel por chamada; não use o mesmo UID como administrador e empreendedor sem revisar a política de claims.

Além de `role=entrepreneur`, a Fase 1 exige conta comercial `ACTIVE`. Um administrador cria ou atualiza esse cadastro por `POST /internal/v1/marketplace/merchants/status`. Suspender a conta bloqueia novas operações comerciais, mesmo que a claim Firebase continue presente.

Toda chave nova exige que `auth_time` do ID token esteja dentro de `TRQ_BEC_DEVICE_ENROLLMENT_MAX_AUTH_AGE_SECONDS` (padrão: 300 segundos). Repetir a mesma chave continua idempotente depois dessa janela. Para visitante, qualquer chave nova fica `ACTIVE` imediatamente e gera apenas o alerta de segurança. Para empreendedor e instituição, inclusive no primeiro aparelho, a chave fica `PENDING_APPROVAL` por `TRQ_BEC_DEVICE_AUTO_ACTIVATION_DELAY_SECONDS` (padrão: 600), sem bloquear a sessão autenticada, e depois é ativada automaticamente.

O e-mail contém o botão **Não fui eu!** para `/account/devices`, sem segredo ou token. Se o próprio usuário entrou, ele desconsidera a mensagem. Se não reconhece o acesso, revisa a lista e troca a senha. `resend-approval` exige autenticação recente, aplica cooldown de 60 segundos e não altera o horário da liberação. Ao terminar os 10 minutos, o backend ativa a chave na próxima consulta ou operação protegida. `revoke-all` inclui dispositivos `ACTIVE` e `PENDING_APPROVAL` e revoga refresh tokens Firebase.

## Replay distribuído

Redis executa Lua atômico para:

- reservar `(issuer, replay_jti)` por operação;
- distinguir `NEW`, `SAME_OP` e `REPLAY`;
- guardar resultado idempotente;
- consumir desafio uma única vez;
- contar tentativas por janela.

Acima de `TRQ_BEC_RATE_HIGH_THRESHOLD`, a autorização é confirmada como `DENY` com `RATE_LIMIT_EXCEEDED`. O controle não é apenas informativo.

PostgreSQL mantém a segunda barreira: `replay_jti` é único por operação; `(offer_id, buyer_uid)` é único; produto e oferta são bloqueados durante o commit; estoque e limite são atualizados na mesma transação do resgate e do ledger. O QR da oferta pode atender compradores diferentes até o limite, mas uma repetição nunca pode produzir segundo efeito para a mesma operação ou pessoa.

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

- validar a sequência até `016_community_content_management.sql` no PostgreSQL do ambiente-alvo e testar backup/restore;
- testar aprovação válida, token expirado/reutilizado/de outro UID, reenvio e revogação total;
- configurar SMTP com TLS, remetente autorizado, SPF, DKIM e DMARC, e monitorar falhas de entrega;
- comprovar que produção recusa inicialização sem host SMTP e remetente;
- garantir que `approval_token` não entre em query string, `returnTo`, logs, analytics ou armazenamento local;
- executar concorrência com PostgreSQL/Redis reais e múltiplos workers;
- manter resgate comercial offline desabilitado;
- trocar FileEd25519Provider por KMS/HSM/provider aprovado;
- instalar e validar o adapter PQC;
- desativar `TRQ_BEC_LAB_SUITE_ENABLED`;
- usar TLS em proxy reverso;
- restringir `FORWARDED_ALLOW_IPS` ao proxy;
- autenticar Redis e PostgreSQL em rede privada;
- exportar checkpoints para ancoragem independente;
- testar falhas parciais de PostgreSQL, Redis, Firebase e provider criptográfico;
- realizar revisão externa.

Pedidos, pagamentos, webhooks e estornos exigem fases próprias e não devem ser simulados por estas rotas.
