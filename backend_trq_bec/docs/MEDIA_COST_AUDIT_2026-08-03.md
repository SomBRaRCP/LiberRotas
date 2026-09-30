# Auditoria de custo de mídia — 03/08/2026, atualizada em 05/08/2026

Esta auditoria registra o estado local observado antes da criação das variantes
e a validação posterior do caminho público por entidade em 05/08/2026.
Ela usa somente contagens e metadados; nenhum documento, URL assinada, credencial,
nome ou e-mail foi reproduzido.

## Resultado dos dados reais

### PostgreSQL local

- tamanho total do banco: 11 MB;
- mídias prontas: 2;
- bytes processados registrados: 132.634;
- duplicações por `checksum_sha256`: 0;
- duplicações prontas por entidade e papel: 0;
- campos `data:image/...;base64`: 0;
- textos maiores que 100 KB nos campos textuais/JSON: 0;
- `pg_stat_statements`: não habilitado.

As duas mídias anteriores à migration `020_media_variants` permanecem válidas e
usam fallback para o objeto principal. Não foi feito backfill automático, pois
isso exigiria ler e reprocessar objetos reais no GCS.

### Firestore real

Foram lidos 13 documentos nas coleções existentes:

| Coleção | Documentos | Imagem Base64 | Referência duplicada |
|---|---:|---:|---:|
| `coupon_validations` | 4 | 0 | 0 |
| `live_fairs` | 1 | 0 | 0 |
| `network_interactions` | 3 | 0 | 0 |
| `private_profiles` | 1 | 0 | 0 |
| `public_profiles` | 4 | 0 | 0 |

Essa verificação confirma o conjunto observado nessa data. Ela não substitui
monitoramento contínuo nem prova o conteúdo de documentos criados depois.

## Medição dos caminhos de leitura

Não houve tráfego público de mídia nos logs das últimas 24 horas. Foram vistas
3 ocorrências do prefixo autenticado `/v1/media`. Como a amostra real não tinha
volume suficiente para ordenar rotas por frequência, a contagem abaixo mede o
caminho determinístico do backend e é protegida por testes automatizados.

| Endpoint | Consultas PostgreSQL por cache miss | Observação |
|---|---:|---|
| `GET /v1/public/media/{media_id}` | 1 | objeto principal |
| `GET /v1/public/media/{media_id}?variant=...` | 1 | `LEFT JOIN` entre ativo e variante |
| `GET /v1/public/media/entities/{tipo}/{id}/{papel}?variant=...` | 1 | ativo pronto mais recente + variante em um único `LEFT JOIN` |
| `GET /v1/public/profile/{uid}/avatar?variant=thumbnail` | 2 | perfil atual + ativo/variante |
| `GET /v1/media/{media_id}` | 1 | metadados privados e URL curta |
| `GET /v1/media?entity_type=...` | 1 | lista paginada |

O avatar custa uma consulta adicional porque o perfil ainda guarda uma
referência estável em `avatar_uri`. Remover esse campo agora exigiria uma
migration de identidade mais ampla e não pertence a este lote seguro.

## Economia introduzida

- redirecionamento de mídia imutável: cache público de até 240 segundos;
- avatar mutável: cache público de até 60 segundos;
- imagem mutável de produto, feira ou instituição: cache público de até 60 segundos;
- ambos usam duração menor que a URL GCS assinada de 300 segundos;
- o aplicativo usa cache `memory-disk`;
- componentes públicos usam diretamente a URL estável `display`, sem consultar
  primeiro o endpoint autenticado de metadados;
- pedidos privados simultâneos do mesmo `media_id` compartilham uma única
  consulta e respeitam margem de 30 segundos antes da expiração;
- novos uploads geram apenas `thumbnail` (até 320 px) e `display` (até 1024 px).
- produto, feira e instituição não recebem URL assinada nem bytes no PostgreSQL
  ou Firestore; as telas derivam uma referência pública estável da entidade;
- a seleção pública por entidade evita primeiro listar mídias e depois consultar
  o ativo escolhido, reduzindo dois acessos de aplicação a um único acesso SQL.

## Limites e custos adicionados

- cada novo upload passa a criar dois objetos WebP adicionais no GCS;
- a confirmação usa CPU para redimensionar e codificar as versões;
- as variantes reduzem bytes transferidos, mas não garantem redução da fatura
  sem tráfego real e métricas do Google Cloud;
- cache do navegador/aplicativo não elimina o primeiro cache miss;
- uma troca de imagem pode permanecer até 60 segundos em cache antes da
  revalidação; esse prazo é deliberadamente menor que a URL assinada;
- GCS, CDN, Firestore e PostgreSQL possuem modelos de cobrança diferentes;
- não foi ativada CDN nem bucket público;
- não foi habilitado `pg_stat_statements` porque isso altera configuração do
  PostgreSQL e exige uma decisão operacional separada.

## Como repetir a medição

Execute na pasta `backend_trq_bec`, nunca imprimindo valores do `.env`:

```powershell
Set-Location "E:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
docker compose logs api --since 24h --no-color |
  Select-String -Pattern '/v1/(public/)?media|/v1/public/profile/.+/avatar'
```

Para volume e frequência confiáveis em produção, use métricas agregadas da API
e do provedor. Não registre URLs assinadas, tokens Firebase ou corpos privados.
