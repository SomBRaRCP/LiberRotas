# Vendas por QR: contexto e verificação

Consulte este arquivo quando a tarefa envolver Cupons do vendedor, geração de QR, baixa de estoque ou benefício institucional. Não é necessário abrir o README completo.

## Comportamento atual

- Na aba **Cupons**, o empreendedor consulta suas ofertas pela API privada, escolhe a quantidade e toca na oferta ou em **Gerar QR para venda**. Visitantes continuam vendo o catálogo público e o leitor.
- O QR exige oferta ativa, validade vigente, produto ativo e estoque disponível. Quantidade inicial: 1; máximo: o menor valor entre estoque, saldo da oferta e 1.000 unidades.
- O backend confere propriedade e assina a quantidade. Abrir ou fechar o QR não baixa estoque e não realiza pagamento Pix.
- A confirmação do visitante pelo leitor realiza o resgate autoritativo no PostgreSQL, descontando a quantidade comprada e atualizando as unidades vendidas.
- Enquanto o QR está aberto, a interface consulta as ofertas a cada 5 segundos. Quando o contador vendido aumenta, fecha o QR e recarrega estoque e relatórios. Fechar manualmente também atualiza os dados.
- O Perfil oferece um atalho ao gerenciador. Emitir uma única oferta no gerenciador já abre o QR. A Vitrine mantém o QR individual e combinado.

## Benefício institucional

- A instituição concede verba promocional aos produtos do parceiro; o QR continua pertencendo à oferta do próprio vendedor.
- O apoio ativo é identificado pela filiação ativa do UID autenticado, pelo `group_id`, pela vigência/limite do evento, pela moeda e pela verba positiva destinada ao produto.
- `EntrepreneurFundedEventResponse` passou a incluir `group_id`, permitindo conferir o vínculo por identificador em vez de comparar nomes.
- O saldo a receber e as unidades com benefício vêm de `loadEntrepreneurFundedEventReport`, somados por produto e moeda. Eventos encerrados também podem compor o saldo histórico.
- Os números institucionais são do produto, enquanto o contador de vendidos da oferta é específico daquela oferta. O repasse efetivo depende do saldo e das regras aplicadas pelo backend na confirmação.
- Uma falha nos relatórios é apresentada como informação indisponível; não é mostrada como saldo zero confirmado.

## Onde consultar o código

- [Cupons](../../mobile_app/src/app/(tabs)/cupons.tsx): escolhe a experiência do vendedor ou visitante.
- [Lista privada do vendedor](../../mobile_app/src/components/entrepreneur-coupons.tsx): ofertas, quantidade, estoque e indicadores institucionais.
- [Modal do QR](../../mobile_app/src/components/sale-qr-modal.tsx): exibição, consulta periódica e atualização depois do resgate.
- [Regras de elegibilidade e totais](../../mobile_app/src/features/marketplace/seller-coupons.ts): funções puras para disponibilidade, parceria e valores do produto.
- [Gerenciador](../../mobile_app/src/app/generate-qr.tsx) e [Perfil](../../mobile_app/src/app/(tabs)/perfil.tsx): emissão, geração e atalho.
- [API de marketplace](../../mobile_app/src/features/marketplace/api.ts): `getOwnLiveOfferQr`, `listOwnLiveOffers` e `listOwnMarketplaceProducts`.
- [Serviço do backend](../../backend_trq_bec/src/trq_bec/server/service.py): localizar `get_offer_qr`, `_quantity_bound_qr`, `_offer_preview` e `_entrepreneur_funded_event_response` com `rg`.
- [Matriz de autoridade](../../backend_trq_bec/docs/DATA_AUTHORITY_MATRIX.md): PostgreSQL decide os fatos comerciais; Redis controla desafios, replay e idempotência.

## Evidências verificadas em 08/10/2026

- Backend completo: **238 testes e 63 subtestes passaram**. Inclui compra de 3 unidades com baixa de 3 no estoque, quantidade protegida, bloqueio de QR de outro vendedor e relatório de valor a receber institucional.
- App: **62 testes passaram**; os 7 casos Firestore foram executados separadamente no emulador e **passaram**. TypeScript e lint passaram.
- [Testes da lista do vendedor](../../mobile_app/tests/seller-coupons.test.ts): disponibilidade, filiação do próprio vendedor, grupo correto, vigência, limite de cupons, produto, moeda e totais históricos.
- [Testes comerciais do backend](../../backend_trq_bec/tests/test_server_api.py): localizar `test_seller_signed_qr_quantity_decrements_units_atomically`, `test_owner_can_reopen_qr_and_remove_finished_offer_from_catalog` e `test_funded_event_allocation_activation_and_amount_due_report`.
- [Teste de vínculo institucional](../../backend_trq_bec/tests/test_institution_badges.py): resposta privada do evento inclui o identificador do grupo correto.
- Web e API reconstruídas com o procedimento local. API, PostgreSQL, Redis e Web responderam saudáveis; o OpenAPI em execução contém `group_id` na resposta do evento do empreendedor.
- Navegador com sessão empreendedora existente: Cupons mostrou somente suas ofertas; clicar na oferta abriu QR para 2 unidades e total de R$ 24,00. O estoque continuou em 20 após abrir e fechar, sem confirmação de compra.

Essas evidências são pontuais. Não foi feita compra operacional com duas contas reais, leitura em celular físico nem conferência de repasse de uma instituição real. O provider pós-quântico continua indisponível; o backend observado está em desenvolvimento com a suíte laboratorial habilitada. Não presumir prontidão criptográfica para produção.

## Repetir somente quando necessário

Em `mobile_app/`: `npm.cmd test -- tests/seller-coupons.test.ts tests/marketplace-api.test.ts tests/trq-bec-api.test.ts`, `npm.cmd run typecheck` e `npm.cmd run lint`.

Em `backend_trq_bec/`: `.\.venv\Scripts\python.exe -m pytest tests/test_server_api.py tests/test_institution_badges.py -q` para mudanças no contrato ou comportamento comercial.

Na raiz: `.\INICIAR_LIBERROTAS.ps1 -Rebuild` para aplicar mudanças à Web/API locais. Para uso real, verificar vendedor e visitante em aparelhos distintos, confirmar a compra e conferir estoque, vendidos e saldo institucional. Preservar os volumes do banco.
