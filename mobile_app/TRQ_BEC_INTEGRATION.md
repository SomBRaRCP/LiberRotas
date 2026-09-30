# TRQ-BEC no LiberRotas — Fase 1

**Escopo:** oferta presencial com desconto, estoque limitado e prova de dispositivo  
**Autoridade comercial:** backend TRQ-BEC + PostgreSQL  
**Fora desta fase:** pedido, pagamento, estorno, PQC de produção, decisão por IA e resgate offline

O funcionamento ponta a ponta, incluindo as cinco portas da autorização e a
separação de autoridade entre aplicativo, Redis e PostgreSQL, está documentado em
[`../backend_trq_bec/docs/FLUXO_TRQ_BEC.md`](../backend_trq_bec/docs/FLUXO_TRQ_BEC.md).

## O que o aplicativo faz

O aplicativo coleta comandos e mostra respostas do backend:

- empreendedor cadastra produto, preço e estoque;
- empreendedor emite, pausa, reativa, exclui ou cancela uma oferta;
- a Vitrine gera QR com referência opaca (`token_ref`) e quantidade assinada;
- de 2 a 5 ofertas do mesmo vendedor podem ser agrupadas em um QR combinado;
- visitante consulta produto, quantidade, preço, desconto, validade e saldo antes de confirmar;
- na confirmação, o aparelho assina o desafio retornado pelo backend;
- somente `decision=ALLOW` é mostrado como resgate concluído.

O aplicativo não calcula o preço final, não reduz estoque e não autoriza um
resgate offline. O registro em Firebase/AsyncStorage é apenas um reflexo para a
interface; o efeito comercial ocorre de forma transacional no PostgreSQL.

## Configuração no Windows

Na pasta `E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app`, copie o
modelo se ainda não existir um arquivo local:

```powershell
Copy-Item ".env.example" ".env.local"
```

No celular físico, não use o IPv4 do computador, `127.0.0.1` ou `localhost`.
A API do Docker permanece protegida no loopback do Windows e o aplicativo deve
usar o endpoint público HTTPS pelo Cloudflare Tunnel.

Configure `mobile_app/.env.local` assim:

```env
EXPO_PUBLIC_TRQ_BEC_API_URL=https://api.liberrotas.com.br
EXPO_PUBLIC_TRQ_BEC_ALLOW_LEGACY_DEMO=false
```

Não libere a porta TCP `8787` na rede local. Depois de alterar o `.env.local`,
encerre o Expo e inicie novamente para incorporar a nova URL ao aplicativo.

Toda variável `EXPO_PUBLIC_*` é incorporada ao app. Nunca coloque ali chave
privada, credencial Firebase Admin, senha do PostgreSQL ou segredo do backend.

## Pré-condições de conta

O login Firebase sozinho não libera operações comerciais:

1. a conta precisa ter a custom claim `role=entrepreneur`;
2. um administrador precisa cadastrar o empreendedor como `ACTIVE`;
3. o cadastro administrativo vincula UID, estabelecimento e nome comercial;
4. o cliente Android/iOS ou Web cadastra sua chave pública em `/devices/enroll`.

Quando essas etapas faltarem, o app exibe a recusa do backend. Não contorne
`MERCHANT_ACCOUNT_INACTIVE` pelo cliente.

## Contratos usados pelo aplicativo

Todos os endpoints abaixo exigem Firebase ID token no cabeçalho
`Authorization: Bearer ...`.

### Empreendedor

- `POST /v1/marketplace/products`
- `GET /v1/marketplace/products/mine`
- `POST /v1/marketplace/products/batch/archive`
- `POST /v1/marketplace/products/batch/activate`
- `POST /v1/marketplace/products/{product_id}/stock`
- `GET /v1/marketplace/offers/mine`
- `GET /v1/marketplace/offers/{offer_id}/qr?quantity=N`
- `DELETE /v1/marketplace/offers/{offer_id}`
- `POST /v1/marketplace/offers/{offer_id}/status`
- `POST /v1/trq-bec/devices/enroll`
- `POST /v1/trq-bec/coupons/issue`

A emissão envia `product_id`, tipo/valor do desconto, limite, validade e
`device_key_id`. Preço original, desconto em centavos, preço final e saldo são
devolvidos pelo backend. O QR da Vitrine acrescenta `quantity`; acima de uma
unidade, o backend devolve `quantity_proof_b64u` para impedir adulteração.

### Visitante

1. `POST /v1/trq-bec/coupons/preview` — consulta sem efeito comercial;
2. `POST /v1/trq-bec/devices/enroll` — cadastro idempotente da chave;
3. `POST /v1/trq-bec/coupons/redeem/begin` — operação, sessão e desafio;
4. assinatura Ed25519 local de `proof_message_b64u`;
5. `POST /v1/trq-bec/coupons/redeem/authorize` — decisão e commit autoritativo.

O backend revalida validade, estado, estoque, limite, quantidade, vínculo do
usuário, desafio e replay no momento da autorização. A prévia não reserva
unidade. Em QR combinado, o cliente repete o fluxo para cada oferta e apresenta
o resultado individual; uma falha não pode ser escondida como sucesso total.

## Chave do dispositivo

O protótipo usa Ed25519, mas armazena a identidade de forma diferente em cada
plataforma:

| Plataforma | Perfil enviado ao backend | Armazenamento local |
|---|---|---|
| Android/iOS | `EXPO_SECURE_STORE_LAB` | seed protegida pelo `expo-secure-store`, separada por Firebase UID |
| Web | `WEB_CRYPTO_INDEXEDDB_LAB` | chave privada `CryptoKey` não exportável, criada pelo WebCrypto e persistida no IndexedDB |

Na Web, operações protegidas exigem WebCrypto Ed25519, IndexedDB e contexto
seguro. Use o domínio HTTPS ou, no laboratório deste PC, uma página aberta por
`http://127.0.0.1`; não use HTTP por IP da rede local. A identidade pertence à
origem completa do navegador. Assim, trocar protocolo, host ou porta cria outra
identidade, mesmo no mesmo computador.

Toda chave nova exige login recente — até 5 minutos, por padrão. Repetir a mesma
chave é idempotente. Para visitante, todo aparelho fica `ACTIVE` imediatamente e
o e-mail é apenas um alerta. Para empreendedor e instituição, todo aparelho novo,
inclusive o primeiro, fica `PENDING_APPROVAL`, sem bloquear a sessão autenticada.
O backend libera essas chaves automaticamente depois de 10 minutos.
Se aparecer `RECENT_AUTHENTICATION_REQUIRED`, saia, entre novamente e repita o
cadastro da chave nova.

Todo dispositivo novo desses três perfis gera um alerta no e-mail registrado no Firebase e oferece o botão **Não fui
eu!** para `/account/devices`. Se o próprio usuário fez o acesso, ele desconsidera
a mensagem. Se não reconhecer, revisa os aparelhos e troca a senha. O e-mail não
contém token nem autoriza o dispositivo. O reenvio exige autenticação recente,
aplica cooldown de 60 segundos e preserva o horário original da liberação.

Um dispositivo pendente não participa de emissão, resgate ou autorização
TRQ-BEC. Em **Segurança da minha conta**, o titular consulta seus estados
`ACTIVE`, `PENDING_APPROVAL` e `REVOKED`. Ao alterar a senha, o app avisa que todos
os aparelhos, inclusive o atual e os pendentes, serão desconectados.

Não limpe os dados do site nem o IndexedDB durante uma operação: a chave privada
não pode ser exportada ou recriada com o mesmo identificador. A perda da chave
local não apaga o registro autoritativo; a nova identidade pode ser cadastrada e
liberada após o cooldown. A chave não exportável reduz exposição acidental, mas um
XSS executado na mesma origem ainda pode usá-la como oráculo de assinatura. Os
dois perfis são de laboratório e não fornecem atestação de hardware. Uma evolução
nativa de produção deve usar Android Keystore/Apple Secure Enclave; PQC permanece
bloqueado até existir provider auditado.

## Como testar

Na pasta `mobile_app`:

```powershell
if (Test-Path -LiteralPath "package-lock.json") { npm ci } else { npm install }
npx tsc --noEmit
npm run lint
npx expo install --check
npx expo start --port 8082
```

Teste o fluxo real em dois aparelhos ou em dois usuários:

1. entre como empreendedor aprovado;
2. abra **Cupons > Gerenciar produtos e ofertas**;
3. cadastre ou ative dois produtos e emita duas ofertas;
4. abra **Perfil > Vitrine > Ofertas**, escolha as quantidades e gere um QR combinado;
5. entre como visitante em outro aparelho;
6. abra **Cupons > Abrir leitor de QR Code**;
7. consulte itens, quantidades e totais e só então confirme;
8. verifique o fechamento automático do QR e a redução do saldo/estoque pelas quantidades.

O `package.json` possui testes Vitest específicos para transporte HTTP,
marketplace, validação estrutural do QR e encadeamento `begin -> assinatura ->
authorize`. Execute `npm test` junto com TypeScript, ESLint e a compatibilidade
dos pacotes Expo. Fluxos de câmera, navegação e resgate completo ainda exigem
validação manual em aparelho físico.

As fronteiras do cliente ficam em:

- `src/features/marketplace/api.ts`: catálogo, produtos, estoque e ofertas;
- `src/features/trq-bec/api.ts`: emissão, QR, prévia, prova de posse e resgate;
- `src/security/trq-bec/service.ts`: fachada compatível usada pelas telas atuais.
