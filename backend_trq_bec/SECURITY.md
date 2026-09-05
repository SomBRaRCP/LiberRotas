# Política de segurança do protótipo

Este repositório é uma implementação de pesquisa. Não use para pagamento real, autenticação crítica ou proteção de dados regulados.

Ao relatar uma falha, não inclua chaves, tokens, dados pessoais, conteúdo de ledger real ou credenciais. Informe versão, componente, pré-condições, impacto, passos mínimos de reprodução e correção sugerida.

## Condições que bloqueiam produção

- provider pós-quântico indisponível;
- PostgreSQL/Redis validados somente no laboratório atual, sem homologação do ambiente-alvo, carga e recuperação de falhas;
- provider de laboratório baseado em arquivos em vez de KMS/HSM;
- política não assinada;
- ausência de homologação completa do TLS/proxy, proteção da origem e teste de carga multi-worker;
- ausência de fuzzing, SAST/SCA, SBOM e revisão independente;
- ausência de auditoria externa do conjunto aplicativo + backend.
