# Mapa de comandos — LiberRotas Web e Mobile

Este mapa considera o ambiente Windows atual:

> Revisado em 01/09/2026. Os pacotes históricos `v0.5.x` não participam destes comandos.

- Web de produção no Docker: `http://127.0.0.1:8081`;
- API local no Docker: `http://127.0.0.1:8787`;
- API pública usada pelo celular: `https://api.liberrotas.com.br`;
- Expo/Metro para desenvolvimento mobile: porta `8082`;
- aplicativo: Expo `57.0.19`/SDK 57, React Native `0.86.3` e React `19.2.3`.

## Visão rápida

```text
F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3
│
├── Web de produção + API + PostgreSQL + Redis
│   ├── iniciar ........ .\INICIAR_LIBERROTAS.ps1
│   ├── atualizar API/Web  .\INICIAR_LIBERROTAS.ps1 -Rebuild
│   ├── verificar ...... .\STATUS_LIBERROTAS.ps1
│   └── parar .......... .\PARAR_LIBERROTAS.ps1
│
└── Mobile com Expo Go — usar outro PowerShell
    ├── entrar no app .. Set-Location .\mobile_app
    ├── iniciar ........ npx expo start --port 8082
    ├── limpar cache ... npx expo start --clear --port 8082
    └── encerrar ....... Ctrl + C
```

Se o PowerShell responder que `npx.ps1` ou `npm.ps1` não pode ser carregado
porque a execução de scripts está desabilitada, use os executáveis do Windows
sem mudar a política do computador:

```powershell
npx.cmd expo start --port 8082
npm.cmd run lint
```

## 1. Iniciar a aplicação Web

Abra o PowerShell na raiz do workspace:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3"
.\INICIAR_LIBERROTAS.ps1
```

O comando inicia e verifica:

- Web Nginx;
- API TRQ-BEC;
- PostgreSQL;
- Redis;
- inicialização segura dos segredos do backend.

Depois, abra no navegador:

```text
http://127.0.0.1:8081
```

O endereço público configurado pelo Cloudflare Tunnel é:

```text
https://app.liberrotas.com.br
```

### Identidade protegida na Web

As operações protegidas funcionam em `https://app.liberrotas.com.br` e, para o
laboratório local, em páginas abertas por `http://127.0.0.1`. O navegador cria
uma chave Ed25519 pelo WebCrypto, mantém a chave privada como `CryptoKey` não
exportável e a persiste no IndexedDB. No Android/iOS, o app continua usando
`expo-secure-store`.

Todo cadastro de uma identidade nova precisa ocorrer até 5 minutos depois do
login. Para visitante, cada dispositivo fica automaticamente `ACTIVE` e gera
apenas um alerta. Para empreendedor e instituição, todo novo dispositivo,
inclusive o primeiro, fica `PENDING_APPROVAL` por 10 minutos. A sessão autenticada
continua válida e, ao terminar o período, o backend promove a chave automaticamente
para `ACTIVE`.

O backend envia ao e-mail registrado no Firebase um alerta com o botão
**Não fui eu!**, que abre `/account/devices`. Se foi o próprio usuário, basta
desconsiderar a mensagem. Se não foi, ele deve revisar os aparelhos e escolher
**Alterar senha e desconectar todos**. O e-mail não autoriza o dispositivo e não
contém token. O reenvio do alerta exige autenticação Firebase recente, possui
intervalo mínimo de 60 segundos e não reinicia a contagem de 10 minutos.

Cada combinação de protocolo, host e porta é uma origem diferente; por isso o
domínio público, `127.0.0.1:8081` e `127.0.0.1:8082` não compartilham a mesma
chave. Não limpe IndexedDB ou SecureStore durante uma operação. Se a chave local
for perdida, cadastre a nova identidade e aguarde os 10 minutos; o registro
anterior continuará no inventário até ser revogado. O perfil Web continua
experimental: a chave não exportável não impede que um XSS da mesma origem
solicite assinaturas.

### E-mail de segurança por SMTP

Para a Brevo, use o configurador seguro na **raiz do workspace**. Ele solicita o
login SMTP e a chave SMTP sem mostrar a chave, atualiza `.env.backend`, grava o
segredo fora do arquivo de ambiente, reinicia somente a API e testa a
autenticação:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3"
.\CONFIGURAR_EMAIL_DISPOSITIVOS.ps1
```

Use a **chave SMTP**, não a chave de API da Brevo. Depois de aparecer
`SMTP_AUTHENTICATION_OK`, volte à tela **Segurança da minha conta** e pressione
**Reenviar alerta de segurança**.

Os passos abaixo são a alternativa manual para outro provedor SMTP.

Na pasta `backend_trq_bec`, abra `.env.backend` e configure host, porta, usuário,
remetente e o caminho do segredo. Não escreva a senha nesse arquivo:

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

Crie o segredo sem colocar a senha no histórico do terminal:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
New-Item -ItemType Directory -Force ".\secrets" | Out-Null
notepad ".\secrets\smtp-password"
```

Salve somente a senha SMTP ou senha de aplicativo. Para a porta `465`, use
`TRQ_BEC_SMTP_SSL=true` e `TRQ_BEC_SMTP_STARTTLS=false`; nunca ative os dois.
Depois do rebuild, confira somente metadados do segredo, sem imprimir seu
conteúdo:

```powershell
docker compose exec api stat -c "%a %u:%g %n" /run/secrets/smtp-password
```

O esperado é modo `600`, proprietário `10001:10001`. Em desenvolvimento, ausência
ou falha do SMTP não derruba o login nem impede a liberação automática após 10
minutos, e o backend nunca informa `SENT` sem entrega aceita pelo servidor SMTP.
Em `TRQ_BEC_ENVIRONMENT=production`, host SMTP e remetente são obrigatórios e a
API deve recusar a inicialização sem eles.

## 2. Iniciar a aplicação Mobile com Expo Go

Primeiro, mantenha o backend ativo executando `INICIAR_LIBERROTAS.ps1` como
mostrado acima.

Abra um **segundo PowerShell** e execute:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app"
npx expo start --port 8082
```

No celular:

1. conecte o celular e o computador à mesma rede Wi-Fi;
2. abra uma versão do Expo Go compatível com o SDK 57;
3. leia o QR Code mostrado no terminal;
4. aguarde o bundle carregar;
5. aceite somente as permissões necessárias.

O Docker continua usando `8081` para a Web, enquanto o Expo usa `8082` para o
Mobile. Assim, as duas aplicações podem funcionar ao mesmo tempo.

### Configuração da API no celular

A porta local `8787` está protegida no loopback do Windows. Portanto, o celular
deve consumir a API pública HTTPS. Confira manualmente em
`mobile_app\.env.local`, sem publicar esse arquivo:

```env
EXPO_PUBLIC_TRQ_BEC_API_URL=https://api.liberrotas.com.br
EXPO_PUBLIC_TRQ_BEC_ALLOW_LEGACY_DEMO=false
```

Este mapa não altera o `.env.local`. Se você editar o arquivo, encerre o Expo
com `Ctrl + C` e inicie novamente.

### Entrada única e autorização de contas

Na tela inicial, todas as contas usam o mesmo formulário **Entrar**, com e-mail
e senha. Visitante e Empreendedor são escolhidos somente em **Criar conta**. O
painel é escolhido pelo backend depois de validar Firebase, Custom Claims,
status e permissões. Não existe escolha manual de função no login.

Para provisionar uma função, execute na pasta `backend_trq_bec` e informe UID
ou e-mail exato, nunca a senha:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
docker compose exec api trq-bec-set-role <UID_OU_EMAIL> <admin|support|security|entrepreneur|visitor>
```

Depois desse comando, a conta deve sair e entrar novamente porque os tokens
anteriores são revogados.

Para `admin`, `support` ou `security`, esse comando **não aprova uma nova
conta**. Sem validação de autoridade já registrada, o backend força `PENDING`
e `staff_validated=false`. No fluxo normal, entre como Administrador, abra
**Equipe autorizada**, crie a conta pendente e valide somente depois que a
pessoa definir a senha e confirmar o e-mail.

Contas `institution` não são criadas pelo cadastro público nem por esse comando
no fluxo normal. Administrador ou Suporte entra no próprio painel, usa
**Criar instituição** e informa nome/e-mail. Na página pública, **Registrar
Instituição** também pode enviar uma Empresa ou ONG para a fila do Suporte.
Quando a análise é aprovada, o backend cria a conta e envia pelo SMTP
autenticado o link Firebase para a pessoa definir a senha do primeiro acesso.

Cada painel autorizado explica suas responsabilidades, ferramentas liberadas
e limites. O botão **SAIR** fica logo abaixo do menu:

- Administrador: **Contas e acessos**, **Equipe autorizada**, **Instituições** e **Operação da plataforma**;
- Suporte: **Atendimentos**, **Consulta de contas**, **Solicitações de instituição**, **Instituições** e **Orientações e diagnóstico**;
- Segurança: **Auditoria**, **Incidentes**, **Monitoramento**, **TRQ-BEC** e **Central de pendências**; os indicadores do TRQ-BEC abrem detalhes e o aviso vermelho direciona para as providências de contas, dispositivos e e-mails;
- Instituição: **Perfil institucional**, **Grupos** e **Relatórios**.

Ao entrar em uma ferramenta, use **Voltar ao painel** para retornar ao menu.
As permissões continuam sendo verificadas na API; esconder ou mostrar
um botão no navegador não concede acesso por si só.

## 3. Iniciar no emulador Android

Com o Android Studio e um emulador já abertos, execute em `mobile_app`:

```powershell
npx expo start --android --port 8082
```

Também é possível iniciar com `npx expo start --port 8082` e pressionar `a` no
terminal. No Windows não existe simulador oficial de iOS.

## 4. Abrir o modo Web de desenvolvimento

Use esta opção apenas para programar com atualização rápida do Expo. Ela não
substitui o Nginx de produção:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app"
npx expo start --web --port 8082
```

Abra `http://127.0.0.1:8082`. A porta pública local `8081` continua sendo
administrada pelo Docker. Usar `localhost` criaria outra origem e, portanto,
outra identidade de dispositivo no IndexedDB.

## 5. Atualizar a Web depois de alterar o código

Execute na raiz do workspace:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3"
.\INICIAR_LIBERROTAS.ps1 -Rebuild
```

O parâmetro `-Rebuild` reconstrói as imagens da API e da Web, gera um novo
export Expo e mantém o PostgreSQL em `backend_trq_bec\database\postgres` e o
volume do Redis.

## 6. Verificar se tudo está funcionando

Na raiz do workspace:

```powershell
.\STATUS_LIBERROTAS.ps1
```

O resultado esperado é:

```text
[OK] Web local
[OK] API local
[OK] API pública
web, api, postgres e redis: healthy
secrets-init: exited com código 0
```

Para ver quem está usando as portas:

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object LocalPort -in 8081,8082,8787 |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

## 7. Encerrar corretamente

Para encerrar somente o Expo Mobile, pressione no terminal do Expo:

```text
Ctrl + C
```

Para parar Web, API, PostgreSQL e Redis sem apagar dados, execute na raiz:

```powershell
.\PARAR_LIBERROTAS.ps1
```

Nunca use `docker compose down -v`, pois `-v` remove os volumes persistentes do
Redis e dos segredos. O PostgreSQL fica na pasta do workspace, mas deve ser
copiado somente por backup lógico.

Para gerar um backup PostgreSQL dentro do workspace, execute na raiz:

```powershell
.\BACKUP_BANCO.ps1
```

## 8. Ordem recomendada depois de reiniciar o Windows

```text
1. Abrir o Docker Desktop e esperar “Engine running”.
2. Na raiz, executar .\INICIAR_LIBERROTAS.ps1.
3. Na raiz, executar .\STATUS_LIBERROTAS.ps1.
4. Para Mobile, abrir outro PowerShell e executar o Expo na porta 8082.
5. Abrir Web em 127.0.0.1:8081 ou ler o QR Code no Expo Go.
```

Se o Expo apresentar cache antigo:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app"
npx expo start --clear --port 8082
```

## 9. Validar código e regras Firestore

Na pasta `mobile_app`, execute primeiro a suíte Vitest e depois a suíte separada das regras Firestore:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app"
npm.cmd test
npm.cmd run test:firestore
npx.cmd tsc --noEmit
npm.cmd run lint
npx.cmd expo-doctor
npx.cmd expo install --check
npm.cmd audit --omit=dev
```

`npm.cmd test` executa os `34` testes Vitest. `npm.cmd run test:firestore` inicia um emulador local com projeto de demonstração e valida `firestore.rules` separadamente; ele exige JDK 21 e não deve acessar nem alterar o projeto Firebase real. Não associe uma quantidade de asserts a essa suíte, pois ela pode evoluir independentemente do Vitest.

Em 01/09/2026, Expo Doctor passou `21/21`. A auditoria da árvore de produção registrou `3` vulnerabilidades moderadas e `0` altas ou críticas, originadas na cadeia upstream do `expo-router`. Não use `npm audit fix --force` para tentar removê-las.

Na pasta `backend_trq_bec`, execute:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
.\.venv\Scripts\python.exe -m pytest tests -q
```

O resultado atual é `197 testes` e `63 subtestes`; o OpenAPI contém `94` caminhos e `106` operações.

## 10. GitHub e entrega acadêmica

O repositório oficial é privado: [https://github.com/SomBRaRCP/LiberRotas](https://github.com/SomBRaRCP/LiberRotas). O GitHub mantém commits, branches e o histórico do desenvolvimento.

O ZIP acadêmico não inclui a pasta `.git`. Isso é esperado e evita enviar metadados de desenvolvimento junto com a entrega; o histórico continua preservado no GitHub privado. Para trabalhar com histórico, use o workspace original ou faça um clone autorizado do repositório, em vez de executar `git init` no ZIP.
