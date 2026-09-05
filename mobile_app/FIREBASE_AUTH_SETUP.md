# LiberRotas — Firebase Authentication, Firestore e chave pública

> Revisado em **01/09/2026**.

## 1. Ativar Firebase Authentication no Console

1. Acesse o Firebase Console.
2. Entre no projeto `liberrotas-fe0af`.
3. Vá em **Build > Authentication**.
4. Clique em **Get started / Começar** caso ainda não esteja iniciado.
5. Abra a aba **Sign-in method / Método de login**.
6. Ative **Email/Password / E-mail e senha**.
7. Salve.

Sem esse passo, o app retornará erro de autenticação mesmo com o código correto.

## 2. O que mudou no código

Arquivos principais alterados:

- `src/services/firebase.ts`
- `src/context/app-context.tsx`
- `src/app/index.tsx`
- `src/app/register.tsx`
- `src/services/cloud-data.ts`
- `firestore.rules`

Mudança estrutural:

- Antes: login local com hash e `AsyncStorage`.
- Agora: cadastro e login usam Firebase Authentication.
- O `uid` do Firebase passa a ser o `profile.id` oficial.
- O Firestore usa esse `uid` para validar escrita nas regras.

## 3. Fluxo de cadastro

1. Usuário preenche cadastro no app.
2. `register()` chama `createUserWithEmailAndPassword()`.
3. Firebase cria usuário e devolve `uid`.
4. O app guarda o cadastro como solicitação local no `AsyncStorage`.
5. O backend consulta claims, função, status e permissões.
6. Sem autorização reconhecida, o usuário permanece em **Acesso pendente** e nenhum perfil público é criado antecipadamente.

## 4. Fluxo de login

1. Usuário informa somente e-mail e senha; não existe seletor de função na entrada.
2. `login()` chama `signInWithEmailAndPassword()`.
3. O app envia somente o ID Token para `GET /v1/access/me`.
4. O backend valida a Custom Claim, a função, o status e as permissões no PostgreSQL.
5. O destino é decidido pela resposta autorizada: interface simples do visitante, painel do empreendedor ou painel interno correspondente.

As opções **Visitante** e **Empreendedor** existem somente em **Criar conta**. Instituição não é cadastrada publicamente: somente Administrador ou Suporte autorizado pode criá-la pelo painel interno.

## 5. Publicar regras Firestore

No Firebase Console:

1. Vá em **Build > Firestore Database**.
2. Abra a aba **Rules / Regras**.
3. Cole o conteúdo de `firestore.rules`.
4. Clique em **Publish / Publicar**.

As regras liberam a leitura necessária para usuários autenticados. Publicações, pontos e feiras são escritos pela API após autorização; o cliente não grava diretamente nessas coleções.

### Testar as regras antes de publicar

Na pasta `mobile_app`, com JDK 21 instalado, execute:

```powershell
npm.cmd run test:firestore
```

Essa suíte é separada dos `34` testes Vitest. O comando inicia o emulador Firestore com um projeto local de demonstração, carrega `firestore.rules` e encerra o emulador ao final. Ele não deve ler nem gravar dados do projeto Firebase real. A quantidade de asserts não é registrada aqui porque pode mudar sem alterar a suíte principal.

Publicar regras continua sendo uma ação manual e consciente. O teste local não executa `firebase deploy`.

## 6. Teste manual obrigatório

Use endereços de teste sob seu controle. Não coloque senhas, ID Tokens ou
credenciais administrativas neste documento.

Checklist:

- Criar conta visitante.
- Sair.
- Entrar como visitante.
- Criar conta empreendedor.
- Sair.
- Entrar como empreendedor.
- Confirmar que cada conta abre a interface determinada pelo backend, sem seletor de função no login.
- Criar postagem com imagem.
- Comentar, responder, editar e excluir conteúdo próprio.
- Salvar favorito/rota.
- Emitir oferta, gerar QR pela Vitrine e validar o resgate em outra conta.
- Conferir documentos no Firestore.

## 7. Coleções esperadas no Firestore

- `public_profiles/{uid}`
- `private_profiles/{uid}` somente para a chave Pix opcional do próprio empreendedor
- `posts/{postId}`
- `network_interactions/{uid_target_kind}`
- `coupon_validations/{uid_couponId}`

Função, status, permissões, mensagens privadas, comentários, eventos
institucionais e metadados autoritativos de mídia ficam no PostgreSQL. Os bytes
das imagens ficam no Google Cloud Storage privado. Não crie `admin_users` no
Firestore para conceder função: os painéis são liberados por Custom Claims e
permissões validadas no backend.

## 8. Observação importante

As contas antigas de demonstração local não funcionam mais como login real.
Agora é necessário criar contas pelo cadastro do app ou pelo painel Authentication do Firebase.

## 9. Restringir a chave pública do Firebase

A chave usada pelo Firebase Web SDK identifica o projeto, mas não autoriza acesso aos dados. A autorização continua sendo responsabilidade do Firebase Authentication, das regras do Firestore e, quando ativado, do App Check.

O Firebase aplica restrições de API automaticamente às chaves que ele cria. Mesmo assim, confirme a chave do app no projeto `liberrotas-fe0af`:

1. abra **Google Cloud Console > APIs e serviços > Credenciais**;
2. abra a chave associada ao Web App do Firebase, sem copiar o valor para documentos ou terminal;
3. em **Restrições de API**, escolha **Restringir chave**;
4. preserve somente as APIs exigidas pelos recursos atuais:
   - `firebase.googleapis.com` — Firebase Management API;
   - `logging.googleapis.com` — Cloud Logging API;
   - `identitytoolkit.googleapis.com` — Firebase Authentication;
   - `securetoken.googleapis.com` — renovação dos tokens de autenticação;
   - `datastore.googleapis.com` — Cloud Firestore;
   - `firestore.googleapis.com` — Cloud Firestore;
5. confirme que Places API, Gemini/Generative Language API e outras APIs faturáveis não estão na lista dessa chave;
6. salve e teste cadastro, login, recuperação de senha e leitura/escrita permitida no Firestore.

Use uma chave separada em `EXPO_PUBLIC_GOOGLE_PLACES_API_KEY` para a Places API. Não reutilize a chave Firebase.

### Restrições de aplicativo

O app atual usa o Firebase JavaScript SDK tanto no Web quanto no Expo Go. Uma chave aceita somente um tipo de restrição de cliente, portanto não aplique uma restrição exclusiva de navegador à mesma chave antes de separar os aplicativos por plataforma.

Para a publicação Web, use uma chave dedicada e preserve estes referenciadores:

- `https://liberrotas.com.br/*`;
- `https://www.liberrotas.com.br/*`;
- `https://app.liberrotas.com.br/*`;
- os domínios Firebase Hosting realmente utilizados;
- `http://localhost:8081/*`, `http://127.0.0.1:8081/*` e
  `http://127.0.0.1:8082/*` apenas na chave de desenvolvimento.

Para builds Android/iOS, primeiro defina `android.package` e `ios.bundleIdentifier` no `app.json`, registre os aplicativos no Firebase e crie chaves próprias. Android exige package name e SHA-1; iOS exige bundle ID.
