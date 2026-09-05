# Roadmap de integração com o app_LiberRotas

As fases são cumulativas. Uma fase posterior não deve ser simulada dentro da anterior.

## Fase 1 — oferta ao vivo em feira

Estado: implementada no backend `0.6.0-alpha.1`, com Compose, PostgreSQL/Redis, migrations `001` a `021` e suíte automatizada validados neste workspace. A homologação manual com duas contas e aparelhos reais continua necessária.

- aprovação administrativa de comerciante;
- produto, preço e estoque autoritativos;
- oferta com limite e validade;
- QR opaco e preview pelo backend;
- quantidade assinada por venda e QR combinado de 2 a 5 ofertas no cliente;
- desafio, prova de posse, anti-replay e idempotência;
- resgate transacional por quantidade, um uso por pessoa em cada oferta e ledger.

Resgate comercial final offline permanece proibido.

## Serviços da plataforma já acoplados

- acesso por função e permissões autoritativas;
- Feed unificado, pesquisa, edição/exclusão pelo autor, comentários, respostas e curtidas;
- imagens JPEG/PNG/WebP em armazenamento privado;
- mensagens privadas com imagem, bloqueios e caixa do Suporte;
- grupos, filiações, relatórios e eventos institucionais financiados;
- ativação/exclusão em massa de produtos e gestão de ofertas pela Vitrine.

Esses serviços não antecipam pedidos ou pagamentos: continuam usando resgates
confirmados como registro operacional, sem declarar liquidação financeira.

## Fase 2 — pedidos sem pagamento

- carrinho e criação autoritativa de pedido;
- reserva e confirmação de itens;
- estados de pedido e cancelamento;
- sem captura financeira.

## Fase 3 — pagamentos

- integração com provedor real;
- confirmação por webhook autenticado e idempotente;
- conciliação, estorno e trilha de auditoria;
- nenhum pagamento deve ser considerado concluído pela resposta do aplicativo.

## Fase 4 — pós-quântico

Selecionar provider ML-KEM/ML-DSA auditado, reproduzir vetores oficiais positivos e negativos, medir tamanho/latência e executar revisão externa. Flags ou nomes de algoritmo não substituem implementação validada.

## Fase 5 — IA em shadow

Liberar a camada de garantia em modo observador somente após ledger e detectores estáveis. Medir falso aceite, falso bloqueio, cobertura, drift e ganho incremental. O modelo não recebe poder de autorizar, negar, alterar estoque ou confirmar operação.
