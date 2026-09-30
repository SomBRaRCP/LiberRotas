# Migração do LiberRotas para o SSD

Concluída em 30/09/2026. A pasta operacional é:

```text
E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3
```

## Ajustes realizados

- Recuperados do HD 86 arquivos que não tinham sido copiados: código-fonte, testes e scripts do aplicativo, incluindo alterações locais ainda não commitadas. Os arquivos existentes no SSD foram preservados.
- Atualizados os caminhos dos guias de operação. Os dois scripts antigos de atualização agora localizam o backend pela pasta do próprio script ou pelo parâmetro informado.
- Corrigido o destino padrão de `BACKUP_BANCO.ps1` para funcionar também no Windows PowerShell 5.1.
- Reinstaladas as dependências do aplicativo com `npm ci`, preservando `package.json` e `package-lock.json`.
- Recriado `backend_trq_bec/.venv` e reinstalado o backend em modo editável no SSD. O ambiente anterior carregava o código do HD. As versões existentes foram registradas e reaproveitadas; `google-cloud-storage` passou de 3.12.1 para 3.15.0 para atender ao mínimo 3.13 já exigido pelo `pyproject.toml`.
- Excluídos backups e ambientes Python antigos do contexto de build Docker.
- Reconstruídas as imagens da API e da Web. Todos os contêineres do projeto agora registram o workspace no E:, e as montagens do PostgreSQL e dos segredos usam o SSD. Os volumes persistentes foram preservados.

## Verificações concluídas

- Antes de iniciar o Docker, os 1.510 arquivos do banco copiado foram comparados por SHA-256: nenhuma diferença entre HD e SSD.
- Nenhum arquivo versionado permanece ausente. Nenhum caminho operacional antigo foi encontrado nos arquivos de ambiente ou nas configurações e montagens dos cinco contêineres.
- O Python importa `trq_bec` de `E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec\src`.
- Os 63 arquivos Python instalados na API em execução correspondem ao código-fonte do SSD.
- `pip check` aprovado tanto no ambiente local quanto no contêiner da API.
- Backend: 238 testes e 63 subtestes aprovados.
- Aplicativo: 45 testes aprovados, TypeScript e lint sem erros. Os testes do emulador Firestore não foram executados nesta migração.
- Sintaxe dos scripts PowerShell e configuração Docker Compose válidas.
- PostgreSQL, Redis, API e Web saudáveis; `secrets-init` encerrado com código 0.
- Web local, API local, API pública, página inicial pública e `/login` público responderam HTTP 200.
- No Chrome, o feed público carregou usando a sessão já existente, e a tela de login local carregou com o relógio sincronizado com o servidor. Novo login com senha e uso em celular físico não foram exercitados nesta validação.

## Como iniciar

Abra o Docker Desktop e aguarde o mecanismo iniciar. No PowerShell:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR_LIBERROTAS.ps1
```

O parâmetro `-ExecutionPolicy Bypass` vale apenas para esse processo. Ele não altera a política permanente do Windows.

Para verificar ou parar, execute na mesma pasta:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\STATUS_LIBERROTAS.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PARAR_LIBERROTAS.ps1
```

Use `-Rebuild` no comando de inicialização após alterar o código ou as dependências. A parada normal preserva os dados; não use `docker compose down -v`.

## Backups e evidências locais

- Backup anterior à troca das montagens: `backend_trq_bec/backups/postgresql/liberrotas-20260927-195900.dump`.
- Backup após a validação final: `backend_trq_bec/backups/postgresql/liberrotas-20260930-181100.dump`, com 144.508 bytes e SHA-256 `AC244BF7B93539CA0D03539502F0557A3E983A5A7D270D0D8DB8776C8B3E64AA`.
- Ambiente Python anterior preservado em `backend_trq_bec/.venv.backup-ssd-20260927`.
- Relação dos arquivos recuperados, comparação do banco e logs em `.codex_tmp/migration-ssd-20260927/`.

Esses backups e logs locais são ignorados pelo Git. Nenhum arquivo foi apagado da cópia no HD. Passe a iniciar e editar o projeto pela pasta no E:.
