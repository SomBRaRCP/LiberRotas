# Atualização — Documentação autoritativa da TRQ-BEC LiberRotas API

Esta atualização altera somente documentação e contratos HTTP do backend. Ela **não toca** em `.env`, credenciais Firebase, chaves privadas, volumes Docker, PostgreSQL ou Redis.

## O que entra

- grupos OpenAPI por domínio, eliminando a categoria `default`;
- botão **Authorize** com HTTP Bearer para Firebase ID token;
- descrições operacionais e exemplos reais do LiberRotas;
- schema tipado para `/health/crypto`;
- schema tipado para checkpoint do ledger;
- respostas documentadas para `400`, `401`, `403`, `404`, `409`, `410`, `422` e `503`;
- envelope estável para erros de autenticação;
- Swagger UI mais organizada;
- ReDoc em `/redoc`;
- OpenAPI desativado em produção junto com as interfaces de documentação;
- referência `docs/API_REFERENCE.md`;
- contrato OpenAPI 3.1 versionado;
- comando `trq-bec-openapi` para regenerar o contrato;
- três testes de regressão documental, elevando a suíte de 33 para 36 testes.

## Aplicar no Windows

Abra PowerShell na pasta extraída desta atualização e execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\APLICAR_ATUALIZACAO.ps1
```

O script usa por padrão:

```text
F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec
```

Para outro caminho:

```powershell
.\APLICAR_ATUALIZACAO.ps1 -BackendPath "C:\caminho\backend_trq_bec"
```

O instalador cria uma cópia dos arquivos anteriores em uma pasta `.backup-api-docs-AAAAmmdd-HHMMSS` dentro do backend.

## Recriar a API

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
docker compose build api
docker compose up -d api
docker compose logs --since 2m api
```

## Validar

```powershell
Invoke-RestMethod "http://127.0.0.1:8787/health/"
Invoke-RestMethod "http://127.0.0.1:8787/health/crypto"
```

Abra:

```text
http://127.0.0.1:8787/docs
http://127.0.0.1:8787/redoc
```

## Resultado da validação local

- compilação Python: aprovada;
- OpenAPI 3.1: gerado e inspecionado;
- Bearer security scheme: presente;
- rotas públicas de saúde: sem autenticação;
- rotas de negócio: protegidas pelo FirebaseIDToken;
- testes: **36 de 36 aprovados**.
