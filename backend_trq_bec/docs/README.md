# Documentação do backend TRQ-BEC

Esta pasta reúne a documentação operacional da versão `0.6.0-alpha.1`. O núcleo comercial continua sendo a **Fase 1 — oferta ao vivo em feira**, acompanhado pelos serviços atuais de acesso, comunidade, mídia, mensagens e instituições do LiberRotas.

## Por onde começar

| Arquivo | Conteúdo |
|---|---|
| [`FLUXO_TRQ_BEC.md`](FLUXO_TRQ_BEC.md) | explicação completa e didática da emissão, QR, desafio, prova de posse, autorização, transação e ledger |
| [`API_REFERENCE.md`](API_REFERENCE.md) | sequência de integração, autenticação, endpoints, exemplos e erros |
| [`BACKEND_DEPLOYMENT.md`](BACKEND_DEPLOYMENT.md) | instalação, Docker Compose, segredos, claims e migrations |
| [`GCS_MEDIA_STORAGE.md`](GCS_MEDIA_STORAGE.md) | armazenamento privado de imagens, IAM, CORS, Lifecycle e operação segura |
| [`architecture.md`](architecture.md) | separação dos componentes do backend |
| [`DATA_AUTHORITY_MATRIX.md`](DATA_AUTHORITY_MATRIX.md) | fonte autoritativa, projeções e regras de escrita de cada classe de dado |
| [`MODULARIZATION_STATUS.md`](MODULARIZATION_STATUS.md) | lotes concluídos, compatibilidade mantida e próxima fatia recomendada |
| [`threat-model.md`](threat-model.md) | ativos, fronteiras e ameaças principais |
| [`roadmap.md`](roadmap.md) | gates ainda bloqueados |
| [`openapi-liberrotas-public-v0.6.0a1.json`](openapi-liberrotas-public-v0.6.0a1.json) | contrato OpenAPI público gerado |
| [`openapi-liberrotas-internal-v0.6.0a1.json`](openapi-liberrotas-internal-v0.6.0a1.json) | contrato OpenAPI administrativo gerado |

As decisões arquitetônicas incrementais ficam em [`adr/`](adr/). A decisão atual
de evolução estrutural é o
[`ADR-ARCH-002`](adr/ADR-ARCH-002-MONOLITO-MODULAR.md): manter um único backend
implantável e separar o código gradualmente por domínio.

## Autoridade de dados nesta fase

- PostgreSQL: conta comercial, função, permissões, produto, preço, estoque, oferta, quantidade, operação, resgate, mensagens, comentários, eventos institucionais e ledger.
- Redis: desafio de uso único, reserva anti-replay, idempotência e controle operacional entre workers.
- Firebase Authentication: identidade e custom claims; não é fonte de preço, estoque ou confirmação comercial.
- Aplicativo Expo: coleta comandos e exibe resultados retornados pela API.

Uma operação comercial só está confirmada depois do commit autoritativo no backend. Não há resgate final offline.

## Escopo implementado

- aprovação ou suspensão administrativa de comerciantes;
- cadastro de produto com preço inteiro em centavos e estoque;
- emissão de oferta com desconto calculado no servidor;
- QR com referência opaca e quantidade assinada; agrupamento de 2 a 5 ofertas no cliente;
- preview sem efeito comercial;
- prova de posse do dispositivo, desafio e anti-replay;
- autenticação recente para toda chave nova; visitante fica ativo imediatamente com alerta, enquanto todo novo dispositivo de empreendedor ou instituição fica pendente por 10 minutos;
- limite de tentativas com negativa autoritativa;
- limite global, um resgate por usuário e decremento transacional de estoque pela quantidade;
- perfis, busca, Feed, edição/exclusão pelo autor, comentários, respostas e curtidas;
- imagens privadas JPEG/PNG/WebP em publicações e mensagens;
- grupos, filiações, eventos com verba, alocações e relatórios institucionais;
- ledger append-only e checkpoint administrativo.

Pedidos, pagamentos, webhooks, estornos, criptografia pós-quântica e decisão por IA não pertencem à Fase 1.

## Regenerar os OpenAPI

Execute na pasta `backend_trq_bec`, no Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
trq-bec-openapi --scope public
trq-bec-openapi --scope internal
```

O exportador separa os contratos: o arquivo público não pode conter `/internal/`, e o arquivo administrativo deve conter somente essas rotas.

## Documentação histórica

Os pacotes abaixo ficam fora desta pasta e permanecem preservados como referência das etapas anteriores:

- `../TRQ_BEC_API_Documentacao_Autoritativa_v0.5.0a1/`;
- `../TRQ_BEC_API_Tres_Fivelas_v0.5.0a2/`.

Eles não devem ser usados como contrato atual da Fase 1 nem sobrescrever os arquivos `v0.6.0a1`.

Os JSON `openapi-liberrotas-*-v0.5.0a2.json` mantidos nesta pasta são snapshots versionados da etapa anterior. As referências operacionais e os comandos de geração apontam somente para `v0.6.0a1`.
