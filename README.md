# LiberRotas + TRQ-BEC — produção Web e instalação no Windows

Workspace acadêmico que reúne o aplicativo **LiberRotas**, evoluído a partir do protótipo FeiTUR, e o backend experimental de segurança **TRQ-BEC**.

> Este guia foi escrito para **Windows 10/11 com PowerShell**. Todos os comandos abaixo devem ser executados no PowerShell. O Docker Desktop utiliza contêineres Linux internamente, mas não é necessário trocar o terminal para Linux.

> O TRQ-BEC `0.6.0-alpha.1` é experimental. Ele não é uma implementação pronta para produção, não possui certificação FIPS e o provider pós-quântico continua bloqueado até existir uma implementação auditada.

## Estado desta instalação

Estado consolidado em **04/09/2026**. Consulte o [registro da retomada](backend_trq_bec/docs/RETOMADA_2026-09-04.md) para evidências e pendências. Probes históricos estão identificados abaixo:

- Node.js `24.19.0` e npm `11.17.0` encontrados;
- dependências do aplicativo instaladas em `mobile_app\node_modules`;
- TypeScript e ESLint aprovados;
- Expo `57.0.20`/SDK 57, React Native `0.86.3` e React `19.2.3` alinhados; `expo install --check` e Expo Doctor `21/21` aprovados;
- `npm audit --omit=dev` registrou `3` vulnerabilidades moderadas e `0` altas ou críticas na árvore de produção; a cadeia é transitiva do `expo-router` e não deve ser corrigida com `--force` enquanto não houver solução compatível upstream;
- exportação Web gerada com as rotas públicas e os painéis protegidos;
- Python `3.13.5` encontrado;
- ambiente virtual criado em `backend_trq_bec\.venv`;
- dependências do backend e de testes instaladas;
- suíte completa do backend aprovada com `197 testes` e `63 subtestes`;
- suíte do aplicativo aprovada com `44 testes`, TypeScript e ESLint;
- regras do Firestore aprovadas separadamente pelo emulador local com `npm run test:firestore`; essa suíte não entra na contagem dos 44 testes Vitest;
- contrato OpenAPI confirmado com `94` caminhos e `106` operações;
- Docker Desktop ativo, com Engine `29.7.2` e Compose `5.3.1` no momento da validação; essas versões podem mudar por atualização automática;
- PostgreSQL 16, Redis 7 e API FastAPI executando em contêineres Docker ativos e saudáveis;
- chaves locais de laboratório geradas em `backend_trq_bec\secrets`;
- imagem Docker da API construída com sucesso;
- volume interno de segredos validado com modo `600` e proprietário `10001`;
- aplicativo configurado em modo acadêmico local por `mobile_app\.env.local`;
- migrations `001_initial` até `021_institution_live_fairs` confirmadas no PostgreSQL operacional;
- fluxo de imagens ativo com Google Cloud Storage privado, formatos JPEG/PNG/WebP, limite de 5 MB e metadados autoritativos no PostgreSQL;
- probe histórico (não repetido nesta retomada) no PostgreSQL/Redis reais aprovado com `1 ALLOW`, `99 DENY`, estoque `0` e idempotência;
- probe histórico (não repetido nesta retomada) PostgreSQL de filiação e relatório institucional aprovado, incluindo propriedade do grupo, uma filiação ativa global e janelas históricas;
- API publicada somente no loopback em `http://127.0.0.1:8787`;
- site Web de produção servido por Nginx não privilegiado em `http://127.0.0.1:8081`;
- API pública respondendo em `https://api.liberrotas.com.br/health/` pelo Cloudflare Tunnel;
- site público respondendo em `https://app.liberrotas.com.br` pelo Cloudflare Tunnel.

O teste de interface com duas contas reais ainda depende de você entrar no app como empreendedor e visitante. A credencial Firebase Admin permanece somente no backend e nunca deve ser enviada por chat, salva no aplicativo ou publicada no Git.

Para abrir a IDE, use `LiberRotas.code-workspace`. A tarefa **LiberRotas: validacao completa**, em **Terminal > Executar Tarefa**, inclui backend, TypeScript, ESLint, testes do app e regras Firestore. O emulador exige JDK 21.

As permissões dos três arquivos de ambiente foram restringidas ao usuário atual, Administradores e SYSTEM. Para reaplicar após recriar esses arquivos, execute `./scripts/proteger-ambiente-local.ps1` na raiz; o script salva as ACLs anteriores em `backend_trq_bec/backups/windows-acl`, sem copiar valores de configuração.

A preparação de APK/AAB está em [BUILD_MOBILE.md](mobile_app/BUILD_MOBILE.md). Faltam login/vínculo EAS, assinatura e homologação física. A auditoria completa de dependências de desenvolvimento também possui alertas moderados; veja o [registro da retomada](backend_trq_bec/docs/RETOMADA_2026-09-04.md).

## Componentes do workspace

```text
LiberRotas_TRQ_BEC_Workspace_v3/
├── mobile_app/       aplicativo LiberRotas 1.1.0 — Expo 57.0.20/SDK 57 e React Native 0.86.3
├── backend_trq_bec/  backend TRQ-BEC 0.6.0-alpha.1 — FastAPI, PostgreSQL e Redis
├── archive/          wheels e backups históricos, fora do build atual
├── scripts/          automação da entrega acadêmica reproduzível
├── INICIAR_LIBERROTAS.ps1  inicia e verifica a pilha de produção
├── STATUS_LIBERROTAS.ps1   mostra serviços, healthchecks e testes HTTP
├── PARAR_LIBERROTAS.ps1    para sem excluir volumes ou dados
└── README.md         este guia
```

Não existe `package.json` na raiz. Portanto:

- comandos `npm` e `npx expo` devem ser executados em `mobile_app`;
- comandos Python e Docker devem ser executados em `backend_trq_bec`.

O wheel histórico `0.5.0a1` foi preservado em `archive/packages/v0.5.0a1` e não deve ser instalado sobre o ambiente atual. O build oficial é gerado em `backend_trq_bec\dist` a partir do `pyproject.toml` `0.6.0a1`. Para executar a pilha completa, use `backend_trq_bec`, pois as migrações do PostgreSQL ficam nessa pasta.

## Tecnologias e dados utilizados

| Camada | Tecnologia | Uso |
| --- | --- | --- |
| Aplicativo | Expo 57.0.20/SDK 57, React 19.2.3, React Native 0.86.3 e TypeScript 6 | telas, navegação, câmera, QR Code e armazenamento local |
| Firebase no aplicativo | Firebase Web SDK, Authentication e Firestore | login/cadastro e sincronização de dados públicos |
| Backend | Python 3.11+, FastAPI e Uvicorn | API protegida do TRQ-BEC |
| Firebase no backend | Firebase Admin SDK | validação do ID token e das Custom Claims assinadas |
| Dados autoritativos | PostgreSQL 16 | funções, status, permissões, comerciantes, produtos, estoque, ofertas, operações, resgates e ledger |
| Estado temporário | Redis 7 | desafio, replay, idempotência e limite efetivo de tentativas |
| Arquivos de imagem | Google Cloud Storage privado | bytes de JPEG, PNG e WebP; PostgreSQL recebe somente metadados e referências |

Este projeto **não usa Firebase Realtime Database**. O aplicativo usa Firestore; o backend usa PostgreSQL e Redis. Firebase Admin nunca deve ser colocado no aplicativo.

## Modo de execução da Fase 1

A operação comercial usa obrigatoriamente o backend, PostgreSQL, Redis, Firebase Authentication e Firebase Admin. O app apenas coleta comandos e exibe a resposta autoritativa. Não existe emissão ou resgate comercial final offline.

```env
EXPO_PUBLIC_TRQ_BEC_API_URL=https://api.liberrotas.com.br
EXPO_PUBLIC_TRQ_BEC_ALLOW_LEGACY_DEMO=false
```

O modo legado deve permanecer `false`. O fluxo protegido funciona nas duas plataformas, com identidades diferentes:

| Plataforma | Identidade de dispositivo |
|---|---|
| Web | par Ed25519 criado pelo WebCrypto; a chave privada é um `CryptoKey` não exportável persistido no IndexedDB |
| Android/iOS | seed Ed25519 protegida pelo `expo-secure-store`, separada por Firebase UID |

Na Web, abra o sistema por `https://app.liberrotas.com.br` ou, no laboratório deste PC, por `http://127.0.0.1`. Não use HTTP por IP da rede local. O cadastro de toda identidade nova exige que o login Firebase tenha ocorrido há no máximo 5 minutos. Para visitante, cada dispositivo fica imediatamente `ACTIVE` e recebe apenas um alerta. Para empreendedor e instituição, todo novo dispositivo, inclusive o primeiro, fica `PENDING_APPROVAL` por 10 minutos e depois é promovido automaticamente para `ACTIVE` pelo backend.

A identidade Web pertence à origem completa do navegador — protocolo, host e porta. Portanto, `https://app.liberrotas.com.br`, `http://127.0.0.1:8081` e `http://127.0.0.1:8082` criam identidades diferentes. Ao cadastrar uma identidade nova de visitante, empreendedor ou instituição, o backend envia um alerta ao e-mail registrado no Firebase. Se foi o próprio usuário, basta desconsiderar. O botão **Não fui eu!** abre `/account/devices`, onde é possível revisar os aparelhos e alterar a senha; a troca desconecta todas as sessões. O e-mail não autoriza o aparelho e não contém token de aprovação.

Limpar os dados do site ou apagar o IndexedDB perde a chave local, mas não apaga o registro autoritativo do dispositivo. A chave Web não exportável reduz a exposição acidental, mas não impede que um XSS na mesma origem peça assinaturas enquanto a página estiver aberta. Este continua sendo um perfil de laboratório, sem atestação de hardware.

## Pré-requisitos no Windows

### Para o aplicativo

- Windows 10 ou 11 de 64 bits;
- conexão com internet para instalar pacotes, acessar Firebase e obter o Expo Go;
- Node.js em uma faixa aceita pelo SDK 57; neste PC foi validado `24.19.0`;
- npm;
- celular Android na mesma rede do computador ou navegador para o teste Web;
- Expo Go compatível com o SDK 57 para teste em celular;
- acesso ao projeto Firebase usado pelo aplicativo.

O SDK 57 suporta Android 7 ou superior. Para compilar nativamente no Android, são necessários Android Studio, Android SDK 36, JDK 17 ou superior e `adb`. Isso é opcional quando o teste é feito com Expo Go em um celular físico. A suíte local das regras Firestore usa o emulador atual do Firebase e exige JDK 21.

No Windows não existe simulador iOS. O teste de iOS exige um iPhone físico ou uma compilação remota. Além disso, a loja do iPhone oferece somente o Expo Go do SDK mais recente; para um SDK anterior, pode ser necessário atualizar o projeto ou usar uma development build.

### Para o backend completo

- Python `3.11` ou superior; Python `3.12` é a versão da imagem Docker e Python `3.13` foi validado neste PC;
- Docker Desktop com Docker Compose v2;
- virtualização habilitada e um backend compatível do Docker Desktop, normalmente WSL 2 ou Hyper-V;
- credencial privada do Firebase Admin;
- Firebase Authentication com provedor Email/Senha;
- projeto Firestore criado e regras publicadas.

Confira as ferramentas no PowerShell:

```powershell
node --version
npm --version
py --version
docker --version
docker compose version
```

Os comandos deste guia usam o caminho atual deste PC: `E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3`. Se a pasta for movida ou copiada para outro Windows, substitua esse início pelo novo caminho. A partir da raiz do workspace, também é possível entrar nos módulos com `Set-Location .\mobile_app` e `Set-Location .\backend_trq_bec`.

A migração para o SSD foi concluída e validada em 30/09/2026. Consulte o [registro da migração](backend_trq_bec/docs/MIGRACAO_SSD_2026-09-30.md) para os ajustes, verificações e localização dos backups.

## Produção Web com Docker Compose

### Arquitetura final

| Componente | Execução | Publicação no Windows | Entrada externa |
| --- | --- | --- | --- |
| Web | exportação estática do Expo servida por `nginxinc/nginx-unprivileged` na porta interna `8080` | `127.0.0.1:8081` | Cloudflare Tunnel para `app.liberrotas.com.br` |
| API TRQ-BEC | FastAPI/Uvicorn na porta interna `8787` | `127.0.0.1:8787` | Cloudflare Tunnel para `api.liberrotas.com.br` |
| PostgreSQL | contêiner `postgres:16-alpine` | nenhuma porta publicada | sem entrada externa |
| Redis | contêiner `redis:7-alpine` | nenhuma porta publicada | sem entrada externa |

Web, API, PostgreSQL e Redis pertencem ao mesmo Docker Compose em `backend_trq_bec\docker-compose.yml`. A única entrada externa permitida é o Cloudflare Tunnel. A web e a API não são publicadas em `0.0.0.0`.

Esta é uma implantação de produção da **camada Web estática** para o piloto. O backend TRQ-BEC continua explicitamente experimental e com `TRQ_BEC_ENVIRONMENT=development`: mudar apenas esse nome faria o guard de produção bloquear a inicialização, porque o provider pós-quântico aprovado ainda não existe. A arquitetura criptográfica e o comportamento fail-closed não foram alterados.

O servidor de desenvolvimento do Expo/Metro **não é servidor de produção**. Na implantação final, a porta `8081` pertence ao contêiner `web`, que entrega arquivos estáticos sem depender de Node.js ou Metro em execução.

### Variável pública usada no build

A URL da API é fixada no build de produção:

```env
EXPO_PUBLIC_TRQ_BEC_API_URL=https://api.liberrotas.com.br
```

O Compose também recebe as seis variáveis `EXPO_PUBLIC_FIREBASE_*` descritas em `mobile_app/.env.example`. `INICIAR_LIBERROTAS.ps1 -Rebuild` importa essas variáveis de `mobile_app/.env.local`. O `Dockerfile.web` usa `EXPO_NO_DOTENV=1`, recebe somente a configuração pública por argumentos de build, exclui `.env*` pelo `.dockerignore` e executa o export com `--clear`. O validador informa apenas campos ausentes, sem imprimir seus valores. Variáveis `EXPO_PUBLIC_*` entram no JavaScript do navegador e nunca podem conter senhas, tokens, conta de serviço, chave privada ou credencial administrativa.

### Comando único para iniciar

Execute na **raiz do workspace**:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3"
.\INICIAR_LIBERROTAS.ps1
```

O script verifica o Docker Desktop, valida o Compose, constrói a imagem web quando ela ainda não existe, inicia a pilha sem remover volumes, aguarda os healthchecks e testa a web e a API local.

Depois de alterar código, imagens ou dependências do frontend ou do backend, atualize as duas imagens com:

```powershell
.\INICIAR_LIBERROTAS.ps1 -Rebuild
```

### Comando único para verificar

Na raiz do workspace:

```powershell
.\STATUS_LIBERROTAS.ps1
```

O status esperado é:

- `web`, `api`, `postgres` e `redis` em execução e saudáveis;
- `secrets-init` finalizado com código `0`, pois ele é um inicializador de execução única;
- web local com HTTP `200` em `http://127.0.0.1:8081/`;
- API local com HTTP `200` em `http://127.0.0.1:8787/health/`;
- API pública com HTTP `200` em `https://api.liberrotas.com.br/health/`.

### Comando seguro para parar

Na raiz do workspace:

```powershell
.\PARAR_LIBERROTAS.ps1
```

O script usa `docker compose stop`: contêineres são parados, mas o PostgreSQL em `backend_trq_bec\database\postgres`, os volumes do Redis e de segredos e as imagens permanecem. **Nunca execute `docker compose down -v` neste projeto**, porque `-v` excluiria os volumes persistentes do Redis e dos segredos.

### Recuperação após reiniciar o Windows

1. abra o Docker Desktop e aguarde aparecer **Engine running**;
2. abra o PowerShell na raiz do workspace;
3. execute `.\INICIAR_LIBERROTAS.ps1`;
4. execute `.\STATUS_LIBERROTAS.ps1`.

A política `restart: unless-stopped` ajuda a recuperar os serviços quando o Docker reinicia. Se a pilha tiver sido parada manualmente pelo script, inicie-a novamente pelo comando acima.

### Diagnóstico do Docker Desktop e das portas

```powershell
docker info
docker compose --file .\backend_trq_bec\docker-compose.yml --project-directory .\backend_trq_bec ps
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 8081,8787
```

Se `docker info` mencionar o pipe `dockerDesktopLinuxEngine`, abra o Docker Desktop e espere o mecanismo iniciar. Em `8081` deve aparecer o encaminhamento do Docker, não `node.exe`. Em `8787` também deve aparecer somente o encaminhamento local do Docker.

Para identificar com segurança um processo que esteja ocupando uma porta antes de encerrá-lo:

```powershell
$conexao = Get-NetTCPConnection -State Listen -LocalPort 8081
Get-CimInstance Win32_Process -Filter "ProcessId = $($conexao.OwningProcess)" |
  Select-Object ProcessId, Name, CommandLine
```

Não finalize todos os processos `node.exe`: encerre somente um Expo/Metro comprovadamente iniciado por este projeto.

### Diagnóstico do Cloudflare Tunnel

O Codex não altera DNS, Tunnel nem Cloudflare Access. Para verificar sem mudar a configuração:

```powershell
Get-Service cloudflared
Resolve-DnsName api.liberrotas.com.br
Invoke-WebRequest https://api.liberrotas.com.br/health/
Resolve-DnsName app.liberrotas.com.br
```

Depois que a web local estiver saudável, ainda é necessário criar **manualmente** no túnel Cloudflare:

```text
Hostname público: app.liberrotas.com.br
Serviço local:    http://localhost:8081
```

Não altere a rota existente de `api.liberrotas.com.br` nem as proteções de `/internal/*`.

### Build e validação manual

Frontend, a partir de `mobile_app`:

```powershell
npm ci
npm run lint
npx tsc --noEmit
npx expo install --check
$env:EXPO_PUBLIC_TRQ_BEC_API_URL = "https://api.liberrotas.com.br"
npx expo export --platform web --output-dir dist --clear
Remove-Item Env:EXPO_PUBLIC_TRQ_BEC_API_URL
```

Backend e Compose, a partir de `backend_trq_bec`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
docker compose config --quiet
docker compose --env-file .env --env-file ../mobile_app/.env.local build web
docker compose ps
```

O diretório estático é `mobile_app\dist`. A imagem final copia somente esse diretório para o Nginx. HTML recebe política sem cache agressivo; recursos versionados de `/_expo/static/` e `/assets/` recebem cache longo. O Nginx mantém os MIME types, impede listagem de diretórios, adiciona headers básicos e usa fallback para navegação e refresh em rotas do Expo Router.

### Desenvolvimento local versus produção

| Situação | Comando | Porta | Observação |
| --- | --- | --- | --- |
| Produção Web | `.\INICIAR_LIBERROTAS.ps1` na raiz | `8081` | Nginx no Docker; não depende do Expo |
| Desenvolvimento Web | `npx expo start --web --port 8082` em `mobile_app` | `8082` | Metro com atualização rápida; não publicar externamente |
| Desenvolvimento Android/Expo Go | `npx expo start --port 8082` em `mobile_app` | `8082` | use a API pública HTTPS no celular físico |

## Executar o aplicativo em desenvolvimento

### Opção A — navegador no próprio computador

Abra um PowerShell na pasta do app:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app"
npx expo start --web --port 8082
```

Abra `http://127.0.0.1:8082`, mantendo a porta de produção `8081` reservada ao Docker. Nesse contexto local seguro, o fluxo TRQ-BEC protegido usa WebCrypto Ed25519 e guarda o `CryptoKey` privado não exportável no IndexedDB. A câmera continua dependente das permissões e do suporte do navegador; no Android/iOS, a identidade continua usando SecureStore.

Não alterne entre `127.0.0.1`, `localhost`, outra porta e o domínio público durante o mesmo teste: cada origem possui um IndexedDB e cria uma identidade própria. O login continuará permitido, porém cada identidade adicional aguardará o cooldown autoritativo de 10 minutos antes de participar das operações TRQ-BEC protegidas.

### Opção B — celular Android com Expo Go

Na pasta `mobile_app`, execute:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app"
npx expo start --port 8082
```

Depois:

1. instale uma versão do Expo Go compatível com o SDK 57;
2. conecte o celular e o computador à mesma rede Wi-Fi;
3. leia o QR Code mostrado pelo Expo;
4. aceite as permissões de câmera e galeria quando o app solicitar; esta versão não solicita acesso ao microfone.

Se o celular não localizar o Metro Bundler, tente:

```powershell
npx expo start --tunnel --port 8082
```

O túnel exige internet e pode solicitar a instalação de `@expo/ngrok`, que não faz parte das dependências atuais. Ele resolve o acesso ao Metro, mas não publica automaticamente a API local da porta `8787`.

Para encerrar o Metro, pressione `Ctrl + C` no mesmo terminal.

## Instalação limpa do aplicativo em outro Windows

Execute estes comandos na pasta `mobile_app`:

```powershell
Set-Location "<CAMINHO_DO_WORKSPACE>\mobile_app"
npm ci
Copy-Item .env.example .env.local
notepad .env.local
```

Configure a integração protegida com a URL do computador e mantenha o legado desativado:

```env
EXPO_PUBLIC_TRQ_BEC_API_URL=https://api.liberrotas.com.br
EXPO_PUBLIC_TRQ_BEC_ALLOW_LEGACY_DEMO=false
```

As variáveis `EXPO_PUBLIC_*` são incorporadas ao aplicativo e são públicas. Nunca coloque nelas senha, chave privada, credencial Firebase Admin, token de serviço ou segredo KMS/HSM.

Observação: a configuração atual do Firebase Web SDK ainda está centralizada em `mobile_app/src/services/firebase.ts`. Os campos Firebase existentes em `.env.example` não alteram o projeto Firebase nesta versão. Para usar outro projeto Firebase, altere a configuração em `firebase.ts` ou primeiro adapte esse arquivo para ler as variáveis de ambiente.

## Configurar o Firebase do aplicativo

O app usa **Firebase Authentication** e **Firestore** pelo Firebase Web SDK.

No Console do Firebase:

1. abra o projeto correspondente ao `projectId` configurado em `mobile_app/src/services/firebase.ts`;
2. acesse **Criação > Authentication > Sign-in method**;
3. ative o provedor **E-mail/senha**;
4. crie o banco em **Criação > Firestore Database**;
5. publique o conteúdo de `mobile_app/firestore.rules`;
6. crie uma conta pelo próprio aplicativo ou pelo painel Authentication.

As antigas contas locais de demonstração não são mais a fonte real de login. Consulte `mobile_app/FIREBASE_AUTH_SETUP.md` para o fluxo atualizado.

## Instalar o backend no Windows

### 1. Criar o ambiente Python

Execute na pasta `backend_trq_bec`:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Não é obrigatório ativar o ambiente virtual. Os comandos deste README chamam diretamente o Python existente em `.venv` para evitar dúvida sobre qual instalação está sendo usada.

Se o PowerShell bloquear a ativação e você quiser ativá-lo mesmo assim:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Essa alteração vale somente para o terminal atual.

### 2. Criar os arquivos de ambiente

Em uma instalação nova:

```powershell
Copy-Item .env.backend.example .env.backend
notepad .env
notepad .env.backend
```

O arquivo `.env` deve conter uma senha local forte escolhida por você. Como ela é interpolada diretamente em uma URL PostgreSQL, use pelo menos 24 caracteres contendo somente letras, números, ponto, hífen, sublinhado e til (`A-Z`, `a-z`, `0-9`, `.`, `-`, `_`, `~`). Evite `$`, `#`, `@`, `:`, `/`, `%`, espaços e outros caracteres que exigem codificação de URL:

```env
TRQ_BEC_POSTGRES_PASSWORD=<SUBSTITUA_POR_UMA_SENHA_LOCAL_FORTE>
```

Não copie literalmente o texto entre `< >`. O `.env` é lido pelo Docker Compose. O `.env.backend` configura o processo FastAPI dentro do contêiner.

O Compose sobrescreve `TRQ_BEC_DATABASE_URL` e `TRQ_BEC_REDIS_URL` do `.env.backend`. A senha efetiva vem de `TRQ_BEC_POSTGRES_PASSWORD` no `.env`; não tente manter uma segunda senha manual na URL do `.env.backend`.

Neste PC os dois arquivos e a pasta persistente `backend_trq_bec\database\postgres` já existem. Não altere somente a senha do `.env`, pois a senha gravada no banco não muda automaticamente. Em uma instalação nova, escolha a senha definitiva antes do primeiro `docker compose up`. Gere uma cópia lógica com `.\BACKUP_BANCO.ps1` antes de mover ou restaurar o ambiente.

### 3. Gerar os segredos de laboratório

Execute somente se a pasta `secrets` ainda não contiver as três chaves:

```powershell
.\.venv\Scripts\trq-bec-keygen.exe --output .\secrets
```

O comando não sobrescreve chaves existentes. Os arquivos esperados são:

```text
secrets/
├── issuer-ed25519.pem
├── checkpoint-ed25519.pem
└── audit-hmac.key
```

Esses arquivos são apenas para laboratório. Não envie para Git, nuvem pública, aplicativo ou chat.

### 4. Adicionar a credencial Firebase Admin

No Console do Firebase, acesse:

**Configurações do projeto > Contas de serviço > Firebase Admin SDK > Gerar nova chave privada**.

Salve o JSON fora do projeto e copie localmente com:

```powershell
Copy-Item "C:\CAMINHO_PRIVADO\service-account.json" ".\secrets\firebase-service-account.json"
```

O destino esperado é:

```text
backend_trq_bec\secrets\firebase-service-account.json
```

Nunca publique nem cole o conteúdo desse JSON. Para produção, prefira credenciais gerenciadas em vez de uma chave permanente.

### 5. Configurar o e-mail de segurança

O alerta de novo dispositivo usa SMTP somente no backend. Para a Brevo, execute o
configurador seguro na raiz do workspace:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3"
.\CONFIGURAR_EMAIL_DISPOSITIVOS.ps1
```

Informe o **login SMTP** e a **chave SMTP** da Brevo quando forem solicitados.
Não use a chave de API. A chave SMTP é digitada de forma oculta, fica fora do
`.env.backend` e não é mostrada nos logs. O script prepara o segredo no Docker,
reinicia somente a API e valida a autenticação sem enviar mensagem. Quando
aparecer `SMTP_AUTHENTICATION_OK`, volte à tela **Segurança da minha conta** e
pressione **Reenviar alerta de segurança**.

Para configurar outro provedor manualmente, abra
`backend_trq_bec\.env.backend` e informe os dados sem colocar a senha diretamente
no arquivo:

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

Na pasta `backend_trq_bec`, crie o arquivo de segredo sem escrever a senha no histórico do PowerShell:

```powershell
New-Item -ItemType Directory -Force ".\secrets" | Out-Null
notepad ".\secrets\smtp-password"
```

Salve somente a senha SMTP ou a senha de aplicativo, sem nome de variável. O `secrets-init` copia esse arquivo para `/run/secrets/smtp-password` com proprietário `10001`, modo `600`, e a API monta o volume somente para leitura. A pasta `secrets` já é ignorada pelo Git e pelo contexto de build.

Para SMTP implícito na porta `465`, use `TRQ_BEC_SMTP_SSL=true` e `TRQ_BEC_SMTP_STARTTLS=false`. Nunca habilite SSL implícito e STARTTLS ao mesmo tempo. O remetente precisa estar autorizado no provedor; para entrega pública confiável, configure também SPF, DKIM e DMARC no domínio.

O destinatário do alerta é obtido exclusivamente por `firebase_admin.auth.get_user(uid).email`. E-mail de formulário, perfil público ou corpo da requisição não é aceito como destino. Em desenvolvimento, o SMTP pode permanecer desconfigurado para testes controlados: o login não cai, o backend retorna `NOT_CONFIGURED` ou `FAILED`, nunca `SENT`, e o aparelho ainda é liberado automaticamente ao terminar os 10 minutos. Em `TRQ_BEC_ENVIRONMENT=production`, host SMTP e remetente continuam sendo requisitos de inicialização para que o aviso de segurança não seja perdido.

### 6. Iniciar Docker, banco, Redis, API e Web

Abra o Docker Desktop e aguarde o mecanismo ficar ativo. Para a pilha completa, use o script na raiz do workspace:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3"
.\INICIAR_LIBERROTAS.ps1
```

O Compose executa esta ordem:

1. inicia PostgreSQL e Redis;
2. aguarda os dois serviços ficarem saudáveis;
3. o serviço `secrets-init` copia os segredos do NTFS para um volume interno e aplica modo `600`;
4. aplica, em ordem e apenas uma vez, as migrations `001_initial.sql` até `016_community_content_management.sql`;
5. inicia a API somente em `127.0.0.1:8787`;
6. inicia a exportação Web no Nginx somente em `127.0.0.1:8081`.

Verifique a API:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/health/
Invoke-RestMethod http://127.0.0.1:8787/health/crypto
```

A documentação interativa fica em:

```text
http://127.0.0.1:8787/docs
```

Para acompanhar erros:

```powershell
docker compose logs -f api
```

Sem `firebase-service-account.json`, a API não inicia. PostgreSQL e Redis podem ser iniciados separadamente:

```powershell
docker compose up -d postgres redis
docker compose ps
```

Neste computador, API, PostgreSQL, Redis e Web são administrados pelo Compose. O inicializador de segredos encerra com código `0` depois de copiar os arquivos, o que é esperado.

## Conectar o aplicativo ao backend

O Compose de produção vincula a API somente a `127.0.0.1`. Isso impede acesso direto pela rede local, conforme o requisito de segurança. Para um celular físico com Expo Go, use a API pública HTTPS:

```env
EXPO_PUBLIC_TRQ_BEC_API_URL=https://api.liberrotas.com.br
EXPO_PUBLIC_TRQ_BEC_ALLOW_LEGACY_DEMO=false
```

Emulador padrão do Android Studio:

```env
EXPO_PUBLIC_TRQ_BEC_API_URL=https://api.liberrotas.com.br
EXPO_PUBLIC_TRQ_BEC_ALLOW_LEGACY_DEMO=false
```

Navegador de desenvolvimento no próprio PC, inclusive para prova de dispositivo Web em uma página aberta por `http://127.0.0.1`:

```env
EXPO_PUBLIC_TRQ_BEC_API_URL=http://127.0.0.1:8787
EXPO_PUBLIC_TRQ_BEC_ALLOW_LEGACY_DEMO=false
```

Não use `localhost` no celular físico: nesse caso, `localhost` aponta para o próprio celular. O arquivo real `mobile_app\.env.local` continua local e não é alterado pelo build Docker. Após mudar esse arquivo para desenvolvimento, pare e reinicie o Expo.

A porta `8787` não deve ser liberada no Firewall para outros computadores: o acesso externo ocorre exclusivamente pelo Cloudflare Tunnel.

## Autorizar contas e painéis no backend

A rota pública `/` apresenta como o LiberRotas funciona, seus benefícios e as diferenças entre Visitante, Empreendedor e Instituição. O botão **Entrar/Registrar** abre `/login`, onde a pessoa pode entrar ou seguir para o cadastro público.

Logo abaixo da explicação sobre instituições, **Registrar Instituição** abre um formulário público para Empresa ou ONG. Ele coleta organização, responsável, e-mail, localização, apresentação e contatos opcionais, exige consentimento para contato e grava somente uma solicitação na fila do Suporte. O envio não cria conta, função ou permissão. O Suporte pode registrar análise, contato ou recusa; **Aprovar e criar conta** exige autenticação recente, cria exclusivamente a função `institution` e só conclui a aprovação depois que o backend envia por SMTP o link Firebase para definição da senha no primeiro acesso.

Existe somente um fluxo público de autenticação. A tela de entrada pede apenas e-mail e senha: ela não permite escolher função. As opções **Visitante** e **Empreendedor** aparecem somente na criação de uma conta pública. **Instituição** não aparece no cadastro público e só pode ser provisionada pelos painéis autorizados de Administrador ou Suporte.

A mesma entrada atende visitantes, empreendedores, instituições e equipes autorizadas. A função real sempre vem do backend.

Depois que o Firebase autentica a conta, o aplicativo chama `GET /v1/access/me`. O backend valida o ID Token, lê a Custom Claim, consulta a função, o status e as permissões no PostgreSQL e só então devolve o painel autorizado. Uma função enviada por formulário, rota, Firestore, AsyncStorage ou JavaScript do navegador não participa dessa decisão.

Visitante não recebe verificação cadastral: entra imediatamente e recebe somente o alerta “foi você?” quando uma identidade de dispositivo é criada. Para empreendedor, a confirmação do endereço permanece obrigatória antes da liberação do painel; depois dela, o novo dispositivo inicia os 10 minutos de segurança.

As publicações do Feed, os pontos e as feiras ao vivo também passam pela API. O backend exige conta ativa e, conforme a ação, `feed.publish` ou `locations.publish`; autoria e função nunca são aceitas do aplicativo. O cliente não grava mais diretamente nessas coleções do Firestore.

Cada empreendedor pode manter somente um ponto ativo no mapa. `POST /v1/community/places` recusa uma segunda publicação com `409 CURATED_PLACE_ALREADY_EXISTS`; `DELETE /v1/community/places/{place_id}` volta a validar conta, permissão e autoria antes de retirar o ponto e seu marcador. Depois da exclusão, o empreendedor pode publicar outro local.

Empreendedores e instituições com `locations.publish` podem criar feiras. O backend deriva o autor do ID Token e grava `ownerId` no Firestore. No perfil público, a aba **Feiras** mostra **Excluir feira** somente quando o perfil pertence ao usuário autenticado. Depois da confirmação, `DELETE /v1/community/live-fairs/{fair_id}` volta a validar a conta e a permissão no PostgreSQL e confere a autoria dentro de uma transação do Firestore. Se o autor não coincidir, a API responde `403` e preserva o documento; quando coincide, a exclusão definitiva retira a feira do perfil e do mapa público.

Na aba **Mapa**, feiras ativas e agendadas aparecem em **Ao vivo agora**. Quando o horário termina ou o autor usa **Encerrar agora**, a feira passa para **Histórico** e o marcador é retirado imediatamente do mapa. Históricos de feiras, a lista de pontos e as ofertas emitidas usam páginas de até 20 itens.

### Pesquisa, mensagens e atendimento

Cada Visitante, Empreendedor ou Instituição possui um **nome público único**, normalizado pelo backend para impedir duplicidade por diferença de maiúsculas, acentos, espaços ou pontuação. A barra no topo do Feed consulta `GET /v1/search` e reúne, em uma única pesquisa, perfis, produtos, ofertas e publicações autorizadas.

Pelo perfil público é possível iniciar uma conversa privada. A aba **Mensagens** reúne as conversas da conta, permite marcar mensagens como lidas e oferece o bloqueio do outro perfil; quando existe bloqueio em qualquer direção, o backend não aceita novas mensagens entre as duas contas. O conteúdo das mensagens fica no PostgreSQL e não é persistido no AsyncStorage.

As conversas privadas aceitam texto e uma imagem JPEG, PNG ou WebP de até 5 MB. A imagem fica vinculada à conversa no armazenamento privado e é entregue por URL temporária somente a participantes autorizados. O usuário pode tocar na imagem recebida para abri-la em tela ampliada.

No próprio Perfil, o botão **Entrar em contato com o SUPORTE** abre um chamado privado. A equipe com função `support` e permissão `support.requests.manage` recebe o chamado em sua caixa de atendimento, pode responder e concluir a solicitação. O Painel do Administrador permanece separado e não recebe automaticamente acesso à caixa privada do Suporte.

### Feed único, imagens e comentários

O Feed reúne em uma única sequência cronológica novos empreendedores, publicações, pontos, feiras, produtos e ofertas. Cada cartão oferece **Curtir** e **Ver perfil** quando existe um perfil responsável. A pesquisa no topo continua abrangendo perfis, produtos, ofertas e publicações.

Novas publicações aceitam somente imagens JPEG, PNG ou WebP de até 5 MB; o botão de vídeo foi retirado da interface, embora a dependência permaneça reservada para compatibilidade futura. As imagens são exibidas completas, sem corte obrigatório, e podem ser abertas em um visualizador ampliado com zoom. A foto do perfil também abre nesse visualizador.

No `mobile_app/app.json`, `expo-camera` mantém a câmera para leitura de QR Code e desativa áudio com `microphonePermission: false` e `recordAudioAndroid: false`. O `expo-image-picker` também usa `microphonePermission: false`, e `expo-video` não aparece na lista de plugins. A dependência continua instalada somente para reproduzir publicações legadas em vídeo.

Publicações possuem comentários e respostas. É possível curtir comentários e respostas; o autor pode editar ou excluir seus próprios comentários e publicações. A exclusão autorizada remove o conteúdo das consultas públicas e do Feed, preservando apenas os registros técnicos mínimos exigidos para integridade e auditoria do backend.

### Compartilhamento público seguro

Perfis, publicações, produtos, ofertas, feiras, locais e eventos possuem ação de compartilhamento. Na Web, o aplicativo usa o compartilhamento nativo do navegador quando disponível e, como alternativa, copia ou apresenta o texto para cópia. No Android e no iOS, abre o compartilhamento do sistema.

Os links usam exclusivamente `https://app.liberrotas.com.br`. Perfis abrem `/profile/{uid}`; publicações, produtos, ofertas e feiras vinculados ao perfil acrescentam somente os parâmetros públicos `tab` e `item`, permitindo abrir e destacar o conteúdo correto. Depois do login, o retorno aceita apenas esse formato interno previamente validado, sem redirecionamento para outro domínio.

O texto compartilhado contém somente título, descrição pública e link. **Nunca inclui chave Pix, QR Code, payload ou token de resgate, mensagens privadas, dados do comprador, relatórios ou informações administrativas.** Um local ou evento sem perfil público responsável compartilha a entrada pública do aplicativo, sem inventar uma rota privada.

### Gestão em massa de produtos e ofertas

Em **Cupons > Gerenciar produtos e ofertas**, o Empreendedor pode selecionar vários itens, respeitando o limite do backend, e executar uma única operação:

- arquivar produtos selecionados, revogando também as ofertas ainda ativas desses produtos;
- excluir ofertas selecionadas, preservando o histórico e marcando-as como revogadas;
- aumentar o desconto de várias ofertas elegíveis;
- ampliar o tempo de validade de várias ofertas elegíveis e receber os QR Codes atualizados.

As ações são transacionais: uma falha de validação ou de propriedade impede a alteração parcial do lote. Cada comando leva um `client_request_id`; repetir exatamente o mesmo comando depois de timeout devolve a resposta já gravada, sem aplicar novamente desconto, tempo ou revogação. Reutilizar o mesmo identificador com outro conteúdo é rejeitado com conflito.

Na interface, **Excluir produtos selecionados** remove imediatamente os produtos da lista ativa do empreendedor e da vitrine pública. O backend usa arquivamento autoritativo para impedir que o mesmo produto volte às consultas normais e, ao mesmo tempo, preservar resgates, ledger e auditoria já existentes. Produtos ativos podem ser selecionados em conjunto e receber estoques individuais por **Ativar estoque selecionado**.

### Fluxo atual de ofertas, quantidade e QR Code

Para entender o protocolo completo — emissão, conteúdo do QR, prévia, desafio,
assinatura do dispositivo, anti-replay, decisão, commit e ledger — consulte
[`backend_trq_bec/docs/FLUXO_TRQ_BEC.md`](backend_trq_bec/docs/FLUXO_TRQ_BEC.md).
Esse documento também deixa explícito o que é apenas laboratório e o que ainda
impede uma declaração de prontidão criptográfica para produção.

Em **Cupons > Emitir oferta**, o empreendedor seleciona um ou mais produtos que já possuem estoque, configura cada desconto e, se não alterar a proposta, usa o estoque disponível e validade de 8 horas. A emissão cria a oferta; o QR Code para venda é administrado depois na **Vitrine > Ofertas** do próprio perfil.

Cada cartão de oferta mostra vendidos, estoque disponível, tempo restante e, quando houver evento financiado aplicável, o valor atribuído pela instituição. O empreendedor pode emitir o relatório disponível para suas próprias ofertas.

Antes de gerar o QR, o vendedor informa a quantidade daquela venda. O contador inicia em `1`, aceita digitação ou os botões de aumentar e diminuir e não ultrapassa o menor valor entre estoque e saldo da oferta. O backend assina a quantidade no QR; alterar manualmente o JSON invalida a leitura. Na autorização, o PostgreSQL reduz o estoque e aumenta a quantidade vendida na mesma transação.

Também é possível selecionar de 2 a 5 ofertas ativas e gerar um único QR combinado. Cada produto mantém sua própria quantidade e seu próprio cupom protegido. O visitante faz uma leitura, mas o aplicativo valida os cupons separadamente; descontos diferentes continuam contando como cupons distintos. Se algum item falhar, a tela informa o resultado parcial em vez de declarar o conjunto inteiro como concluído.

Enquanto o QR está aberto, a tela do vendedor consulta o saldo autoritativo. Ao detectar o resgate, fecha o QR automaticamente e devolve o contador da oferta para `1`.

As funções reconhecidas são:

| Função | Destino e responsabilidade |
| --- | --- |
| `admin` | Painel do Administrador: consulta contas, cria e valida equipe autorizada, gerencia instituições e acompanha a operação |
| `support` | Painel do Suporte: atende solicitações, consulta o estado mínimo das contas, cria instituições e executa diagnósticos controlados |
| `security` | Painel da Segurança: consulta auditoria, contém incidentes e acompanha os controles e a telemetria sanitizada do TRQ-BEC |
| `institution` | Painel Institucional: atualiza o próprio perfil, gerencia os próprios grupos e consulta relatórios agregados |
| `entrepreneur` | Abas normais do Empreendedor, com perfil, produtos, ofertas, pontos e feiras |
| `visitor` | Abas comuns do Visitante, sem ferramentas comerciais do Empreendedor |

Conta sem função reconhecida, com divergência entre claim e banco, suspensa ou sem a permissão do painel permanece na tela neutra de acesso pendente. Para `admin`, `support` e `security`, função e permissões também não bastam: o PostgreSQL precisa conter uma validação de autoridade `APPROVED`. O fallback para empreendedor é desativado por padrão.

As três contas internas existentes foram registradas como oficiais, com `protection_level=SYSTEM`, origem `BOOTSTRAP`, validação `APPROVED` e evento append-only. Novas contas de equipe usam outro fluxo:

1. o Administrador abre **Equipe autorizada** e cria a conta com uma das três funções fechadas;
2. o backend cria a identidade sem senha e sem acesso, grava `PENDING`, deriva as permissões pela função e coloca a confirmação de e-mail na fila;
3. a pessoa define a senha e confirma o endereço de e-mail;
4. o Administrador registra o motivo e solicita a validação;
5. o backend confere o Firebase, aplica `staff_validated=true`, ativa a conta, revoga sessões anteriores e grava a auditoria;
6. a pessoa entra novamente para receber o token atualizado.

O formulário nunca aceita uma lista livre de permissões, status ativo ou Custom Claims.

O provisionamento aceita o UID ou o e-mail exato da conta. Execute na pasta `backend_trq_bec`:

```powershell
docker compose exec api trq-bec-set-role <UID_OU_EMAIL> admin
docker compose exec api trq-bec-set-role <UID_OU_EMAIL> support
docker compose exec api trq-bec-set-role <UID_OU_EMAIL> security
docker compose exec api trq-bec-set-role <UID_OU_EMAIL> entrepreneur
docker compose exec api trq-bec-set-role <UID_OU_EMAIL> visitor
```

Esse comando continua disponível para manutenção técnica. Para uma função privilegiada sem validação `APPROVED`, ele força o estado `PENDING` e `staff_validated=false`; portanto, não substitui **Equipe autorizada** e não libera um novo painel administrativo. Para contas públicas ele grava a função e as permissões, atualiza as Custom Claims e revoga os tokens anteriores. Nunca coloque senha ou ID Token nesse comando, no README, no `.env` ou no Git.

No uso normal do aplicativo, não execute o comando manual para criar uma instituição. Entre com a conta de Administrador ou Suporte, abra o respectivo painel e use **Criar instituição**, ou analise a fila pública no Painel do Suporte. O backend fixa a função `institution`, grava as permissões fechadas, registra auditoria, gera o link Firebase e o envia pelo SMTP autenticado para a própria pessoa definir a senha. Se o link não puder ser entregue, a identidade recém-criada é revertida e a solicitação não recebe o estado aprovado.

### Ferramentas dos painéis autorizados

Cada painel mostra uma explicação das responsabilidades, das ferramentas realmente liberadas e dos limites de segurança daquela função. O botão **SAIR** fica abaixo das ferramentas. Ao abrir uma ferramenta, o menu é substituído pela interface escolhida e o usuário pode usar **Voltar ao painel** para retornar.

- **Administrador:** Contas e acessos, Equipe autorizada, Instituições e Operação da plataforma. A consulta mostra funções, estados e permissões reais, mas não oferece edição livre de Custom Claims. A ferramenta de equipe cria contas pendentes e valida a autoridade somente depois da confirmação do e-mail.
- **Suporte:** Atendimentos, Consulta de contas, Solicitações de instituição, Instituições e Orientações e diagnóstico. O suporte pesquisa e responde chamados, analisa pedidos públicos de Empresa ou ONG e pode aprovar a criação institucional com primeiro acesso enviado ao e-mail conferido; a consulta geral de contas continua mínima e somente leitura.
- **Segurança:** Auditoria, Incidentes, Monitoramento, TRQ-BEC e Central de pendências. A suspensão ou reativação exige autenticação recente, confirmação e motivo. Contas oficiais `SYSTEM`, Administrador e Segurança são protegidas. Na ferramenta TRQ-BEC, cada indicador é um botão com explicação e providência; o aviso de análise abre a Central de pendências para contas privilegiadas, dispositivos e verificação de e-mail sem misturar as responsabilidades de Segurança, Administrador e titular da conta.
- **Instituição:** Perfil institucional, Grupos e Relatórios. A instituição altera somente nome, descrição e cidade do próprio perfil, gerencia somente os próprios grupos e recebe apenas totais agregados dos próprios dados.

Uma sessão autenticada não permanece na página institucional pública: contas internas são redirecionadas ao painel autorizado. Nas rotas privadas de visitante e empreendedor, o retorno principal é **Perfil** e substitui o histórico de navegação para não levar a pessoa de volta à página inicial.

Os cartões do menu não substituem autorização. Toda ferramenta chama um endpoint protegido que confere novamente ID Token, função, estado e permissão no backend.

### Filiação de vendedores e relatório institucional

Dentro de **Grupos**, a instituição convida o empreendedor pelo nome público único. O convite não usa e-mail nem UID informado pelo frontend; o empreendedor decide entre aceitar ou recusar no próprio Perfil. Ele pode sair depois, e a instituição pode cancelar um convite pendente ou remover um membro. O banco permite no máximo **uma filiação `ACTIVE` global por empreendedor**, evitando atribuir o mesmo resgate simultaneamente a duas instituições ou grupos.

O relatório em **Relatórios** considera somente resgates confirmados que ocorreram dentro da janela em que a filiação estava ativa. Ele pode filtrar por grupo e período, separa os valores por moeda e mostra totais e linhas por vendedor. Registros legados sem snapshot financeiro completo entram em `amounts_unavailable_count`, mas ficam fora dos totais em dinheiro, sem estimativa.

Esses números representam **resgates/vendas registrados no LiberRotas**. Eles não comprovam recebimento, Pix, cartão, liquidação, estorno ou faturamento contábil e não revelam comprador, chave Pix, QR, token ou mensagem privada.

### Eventos institucionais com verba

A instituição pode criar um evento financiado com valor total, moeda, janela de início/fim e regra de término por horário ou esgotamento dos cupons. Antes da ativação, o valor é dividido igualmente entre os afiliados elegíveis quando nenhuma configuração manual é informada; a instituição pode ajustar as cotas por vendedor, desde que a soma continue igual ao orçamento.

Cada empreendedor participante recebe a própria cota e pode distribuí-la entre seus produtos. Sem ajuste, a divisão entre os produtos elegíveis também é igual. Após a ativação, as alocações ficam congeladas para preservar o relatório. A instituição pode encerrar o evento manualmente e consulta um relatório com orçamento, uso de cupons, unidades vendidas, valor utilizado e valor devido a cada afiliado. O empreendedor vê somente sua própria cota e seus produtos.

## Relógio, validade e horário das feiras

O cabeçalho mostra a hora local atualizada a cada segundo. Para evitar que a alteração manual do relógio do celular burle prazos, o aplicativo consulta `GET /v1/time`, calcula a diferença para o relógio UTC do backend e usa essa referência nas contagens regressivas.

- cupons mostram o tempo restante e deixam de oferecer o QR/resgate quando a validade visual termina;
- feiras mostram quanto falta para começar ou terminar;
- o relógio é sincronizado novamente a cada cinco minutos e quando o aplicativo volta ao primeiro plano;
- se a API estiver indisponível, a interface pode mostrar a hora do aparelho, mas nenhuma decisão comercial ou de segurança é aprovada localmente.

A autoridade final continua no backend: expiração de oferta, encerramento de feira, validade de desafio, proteção contra repetição, autenticação recente e limites de requisição usam `time.time()`, `now()` e TTL do Redis/PostgreSQL no servidor. O cliente nunca envia uma hora confiável para decidir essas operações.

Para empreendedor, a Fase 1 ainda exige duas autorizações separadas:

1. custom claim Firebase `role=entrepreneur`;
2. conta comercial `ACTIVE` no PostgreSQL.

Depois de criar o usuário no Firebase Authentication, provisione a função:

```powershell
docker compose exec api trq-bec-set-role <UID_OU_EMAIL> entrepreneur
```

Depois, abra `http://127.0.0.1:8787/internal/docs`, autorize com o Firebase ID token renovado do administrador e execute `POST /internal/v1/marketplace/merchants/status` com um corpo semelhante a:

```json
{
  "firebase_uid": "UID_REAL_DO_EMPREENDEDOR",
  "display_name": "Nome do empreendedor",
  "establishment_id": "EST-FEIRA-01",
  "establishment_name": "Nome do estabelecimento",
  "status": "ACTIVE"
}
```

Substitua os valores de exemplo pelos reais. Não coloque ID token no README, `.env` ou Git. Depois de alterar claims, saia e entre novamente no aplicativo para renovar o token. Toda chave nova de dispositivo deve ser cadastrada até 5 minutos depois desse login recente. Para visitante, cada chave fica `ACTIVE` imediatamente e o e-mail é somente um alerta. Para empreendedor e instituição, toda chave nova fica `PENDING_APPROVAL` durante 10 minutos e então é ativada automaticamente. O e-mail não autoriza o dispositivo.

Na Web, a identidade fica no IndexedDB da origem atual. Não limpe os dados do site durante uma operação: perder o IndexedDB perde a chave privada local. Se isso acontecer, entre novamente, cadastre a nova identidade e confirme-a em **Segurança da minha conta**. O registro anterior continuará aparecendo no inventário até ser revogado.

## Ordem para executar a integração completa

Para produção Web, execute na raiz:

```powershell
.\INICIAR_LIBERROTAS.ps1
.\STATUS_LIBERROTAS.ps1
```

Para testar o aplicativo móvel com Expo Go, abra outro terminal:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app"
npx expo start --port 8082
```

Primeiro confirme `http://127.0.0.1:8787/health/`; somente depois teste emissão e leitura de cupons no app.

Para validar o fluxo completo de emissão e resgate, use duas contas Firebase: uma conta empreendedora com a custom claim `entrepreneur` e uma conta visitante. Na demonstração prática, normalmente são necessários dois dispositivos ou duas telas, uma para exibir o QR Code e outra para escaneá-lo.

## Validação do projeto

### Aplicativo

Execute em `mobile_app`:

```powershell
npm.cmd test
npm.cmd run test:firestore
npm run lint
npx tsc --noEmit
npx expo install --check
npx expo-doctor
$env:EXPO_PUBLIC_TRQ_BEC_API_URL = "https://api.liberrotas.com.br"
npx expo export --platform web --output-dir dist --clear
Remove-Item Env:EXPO_PUBLIC_TRQ_BEC_API_URL
npm audit --omit=dev
```

Resultado do aplicativo em 04/09/2026:

- `npm.cmd test`: `44` testes Vitest aprovados;
- `npm.cmd run test:firestore`: regras aprovadas separadamente no emulador local, sem usar o projeto Firebase real;
- `npx.cmd tsc --noEmit`: aprovado;
- `npm.cmd run lint`: aprovado;
- `npx.cmd expo install --check`: aprovado, sem versões pendentes;
- Expo `57.0.20`/SDK 57, React Native `0.86.3` e React `19.2.3` confirmados;
- `npx.cmd expo-doctor`: `21/21` verificações aprovadas;
- `npx.cmd expo config --type public`: aprovado; permissões exibem LiberRotas, áudio está desativado e não existe plugin explícito `expo-video`;
- exportação Web estática: aprovada;
- `npm.cmd audit --omit=dev`: `3` vulnerabilidades moderadas e `0` altas ou críticas na árvore de produção, todas na cadeia transitiva upstream do `expo-router`.

Não use `npm audit fix --force`: a correção automática proposta troca dependências do Expo Router de forma incompatível. Repita a auditoria depois de uma correção upstream compatível com o SDK 57.

### Backend

Execute em `backend_trq_bec`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Resultado confirmado em 04/09/2026: `197 testes` e `63 subtestes` aprovados. O contrato OpenAPI contém `94` caminhos e `106` operações. A suíte cobre a regressão criptográfica e comercial, dispositivos, SMTP, mídia e variantes, seleção pública de imagem por entidade, comentários, eventos institucionais, exclusão de feira com controle de autoria, quantidade assinada e resgate transacional. Os probes com PostgreSQL/Redis reais continuam sendo verificações separadas da suíte unitária.

O código foi ajustado para não interpretar bits POSIX como permissões NTFS no Python nativo do Windows. A validação POSIX permanece ativa dentro de Linux e dos contêineres Docker.

## Parar os serviços sem apagar dados

Na raiz do workspace:

```powershell
.\PARAR_LIBERROTAS.ps1
```

Esse script usa `docker compose stop` e preserva a pasta do banco, Redis, imagens e segredos. Para criar um dump dentro do workspace, execute `.\BACKUP_BANCO.ps1`. Nunca use `docker compose down -v` neste projeto.

## Erros comuns no Windows

### Docker informa que não encontrou o pipe

Mensagem parecida:

```text
open //./pipe/dockerDesktopLinuxEngine: O sistema não pode encontrar o arquivo especificado
```

Abra o Docker Desktop, aguarde aparecer **Engine running** e repita `docker compose ps`.

### `CONFIGURATION_NOT_FOUND` no Firebase

Confirme se o provedor **E-mail/senha** foi ativado no Firebase Authentication e se o app está apontando para o projeto correto.

### Não foi possível validar as permissões da conta

Se o Firebase aceitar o e-mail e a senha, mas a API responder `AUTH_TOKEN_INVALID` logo após o login, confira o relógio do Windows em **Configurações > Hora e idioma > Data e hora**. Ative **Definir hora automaticamente** e use **Sincronizar agora**. No PowerShell, a situação pode ser consultada sem alterar o sistema:

```powershell
w32tm /query /status
```

O backend tolera uma diferença curta de até 30 segundos entre Windows, Docker Desktop e Firebase, mantendo a validação de assinatura, expiração e revogação do ID Token. Uma diferença maior deve ser corrigida no relógio do Windows.

### O app abre, mas não gera cupom

Confira `mobile_app\.env.local`:

- URL apontando para `https://api.liberrotas.com.br` no celular físico ou para `http://127.0.0.1:8787` somente no navegador deste PC;
- `EXPO_PUBLIC_TRQ_BEC_ALLOW_LEGACY_DEMO=false`;
- usuário com claim `entrepreneur`, conta comercial `ACTIVE`, produto com estoque e dispositivo cadastrado.

Na Web, confirme também que a página foi aberta por HTTPS ou `http://127.0.0.1`, que o navegador oferece WebCrypto Ed25519 e IndexedDB e que os dados dessa origem não foram apagados. Se o botão não enviar a requisição, saia, entre novamente e tente o cadastro da chave nova dentro de 5 minutos.

Reinicie o Expo após mudar o arquivo.

### `RECENT_AUTHENTICATION_REQUIRED`

O cadastro de uma chave nova exige autenticação recente. Saia da conta no app, entre novamente e repita em até 5 minutos. O recadastro idempotente da mesma chave continua funcionando depois dessa janela.

### Novo dispositivo em período de segurança

O login em mais de um aparelho é permitido. Para visitantes, todo dispositivo novo fica `ACTIVE` imediatamente e o e-mail é apenas um alerta de acesso. Para empreendedores e instituições, todo dispositivo novo, inclusive o primeiro, aparece como **Em período de segurança** em **Segurança da minha conta**. Contas internas preservam a política restrita própria do backend.

O backend libera esse aparelho automaticamente depois de 10 minutos. A tela mostra a contagem e consulta novamente o servidor ao chegar a zero. O e-mail é apenas um alerta: se foi você, desconsidere; se não foi, use **Não fui eu!** para abrir a lista de dispositivos e escolha **Alterar senha e desconectar todos**.

Se o e-mail não chegar, use **Reenviar alerta de segurança** depois de 60 segundos. O reenvio não reinicia nem aumenta os 10 minutos. Falha ou ausência do SMTP também não prende o usuário: ao vencer o horário autoritativo, o backend muda `PENDING_APPROVAL` para `ACTIVE`. Antes da troca de senha, o aplicativo avisa que todos os dispositivos, inclusive o atual e os ainda pendentes, serão desconectados.

### O celular não acessa a API

- não use `127.0.0.1` ou `localhost` no celular;
- confirme que `mobile_app\.env.local` usa `https://api.liberrotas.com.br`;
- confirme que `docker compose ps` mostra a API ativa e saudável;
- teste `curl.exe -4 --fail --show-error https://api.liberrotas.com.br/health/` no PC;
- verifique se o serviço `cloudflared` e a conexão de Internet estão ativos.

### `KEY_FILE_PERMISSIONS_TOO_BROAD`

No Python nativo do Windows, essa incompatibilidade com NTFS foi corrigida. No Docker Desktop, o Compose não entrega mais o bind mount NTFS diretamente à API: `secrets-init` copia os arquivos para um volume interno, define proprietário `10001` e modo `600`, mantendo a validação rígida.

Se o erro ainda aparecer, execute na pasta `backend_trq_bec`:

```powershell
docker compose run --rm secrets-init
docker compose up -d api
docker compose logs --tail 100 api
```

Não remova a validação de permissões do contêiner.

### `adb` não é reconhecido

O `adb` só é necessário para emulador ou aparelho Android por USB. Para usar Expo Go via QR Code, ele não é obrigatório. Se precisar, instale Android Studio/Platform Tools e configure `ANDROID_HOME` e o `Path`.

### A porta 8081 ou 8787 já está ocupada

Confira no PowerShell:

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 8081,8787
```

Em produção, ambas as portas devem pertencer ao Docker e estar vinculadas somente a `127.0.0.1`. Se `8081` pertencer a `node.exe`, confirme a linha de comando e encerre somente o Expo/Metro deste workspace. Não finalize processos desconhecidos à força.

## Segurança

Arquivos que nunca devem ser publicados:

```text
mobile_app/.env.local
backend_trq_bec/.env
backend_trq_bec/.env.backend
backend_trq_bec/secrets/*
```

Os `.gitignore` dos módulos já cobrem esses arquivos. Antes de qualquer commit, confira se nenhum segredo foi adicionado.

## Controle de versão e ZIP acadêmico

O histórico oficial do projeto fica no repositório privado [SomBRaRCP/LiberRotas](https://github.com/SomBRaRCP/LiberRotas). A pasta `.git` pertence ao workspace de desenvolvimento e mantém commits, branches e vínculo com o GitHub.

O ZIP acadêmico gerado por `scripts\build-academic-package.ps1` não inclui `.git`. Isso é intencional: o pacote de entrega contém o código necessário para avaliação, enquanto o GitHub privado preserva o histórico completo. Para continuar o desenvolvimento com histórico, use o workspace original ou clone o repositório privado; não execute `git init` dentro do ZIP extraído.

O contrato comercial atual não usa o modo legado. Mantenha:

```env
EXPO_PUBLIC_TRQ_BEC_ALLOW_LEGACY_DEMO=false
```

## Documentação complementar

- `MAPA_DE_COMANDOS.md` — sequência prática para iniciar Web, Mobile, verificar e parar;
- `mobile_app/FIREBASE_AUTH_SETUP.md` — configuração atual do Firebase Authentication;
- `mobile_app/TRQ_BEC_INTEGRATION.md` — contratos entre app e backend;
- `mobile_app/VALIDACAO_TRQ_BEC.md` — checklist atual do QR individual/combinado e quantidade;
- `backend_trq_bec/README.md` — arquitetura do pacote TRQ-BEC;
- `backend_trq_bec/VALIDATION.md` — resultados automatizados e limites da validação atual;
- `backend_trq_bec/docs/GCS_MEDIA_STORAGE.md` — imagens privadas, IAM, CORS, Lifecycle, testes e ativação manual;
- `backend_trq_bec/docs/MEDIA_COST_AUDIT_2026-08-03.md` — auditoria de Base64, duplicações, cache, consultas e custos de mídia;
- `backend_trq_bec/docs/HOMOLOGACAO_FUNCIONAL_2026-08-05.md` — matriz automática, Web local e roteiro obrigatório em aparelho físico;
- `backend_trq_bec/docs/SEQUENCIA_SEGURA_2026-08-05.md` — registro dos lotes concluídos e gates externos de produção;
- `backend_trq_bec/docs/BACKEND_DEPLOYMENT.md` — implantação detalhada;
- `backend_trq_bec/SECURITY.md` — limites e requisitos de segurança;
- [Expo SDK 57](https://docs.expo.dev/versions/v57.0.0/);
- [Expo Go e development builds](https://docs.expo.dev/develop/development-builds/introduction/);
- [Simulador iOS e limitações no Windows](https://docs.expo.dev/workflow/ios-simulator/).

As pastas `backend_trq_bec/TRQ_BEC_API_Documentacao_Autoritativa_v0.5.0a1`,
`backend_trq_bec/TRQ_BEC_API_Tres_Fivelas_v0.5.0a2` e `archive` são registros
históricos. Elas não foram reescritas nesta revisão e não devem ser usadas como
documentação operacional da versão atual.
