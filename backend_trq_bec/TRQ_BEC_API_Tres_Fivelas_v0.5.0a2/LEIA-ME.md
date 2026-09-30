# TRQ-BEC LiberRotas API — As três fivelas

**Versão:** `0.5.0-alpha.2`

Esta atualização fecha os três pontos restantes antes da apresentação ao mercado. Ela não altera `.env`, credencial Firebase, chaves privadas, PostgreSQL, Redis ou volumes Docker.

## Primeira fivela — erros aderentes ao comportamento real

Os exemplos OpenAPI agora são específicos por rota e correspondem aos códigos emitidos pelo serviço:

- `QR_BINDING_MISMATCH` e `TOKEN_CRYPTO_INVALID` no QR inválido;
- `COUPON_NOT_ACTIVE_OR_NOT_OWNED` no cupom indisponível;
- `OPERATION_UNKNOWN` na operação de resgate desconhecida;
- `REPLAY_STORE_UNAVAILABLE` na indisponibilidade do replay distribuído;
- `ADMIN_CLAIM_REQUIRED` na rota administrativa;
- `LEDGER_EMPTY` no checkpoint sem eventos.

O backend também converte `LEDGER_EMPTY` em HTTP `409`, alinhando a execução ao contrato documentado.

## Segunda fivela — documentação em português

As descrições dos schemas, campos, autenticação, respostas e contratos foram uniformizadas em português. Identificadores técnicos, algoritmos e códigos de erro permanecem inalterados.

## Terceira fivela — separação pública e administrativa

### Público

```text
http://127.0.0.1:8787/docs
http://127.0.0.1:8787/redoc
http://127.0.0.1:8787/openapi.json
```

### Administrativo

```text
http://127.0.0.1:8787/internal/docs
http://127.0.0.1:8787/internal/redoc
http://127.0.0.1:8787/internal/openapi.json
```

O contrato público não contém `/internal/v1/ledger/checkpoint`. O contrato administrativo contém somente a rota interna. As interfaces continuam desativadas em produção.

## Aplicar no Windows

Como a pasta desta atualização foi colocada dentro de `backend_trq_bec`, execute a partir da raiz do backend:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& ".\TRQ_BEC_API_Tres_Fivelas_v0.5.0a2\APLICAR_ATUALIZACAO.ps1"
```

O script detecta automaticamente a pasta pai como backend. Para informar outro caminho:

```powershell
& ".\TRQ_BEC_API_Tres_Fivelas_v0.5.0a2\APLICAR_ATUALIZACAO.ps1" `
  -BackendPath "C:\caminho\backend_trq_bec"
```

O instalador cria backup antes de substituir ou remover arquivos.

## Reconstruir a API

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
docker compose build api
docker compose up -d api
docker compose logs --since 2m api
```

## Validar

```powershell
Invoke-RestMethod "http://127.0.0.1:8787/health/"
Invoke-RestMethod "http://127.0.0.1:8787/health/crypto"
```

Confirme a separação dos contratos:

```powershell
$publico = Invoke-RestMethod "http://127.0.0.1:8787/openapi.json"
$interno = Invoke-RestMethod "http://127.0.0.1:8787/internal/openapi.json"

$publico.paths.PSObject.Properties.Name
$interno.paths.PSObject.Properties.Name
```

O primeiro resultado não deve conter rotas iniciadas por `/internal/`. O segundo deve conter somente:

```text
/internal/v1/ledger/checkpoint
```

## Validação realizada

- compilação Python: aprovada;
- fluxo de emissão e resgate: aprovado;
- contrato público isolado: aprovado;
- contrato administrativo isolado: aprovado;
- exemplos de erro por rota: aprovados;
- descrições em português: aprovadas;
- checkpoint vazio retornando `409/LEDGER_EMPTY`: aprovado;
- suíte completa: **40 de 40 testes aprovados**.
