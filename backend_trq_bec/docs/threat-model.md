# Threat model inicial

## Ativos

- chaves de emissor, dispositivo, checkpoint e sessão;
- intenção autoritativa e estado da operação;
- allowlist de suítes e política;
- armazenamento anti-replay;
- ledger e checkpoints;
- identidade Firebase e vínculo com dispositivo;
- token opaco de aprovação, inventário de dispositivos e sessões Firebase;
- endereço de e-mail registrado e credencial SMTP do backend;
- conta comercial, produto, preço, estoque, oferta e resgate.
- quantidade assinada da venda e totais financeiros do resgate;
- mensagens privadas, comentários, bloqueios e autoria de conteúdo;
- imagens privadas, metadados, URLs temporárias e credencial do GCS;
- grupos, filiações, orçamento e alocações de eventos institucionais.

## Fronteiras

- aplicativo Expo é ambiente parcialmente hostil;
- rede é hostil, mesmo sob TLS;
- Firebase ID token identifica conta, não prova sozinho a posse do dispositivo;
- e-mail de segurança é apenas um canal de alerta, não autoriza o dispositivo e não substitui MFA;
- coletores contextuais precisam de autenticação e frescor;
- modelo de IA e prompts são não confiáveis para autorização.

## Ameaças e controles

| Ameaça | Controle | Teste |
|---|---|---|
| preço/desconto adulterado no aplicativo | preço lido do PostgreSQL e desconto recalculado no servidor | `test_backend_calculates_price_and_rejects_client_price_fields` |
| estoque negativo ou resgate acima do limite | locks, constraints e commit transacional | `test_one_stock_unit_allows_exactly_one_of_one_hundred_buyers` |
| quantidade do QR alterada | assinatura `quantity_proof_b64u`, validação do saldo no preview e nova validação no commit | testes de quantidade válida, adulterada e acima do saldo |
| segundo resgate da mesma pessoa | unicidade `(offer_id, buyer_uid)` | teste de emissão e resgate da API |
| token adulterado | assinatura sobre bytes canônicos | `test_tampered_envelope_is_denied` |
| replay exato/concorrente | reserva atômica `(iss,replay_jti)` e operação idempotente | testes Redis/Lua e concorrência |
| token Firebase roubado usado para cadastrar outro aparelho | toda chave nova exige autenticação recente; visitante recebe alerta sem espera; todo novo aparelho de empreendedor ou instituição aguarda 10 minutos; alerta **Não fui eu!** vai ao e-mail consultado no Firebase Admin; operações protegidas exigem chave `ACTIVE` e prova de posse | testes de cooldown, ativação automática, revogação e prova com chave errada |
| atacante aguarda a ativação automática | janela de 10 minutos para reação do titular, inventário de aparelhos e troca de senha com revogação de chaves e refresh tokens | testes de dispositivo pendente, alerta e revogação total |
| enumeração de dispositivos de outra conta | UID sempre vem do ID token validado; listagem, aprovação, reenvio e revogação não aceitam UID do frontend | teste de isolamento por UID |
| indisponibilidade ou erro do SMTP em desenvolvimento | estado honesto `NOT_CONFIGURED`/`FAILED`; o login e a ativação automática continuam, sem falso `SENT` | testes com notifier ausente e falhando |
| produção iniciada sem canal de alerta | guard de configuração exige host SMTP e remetente antes de iniciar | teste de configuração de produção incompleta |
| pendências vencidas consumindo o limite da conta | promoção autoritativa para `ACTIVE` antes de contar pendências ou cadastrar nova chave | testes de cooldown concluído e nova matrícula |
| conta ou senha comprometida | inventário de dispositivos, aviso explícito e revogação de `ACTIVE`/`PENDING_APPROVAL` mais refresh tokens ao alterar senha | testes de revogação total e falha do Firebase |
| acesso a mensagem, comentário ou imagem de outra conta | UID vem do ID token; backend valida participante, autoria, propriedade da entidade e bloqueios | testes de isolamento, autoria e mídia privada |
| upload disfarçado ou imagem excessiva | allowlist JPEG/PNG/WebP, limite de bytes/pixels/dimensão, confirmação e reprocessamento no backend | testes de processamento e configuração de mídia |
| manipulação de orçamento institucional | proprietário derivado do token, somas exatas, alocações congeladas na ativação e relatório limitado aos próprios grupos | testes de eventos financiados e probes PostgreSQL |
| abuso de tentativas | contador Redis por ator/janela e negativa terminal `RATE_LIMIT_EXCEEDED` | `test_rate_limit_denies_instead_of_only_raising_risk_score` |
| downgrade | `suite_id` assinado e allowlist | suíte desconhecida falha fechado |
| intenção alterada | digest e comparação autoritativa | `INTENT_MISMATCH` |
| contexto forjado | fonte, frescor, qualidade e integridade | cobertura cai e exige step-up |
| vazamento por logs | allowlist negativa de campos + pseudônimo de chave | teste de sanitização |
| prompt injection | IA recebe somente visão sanitizada e não executa | teste de ausência de capacidade |
| truncamento/fork do ledger | checkpoint externo e sequência | cadeia local detecta tamper; ancoragem pendente |
| comprometimento do celular | keystore/attestation, revogação e step-up | pendente no app real |
| backend ou Redis indisponível | falha fechada; sem confirmação comercial offline | `test_redis_failure_fails_closed` |

O link **Não fui eu!** usa
`https://app.liberrotas.com.br/account/devices` sem token, segredo ou UID. A conta
autenticada é sempre determinada pelo Firebase ID token validado no backend.

Riscos residuais: um atacante com credencial Firebase válida pode esperar os 10
minutos se o titular não vir ou não agir sobre o alerta; o SMTP não garante
entrega instantânea. Para maior garantia, adicionar MFA, confirmação push ou em
um aparelho já ativo e monitoramento de entrega.

Para visitante, todo novo registro é ativado imediatamente e gera um alerta. Para
empreendedor e instituição, todo novo registro começa `PENDING_APPROVAL`, inclusive
o primeiro. O reenvio exige autenticação recente e não altera o horário original.
Ao terminar o período, o registro muda para `ACTIVE` e o evento fica no ledger.

## Fora do escopo desta versão

- Pix real e campos oficiais do BR Code;
- pedidos, pagamentos, webhooks e estornos;
- resistência comprovada a side channels;
- forward secrecy e post-compromise security;
- validação FIPS 140-3;
- ML-KEM/ML-DSA executável;
- operação comercial offline.
