# Arquitetura e fronteiras de autoridade

O backend adota um **monólito modular por domínio**: existe uma única API
implantável, mas as novas extrações devem separar router, serviço, repositório e
schemas por capacidade. Consulte o
[`ADR-ARCH-002`](adr/ADR-ARCH-002-MONOLITO-MODULAR.md) e a
[`matriz de autoridade dos dados`](DATA_AUTHORITY_MATRIX.md).

## Caminho de execução

Para acompanhar esse caminho ponta a ponta com os atores, endpoints, dados do QR
e as cinco portas da autorização, consulte
[`FLUXO_TRQ_BEC.md`](FLUXO_TRQ_BEC.md).

1. FastAPI autentica o Firebase ID token e valida o schema fechado.
2. PostgreSQL fornece conta, permissões, comerciante, produto, preço, estoque, oferta e quantidade autoritativos.
3. `Protocol Engine` valida suíte, política, tempo, intenção, prova de posse e desafio.
4. Redis reserva o `replay_jti` da operação e coordena idempotência entre workers.
5. `Crypto Core`, `Boundary / Risk` e `Policy Engine` produzem a decisão.
6. PostgreSQL confirma quantidade, estoque, limite e unicidade do comprador na mesma transação do resgate e do ledger.

Publicações, comentários, mensagens e eventos institucionais usam a mesma
fronteira de autenticação e autorização. Imagens seguem fluxo separado: o
PostgreSQL guarda metadados e propriedade; o Google Cloud Storage privado guarda
os bytes e libera URLs temporárias somente depois da autorização.

## Caminho de observação

`AI Assurance Layer` recebe eventos sanitizados, `RiskResult` e versões. Ela não recebe chave, segredo, assinatura, token, plaintext sensível, política mutável ou credencial de execução.

## Invariantes

- `CryptoOK = false -> DENY`.
- Campo desconhecido, versão desconhecida e suíte fora da allowlist falham fechado.
- Valores monetários são inteiros em menor unidade.
- O aplicativo nunca é fonte de preço, estoque, desconto ou confirmação comercial.
- O QR contém referência opaca e quantidade assinada; preço, desconto, saldo e dados exibidos são resolvidos pelo backend.
- Um QR combinado apenas agrupa payloads individuais; cada oferta mantém operação e decisão próprias.
- `jti` do envelope e `replay_jti` da operação são aleatórios e têm funções distintas.
- Prova de posse inclui hash do envelope, `jti`, `replay_jti`, desafio, sessão e chave de dispositivo.
- Desafio e replay são consumidos atomicamente.
- Um comprador resgata cada oferta no máximo uma vez; quantidade, estoque e limite são protegidos por transação.
- Função, autoria, propriedade de mídia, participantes da conversa e dono do grupo nunca são aceitos do frontend.
- Falha de Redis/PostgreSQL não autoriza resgate offline.
- Ausência de sinais reduz cobertura; não reduz risco por conveniência.
- Recomendação da IA não produz efeito por si só.

## Gates

| Gate | Entrega | Estado neste pacote |
|---|---|---|
| P0 | contratos, ADRs, ameaça, estados | implementado |
| P1 | harness de primitivas e vetores oficiais | parcial: laboratório Ed25519 |
| P2 | token, posse, frescor, replay e ledger | implementado e validado no laboratório com Redis/PostgreSQL; falta homologação do ambiente-alvo |
| P3 | contexto e IA em shadow | esqueleto funcional, sem automação |
| P4 | fuzzing, side channel, SBOM e auditoria externa | pendente |
