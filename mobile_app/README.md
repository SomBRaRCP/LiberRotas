# LiberRotas

Aplicativo móvel acadêmico de turismo comunitário, economia solidária e feiras locais. O projeto conecta visitantes, expositores e guias em uma experiência com feed social, cupons, mapa de Pinhais, rotas turísticas, lista de interesses e perfil personalizado.

A interface nasceu do protótipo **FeiTUR - Recriação do App Libersol**, desenvolvido no Figma, e evoluiu para o aplicativo **LiberRotas** em React Native com Expo `57.0.20`/SDK 57.

> Estado técnico revalidado em **04/09/2026**.

Preparação de APK/AAB: [BUILD_MOBILE.md](BUILD_MOBILE.md). Evidências e pendências desta retomada: [RETOMADA_2026-09-04.md](../backend_trq_bec/docs/RETOMADA_2026-09-04.md).

## Objetivo acadêmico

O projeto aplica os conteúdos trabalhados na disciplina de Desenvolvimento Mobile:

- criação e estilização de componentes;
- componentes reutilizáveis e props;
- estados com `useState`;
- efeitos com `useEffect`;
- iteração e filtragem de arrays;
- navegação entre telas com Expo Router;
- formulários e captura de dados;
- armazenamento local com AsyncStorage;
- acesso a recurso nativo com a câmera;
- execução e testes pelo Expo Go.

## Requisitos atendidos

| Requisito | Implementação |
| --- | --- |
| Cinco telas com navegação | Abas Feed, Cupons, Mapa, Mensagens e Perfil com Expo Router |
| Controle de acesso | Login único, cadastro público de dois perfis e painéis internos definidos pelo backend |
| Coleta de dados | Formulários de cadastro, edição do perfil, posts e mídia |
| Armazenamento no dispositivo | Cache de perfil, favoritos, publicações e cupons no AsyncStorage; identidade protegida fora dele |
| Recurso nativo | Leitura de QR Code e captura de imagem pela câmera |
| Imagens | Fotos de perfil, publicações, mensagens, produtos, feiras e instituições; novas mídias aceitam somente JPEG, PNG ou WebP |
| Botões e entradas | Botões reutilizáveis, `TextInput`, busca e senha protegida |
| Caixas de seleção | Interesses no cadastro/perfil e seleção de feiras |
| Listagem de conteúdo | Publicações, produtos, cupons e pontos turísticos de Pinhais gerados por arrays |
| Qualidade visual | Tokens de cores, espaçamento, bordas e componentes consistentes com o Figma |

## Funcionalidades

### Página inicial pública

- apresentação do funcionamento, propósito e benefícios do LiberRotas;
- explicação das contas de Visitante, Empreendedor e Instituição;
- cartões **Descubra**, **Conecte-se** e **Viva a experiência** abrem explicações detalhadas em uma caixa sobreposta;
- cartões **Visitantes** e **Empreendedores** abrem detalhes com o botão **Registre-se**, que leva ao cadastro público;
- cartão **Instituições** explica o processo institucional sem oferecer cadastro público; o formulário institucional continua no botão separado abaixo dos cartões;
- botão **Entrar/Registrar** no canto superior direito;
- formulário de autenticação preservado na rota `/login`;
- redirecionamento de rotas protegidas diretamente para `/login`, incluindo o retorno seguro de links compartilhados.

### Autenticação e cadastro

- autenticação real por e-mail e senha com Firebase Authentication (Web SDK);
- cadastro com `createUserWithEmailAndPassword` e login com `signInWithEmailAndPassword`;
- recuperação de senha por e-mail com `sendPasswordResetEmail`;
- tela de entrada neutra, sem seletor de função;
- aviso específico quando o login não existe, a senha está incorreta, há bloqueio temporário ou a conta foi desativada;
- validação mínima dos campos;
- cadastro com campos adaptados ao tipo de perfil;
- visitante entra imediatamente sem e-mail cadastral; empreendedor continua aguardando a confirmação do endereço;
- acompanhamento da sessão com `onAuthStateChanged` e cache local dos dados de interface;
- logout limpando sessão, perfil e preferências da conta no dispositivo.

As senhas são tratadas pelo Firebase Authentication e não são persistidas pelo aplicativo. Os módulos locais antigos de hash foram removidos; durante a hidratação, o app também apaga a chave legada `feitour:password-hashes` do AsyncStorage. Visitante não recebe mensagem cadastral: entra no Feed e recebe somente o alerta de novo dispositivo. Para empreendedor, a verificação do endereço continua enfileirada e obrigatória antes do painel.

### Tipos de perfil

| Perfil | Objetivo | Dados e recursos |
| --- | --- | --- |
| Empreendedor | Divulgar produtos, serviços e experiências | Responsável, e-mail, cidade, categoria do empreendimento, áreas de atuação, vitrine e cupons |
| Visitante | Descobrir e organizar experiências locais | Nome, e-mail, cidade, interesses, feiras salvas e cupons |

Visitante e Empreendedor são as únicas opções do cadastro público. O tipo escolhido é guardado como solicitação inicial. Depois do login, a função efetiva vem da Custom Claim e das permissões consultadas no backend.

`admin`, `support`, `security` e `institution` não são escolhidos na tela de entrada nem no cadastro público. Administrador e Suporte podem criar uma conta institucional em seus painéis; o backend fixa `role=institution`, e a instituição autenticada pode criar e encerrar somente os próprios grupos.

### Filiação institucional e relatórios

- a instituição convida um empreendedor pelo nome público único, sem pesquisar por e-mail ou UID;
- o empreendedor aceita ou recusa o convite no próprio perfil e pode manter somente uma filiação ativa;
- aceitar exige confirmação informando que a instituição verá somente totais agregados do período da filiação;
- instituição e empreendedor podem encerrar a filiação, preservando o histórico já registrado;
- o Painel Institucional mantém os três acessos principais e inclui membros/convites dentro de **Grupos** e o relatório dentro de **Relatórios**;
- o relatório filtra por grupo e pelos últimos 7, 30 ou 90 dias, separa valores por moeda e mostra linhas por vendedor;
- os números representam resgates/vendas registrados no LiberRotas e não comprovam pagamento, Pix ou liquidação financeira;
- registros legados sem valor completo são contados e excluídos dos totais em dinheiro, sem estimativa;
- relatórios e telas de filiação não exibem compradores, UIDs, tokens nem chaves Pix.

### Relógio e prazos

- o cabeçalho exibe a hora local em tempo real;
- `TrustedClockProvider` sincroniza o instante com `GET /v1/time` e atualiza contagens a cada segundo;
- ofertas, QR Codes e feiras mostram o tempo restante;
- o backend continua sendo a autoridade final para expiração, encerramento e validações de segurança, mesmo se o relógio do aparelho for alterado.

### Feed

- criação de publicação para Empreendedores e Visitantes;
- texto de até 500 caracteres;
- imagem opcional JPEG, PNG ou WebP, com até 5 MB, capturada pela câmera;
- imagem opcional selecionada da galeria;
- pré-visualização e remoção da mídia antes de publicar;
- publicação autorizada pelo backend e sincronização dos dados públicos no Firestore;
- imagem ajustada para aparecer completa e visualizador ampliado com zoom ao tocar;
- avatar do autor e navegação para o perfil público;
- Feed único com novos empreendedores, publicações, pontos, feiras, produtos e ofertas;
- barra de pesquisa global no topo, com resultados de perfis, produtos, ofertas e publicações;
- pesquisa e abertura de perfis pelo nome público único;
- filtros por categoria;
- cartões com imagem e informações do expositor;
- ações **Curtir**, **Comentar**, **Compartilhar** e **Ver perfil** conforme o tipo do cartão;
- comentários, respostas e curtidas em comentários/respostas;
- edição e exclusão das próprias publicações e dos próprios comentários;
- estado vazio quando nenhum resultado corresponde à busca.

### Mensagens e Suporte

- conversa privada iniciada pelo perfil público de outro usuário;
- caixa de entrada na aba **Mensagens**, com contagem de não lidas e abertura da conversa;
- envio idempotente com `client_message_id`, evitando duplicar a mensagem em uma repetição após timeout;
- envio opcional de imagem privada JPEG, PNG ou WebP, com até 5 MB;
- abertura da imagem da conversa em visualizador ampliado;
- bloqueio e desbloqueio de perfis; o bloqueio impede novas mensagens nas duas direções;
- botão **Entrar em contato com o SUPORTE** no próprio perfil, com assunto e mensagem;
- caixa de chamados no Painel do Suporte, com leitura, resposta e conclusão do atendimento;
- conteúdo das mensagens mantido no backend, sem gravação do corpo no AsyncStorage ou no Firestore público.

### Compartilhamento público

- perfis, publicações, produtos, ofertas, feiras, locais e eventos exibem uma ação de compartilhamento;
- todos os links usam `https://app.liberrotas.com.br`;
- conteúdo vinculado a um perfil abre `/profile/{uid}` e, quando aplicável, usa somente `tab` e `item` para selecionar e destacar a publicação, produto, oferta ou feira;
- na Web, o app tenta o compartilhamento do navegador e depois oferece cópia; no Android/iOS, abre a folha de compartilhamento do sistema;
- o retorno após autenticação aceita somente rotas internas de perfil público em formato permitido, impedindo redirecionamento para outro domínio;
- nunca são compartilhados chave Pix, QR ou payload de resgate, token, mensagem privada, comprador, relatório ou dado administrativo.

### Cupons

- filtros de categoria;
- indicação visual de cupons utilizados;
- gestão de produto, preço e estoque pelo Empreendedor;
- seleção de vários produtos, com estoque individual, para ativação em uma única operação;
- exclusão visual de produtos descontinuados da lista ativa e da vitrine, com preservação técnica do histórico autoritativo;
- emissão de ofertas para um ou mais produtos, usando por padrão o estoque total e validade de 8 horas;
- pausa, reativação e cancelamento de ofertas ao vivo;
- seleção múltipla de produtos para arquivar/excluir em uma única operação;
- seleção múltipla de ofertas para excluir, aumentar o desconto ou ampliar o tempo de validade;
- ofertas emitidas paginadas em blocos de até 20 itens;
- `client_request_id` estável durante novas tentativas do mesmo lote, impedindo aplicar desconto ou tempo duas vezes;
- QR Code com referência opaca emitida pelo backend TRQ-BEC e exibida somente na Vitrine do perfil do empreendedor;
- contador de quantidade por oferta, iniciado em `1`, limitado pelo estoque e protegido por assinatura do backend;
- seleção de 2 a 5 ofertas para gerar um único QR combinado, mantendo cada cupom e desconto independentes;
- prévia de quantidade, preço unitário, total, desconto, validade e saldo antes do resgate;
- resgate com desafio, prova do dispositivo e autorização online;
- fechamento automático do QR na tela do vendedor depois que o saldo autoritativo confirma a venda.

### Mapa de Pinhais

- centro aproximado em latitude `-25.4325` e longitude `-49.1931`;
- categorias do app para turismo, parques, feiras livres, artesanato, bordados, gastronomia, eventos e comércio local;
- pontos iniciais como Expotrade Convention Center, Parque das Águas, Espaço Boulevard, Praça Maria Antonieta, Bosque Municipal e âncoras de comércio local;
- mapa gratuito Leaflet/OpenStreetMap com Pinhais como visão principal;
- marcadores posicionados pelas coordenadas reais do item e acompanhando o zoom do mapa;
- mapa protegido contra arraste e zoom involuntários durante a rolagem da página; um clique ou toque sobre a proteção libera a interação;
- botão **MAXIMIZAR** ao lado da quantidade de pontos, abrindo o mapa em tela cheia com ação **FECHAR**;
- filtros horizontais e busca textual;
- cards com endereço, potencial turístico, origem, tags e ações;
- botão para abrir rota no Google Maps;
- botão para ver o ponto no Google Maps;
- botão para adicionar/remover o ponto da rota salva;
- publicação de somente um ponto ativo por Empreendedor autorizado, com exclusão protegida do próprio ponto antes de publicar outro;
- formulário do ponto posicionado logo abaixo de **Publicar feira ao vivo**;
- lista de pontos paginada em blocos de até 20 itens;
- publicação de feira por Empreendedor ou Instituição com `locations.publish`; visitantes apenas consultam e salvam locais;
- feiras separadas entre **Ao vivo agora** e **Histórico**, com até 20 encerradas por página;
- encerramento confirmado em modal compatível com Web e celular; ao encerrar ou excluir a feira, seu marcador sai do mapa.

### Perfil

- apresentação visual diferente para Empreendedor e Visitante;
- troca de foto de perfil pela câmera ou galeria;
- foto de perfil ampliada ao toque;
- perfil do empreendedor com botão **Vitrine**, categoria, áreas de atuação, endereço completo e chave Pix opcional privada;
- perfil do visitante com dados pessoais, interesses e experiências salvas;
- Vitrine do Empreendedor separada em postagens, produtos, ofertas e feiras; o perfil da Instituição abre diretamente suas feiras;
- gerenciamento das próprias publicações e ofertas na Vitrine;
- exclusão definitiva da própria feira no perfil, com confirmação e nova validação de autoria pelo backend;
- ofertas próprias com vendidos, estoque, tempo restante, valor institucional, relatório, exclusão e geração de QR;
- edição de nome público único, e-mail e cidade;
- botão para iniciar conversa em perfis públicos e botão próprio para abrir um chamado ao Suporte;
- armazenamento local do formulário;
- encerramento da sessão.

### Leitor de QR Code

- solicitação de permissão da câmera em tempo de execução;
- leitura limitada a códigos QR;
- pausa automática após detectar um código;
- consulta de um QR individual `trq-bec-offer-v1` ou combinado `trq-bec-offer-bundle-v1`;
- confirmação do visitante antes do fluxo protegido `begin` + prova do dispositivo + `authorize`;
- validação separada de cada cupom do QR combinado e resultado parcial explícito se algum item falhar;
- opção de ler novamente ou voltar para os cupons.

## Tecnologias

- Expo `57.0.20`/SDK 57;
- React `19.2.3`;
- React Native `0.86.3`;
- TypeScript 6 em modo estrito;
- Expo Router;
- Expo Camera;
- Expo Crypto;
- Expo Image Picker;
- Expo File System;
- Expo Image;
- Expo Video mantido apenas como dependência de leitura de conteúdo local legado e evolução futura; o plugin nativo foi removido, o app não solicita microfone e novos uploads são somente imagens;
- Firebase Firestore;
- Google Places Web Service preparado para Text Search e Nearby Search;
- Leaflet e tiles do OpenStreetMap; no Android/iOS, o mapa roda dentro de React Native WebView;
- React Native Async Storage;
- React Native Safe Area Context;
- React Native SVG;
- React Native QR Code SVG;
- Expo Vector Icons;
- ESLint com configuração oficial do Expo.

## Pré-requisitos

- Node.js instalado;
- npm;
- aplicativo Expo Go compatível com o SDK 57;
- dispositivo e computador conectados à mesma rede para leitura direta do QR Code do Metro.

## Instalação

O backend e o aplicativo possuem ambientes separados. Nenhum ambiente virtual ou `node_modules` deve entrar no ZIP acadêmico.

A pasta `.git` também não entra no ZIP acadêmico. O pacote serve para avaliação do código, enquanto commits, branches e histórico permanecem no repositório privado [SomBRaRCP/LiberRotas](https://github.com/SomBRaRCP/LiberRotas). Para continuar o desenvolvimento com histórico, use o workspace original ou clone o repositório; não execute `git init` no ZIP extraído.

O ambiente virtual recomendado para o backend fica na própria pasta do backend:

```text
E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec\.venv
```

O ponto que estava confundindo tudo é outro: a raiz é o **workspace completo**, mas o projeto Python instalável está dentro de:

```text
LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec
```

Portanto:

* `backend_trq_bec\.venv`: ambiente Python local recomendado;
* `.venv` na raiz: ambiente legado opcional, não incluído na entrega;
* executar `pip install -e .` na raiz: incorreto, porque ali não existe `pyproject.toml`;
* instalar `.\backend_trq_bec`: correto.

Os comandos abaixo usam **um único `.venv` dentro de `backend_trq_bec`**.

## 1. Saia do ambiente atual

```powershell
deactivate
```

Entre na pasta do backend:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
```

## 2. Crie o ambiente do backend se ele ainda não existir

Não apague o ambiente atual durante uma instalação normal. Se
`backend_trq_bec\.venv` ainda não existir, crie-o:

```powershell
py -m venv ".\.venv"
```

Ative:

```powershell
& ".\.venv\Scripts\Activate.ps1"
```

Confirme qual Python está sendo usado:

```powershell
(Get-Command python).Source
```

O resultado precisa apontar para:

```text
E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec\.venv\Scripts\python.exe
```

## 3. Instale o backend na própria pasta

Use o Python explícito do ambiente:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
```

Agora instale o projeto Python que está na subpasta:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -e ".[test]"
```

O detalhe decisivo está aqui:

```text
.[test]
```

O ponto representa `backend_trq_bec`, que contém o `pyproject.toml` autoritativo.

## 4. Confirme a instalação da CLI

```powershell
Test-Path ".\.venv\Scripts\trq-bec.exe"
```

O resultado esperado:

```text
True
```

Confira a localização:

```powershell
Get-Command trq-bec
```

Depois execute:

```powershell
trq-bec demo
```

Também pode usar o caminho absoluto do ambiente:

```powershell
& ".\.venv\Scripts\trq-bec.exe" demo
```

## 5. Execute os testes no diretório correto

Confirme que o terminal continua em `backend_trq_bec`:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
```

Execute os testes usando o ambiente do backend:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest tests -q
```

Quando terminar, volte à raiz do workspace:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3"
```

## Estrutura atual

```text
LiberRotas_TRQ_BEC_Workspace_v3
├── backend_trq_bec
│   ├── .venv                     ← ambiente Python local, fora do ZIP
│   ├── pyproject.toml            ← projeto Python instalável
│   ├── src
│   ├── tests
│   ├── docker-compose.yml
│   └── secrets
├── mobile_app                    ← projeto Expo/Node
├── archive                       ← artefatos históricos preservados
└── README.md
```

O ambiente legado abaixo pode existir na raiz, mas não participa dos comandos
documentados. Não o remova durante a instalação:

```text
.venv
```

Use sempre o ambiente de `backend_trq_bec`:

```powershell
& ".\backend_trq_bec\.venv\Scripts\trq-bec.exe" demo
```

```powershell
Push-Location ".\backend_trq_bec"
& ".\.venv\Scripts\python.exe" -m pytest tests -q
Pop-Location
```

O pacote Python instalável e seu ambiente local pertencem ao backend. A raiz organiza o workspace completo e não deve receber `pip install -e .`.


## Aplicativo Expo

O projeto Node/Expo está dentro de:

```text
E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app
```

Entre nessa pasta e execute:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app"

npm ci
```

Depois confira os comandos disponíveis:

```powershell
npm run
```

Para iniciar o Expo:

```powershell
npx expo start --port 8082
```

Ou, para abrir diretamente a versão Web:

```powershell
npx expo start --web --port 8082
```

O `.venv` ativo não interfere no `npm`; ele pertence ao Python. A estrutura correta é:

```text
LiberRotas_TRQ_BEC_Workspace_v3
├── .venv
├── backend_trq_bec
│   └── pyproject.toml
└── mobile_app
    └── package.json
```

Não crie um `package.json` na raiz apenas para eliminar esse erro. A raiz é o workspace; o projeto Expo mora em `mobile_app`.

Inicie o servidor do Expo:

```powershell
npx expo start --port 8082
```

Abra o Expo Go no dispositivo e leia o QR Code exibido no terminal ou na interface do Expo.

Outros comandos disponíveis:

```powershell
npx expo start --android --port 8082  # abre o fluxo Android
npx expo start --web --port 8082     # abre a versão Web de desenvolvimento
npm run lint                         # verifica a qualidade do código
```

No Windows não existe simulador oficial de iOS; use um aparelho físico ou uma
build remota quando precisar validar iOS.

## Fluxo de demonstração

1. Abra o aplicativo no Expo Go.
2. Entre com e-mail e senha ou escolha **Criar conta**.
3. No cadastro público, escolha **Empreendedor** ou **Visitante** e defina um nome público único.
4. Depois da validação da função pelo backend, navegue pelas cinco abas inferiores.
5. No Feed, escreva um texto, tire uma foto ou escolha uma imagem JPEG, PNG ou WebP da galeria e publique.
6. Ainda no Feed, toque no nome de um autor para abrir o perfil público com foto e postagens.
7. Em Mapa, filtre pontos de Pinhais, abra uma rota no Google Maps e salve locais na sua rota.
8. Em Perfil, confira a interface correspondente ao tipo de conta, troque a foto, edite os dados e pressione **Salvar perfil**.
9. Como Empreendedor aprovado, abra **Cupons > Gerenciar produtos e ofertas**, cadastre ou ative produtos com estoque e emita as ofertas.
10. Abra **Perfil > Vitrine > Ofertas**, escolha a quantidade de cada produto e gere um QR individual ou selecione de 2 a 5 ofertas para gerar um QR combinado.
11. Em outro aparelho, entre como Visitante, leia o QR, confira quantidades e totais e confirme o resgate.
12. Confira o fechamento automático do QR do vendedor e os números atualizados de vendidos e estoque.
13. Use a busca global do Feed para encontrar um perfil, produto ou publicação e abra o resultado.
14. No perfil público, envie uma mensagem; na outra conta, abra **Mensagens** e teste a opção de bloqueio.
15. No próprio Perfil, abra **Entrar em contato com o SUPORTE** e confira o chamado na conta de Suporte.
16. Saia da conta e entre novamente para conferir o papel, as publicações e os dados persistidos.

## Arquitetura

O projeto usa separação por responsabilidade:

```text
src/
├── api/
│   └── http-client.ts   # transporte HTTP autenticado e público compartilhado
├── app/
│   ├── (tabs)/
│   │   ├── _layout.tsx   # configuração e proteção das cinco abas
│   │   ├── feed.tsx      # feed, busca, filtros e favoritos
│   │   ├── cupons.tsx    # listagem de cupons e acesso à câmera
│   │   ├── feiras.tsx    # mapa de Pinhais, filtros, rotas e curadoria
│   │   ├── mensagens.tsx # caixa de entrada de mensagens privadas
│   │   └── perfil.tsx    # edição e persistência do perfil
│   ├── _layout.tsx       # providers e Stack raiz
│   ├── index.tsx         # login e redirecionamento de sessão
│   ├── profile/
│   │   └── [profileId].tsx # perfil público e Vitrine com posts, produtos, ofertas e feiras
│   ├── messages/
│   │   └── [conversationId].tsx # conversa privada
│   ├── support.tsx       # caixa de chamados da conta de Suporte
│   ├── register.tsx      # coleta de dados do cadastro
│   ├── scanner.tsx       # leitura nativa de QR Code
│   └── generate-qr.tsx   # geração de QR Code para empreendedores
├── components/
│   ├── brand-header.tsx  # cabeçalho reutilizável
│   ├── image-viewer-modal.tsx # ampliação e zoom de imagens
│   ├── post-comments.tsx # comentários, respostas e curtidas
│   └── ui.tsx            # botões, campos e seleções
├── constants/
│   └── theme.ts          # design tokens visuais do LiberRotas
├── context/
│   └── app-context.tsx   # sessão, perfil, cache local e sincronização
├── data/
│   ├── demo.ts           # tipos e conteúdo local de demonstração
│   └── pinhais.ts        # categorias, buscas e pontos curados de Pinhais
├── features/
│   ├── community/
│   │   └── api.ts        # Feed, comentários, pontos e feiras autorizados pela API
│   ├── directory/
│   │   └── api.ts        # contratos e operações de perfis e pesquisa
│   ├── institutions/
│   │   └── api.ts        # grupos, filiações, eventos financiados e relatórios
│   ├── marketplace/
│   │   └── api.ts        # catálogo, produtos, estoque e ofertas
│   ├── messaging/
│   │   └── api.ts        # conversas privadas, bloqueios e chamados de suporte
│   └── trq-bec/
│       └── api.ts        # emissão, QR, prévia, prova de posse e resgate
└── services/
    ├── firebase.ts       # inicialização do Firebase fora das rotas
    ├── cloud-data.ts     # Firestore, LGPD e coleções da rede
    └── googlePlacesService.ts # Text Search/Nearby Search para Pinhais
```

## Rotas

| Caminho | Arquivo | Acesso |
| --- | --- | --- |
| `/` | `src/app/index.tsx` | Público |
| `/register` | `src/app/register.tsx` | Público |
| `/feed` | `src/app/(tabs)/feed.tsx` | Protegido |
| `/cupons` | `src/app/(tabs)/cupons.tsx` | Protegido |
| `/feiras` | `src/app/(tabs)/feiras.tsx` | Protegido, aba Mapa |
| `/mensagens` | `src/app/(tabs)/mensagens.tsx` | Protegido |
| `/perfil` | `src/app/(tabs)/perfil.tsx` | Protegido |
| `/profile/[profileId]` | `src/app/profile/[profileId].tsx` | Protegido |
| `/messages/[conversationId]` | `src/app/messages/[conversationId].tsx` | Participante da conversa |
| `/support` | `src/app/support.tsx` | Exclusivo da conta de Suporte autorizada |
| `/scanner` | `src/app/scanner.tsx` | Acessado pela área de cupons |
| `/generate-qr` | `src/app/generate-qr.tsx` | Exclusivo do Empreendedor |

O arquivo `src/app/(tabs)/_layout.tsx` verifica a sessão antes de renderizar as abas. Usuários sem sessão são redirecionados para `/`.

## Persistência local e Firebase

O `AppProvider` coordena a hidratação, mas publica quatro contextos separados:
sessão, perfil, preferências e cache público. A função `useApp` permanece como
fachada compatível; telas novas podem consumir somente `useSessionState`,
`useProfileState`, `usePreferencesState` ou `usePublicCacheState`.

Os contextos utilizam estas chaves:

| Chave | Conteúdo |
| --- | --- |
| `feitour:profile` | cache do perfil público serializado em JSON |
| `feitour:favorites` | identificadores salvos |
| `feitour:used-coupons` | cupons validados |
| `feitour:user-posts` | cache de textos, autores, datas e referências opacas das mídias publicadas |
| `feitour:pinhais-manual-places` | pontos de Pinhais cadastrados manualmente para curadoria local |

O AsyncStorage armazena strings. Objetos e arrays são convertidos com `JSON.stringify` e recuperados com `JSON.parse`.

As chaves legadas `feitour:session` e `feitour:password-hashes` são removidas automaticamente. A sessão atual pertence ao Firebase Authentication.

O Firestore complementa o cache local com dados de rede. O app continua funcionando localmente se a conexão falhar, mas tenta sincronizar as ações principais quando o Firebase estiver acessível.

O service `src/services/googlePlacesService.ts` prepara a descoberta de pontos por Google Places com:

- Nearby Search por tipos como `tourist_attraction`, `park`, `convention_center`, `event_venue`, `farmers_market`, `gift_shop`, `restaurant` e `cafe`;
- Text Search para consultas como `artesanato em Pinhais PR`, `bordados em Pinhais PR`, `feira livre Pinhais PR`, `Parque das Águas Pinhais` e `Expotrade Convention Center Pinhais`;
- normalização para o formato usado pelo app, mantendo `googlePlaceId`, endereço, coordenadas, nota, tipos, URL do Google Maps, origem e potencial turístico.

Para chamada direta no app Expo, use a variável pública `EXPO_PUBLIC_GOOGLE_PLACES_API_KEY`. Em produção, a recomendação é chamar esse service por um backend próprio para proteger a chave, controlar cota e salvar os resultados curados no Firebase.

| Coleção Firestore | Conteúdo | Observação LGPD |
| --- | --- | --- |
| `public_profiles` | nome público, papel, cidade, categoria e interesses | não salva senha, e-mail nem foto local |
| `private_profiles` | chave Pix opcional do empreendedor | somente o próprio UID pode ler; nunca é enviada ao perfil público ou ao cache local |
| `posts` | texto, autor, papel, cidade/categoria, data e referência pública da imagem autorizada | não contém bytes da imagem nem segredo de acesso ao bucket |
| `network_interactions` | curtidas, favoritos e rotas salvas | salva somente `userId`, alvo e tipo da interação |
| `coupon_validations` | cupons validados por usuário | mantém apenas identificador do usuário e do cupom |

O arquivo `src/services/cloud-data.ts` concentra a sanitização dos dados antes do envio. Isso aplica minimização: só vai para a nuvem o que é necessário para a função social do app.

O diretório público, a pesquisa global, publicações, comentários, conversas privadas, imagens, bloqueios e chamados de Suporte são acessados pelo service do backend TRQ-BEC. O nome público é validado como único no servidor, e o aplicativo não aceita função, autoria, remetente ou destinatário confiável vindos do cache local.

### Segurança

AsyncStorage é persistente, mas não criptografado, por isso guarda somente cache de interface, preferências e dados não secretos. A senha digitada é enviada ao Firebase Authentication e não é salva pelo app. A autorização do backend depende do Firebase ID token e das claims exigidas pelo TRQ-BEC; as regras do Firestore e as restrições das chaves públicas do cliente também precisam permanecer configuradas.

O roteiro de restrições de API, separação da chave Places e preparação das chaves Web/Android/iOS está em [`FIREBASE_AUTH_SETUP.md`](./FIREBASE_AUTH_SETUP.md#9-restringir-a-chave-pública-do-firebase).

### Integração TRQ-BEC — Fase 1

O backend TRQ-BEC é a autoridade de produtos, preços, estoque, ofertas e resgates. O empreendedor cadastra o produto e emite uma oferta ao vivo; o visitante consulta a prévia e confirma o fluxo `begin` + prova do dispositivo + `authorize` usando Firebase ID token.

O QR individual carrega somente referência opaca, validade e quantidade protegida. O QR combinado agrupa de 2 a 5 payloads individuais no contrato `trq-bec-offer-bundle-v1`; ele não transforma cupons diferentes em um único desconto. O app não calcula o preço final, não reduz estoque e não conclui operação comercial offline. O scanner só mostra cada item como concluído depois de seu respectivo `decision=ALLOW`.

Cada Firebase UID usa uma identidade própria. No Android/iOS, a seed Ed25519 fica protegida pelo `expo-secure-store`. Na Web, o navegador gera o par Ed25519 pelo WebCrypto, persiste a chave privada como `CryptoKey` não exportável no IndexedDB e exporta somente a chave pública necessária ao vínculo.

O fluxo Web protegido exige uma página em contexto seguro: use `https://app.liberrotas.com.br` ou `http://127.0.0.1` no laboratório local. A identidade é separada pela origem completa — protocolo, host e porta. O domínio público, `127.0.0.1:8081` e `127.0.0.1:8082` não compartilham a mesma chave.

Toda chave nova exige login Firebase recente, com no máximo 5 minutos. Para visitante, qualquer aparelho, perfil de navegador ou origem Web fica imediatamente `ACTIVE`; o e-mail é apenas um alerta para confirmar se ele reconhece o acesso. Para empreendedor e instituição, todo novo dispositivo, inclusive o primeiro, fica `PENDING_APPROVAL` durante 10 minutos. Durante esse período, a chave ainda não participa de emissão, resgate ou outra operação TRQ-BEC protegida.

O backend envia o alerta para todo novo dispositivo de visitante, empreendedor ou instituição ao endereço consultado diretamente no Firebase Admin. O botão **Não fui eu!** abre `/account/devices`, sem token na URL. Se foi o próprio usuário, basta desconsiderar; se não foi, ele revisa os aparelhos e troca a senha. A página **Segurança da minha conta** mostra a contagem, permite reenviar o alerta de dispositivos pendentes depois de 60 segundos e lista os estados `ACTIVE`, `PENDING_APPROVAL` e `REVOKED`. O reenvio não reinicia a contagem. Para empreendedor e instituição, ao completar 10 minutos o backend promove automaticamente o aparelho para `ACTIVE`, mesmo quando o alerta SMTP falhou.

Limpar os dados do site ou o IndexedDB perde a chave local, mas não apaga o registro autoritativo; uma nova identidade pode ser cadastrada e liberada após o período de segurança.

Ao pressionar **Alterar senha**, o aplicativo deve avisar que todos os dispositivos, inclusive o atual e os pendentes, serão desconectados. A confirmação revoga os registros de dispositivos e os refresh tokens Firebase. Este continua sendo um perfil de laboratório: a chave Web não exportável não possui atestação de hardware e um XSS na mesma origem ainda pode solicitar assinaturas enquanto a aplicação estiver aberta.

Consulte [`TRQ_BEC_INTEGRATION.md`](./TRQ_BEC_INTEGRATION.md) para configuração no Windows, pré-condições da conta, endpoints e roteiro de teste.

## Permissões de câmera e mídia

`expo-camera` está configurado em `app.json` com uma mensagem de permissão em português para leitura de QR Code. O plugin define `microphonePermission: false` e `recordAudioAndroid: false`. A tela usa `useCameraPermissions` antes de montar `CameraView`.

A câmera deve ser validada em um dispositivo físico pelo Expo Go. No navegador, o comportamento depende das permissões e do suporte à câmera do ambiente.

`expo-image-picker` solicita acesso à câmera ou às imagens somente quando a pessoa toca nas ações do Feed, de mensagens, foto de perfil, produto, feira ou instituição. O plugin também define `microphonePermission: false`. Novos uploads aceitam somente JPEG, PNG e WebP de até 5 MB. O backend mantém um ativo lógico e gera somente `thumbnail` e `display`; não grava bytes ou URL assinada no PostgreSQL/Firestore. Vídeos e outros arquivos não aparecem como opção de publicação nesta versão; `expo-video` não está na lista `expo.plugins`, mas a dependência permanece para reproduzir publicações legadas.

## Identidade visual

Os principais tokens estão em `src/constants/theme.ts`:

- azul primário: `#2B5CC7`;
- azul escuro: `#0F2E6E`;
- laranja: `#FF6E17`;
- fundo claro: `#FCFAF2`;
- creme: `#F5EDDB`;
- borda: `#E0D6C2`.

Centralizar esses valores evita diferenças entre telas e simplifica futuras alterações no design.

## Qualidade e validação

Comandos utilizados para conferir o projeto:

```powershell
npm.cmd test
npm.cmd run test:firestore
npx.cmd tsc --noEmit
npm.cmd run lint
npx.cmd expo-doctor
npx.cmd expo install --check
npx.cmd expo config --type public
npm.cmd audit --omit=dev
```

Resultado reconferido em 04/09/2026:

- Vitest: `44` testes aprovados para transporte HTTP, renovação de claims,
  revogação de sessão, diretório, comunidade, instituições, marketplace, fluxo
  TRQ-BEC, mensagens, bloqueios e suporte;
- regras Firestore: aprovadas separadamente com `npm run test:firestore` no emulador local; essa suíte não faz parte da contagem Vitest e sua quantidade de asserts não é fixada neste documento;
- interface: os 44 testes incluem 10 casos de renderização do painel autorizado na Web, cobrindo carregamento, função, estado de acesso, dispositivo, permissões adicionais e seleção de ferramenta. As dependências de sessão e navegação são simuladas; isso não substitui navegação autenticada nem testes nativos;
- TypeScript: aprovado;
- ESLint: aprovado;
- compatibilidade Expo: aprovada com `npx expo install --check`;
- Expo Doctor: `21/21` verificações aprovadas;
- compatibilidade Expo: aprovada; `@expo/ui`, `expo`, `expo-constants`,
  `expo-image-picker`, `expo-linking`, `expo-location`, `expo-router`,
  `expo-splash-screen`, `expo-web-browser` e `react-native-screens` estão nas
  versões esperadas pelo SDK 57;
- configuração pública do Expo: mensagens de permissão usam LiberRotas,
  `microphonePermission` e `recordAudioAndroid` estão desativados e não existe
  plugin explícito `expo-video`;
- exportação Web estática: aprovada;
- auditoria da árvore de produção: `3` vulnerabilidades moderadas e `0` altas ou críticas, originadas na cadeia upstream do `expo-router`. Não use `npm audit fix --force`, pois a solução proposta é incompatível com o SDK 57.

## Limitações atuais

- função, status, permissões e painel dependem da validação online no backend;
- pontos iniciais de Pinhais ainda partem de curadoria local; pontos e feiras publicados por empreendedores vêm do backend;
- na Web, o mapa interativo usa Leaflet/OpenStreetMap; no nativo, a integração continua adaptada às capacidades disponíveis, sem `react-native-maps`;
- Google Places está preparado como service, mas não é chamado automaticamente sem chave configurada;
- alguns perfis, produtos e pontos demonstrativos permanecem como conteúdo acadêmico inicial;
- novos uploads públicos e privados aceitam somente imagens; vídeo e outros anexos ficam para uma fase futura;
- imagem de evento financiado permanece fora do escopo até existir requisito acadêmico confirmado;
- o Firestore recebe projeções públicas e interações; decisões comerciais, mensagens privadas, comentários e metadados de mídia pertencem ao backend;
- leitura e resgate de ofertas TRQ-BEC exigem conexão com o backend e falham sem autorização online;
- testes da câmera dependem de aparelho físico.

## Evoluções possíveis

- manter `npm run test:firestore` aprovado antes de revisar e publicar as regras de segurança do Firestore em cada ambiente;
- restringir as chaves públicas Firebase/Google por domínio, aplicativo e APIs necessárias;
- permitir substituição e exclusão visual de logos/capas antigos quando o requisito acadêmico exigir histórico de imagens;
- substituir o mapa em WebView por integração nativa quando o requisito acadêmico justificar;
- ampliar auditoria e monitoramento dos resgates autorizados pelo TRQ-BEC;
- notificações sobre eventos e cupons;
- suporte controlado a vídeo e outros anexos depois de definir limites, processamento e políticas;
- ampliar os testes automatizados atuais para componentes e fluxos completos de
  login, navegação, mensagens e resgate em aparelho.

## Referências

- [Protótipo FeiTUR no Figma](https://www.figma.com/design/SdocHOTsmo0DxuvK7v2KAy/FeiTUR---Recria%C3%A7%C3%A3o-do-App-Libersol)
- [Expo SDK 57](https://docs.expo.dev/versions/v57.0.0/)
- [Expo Router SDK 57](https://docs.expo.dev/versions/v57.0.0/sdk/router/)
- [Expo Camera SDK 57](https://docs.expo.dev/versions/v57.0.0/sdk/camera/)
- [Expo Crypto SDK 57](https://docs.expo.dev/versions/v57.0.0/sdk/crypto/)
- [Expo Image Picker SDK 57](https://docs.expo.dev/versions/v57.0.0/sdk/imagepicker/)
- [Expo File System SDK 57](https://docs.expo.dev/versions/v57.0.0/sdk/filesystem/)
- [Expo Video SDK 57](https://docs.expo.dev/versions/v57.0.0/sdk/video/)
- [AsyncStorage no Expo SDK 57](https://docs.expo.dev/versions/v57.0.0/sdk/async-storage/)
- [Firebase Firestore](https://firebase.google.com/docs/firestore)
- [React Native QR Code SVG](https://github.com/Expensify/react-native-qrcode-svg)

## Licença

Consulte [`LICENSE`](./LICENSE) nesta pasta.
