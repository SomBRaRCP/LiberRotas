# Matriz de autoridade dos dados

Esta matriz define qual componente decide o valor válido de cada informação.
Cache, projeção ou cópia de leitura nunca substitui a fonte autoritativa.

| Dado ou capacidade | Fonte autoritativa | Cópias ou projeções | Regra de escrita |
|---|---|---|---|
| Identidade, e-mail verificado e sessão | Firebase Authentication | ID token no aplicativo e na API | Firebase SDK no cadastro/login; Admin SDK somente em operações administrativas autorizadas |
| Função, status e permissões | PostgreSQL | custom claims do Firebase e sessão de acesso retornada pela API | somente backend administrativo |
| Perfil público e nome público único | PostgreSQL | coleção `public_profiles` do Firestore e cache local | aplicativo envia comando à API; backend valida e publica a projeção |
| Chave Pix privada atual | Firestore `private_profiles` | estado temporário da tela | somente o próprio UID empreendedor conforme regras do Firestore; não participa de autorização comercial |
| Produtos, preço, estoque e ofertas | PostgreSQL | respostas e cache de interface | somente API; frontend nunca calcula ou confirma o valor autoritativo |
| Desafio, replay e idempotência operacional | Redis | nenhuma cópia confiável no aplicativo | somente backend, com operações atômicas |
| Resgates, quantidade e ledger | PostgreSQL | resultado exibido no aplicativo | transação autoritativa no backend; não existe confirmação offline |
| Publicações e conteúdo público do Feed | Firestore, escrito pelo backend | cache local do Feed | aplicativo chama a API; Firebase Admin publica após autenticação e autorização |
| Comentários e mensagens privadas | PostgreSQL | estado em memória da tela | somente API; autoria e participantes são derivados do token e do banco |
| Interações pessoais de baixo risco | Firestore `network_interactions` | AsyncStorage | próprio UID conforme regras; não concede função, desconto ou permissão |
| Histórico local de cupons exibidos como usados | Firestore `coupon_validations` | AsyncStorage | próprio UID; é conveniência de interface, não comprova resgate comercial |
| Metadados e propriedade de mídia | PostgreSQL | resposta temporária da API | somente backend |
| Bytes das imagens | Google Cloud Storage privado | URL temporária autorizada | upload autorizado e confirmação pelo backend |
| Preferências e cache de interface | AsyncStorage | nenhuma | aplicativo; nunca guardar senha, token, chave privada ou decisão autoritativa |
| Chave privada do dispositivo | SecureStore no nativo ou IndexedDB/WebCrypto na Web | chave pública cadastrada no PostgreSQL | criada localmente; chave privada nunca é enviada ao backend |

## Regras para novas funcionalidades

Antes de adicionar uma coleção, tabela ou chave local, documente:

1. qual armazenamento é a fonte autoritativa;
2. quem pode escrever;
3. como uma cópia desatualizada é reconciliada;
4. se uma falha parcial pode conceder acesso ou confirmar operação;
5. quais dados precisam ser removidos na exclusão da conta.

Quando uma mesma operação exigir duas gravações duráveis, evite um `try/catch`
que trate a segunda gravação como se fosse atômica. Prefira uma transação em uma
única fonte; se isso não for possível e a consistência for necessária, planeje
uma outbox persistente e processamento idempotente.
