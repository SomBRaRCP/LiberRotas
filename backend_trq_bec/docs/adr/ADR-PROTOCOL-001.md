# ADR-PROTOCOL-001 — Codificação e prova de posse

**Status:** aceito para laboratório  
**Data:** 2026-07-10

## Codificação

O domínio assinado aceita somente `null`, booleano, inteiro, string UTF-8, lista e objeto com chaves textuais. `float` e bytes crus são proibidos. Objetos são JSON UTF-8 com chaves ordenadas, sem espaços e com domínio/compimento prefixados.

Essa definição é o codec do laboratório. Antes de interoperabilidade entre Python e TypeScript, publicar vetores byte a byte e decidir se será mantida ou substituída por JCS/CBOR determinístico.

## Prova de posse

A assinatura do dispositivo cobre hash do envelope, `jti`, identificador e aleatoriedade do desafio, sessão e `device_key_id`. O desafio é emitido pelo verificador e consumido uma vez.

