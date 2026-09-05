# Validação atual do backend — 1 de setembro de 2026

Este registro descreve o que foi verificado no workspace atual. Ele não substitui
homologação externa, teste de carga, auditoria independente ou teste manual em
aparelhos reais.

## Ambiente conferido

- Windows 10/11 com PowerShell;
- pacote `trq-bec 0.6.0a1`;
- PostgreSQL 16 e Redis 7 em contêineres saudáveis;
- API saudável em `127.0.0.1:8787`;
- Web Nginx saudável em `127.0.0.1:8081`;
- migrations `001_initial` até `021_institution_live_fairs` confirmadas no PostgreSQL
  operacional em 05/08/2026; a migration `020` é aditiva e não fez backfill.

## Resultados automatizados

Executado na pasta `backend_trq_bec`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Resultado:

```text
197 passed, 63 subtests passed
```

A bateria inclui regressão criptográfica/comercial e testes para:

- visitante com liberação imediata e alerta; empreendedor e instituição com cooldown e ativação automática de dispositivos;
- SMTP ausente, parcial, inválido ou falhando sem falso `SENT`;
- autorização, anti-replay, idempotência e concorrência;
- produto, estoque, oferta, ações em massa e exclusão operacional;
- quantidade assinada no QR, adulteração, saldo insuficiente e commit por
  quantidade;
- mídia privada, processamento de imagem e configuração do GCS;
- variantes WebP, cache público controlado, fallback legado e exclusão derivada;
- mensagens, comentários, respostas, curtidas, edição e exclusão por autoria;
- criação e exclusão de feira por empreendedor ou instituição, com bloqueio para outro autor;
- filiação, relatórios e eventos institucionais financiados;
- fronteiras dos routers de comunidade, comunicação, instituições, marketplace e cupons.

O projeto contém `197` testes coletados. Os `63 subtestes` pertencem às matrizes
internas executadas por esses testes.

Os contratos OpenAPI foram regenerados e validados como JSON. O contrato operacional contém `94` caminhos e `106` operações; os escopos público e administrativo permanecem separados, e as rotas `/internal/` não são expostas no contrato público.

## PostgreSQL e Redis reais

O banco operacional confirmou as 21 migrations. Os probes disponíveis para
ambientes isolados são:

```text
tests/postgres_phase1_probe.py
tests/postgres_batch_idempotency_probe.py
tests/postgres_institution_reports_probe.py
tests/postgres_funded_events_probe.py
tests/postgres_multi_device_probe.py
```

Esses probes não devem ser executados contra o banco principal sem revisar o
alvo. Eles criam dados de ensaio e servem para validar concorrência, transações e
isolamento em uma base preparada para testes.

## Validação complementar do aplicativo

Na pasta `mobile_app`, execute:

```powershell
npm.cmd test
npm.cmd run test:firestore
npx.cmd tsc --noEmit
npm.cmd run lint
npx.cmd expo-doctor
npx.cmd expo install --check
npm.cmd audit --omit=dev
```

A suíte Vitest contém `34` testes em `9` arquivos para transporte HTTP, diretório, comunidade,
instituições, marketplace, fluxo TRQ-BEC, mensagens, cache de mídia, bloqueios e chamados de suporte. A validação das regras Firestore é executada separadamente por `npm.cmd run test:firestore`, com emulador local e sem entrar na contagem do Vitest.

Em 01/09/2026, TypeScript e ESLint foram aprovados; Expo `57.0.19`/SDK 57, React Native `0.86.3` e React `19.2.3` foram confirmados; Expo Doctor passou `21/21`. `npm audit --omit=dev` registrou `3` vulnerabilidades moderadas e `0` altas ou críticas na cadeia upstream do `expo-router`. Não use `npm audit fix --force`, pois a troca proposta é incompatível com a árvore Expo atual.

Depois faça o teste manual com contas distintas:

1. empreendedor cadastra ou ativa produtos com estoque;
2. emite uma ou mais ofertas;
3. abre **Perfil > Vitrine > Ofertas**;
4. gera QR individual com quantidade maior que `1`;
5. gera QR combinado com 2 a 5 ofertas e quantidades independentes;
6. visitante confere itens e totais e confirma o resgate;
7. vendedor confirma fechamento automático do QR, vendidos e estoque;
8. publique imagem, comente, responda, curta, edite e exclua conteúdo próprio;
9. envie imagem em conversa privada e confirme bloqueio;
10. valide evento financiado com instituição e empreendedor afiliado.
11. crie uma feira como empreendedor e como instituição, exclua-a no próprio perfil e confirme que outra conta não vê o botão nem consegue excluí-la pela API.

## Limites desta validação

- entrega de e-mail real depende do provedor SMTP, DNS e endereço do Firebase;
- câmera, galeria, Expo Go e permissões precisam de aparelho físico;
- o QR combinado produz operações independentes; falha parcial deve ser exibida;
- Ed25519/SecureStore/WebCrypto continuam sendo perfil de laboratório;
- em 05/08/2026, o endpoint local `/health/crypto` informou provider
  `UNAVAILABLE` e `ready=false`; portanto, a prontidão PQC continua bloqueada;
- esta validação não prova MFA, FIPS 140-3, hardware atestado, resistência
  pós-quântica, pagamento, estorno ou liquidação financeira;
- resgate comercial offline continua proibido.
