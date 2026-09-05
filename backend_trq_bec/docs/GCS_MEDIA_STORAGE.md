# Armazenamento privado de imagens no Google Cloud Storage

Este documento descreve a integração de mídia do LiberRotas com o Google Cloud
Storage (GCS). Ele separa claramente o que pertence ao código da aplicação do que
exige uma ação administrativa manual no Google Cloud.

Nenhum comando deste documento é executado automaticamente. O repositório não
cria bucket, service account, chave, política IAM, CORS ou regra de Lifecycle.

> Estado do workspace em 28/07/2026: o provider GCS está habilitado na
> configuração operacional e é usado por publicações e mensagens privadas. Os
> identificadores do projeto, bucket e credencial permanecem somente nos
> arquivos locais protegidos e não são reproduzidos nesta documentação.

## Objetivo e limites da primeira fase

A primeira fase aceita somente imagens:

- JPEG (`image/jpeg`);
- PNG (`image/png`);
- WebP (`image/webp`);
- no máximo 5 MiB por arquivo, configurável;
- sem SVG, PDF, vídeo, HTML, arquivo compactado ou executável.

Os arquivos reais ficam no bucket privado. O PostgreSQL guarda somente metadados,
estado, propriedade, integridade e referência ao objeto. O frontend nunca recebe
credencial Google, chave de service account ou permissão administrativa.

Não grave imagens em:

- `bytea`, Base64 ou blob no PostgreSQL;
- Firestore ou Firebase Realtime Database;
- volume permanente da API;
- imagem Docker;
- repositório Git;
- bundle Expo.

## Arquitetura

```text
Web ou Expo
    |
    | 1. Firebase ID Token + categoria + metadados declarados
    v
API FastAPI / TRQ-BEC
    |
    | 2. valida conta, papel, permissão, entidade, MIME e tamanho
    | 3. cria media_asset pendente no PostgreSQL
    | 4. gera URL V4 curta para um único objeto e método PUT
    v
Bucket GCS privado
    |
    | 5. cliente envia os bytes diretamente
    v
API FastAPI / TRQ-BEC
    |
    | 6. confirma existência e metadados reais
    | 7. valida assinatura mágica e decodifica a imagem
    | 8. remove metadados sensíveis no processamento
    | 9. vincula media_id à entidade e registra auditoria
    v
Feed recebe uma referência estável, nunca a URL assinada permanente
```

A API não recebe o corpo completo no pedido público normal de upload. Na
confirmação, o backend pode ler o objeto já armazenado para validar conteúdo,
dimensões e integridade.

Uma URL assinada é uma credencial temporária de portador: quem a possuir poderá
usá-la enquanto estiver válida. Portanto:

- validade curta, padrão de 600 segundos;
- método e `Content-Type` fazem parte da assinatura;
- chave do objeto é gerada pelo backend;
- upload deve usar precondição de geração para impedir sobrescrita;
- URL completa nunca entra em log, banco, Firestore ou ledger;
- resposta com a URL usa `Cache-Control: no-store`.

## Fronteira do provider

O código deve depender de uma interface, não diretamente do SDK:

```text
StorageProvider
  create_upload_url()
  create_download_url()
  get_metadata()
  download_bytes()
  replace_object()
  delete_object()
```

Implementações previstas:

- `GoogleCloudStorageProvider`: produção e integração local;
- `FakeStorageProvider`: testes sem rede e sem bucket;
- provider desativado: inicialização normal com GCS desligado.

Não é necessário adicionar MinIO, S3 ou R2 agora. A interface apenas mantém essa
evolução possível.

## Organização dos objetos

Nomes originais nunca são usados como chave. O backend gera UUID e extensão já
validada. Campos enviados pelo cliente não podem inserir `/`, `\`, `..` ou
qualquer prefixo arbitrário.

Estrutura efetivamente gerada nesta fase:

```text
media/{entity_type}/{hash_do_proprietario}/{ano}/{mes}/{hash_da_entidade}/{uuid}.{ext}
```

Os hashes evitam expor UID e identificador da entidade na chave. A associação
definitiva fica no PostgreSQL e a chave nunca é escolhida pelo frontend.

## Metadados no PostgreSQL

A tabela de mídia deve registrar, no mínimo:

- `media_id`;
- `owner_user_id`;
- `entity_type` e `entity_id`;
- `media_role`;
- `bucket_name` e `object_key`;
- nome original saneado;
- MIME declarado e MIME detectado;
- tamanho declarado e tamanho real;
- checksum;
- largura e altura;
- geração e CRC32C do objeto GCS, quando disponíveis;
- estado, visibilidade e moderação;
- criação, upload, confirmação e exclusão;
- criador e responsável pela exclusão.

Estados recomendados:

```text
pending, uploaded, processing, ready, rejected, quarantined, deleted, orphaned
```

Não persista URL assinada. Para leitura de bucket privado, o backend gera outra
URL curta após autenticação e autorização.

### Variantes econômicas

A migration aditiva `migrations/020_media_variants.sql` mantém um único ativo
lógico em `media_assets` e registra em `media_variants` somente duas versões:

| Variante | Maior dimensão | Uso principal |
|---|---:|---|
| `thumbnail` | 320 px | avatar, miniatura e lista compacta |
| `display` | 1024 px | Feed e visualização normal |

As duas variantes são WebP, preservam a proporção, não ampliam artificialmente
a imagem e possuem chave, tamanho, dimensões, checksum e geração próprios. A
chave deriva do UUID criado pelo backend:

```text
.../{media_id}.jpg
.../{media_id}.thumbnail.webp
.../{media_id}.display.webp
```

Uploads novos geram as duas versões durante a confirmação. Ativos antigos sem
linhas em `media_variants` continuam sendo servidos pelo objeto principal. Essa
compatibilidade evita ler e reprocessar todo o bucket apenas para fazer backfill.

Na exclusão, o backend remove primeiro as variantes, depois o objeto principal
e, por fim, apaga os metadados derivados na mesma transação que marca o ativo
como `deleted`. Uma repetição continua segura quando algum objeto já não existe.

### Seleção e cache

```text
GET /v1/public/media/{media_id}?variant=thumbnail
GET /v1/public/media/{media_id}?variant=display
GET /v1/public/profile/{uid}/avatar?variant=thumbnail
GET /v1/public/media/entities/product/{product_id}/product_image?variant=thumbnail
GET /v1/public/media/entities/fair/{fair_id}/fair_cover?variant=display
GET /v1/public/media/entities/institution/{uid}/institution_logo?variant=display
```

Se a variante não existir, o backend usa o objeto principal. O redirecionamento
por `media_id`, que é imutável, recebe cache público de no máximo 240 segundos.
O avatar, cujo conteúdo pode mudar sem alterar a URL do perfil, recebe no máximo
60 segundos. As referências mutáveis de produto, feira e instituição usam o
mesmo limite e fazem um único `LEFT JOIN` para selecionar o ativo pronto e a
variante. Todos permanecem abaixo dos 300 segundos padrão da URL assinada.

No aplicativo, produto, capa de feira e logo institucional podem ser enviados
somente por seus proprietários autorizados. A criação da entidade é concluída
antes do upload; se a imagem falhar, o produto ou a feira continuam válidos e a
tela informa a falha sem executar rollback destrutivo.

Imagem de evento financiado não integra este lote. Esse tipo ainda não possui
papel de mídia nem requisito acadêmico confirmado; adicioná-lo agora ampliaria
contratos, autorização e modelo de dados sem necessidade comprovada.

Respostas autenticadas, autorizações de upload, erros e demais endpoints
continuam com `Cache-Control: no-store`. O aplicativo usa `memory-disk` para
mídia pública e compartilha temporariamente a resolução de URL assinada para
imagens privadas, sem persistir a assinatura no Firestore ou AsyncStorage.

Os resultados medidos e os limites de custo estão em
[`MEDIA_COST_AUDIT_2026-08-03.md`](MEDIA_COST_AUDIT_2026-08-03.md).

Campos legados como `avatar_uri` não devem ser removidos em uma primeira
migration. A transição deve aceitar leitura legada, impedir novos URLs
arbitrários e passar a preferir `media_id`.

### Migration e rollback

A migration aditiva é `migrations/012_media_assets.sql`. Ela cria a tabela,
constraints, índices e permissões iniciais sem remover tabela ou campo legado.
O comando normal da API executa migrations antes de iniciar:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
docker compose run --rm api trq-bec-migrate
```

O projeto não usa migrations automáticas de downgrade. Um rollback exige:

1. parar primeiro a versão do código que escreve `media_assets`;
2. fazer backup do PostgreSQL;
3. preservar/exportar os registros de auditoria e metadados necessários;
4. confirmar que não há imagem válida referenciada;
5. somente então remover manualmente a tabela, as três permissões de mídia e o
   registro `012_media_assets` dentro de uma transação revisada.

Esse rollback é destrutivo e não foi executado nem automatizado.

## Endpoints esperados

O padrão atual da API usa o prefixo `/v1`:

```text
POST   /v1/media/uploads
POST   /v1/media/uploads/{media_id}/confirm
GET    /v1/media/{media_id}
GET    /v1/media?entity_type=post&entity_id=...
DELETE /v1/media/{media_id}
POST   /v1/admin/media/cleanup?limit=25
```

O pedido de autorização informa somente categoria, entidade, nome original,
MIME e tamanho. O backend deriva proprietário, caminho, bucket e permissões.

A confirmação deve ser idempotente. Uma repetição compatível retorna o estado
já confirmado; uma tentativa com proprietário, objeto, geração ou metadados
incompatíveis falha fechada.

## Variáveis de ambiente

Todas seguem o prefixo existente `TRQ_BEC_`.

| Variável | Padrão seguro | Finalidade |
|---|---:|---|
| `TRQ_BEC_GCS_ENABLED` | `false` | Liga o provider GCS |
| `TRQ_BEC_GCS_PROJECT_ID` | vazio | Projeto que contém o bucket |
| `TRQ_BEC_GCS_BUCKET_NAME` | vazio | Nome do bucket privado |
| `TRQ_BEC_GCS_CREDENTIALS_FILE` | `/run/secrets/gcs-service-account.json` | Credencial montada somente na API |
| `TRQ_BEC_GCS_CREDENTIALS_JSON` | vazio | Injeção por gerenciador externo; não usar no `.env` |
| `TRQ_BEC_GCS_SIGNED_URL_EXPIRATION_SECONDS` | `600` | Validade da URL temporária |
| `TRQ_BEC_GCS_DOWNLOAD_URL_EXPIRATION_SECONDS` | `300` | Validade da URL privada de leitura |
| `TRQ_BEC_GCS_UPLOAD_MAX_SIZE_BYTES` | `5242880` | Limite declarado e real |
| `TRQ_BEC_GCS_PUBLIC_MEDIA_BASE_URL` | vazio | Reserva para CDN processada futura |
| `TRQ_BEC_GCS_ALLOWED_IMAGE_TYPES` | `image/jpeg,image/png,image/webp` | Lista fechada de MIME |
| `TRQ_BEC_MEDIA_PENDING_EXPIRATION_SECONDS` | `86400` | Expiração lógica no banco |
| `TRQ_BEC_MEDIA_ORPHAN_RETENTION_SECONDS` | `604800` | Prazo antes da remoção física de órfãos revisáveis |
| `TRQ_BEC_MEDIA_MAX_PENDING_PER_USER` | `10` | Proteção contra acúmulo |
| `TRQ_BEC_MEDIA_MAX_AVATAR_IMAGES` | `1` | Avatar ativo |
| `TRQ_BEC_MEDIA_MAX_LOGO_IMAGES` | `1` | Logo ativa |
| `TRQ_BEC_MEDIA_MAX_PRODUCT_IMAGES` | `10` | Limite por produto |
| `TRQ_BEC_MEDIA_MAX_POST_IMAGES` | `8` | Limite por publicação |
| `TRQ_BEC_MEDIA_MAX_FAIR_COVER_IMAGES` | `1` | Capa principal da feira |
| `TRQ_BEC_MEDIA_IMAGE_MAX_PIXELS` | `40000000` | Proteção contra bomba de descompressão |
| `TRQ_BEC_MEDIA_IMAGE_MAX_DIMENSION` | `4096` | Maior largura ou altura processada |

Regras obrigatórias:

1. com `TRQ_BEC_GCS_ENABLED=false`, bucket e credencial não são exigidos;
2. com GCS ligado, configuração incompleta falha na inicialização;
3. arquivo e JSON não podem ser configurados simultaneamente;
4. produção deve preferir arquivo montado ou identidade sem chave;
5. JSON inline deve ser tratado como segredo e jamais aparecer em validação,
   representação, log ou exceção;
6. nenhuma variável `EXPO_PUBLIC_*` recebe configuração privada GCS.

O arquivo operacional `.env.backend` é local e ignorado pelo Git. O exemplo
`.env.backend.example` contém somente valores vazios ou caminhos sem segredo.

## Dependências

O `pyproject.toml` declara somente bibliotecas mantidas para esta camada:

- `google-cloud-storage>=3.13,<4`, SDK oficial do provider;
- `Pillow>=12.3,<13`, validação, orientação, remoção de metadados e regravação.

O rebuild da API instala essas versões dentro da imagem Docker. Para atualizar a
`.venv` local, execute na pasta `backend_trq_bec` quando o acesso ao índice de
pacotes estiver disponível:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

## Montagem segura no Docker

No desenvolvimento local, a origem esperada é:

```text
backend_trq_bec/secrets/gcs-service-account.json
```

O serviço `secrets-init`:

1. monta `./secrets` como somente leitura;
2. copia apenas nomes explicitamente permitidos;
3. troca o proprietário para UID/GID `10001`;
4. aplica modo `600`;
5. remove do volume uma credencial antiga quando o arquivo de origem não existe.

O volume `trq_bec_secrets` é montado em `/run/secrets` somente na API. O
container web não recebe esse volume. O diretório `secrets/` também é excluído
do contexto de build e ignorado pelo Git.

Nunca abra, imprima ou faça `Get-Content` da chave para validar a montagem.
Confira somente metadados:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
docker compose exec api stat -c "%a %u:%g %n" /run/secrets/gcs-service-account.json
```

Resultado esperado:

```text
600 10001:10001 /run/secrets/gcs-service-account.json
```

## Preparação manual no Google Cloud

As etapas desta seção alteram recursos externos. Revise projeto, região, custo e
políticas da organização antes de executá-las.

### 1. Definir os identificadores no PowerShell

Use valores reais somente no seu terminal administrativo:

```powershell
$ProjectId = "SEU_PROJECT_ID"
$Bucket = "NOME_GLOBALMENTE_UNICO_DO_BUCKET"
$Region = "southamerica-east1"
$ServiceAccountName = "liberrotas-media"
$ServiceAccount = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"
```

### 2. Criar o bucket privado

Exemplo para revisão manual:

```powershell
gcloud config set project $ProjectId
gcloud storage buckets create "gs://$Bucket" `
  --project=$ProjectId `
  --location=$Region `
  --default-storage-class=STANDARD `
  --uniform-bucket-level-access `
  --public-access-prevention
```

Confirme no Console:

- Public Access Prevention aplicada;
- Uniform Bucket-Level Access ativa;
- nenhuma associação `allUsers`;
- nenhuma associação `allAuthenticatedUsers`;
- sem ACL pública.

Uniform Bucket-Level Access simplifica a política e desativa ACL por objeto. Em
um bucket existente, revise dependências antes: depois de 90 dias contínuos a
opção não pode mais ser desativada.

### 3. Criar uma service account exclusiva

Não reutilize uma conta Firebase Admin ampla:

```powershell
gcloud iam service-accounts create $ServiceAccountName `
  --project=$ProjectId `
  --display-name="LiberRotas Media Storage"
```

### 4. Conceder IAM mínimo

A identidade da aplicação precisa, conforme as funções habilitadas:

- `storage.objects.create`;
- `storage.objects.get`;
- `storage.objects.delete`;
- acesso a metadados do objeto;
- `storage.objects.list` apenas se a rotina administrativa realmente listar.

Uma opção prática inicial, restrita ao bucket, é `roles/storage.objectUser`:

```powershell
gcloud storage buckets add-iam-policy-binding "gs://$Bucket" `
  --member="serviceAccount:$ServiceAccount" `
  --role="roles/storage.objectUser"
```

Para privilégio ainda menor, crie um papel personalizado somente com as
permissões efetivamente usadas. Não conceda `Owner`, `Editor` ou
`roles/storage.admin` à aplicação.

A identidade humana que configura CORS, Lifecycle e IAM é separada da identidade
da API. A aplicação não precisa alterar a configuração do bucket.

### 5. Assinatura de URL

Há duas estratégias:

1. chave JSON local: o SDK assina com a chave privada montada;
2. ambiente gerenciado sem chave: a identidade chama `signBlob`.

Na segunda estratégia, o chamador precisa de
`iam.serviceAccounts.signBlob`, normalmente fornecida por
`roles/iam.serviceAccountTokenCreator` na service account assinante. Esse papel
não substitui as permissões de objeto no bucket.

Para o laboratório Docker local, gere a chave apenas quando necessário e
transfira-a diretamente para a pasta ignorada:

```powershell
$TemporaryKey = Join-Path $env:TEMP "liberrotas-gcs-key.json"
gcloud iam service-accounts keys create $TemporaryKey `
  --iam-account=$ServiceAccount `
  --project=$ProjectId

Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
New-Item -ItemType Directory -Force ".\secrets" | Out-Null
Copy-Item -LiteralPath $TemporaryKey `
  -Destination ".\secrets\gcs-service-account.json"
Remove-Item -LiteralPath $TemporaryKey
```

Não cole a chave em chat, issue, commit, `.env`, CI log ou variável
`EXPO_PUBLIC_*`. Em produção, prefira Workload Identity ou mecanismo equivalente
sem chave permanente.

## CORS do bucket

O upload Web vai diretamente para o endpoint XML do GCS e, portanto, precisa do
CORS do bucket. Isso é independente do middleware CORS da API FastAPI.

O arquivo [`../config/gcs-cors.example.json`](../config/gcs-cors.example.json)
permite somente:

- `https://app.liberrotas.com.br`;
- as origens locais `8081` e `8082` já utilizadas pelo projeto;
- métodos `GET`, `HEAD` e `PUT`;
- headers necessários para upload e leitura de metadados;
- sem curinga `*`.

Revise antes de aplicar:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
Get-Content -LiteralPath ".\config\gcs-cors.example.json"
```

Aplicação manual:

```powershell
gcloud storage buckets update "gs://$Bucket" `
  --cors-file=".\config\gcs-cors.example.json"
```

Verificação:

```powershell
gcloud storage buckets describe "gs://$Bucket" `
  --format="default(cors_config)"
```

Não adicione outro domínio sem confirmar a origem exata exibida no navegador.

## Lifecycle e objetos órfãos

O banco expira uploads pendentes após 24 horas. A regra GCS é uma segunda
barreira, não substitui a reconciliação do PostgreSQL.

O arquivo
[`../config/gcs-lifecycle.example.json`](../config/gcs-lifecycle.example.json)
é um modelo conservador para uma fase futura com prefixos temporários
`pending/` e `quarantine/`. A implementação atual usa o prefixo `media/`;
portanto, essa regra não remove objetos atuais. Não troque o prefixo por
`media/`, pois isso também alcançaria imagens válidas. Nesta fase, execute a
limpeza autenticada e auditada pelo endpoint administrativo. Na primeira
execução, pendências vencidas passam para `orphaned`; depois do prazo de
retenção configurado, o objeto é removido e o registro preservado como
`deleted`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8787/v1/admin/media/cleanup?limit=25" `
  -Headers $Headers
```

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
Get-Content -LiteralPath ".\config\gcs-lifecycle.example.json"

gcloud storage buckets update "gs://$Bucket" `
  --lifecycle-file=".\config\gcs-lifecycle.example.json"

gcloud storage buckets describe "gs://$Bucket" `
  --format="default(lifecycle_config)"
```

Lifecycle é assíncrono. A aplicação não deve presumir exclusão imediata. Não use
regra `age: 0`, não aplique prefixo vazio e não remova originais confirmados sem
política de retenção aprovada.

## Configuração local

Copie o exemplo somente se o arquivo operacional ainda não existir:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
if (-not (Test-Path -LiteralPath ".env.backend")) {
  Copy-Item -LiteralPath ".env.backend.example" -Destination ".env.backend"
}
```

Primeiro mantenha:

```env
TRQ_BEC_GCS_ENABLED=false
```

Depois de bucket, IAM e credencial estarem prontos, preencha no arquivo local:

```env
TRQ_BEC_GCS_ENABLED=true
TRQ_BEC_GCS_PROJECT_ID=SEU_PROJECT_ID
TRQ_BEC_GCS_BUCKET_NAME=SEU_BUCKET
TRQ_BEC_GCS_CREDENTIALS_FILE=/run/secrets/gcs-service-account.json
TRQ_BEC_GCS_CREDENTIALS_JSON=
```

Para listar somente os nomes configurados, sem imprimir valores:

```powershell
Get-Content -LiteralPath ".env.backend" |
  Where-Object { $_ -match '^TRQ_BEC_(GCS|MEDIA)_[A-Z0-9_]+=' } |
  ForEach-Object { ($_ -split '=', 2)[0] }
```

## Rebuild e validação local

Da raiz do workspace:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3"
.\INICIAR_LIBERROTAS.ps1 -Rebuild
```

O comando preserva o PostgreSQL em `database/postgres` e o volume Redis. Nunca use:

```text
docker compose down -v
```

Verifique:

```powershell
.\STATUS_LIBERROTAS.ps1
Invoke-RestMethod "http://127.0.0.1:8787/health/"
```

O health de mídia deve expor somente provider, habilitação, configuração e
estado resumido. Não deve retornar projeto, bucket, e-mail, caminho, JSON de
credencial ou mensagem bruta do SDK.

## Testes

Os testes automatizados não devem exigir bucket real. Use o
`FakeStorageProvider` para:

- autorização e propriedade;
- MIME e tamanho;
- path traversal;
- expiração da URL;
- confirmação ausente, divergente e repetida;
- exclusão própria, cruzada e administrativa;
- conta suspensa;
- GCS desabilitado ou incompleto;
- falha simulada do provider;
- limpeza de pendência;
- ausência de segredo e URL completa em logs.

Comandos locais:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m compileall -q src tests
```

Frontend:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app"
npm run lint
npx tsc --noEmit
npx expo install --check
```

## Teste manual do fluxo

Use uma imagem não sensível de até 5 MiB. Guarde o Firebase ID Token apenas em
variável temporária da sessão:

```powershell
$Headers = @{
  Authorization = "Bearer $env:FIREBASE_ID_TOKEN"
  "X-Request-ID" = [guid]::NewGuid().ToString()
}
```

Solicite autorização pelo endpoint implementado, envie com `PUT` e confirme.
Não imprima `$Authorization.upload_url` nem grave a resposta em arquivo:

```powershell
$Body = @{
  entity_type = "post"
  entity_id = $null
  media_role = "post_image"
  original_filename = "imagem-teste.jpg"
  content_type = "image/jpeg"
  size_bytes = (Get-Item -LiteralPath ".\imagem-teste.jpg").Length
  client_request_id = [guid]::NewGuid().ToString()
} | ConvertTo-Json

$Authorization = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8787/v1/media/uploads" `
  -Headers $Headers `
  -ContentType "application/json" `
  -Body $Body

$UploadHeaders = @{}
$Authorization.required_headers.PSObject.Properties |
  ForEach-Object { $UploadHeaders[$_.Name] = [string]$_.Value }

Invoke-WebRequest `
  -Method Put `
  -Uri $Authorization.upload_url `
  -Headers $UploadHeaders `
  -InFile ".\imagem-teste.jpg" | Out-Null

$Media = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8787/v1/media/uploads/$($Authorization.media_id)/confirm" `
  -Headers $Headers

$PostBody = @{
  text = "Publicação de teste com imagem"
  media = @{
    type = "image"
    media_id = $Media.media_id
  }
} | ConvertTo-Json -Depth 3

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8787/v1/community/posts" `
  -Headers $Headers `
  -ContentType "application/json" `
  -Body $PostBody

Remove-Variable UploadHeaders, Media, PostBody
Remove-Variable Authorization
```

Em Expo Web, repita em `http://127.0.0.1:8082` para validar o preflight. Em
Android/iOS, teste seleção, rede interrompida, URL expirada e nova tentativa.

## Validação de imagem

O frontend faz validação amigável, mas a segurança final pertence ao backend.

Antes da URL:

- conta ativa e autorizada;
- entidade existente e pertencente ao usuário;
- papel de mídia permitido;
- nome sem traversal;
- MIME na lista fechada;
- tamanho entre 1 byte e o limite;
- limite pendente e limite por entidade.

Depois do upload:

- objeto existe no bucket e chave esperados;
- tamanho real não supera o limite;
- MIME armazenado corresponde;
- assinatura mágica é JPEG, PNG ou WebP;
- Pillow consegue decodificar;
- limites de pixels e dimensões evitam bomba de descompressão;
- orientação é corrigida;
- EXIF e GPS são removidos;
- versão processada é regravada sem metadados privados;
- checksum e geração são persistidos;
- associação e auditoria são atualizadas.

Não use somente extensão, nome original ou `Content-Type` informado pelo cliente.

## Auditoria TRQ-BEC

Registre eventos com identificadores e resultados seguros:

```text
MEDIA_UPLOAD_REQUESTED
MEDIA_UPLOAD_URL_ISSUED
MEDIA_UPLOAD_CONFIRMED
MEDIA_UPLOAD_REJECTED
MEDIA_PROCESSING_STARTED
MEDIA_PROCESSING_COMPLETED
MEDIA_QUARANTINED
MEDIA_DELETED
MEDIA_RESTORED
MEDIA_ACCESS_DENIED
MEDIA_ADMIN_ACTION
MEDIA_ORPHAN_CLEANUP
```

Podem constar `media_id`, usuário pseudonimizado, papel, entidade, chave do
objeto, resultado, motivo e transição de estado. Não podem constar URL assinada,
token, credencial, chave privada, conteúdo de imagem ou segredo.

## Troubleshooting

### Backend inicia com GCS desligado

É o comportamento esperado. Confirme apenas:

```env
TRQ_BEC_GCS_ENABLED=false
```

### Configuração incompleta

Com GCS ligado, projeto, bucket e uma fonte de credencial válida são
obrigatórios. Não preencha valores fictícios em produção.

### Arquivo não aparece no container

Confira nome e metadados, sem abrir o conteúdo:

```powershell
Test-Path -LiteralPath ".\secrets\gcs-service-account.json"
docker compose run --rm secrets-init
docker compose exec api stat -c "%a %u:%g %n" /run/secrets/gcs-service-account.json
```

### `403 Forbidden`

Verifique:

- projeto e bucket corretos;
- IAM concedido no bucket à service account correta;
- permissão de objeto necessária;
- assinatura feita pela identidade esperada;
- relógio do host sincronizado;
- `Content-Type` idêntico ao assinado.

Não copie a mensagem completa do SDK se ela contiver identificadores internos.

### Preflight ou CORS no navegador

Confirme a origem exata, inclusive protocolo e porta. `localhost` e
`127.0.0.1` são origens diferentes. Confira se o upload usa o endpoint XML da
URL assinada e se o método `PUT` consta no CORS do bucket.

### `412 Precondition Failed`

O objeto já existe ou a geração esperada mudou. Não sobrescreva. Gere outro UUID
e outra autorização.

### Imagem rejeitada após upload

Isso pode indicar tamanho real divergente, MIME incompatível, assinatura mágica
inválida, imagem corrompida ou dimensões excessivas. O objeto deve ser removido
ou movido para quarentena e o motivo seguro deve ser auditado.

### Logs seguros

Consulte somente linhas que não contenham assinatura ou material privado:

```powershell
docker compose logs api --tail 200 |
  Select-String -NotMatch 'X-Goog-Signature|private_key|credentials'
```

O filtro é uma defesa adicional; o código não deve registrar esses dados.

## Rotação de credencial

1. crie uma nova chave ou identidade;
2. coloque o novo arquivo na pasta ignorada;
3. execute rebuild/restart apenas da pilha autorizada;
4. valide health, upload, confirmação, leitura e exclusão;
5. revogue a chave antiga no IAM;
6. confirme que a antiga não autentica;
7. registre a rotação sem registrar chave, JSON ou URL.

Mantenha no máximo as chaves necessárias. Prefira identidade sem chave em
ambiente gerenciado.

## Resposta a vazamento

Se uma chave JSON for exposta:

1. desative ou exclua imediatamente a chave comprometida;
2. gere uma identidade substituta com IAM mínimo;
3. revise Cloud Audit Logs e objetos alterados;
4. procure o segredo no histórico Git, artefatos, CI, logs e backups;
5. remova cópias locais desnecessárias;
6. altere o fluxo para identidade sem chave quando possível;
7. documente o incidente sem reproduzir o segredo.

Se uma URL assinada vazar, ela permanece utilizável até expirar. A validade curta
reduz o impacto. Para upload, elimine a pendência e o objeto; para leitura,
remova ou troque a geração/chave do objeto quando a política permitir.

## Exclusão e retenção

Exclusão de mídia deve:

- validar proprietário e permissão;
- marcar `deleted` no PostgreSQL;
- remover com precondição de geração ou agendar remoção;
- preservar referências exigidas pelo ledger;
- registrar auditoria;
- não apagar mídia de outro usuário.

Soft Delete, Object Versioning e políticas de retenção têm custo e efeito
operacional. Decida-os antes do piloto. Não aplique regra destrutiva sem backup,
simulação e aprovação.

## Referências oficiais

- [URLs assinadas V4](https://cloud.google.com/storage/docs/access-control/signing-urls-with-helpers)
- [CORS no Cloud Storage](https://cloud.google.com/storage/docs/configuring-cors)
- [Uniform Bucket-Level Access](https://cloud.google.com/storage/docs/uniform-bucket-level-access)
- [Precondições de geração](https://cloud.google.com/storage/docs/request-preconditions)
- [Object Lifecycle Management](https://cloud.google.com/storage/docs/lifecycle)
- [SDK oficial Python](https://cloud.google.com/python/docs/reference/storage/latest)

## Estado e garantias atuais

- novos uploads aceitam somente JPEG, PNG ou WebP de até 5 MiB;
- o frontend não recebe credencial Google nem acesso administrativo;
- PostgreSQL armazena metadados e propriedade, nunca os bytes da imagem;
- o contêiner Web não recebe o volume de segredos;
- publicações e mensagens usam referências de mídia autorizadas pelo backend;
- URLs de leitura são temporárias e dependem da autorização da entidade;
- nenhuma imagem ou credencial deve ser adicionada ao Git;
- CORS, IAM, Lifecycle, faturamento e rotação da service account continuam sendo
  responsabilidades operacionais externas ao código;
- não presuma que a configuração atual vale em outro ambiente: execute os testes
  de autorização, upload, confirmação, download e exclusão antes do deploy.
