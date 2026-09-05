# Sequência segura de evolução — registro de 05/08/2026

## Etapas concluídas neste lote

1. Higiene operacional sem mudança funcional:
   - permissão de modificação restaurada em `backend_trq_bec/.pytest_cache`;
   - `C:\Users\regin\.docker\config.json` validado por proprietário e ACL, sem
     abrir nem copiar seu conteúdo;
   - ambiente Python ativo unificado em `backend_trq_bec/.venv`;
   - ambiente antigo movido de forma recuperável para
     `archive/retired-environments/`;
   - datas e contagens de validação atualizadas.
2. Homologação automática e Web local registrada em
   [`HOMOLOGACAO_FUNCIONAL_2026-08-05.md`](HOMOLOGACAO_FUNCIONAL_2026-08-05.md).
3. Mídia acadêmica adicionada a produto, feira e instituição:
   - propriedade e permissão verificadas pelo backend;
   - um ativo lógico em `media_assets`;
   - somente `thumbnail` e `display` em `media_variants`;
   - leitura pública estável sem persistir URL assinada.
4. Estado do aplicativo dividido em sessão, perfil, preferências e cache
   público. A fachada `useApp` foi preservada para migração gradual.
5. Primeiro domínio de backend extraído: leitura pública de mídia, com serviço e
   repositório próprios em `public_media.py`, dentro do monólito e sem alterar
   contratos existentes.

Imagem de evento financiado não foi criada. O requisito foi condicionado à
exigência do professor e não existe papel `event_image` aprovado no contrato
atual. A inclusão exigiria autorização, modelo, interface e testes próprios.

## Evidência entre os lotes

- backend: `194 passed, 63 subtests passed`;
- aplicativo: `34 passed`;
- TypeScript: aprovado;
- ESLint/Expo: aprovado;
- endpoint público por entidade: variante e cache cobertos por teste;
- exclusão de variantes: coberta pela regressão de mídia.

## Produção real: discussão liberada, prontidão ainda bloqueada

Os itens abaixo não são detalhes opcionais. Eles exigem fornecedor, ambiente,
evidência externa ou aparelho homologado e não podem ser simulados pelo código
local.

| Gate | Estado em 05/08/2026 | Para concluir |
|---|---|---|
| Provider criptográfico aprovado | bloqueado; health informa `LAB_ED25519_PQ_BLOCKED` e `pqc_ready=false` | selecionar implementação ML-KEM/ML-DSA auditada, validar vetores e ciclo de chaves |
| Fuzzing | pendente | definir alvos de parser/protocolo, corpus, orçamento e execução contínua |
| SBOM | pendente como artefato de entrega | gerar SBOM versionada de backend, app e imagem de contêiner e revisar licenças/CVEs |
| Teste de carga | pendente | definir volume acadêmico/operacional, ambiente isolado e critérios de latência/erro |
| Ancoragem externa do ledger | pendente | escolher autoridade, frequência, formato de raiz/hash e procedimento de verificação |
| Auditoria independente | pendente | contratar ou designar revisor sem vínculo com a implementação e registrar escopo |
| APK/AAB homologado | pendente | gerar build assinado por canal apropriado e executar o roteiro em aparelhos-alvo |

Não basta alterar `TRQ_BEC_ENVIRONMENT` para `production`. O guard deve continuar
recusando produção enquanto o provider aprovado e os demais requisitos
obrigatórios não existirem.

## Próximo lote arquitetônico permitido

Somente depois da homologação física, escolher um novo domínio do backend e
repetir: extração pequena, contratos intactos, testes completos e documentação.
O upload/processamento de mídia é candidato, mas deve ficar separado da leitura
pública já extraída para não misturar transação, GCS e autorização num único
lote grande.
