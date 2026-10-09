# Minhas compras: contexto e verificação

Consulte este arquivo para histórico, gastos e economia do visitante na aba Cupons. Para geração de QR e baixa de estoque, consulte [QR_VENDAS.md](QR_VENDAS.md).

## Comportamento e autoridade

- **Minhas compras** aparece na aba Cupons do visitante com `coupons.redeem`, antes das ofertas públicas. Mostra número de compras, unidades compradas, gasto e economia por moeda, além de vendedor/estabelecimento, produto, data e quantidade em cada compra.
- Os dados vêm de `GET /v1/trq-bec/coupons/purchases/mine?limit=20&offset=0`. O backend exige conta visitante autorizada e permissão de resgate; filtra pelo UID autenticado, sem aceitar outro comprador como escopo. As respostas seguem o `Cache-Control: no-store` existente.
- Fonte: `coupon_redemptions` no PostgreSQL, somente `status='REDEEMED'`. Prévia, QR aberto, operação pendente ou negada e espelhos em Firestore/AsyncStorage não são compras confirmadas.
- `final_amount_minor`, `original_amount_minor` e `amount_saved_minor` são valores históricos **totais da compra**, já incluindo `quantity`. Nunca multiplicar novamente pela quantidade nem recalcular com o preço atual.
- Os totais abrangem todas as páginas; moedas diferentes ficam separadas. Registros antigos com valor final nulo apresentam gasto indisponível e são explicitamente excluídos do total gasto conhecido. A economia registrada continua disponível.
- Produto arquivado e oferta encerrada não removem compras do histórico. Nomes do produto e do vendedor vêm dos cadastros atuais; não são snapshots históricos de nomes. Valores financeiros e quantidade vêm do resgate.
- O gasto representa o valor comercial do resgate confirmado no app, não comprovação de transferência Pix ou liquidação bancária.
- A consulta é somente leitura, não movimenta estoque nem saldo. Não exigiu migration: snapshots vieram da migration `010_institution_seller_reports.sql`; o índice por comprador/data já existe na `002_marketplace_phase1.sql`.
- Reabrir Cupons ou tocar em **Atualizar minhas compras** recarrega o relatório. **Ver compras anteriores** pagina os registros. Respostas de requisições antigas são descartadas; o componente é recriado quando o UID muda.

## Arquivos necessários

- [Cupons](../../mobile_app/src/app/(tabs)/cupons.tsx): montagem por papel e permissão.
- [Consulta e estados da tela](../../mobile_app/src/components/visitor-purchases.tsx): foco, atualização, paginação, carregamento e erro.
- [Apresentação](../../mobile_app/src/components/purchase-report.tsx) e [tipos/valores](../../mobile_app/src/features/marketplace/purchases.ts).
- [API do app](../../mobile_app/src/features/marketplace/api.ts): `loadOwnPurchases`; fachada em `src/security/trq-bec/service.ts`.
- [Router](../../backend_trq_bec/src/trq_bec/server/routers/coupons.py), [serviço](../../backend_trq_bec/src/trq_bec/server/service.py), [PostgreSQL](../../backend_trq_bec/src/trq_bec/server/store.py) e [store de testes](../../backend_trq_bec/src/trq_bec/server/memory_store.py): localizar `get_visitor_purchases` com `rg`, sem abrir os arquivos inteiros.
- [Contrato do backend](../../backend_trq_bec/src/trq_bec/server/models.py): `VisitorPurchasesResponse`, `VisitorPurchaseResponse`, `PurchaseCurrencyTotalResponse`.

## Evidências verificadas em 08/10/2026

- Backend: **246 testes e 63 subtestes passaram**. App: **66 testes passaram**; **7 testes Firestore passaram** separadamente no emulador. TypeScript, lint e build Web/API passaram.
- [Testes do histórico](../../backend_trq_bec/tests/test_visitor_purchases.py): isolamento por comprador, autenticação, papel, conta suspensa, permissão, confirmação real do serviço, quantidade, preservação após mudança de preço/arquivamento, paginação, moedas e legado.
- [Testes da apresentação/API](../../mobile_app/tests/visitor-purchases.test.tsx): vendedor/produto, valores sem multiplicação duplicada, histórico vazio, gasto indisponível, moedas e consulta autenticada.
- [Probe PostgreSQL](../../backend_trq_bec/tests/postgres_visitor_purchases_probe.py): compra de 3 unidades, gasto 12.000 centavos, economia 3.000, isolamento, prévia/operação pendente fora do relatório, confirmação idempotente, paginação e legado. Executado com migrations num banco temporário `trq_bec_purchases_probe_*`, removido ao terminar. Fixtures e simulação do prazo de aprovação do dispositivo só nesse banco; sem enviar e-mails. Banco operacional preservado.
- Web, API, PostgreSQL e Redis ficaram saudáveis após `.\INICIAR_LIBERROTAS.ps1 -Rebuild`. OpenAPI em execução inclui `getOwnVisitorPurchases`; consulta sem autenticação retorna 401; `/cupons` responde 200.
- Navegador com sessão visitante existente: mostrou e atualizou uma compra previamente confirmada de 2 unidades de Pano de prato, vendedor Reginaldo Camargo, R$ 24,00 gastos e R$ 6,00 economizados. A confirmação dessa compra não foi executada pelo agente; a verificação foi de leitura/atualização do histórico. Prévia adicional do componente conferida com dados fictícios.

Testes são evidências pontuais. Fluxo completo de compra entre aparelhos, leitura física do QR e liquidação financeira não foram acompanhados. O provider pós-quântico permanece indisponível; não inferir prontidão criptográfica para produção.

## Repetir quando necessário

Em `mobile_app/`: `npm.cmd test -- tests/visitor-purchases.test.tsx tests/marketplace-api.test.ts`, `npm.cmd run typecheck`, `npm.cmd run lint`.

Em `backend_trq_bec/`: `.\.venv\Scripts\python.exe -m pytest tests/test_visitor_purchases.py tests/test_marketplace_coupons_routers.py -q`. O probe exige `TRQ_BEC_DATABASE_URL` apontando para banco temporário já migrado com o prefixo indicado; nunca rodar no banco operacional.

Na raiz, `.\INICIAR_LIBERROTAS.ps1 -Rebuild` aplica mudanças à Web/API locais preservando volumes. Para conferir na interface: entrar como visitante, abrir **Cupons → Minhas compras** e tocar em **Atualizar minhas compras** depois de um resgate confirmado.
