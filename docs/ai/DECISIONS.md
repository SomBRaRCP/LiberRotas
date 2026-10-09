# Decisões duradouras

## D001 — Produto separado da pesquisa TRQ

Decisão: LiberRotas é o produto; TRQ-BEC é componente experimental e substituível.
Motivo: a continuidade do produto não deve depender da validação científica da TRQ.
Consequência: uma substituição deve preservar contratos e controles de segurança. Esta é uma diretriz de produto, não evidência de desacoplamento técnico concluído nem autorização para desativar validações.

## D002 — Autoridade dos dados explícita

Decisão: seguir a [matriz de autoridade](../../backend_trq_bec/docs/DATA_AUTHORITY_MATRIX.md).
Motivo: cópias e estados do cliente não podem confirmar fatos comerciais.
Consequência: mudanças de armazenamento ou escrita precisam respeitar os responsáveis definidos na matriz.

## D003 — Evolução incremental

Decisão: manter uma API e evoluir por domínio conforme o [ADR do monólito modular](../../backend_trq_bec/docs/adr/ADR-ARCH-002-MONOLITO-MODULAR.md).
Motivo: preservar comportamento durante melhorias estruturais.
Consequência: conservar URLs, payloads e fachadas compatíveis; tamanho de arquivo isoladamente não justifica dividir serviços.

## D004 — Contexto progressivo

Decisão: usar esta camada como índice curto, preservando a documentação completa.
Motivo: reduzir leitura repetida sem perder fontes de conhecimento.
Consequência: guardar estado e prioridades atuais, consultar detalhes sob demanda e não acumular changelog nestes arquivos.
