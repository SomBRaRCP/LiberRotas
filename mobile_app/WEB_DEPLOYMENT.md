# Implantação Web de produção do LiberRotas

O site público é uma exportação estática do Expo Router servida por Nginx não
privilegiado. O runtime não usa Node.js, Metro Bundler ou Expo Dev Server.

Endereços definidos:

- site local: `http://127.0.0.1:8081`;
- site público: `https://app.liberrotas.com.br`;
- API pública usada pelo bundle: `https://api.liberrotas.com.br`.

## Contexto seguro e identidade Web

O fluxo protegido de emissão e resgate funciona no navegador quando a página
possui WebCrypto Ed25519, IndexedDB e contexto seguro. Em produção, use somente
`https://app.liberrotas.com.br`. No laboratório local deste computador, use
`http://127.0.0.1:8081` ou `http://127.0.0.1:8082`; não publique nem acesse o
fluxo por HTTP em um IP da rede local.

O navegador cria a chave privada como `CryptoKey` não exportável e a persiste no
IndexedDB. Android/iOS não usam esse banco: continuam com a seed protegida pelo
`expo-secure-store`.

A identidade Web é isolada por origem, isto é, pela combinação de protocolo,
host e porta. O domínio público e cada porta local criam chaves diferentes. Toda
chave nova deve ser cadastrada até 5 minutos depois do login Firebase. Para
visitante, cada origem ou aparelho fica `ACTIVE` imediatamente e gera um alerta.
Para empreendedor e instituição, toda origem ou aparelho novo, inclusive o
primeiro, fica `PENDING_APPROVAL` por 10 minutos e depois é ativado automaticamente.

Enquanto o registro continua `PENDING_APPROVAL`, o reenvio do alerta exige
autenticação recente e respeita 60 segundos, mas não reinicia a contagem. Ao
vencer o horário, o backend promove o aparelho para `ACTIVE`.

O e-mail de segurança abre
`https://app.liberrotas.com.br/account/devices` pelo botão **Não fui eu!**. Não há
token na URL. Se o acesso for legítimo, o usuário desconsidera a mensagem; se não
for, revisa os aparelhos e troca a senha.

O horário de liberação vem do backend em `approval_expires_at`; a tela usa esse
valor para exibir a contagem e consulta novamente a API ao chegar a zero.

Não limpe os dados do site, não apague o IndexedDB e não use navegação privada
para uma identidade que precise permanecer vinculada. Perder esses dados perde a
chave não exportável, mas não apaga o registro autoritativo; uma nova chave pode
ser cadastrada e ficará em cooldown por 10 minutos. O e-mail é somente um alerta
e não autoriza a chave. Este é um controle de laboratório, não
atestação de hardware. Um XSS na mesma origem ainda pode pedir que a chave assine
dados, portanto dependências, conteúdo injetado e políticas contra XSS continuam
sendo parte da segurança do deploy.

## 1. Build manual para conferência

Execute na pasta `mobile_app`:

```powershell
npm ci
npm run lint
npx tsc --noEmit
npx expo install --check
$env:EXPO_PUBLIC_TRQ_BEC_API_URL = "https://api.liberrotas.com.br"
npx expo export --platform web --output-dir dist --clear
Remove-Item Env:EXPO_PUBLIC_TRQ_BEC_API_URL
```

O resultado é criado em `mobile_app/dist`. O `--clear` evita reaproveitar um
bundle antigo com URL local. Neste export manual, o Expo lê as seis variáveis
`EXPO_PUBLIC_FIREBASE_*` de `.env.local`; confira o projeto Firebase antes de
exportar. O build Docker abaixo desativa essa leitura e recebe os valores
públicos explicitamente pelo Compose.

## 2. Build usado pelo Docker

O `Dockerfile.web` executa `npm ci` e gera um novo `dist` em uma etapa Node 22.
O conteúdo estático é copiado para `nginxinc/nginx-unprivileged`, que atende na
porta interna `8080` como usuário não root. O `dist` antigo é ignorado pelo
`.dockerignore` e nunca é copiado diretamente.

O Compose fica em `backend_trq_bec/docker-compose.yml`. Para construir somente
a imagem Web:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
docker compose --env-file .env --env-file ../mobile_app/.env.local build web
```

Para iniciar toda a pilha, volte à raiz e use:

```powershell
Set-Location "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3"
.\INICIAR_LIBERROTAS.ps1
```

Depois de mudar o frontend, force uma nova build com:

```powershell
.\INICIAR_LIBERROTAS.ps1 -Rebuild
```

## 3. Rotas e cache

O Expo Router gera páginas HTML estáticas, inclusive um molde literal para a
rota dinâmica `profile/[profileId]`. O `nginx.conf` tenta o arquivo solicitado,
a versão `.html`, a página do diretório e, por último, `index.html`. Isso mantém
navegação e refresh em deep links.

- HTML e fallback: sem cache agressivo;
- `/_expo/static/` e `/assets/`: cache longo para arquivos versionados;
- listagem de diretórios: desativada;
- healthcheck interno: `http://127.0.0.1:8080/healthz` dentro do contêiner.

## 4. Cloudflare Tunnel

O Cloudflare não é configurado por arquivos deste projeto. Depois de confirmar
HTTP 200 em `http://127.0.0.1:8081`, crie manualmente no túnel:

```text
Hostname público: app.liberrotas.com.br
Serviço local:    http://localhost:8081
```

Não exponha a porta `8081` no roteador ou em `0.0.0.0`.

## Segurança das configurações públicas

Variáveis com prefixo `EXPO_PUBLIC_` são incorporadas ao JavaScript entregue ao
navegador. Portanto, elas nunca podem conter senha, chave privada, token de
administração, conta de serviço Firebase ou segredo do backend TRQ-BEC.

A configuração Firebase Web é pública por natureza. A chave do Google Places
usada no navegador deve ser limitada no Google Cloud Console por:

- domínios HTTP autorizados;
- APIs estritamente necessarias;
- cotas de uso;
- alertas de consumo.

O deploy nunca deve conter:

- `.env.local`, `.env` ou `.env.backend`;
- `firebase-service-account.json`;
- arquivos `.pem`, `.key`, `.p12`, `.jks` ou semelhantes;
- a pasta `backend_trq_bec/secrets`;
- `node_modules` ou ambientes virtuais Python.

Para gerar os dois pacotes acadêmicos de maneira automatizada, execute na raiz
do workspace:

```powershell
.\scripts\build-academic-package.ps1
```

Se a pasta de saída de uma execução anterior existir, use `-Force` somente
depois de confirmar que ela pode ser substituída.
