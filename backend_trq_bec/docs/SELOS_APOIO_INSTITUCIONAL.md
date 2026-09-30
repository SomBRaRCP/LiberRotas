# Selos de apoio dos feirantes

Cada instituição classifica os filiados de seus grupos com três selos:

| Selo | Significado |
|---|---|
| Verde | OK |
| Amarelo | Precisa de atenção |
| Vermelho | Precisa de ajuda |

Os selos pertencem à filiação no grupo. Os cadastros existentes começam sem classificação; a instituição precisa avaliá-los. A lista apresenta vermelho, amarelo, verde e depois os não classificados. Nenhum selo é atribuído automaticamente a partir das vendas.

## Como usar

1. Entre com uma conta de instituição e abra **Painel da instituição → Grupos → Vendedores filiados**.
2. Selecione o grupo. Em **Recursos por selo**, informe percentuais inteiros de 0 a 100, com soma exatamente igual a 100, e salve.
3. Nos filiados ativos, selecione o selo. O clique salva a classificação; aguarde o término da gravação.
4. Abra **Eventos com verba**, crie um rascunho com a verba total e use **Aplicar divisão por selos**.
5. Revise as cotas retornadas antes de ativar o evento.

Exemplo: verba de R$ 1.000,00, verde 20%, amarelo 30%, vermelho 50%. A categoria verde recebe R$ 200,00, a amarela R$ 300,00 e a vermelha R$ 500,00. Se houver dois participantes vermelhos, cada um recebe uma cota de R$ 250,00.

Os percentuais representam parcelas do total por categoria. Não são um percentual individual nem uma garantia de que cada participante vermelho receberá mais que cada participante de outra categoria: isso depende também da quantidade de participantes. A instituição escolhe os percentuais.

## Regras da distribuição

- Todos os participantes do evento devem continuar filiados e estar classificados.
- Um selo sem participantes no evento precisa ter percentual zero. A API recusa a aplicação se houver verba atribuída a uma categoria vazia.
- A parcela de cada categoria é dividida igualmente entre seus participantes, com diferença máxima de um centavo. Os centavos residuais entre categorias usam os maiores restos, com desempate vermelho, amarelo, verde; dentro da categoria, usa-se a ordem estável de UID.
- A distribuição por selos substitui as cotas do rascunho e limpa a divisão entre produtos, assim como o ajuste manual já existente. Essa divisão precisa ser refeita antes do uso, pelo fluxo existente.
- Alterar percentuais ou reclassificar alguém não recalcula eventos automaticamente. Use novamente **Aplicar divisão por selos** nos rascunhos quando necessário.
- Eventos ativos ou encerrados não podem ser redistribuídos. O snapshot conserva os percentuais e selos utilizados.
- Salvar uma divisão personalizada remove a identificação de rateio por selos daquele rascunho.
- Os rascunhos continuam começando com divisão igual, para preservar o fluxo existente. O modo por selos é aplicado explicitamente.

## Arquivos e instalação

- Migração: `migrations/022_institution_support_badges.sql`.
- Cálculo: `src/trq_bec/server/institution_badges.py`.
- Interface: `mobile_app/src/components/institution-support-badges.tsx`, integrada às telas de filiados e eventos.
- Fonte autoritativa: PostgreSQL. Firebase Authentication continua cuidando da identidade; os selos não são gravados em Realtime Database nem Firestore.

A migração acrescenta colunas e não classifica, remove ou redistribui registros existentes. A versão nova da API exige a migração aplicada. O Compose executa as migrações na inicialização da API.

Para atualizar os serviços locais, execute no PowerShell em `E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec`:

```powershell
docker compose --env-file .env --env-file ../mobile_app/.env.local build api web
docker compose --env-file .env --env-file ../mobile_app/.env.local up -d api web
```

Se o túnel público apontar para esses serviços, a atualização também ficará disponível pelo endereço público. A implementação e os testes não executam esses comandos de publicação automaticamente.

## Verificação

Na pasta `backend_trq_bec`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_institution_badges.py tests/test_institutions_router.py tests/test_server_api.py -q
```

Na pasta `mobile_app`:

```powershell
npm.cmd test -- tests/institutions-api.test.ts
npm.cmd run typecheck
npm.cmd run lint
```

O probe `tests/postgres_funded_events_probe.py` também verifica gravação e releitura dos selos, preservação do snapshot, rollback em categoria vazia e limpeza do snapshot no ajuste manual. Execute-o somente em banco temporário com as migrações aplicadas e nome começando por `trq_bec_funded_probe`.
