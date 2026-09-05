# ADR-ARCH-001 — Separação execução/auditoria

**Status:** aceito  
**Data:** 2026-07-10

## Decisão

O caminho criptográfico funciona sem modelo, prompt ou inferência. A camada de IA recebe uma visão sanitizada depois do resultado autoritativo e expõe somente recomendações.

## Consequência

Falha ou indisponibilidade da IA não interrompe validação criptográfica. Nenhuma recomendação altera `CryptoOK`, replay, suíte, chave ou política.

