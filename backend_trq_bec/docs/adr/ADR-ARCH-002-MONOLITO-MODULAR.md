# ADR-ARCH-002 — Monólito modular por domínio

**Status:** aceito  
**Data:** 2026-08-03

## Contexto

O LiberRotas já possui fronteiras operacionais adequadas entre aplicativo Expo,
API FastAPI, PostgreSQL, Redis, Firebase e Google Cloud Storage. Entretanto, a
camada HTTP, a orquestração dos casos de uso e o acesso aos dados cresceram em
poucos arquivos centrais. Esse crescimento aumenta o acoplamento e dificulta
testes e manutenção, mas ainda não existe necessidade operacional que justifique
microserviços, filas obrigatórias ou bancos separados por serviço.

## Decisão

O backend continuará sendo um único artefato implantável e uma única API
FastAPI. O código será reorganizado gradualmente em módulos por domínio, com
routers, serviços, repositórios e schemas próprios quando a separação trouxer
clareza real.

Os domínios iniciais são:

- acesso e contas;
- diretório e perfis públicos;
- comunidade;
- mensagens e suporte;
- marketplace e cupons;
- instituições;
- mídia;
- segurança, protocolo, política e ledger.

O aplicativo seguirá a mesma divisão em `features`, mantendo os arquivos do
Expo Router pequenos e preservando fachadas compatíveis durante a migração.

## Restrições da migração

- Não alterar URLs, payloads ou códigos de erro durante uma extração estrutural.
- Não mover regras comerciais para o cliente.
- Não modificar `crypto`, `protocol`, `policy` ou `ledger` junto com uma mudança
  apenas organizacional.
- Cada domínio migrado deve conservar testes de contrato e regressão.
- PostgreSQL e Redis continuam compartilhados pelo único backend.
- Uma separação futura em serviços exige evidência de escala, isolamento ou
  operação independente; tamanho de arquivo, sozinho, não justifica microserviço.

## Consequências

### Positivas

- mudanças menores e mais fáceis de revisar;
- testes direcionados por domínio;
- menor risco de uma funcionalidade afetar outra;
- preparação para crescimento sem assumir a complexidade de sistemas
  distribuídos.

### Custos

- período temporário com fachadas e módulos antigos coexistindo;
- necessidade de migrar um domínio por vez;
- disciplina para impedir importações diretas entre domínios sem contrato.

## Estratégia de adoção

1. registrar a autoridade de cada dado;
2. extrair infraestrutura compartilhada sem mudar comportamento;
3. migrar primeiro diretório e pesquisa;
4. avançar para mensagens, comunidade e instituições;
5. migrar marketplace e fluxos TRQ-BEC somente depois das fronteiras anteriores;
6. avaliar outbox apenas quando uma operação precisar coordenar gravações
   duráveis em mais de um armazenamento.
