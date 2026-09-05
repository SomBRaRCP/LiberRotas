# ADR-CRYPTO-001 — Perfis criptográficos

**Status:** laboratório aceito; produção pendente  
**Data:** 2026-07-10

## Decisão de laboratório

Usar Ed25519 e SHA3-256 apenas para exercitar contratos e fluxos. A suíte declara explicitamente `LAB` e não pode ser apresentada como pós-quântica.

## Baseline candidata de produção

ML-KEM-768, ML-DSA-65, AES-256-GCM, SHA3-256 e KDF aprovada, com CSPRNG do sistema. O provider fica indisponível até que biblioteca, vetores oficiais, parâmetros, lifecycle de chaves e revisão independente estejam aprovados.

## Downgrade

`suite_id` é assinado, pertence a allowlist governada e nunca é aceito porque o cliente o pediu. Perfil desconhecido ou indisponível falha fechado.

