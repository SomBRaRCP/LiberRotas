# Backend LiberRotas

Complemente o [AGENTS.md raiz](../AGENTS.md); não releia o contexto já carregado.

## Localizar e preservar

- Comece pelo domínio em `src/trq_bec/server/routers/` e pelos testes correspondentes em `tests/`. Use `rg` para localizar funções em `service.py` e `store.py`; não abra esses arquivos inteiros por padrão.
- Preserve autenticação Firebase, autorização, propriedade, idempotência e comportamento fail-closed existente.
- Siga a [matriz de autoridade](docs/DATA_AUTHORITY_MATRIX.md): PostgreSQL para os fatos definidos e Redis para estado temporário. Firebase Admin só no backend.
- Nunca reduza validações para passar testes nem coloque segredos em logs. TRQ-BEC é experimental, sem certificação ou validação científica presumida.
- Preserve URLs, payloads e códigos de erro; mudanças de contrato devem ser explícitas. Prefira nova migration; não reescreva migrations aplicadas sem necessidade justificada.

## Verificar

Na pasta `backend_trq_bec/`, use `.venv` e escolha primeiro o teste do módulo. Exemplo para instituições:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_institutions_router.py -q
```

Suíte completa (`.\.venv\Scripts\python.exe -m pytest -q`) para mudança ampla ou entrega funcional. Probes PostgreSQL exigem banco temporário conforme instruções do próprio probe; não use o banco operacional para testes destrutivos.

Para infraestrutura, consulte só a seção relevante em [BACKEND_DEPLOYMENT.md](docs/BACKEND_DEPLOYMENT.md) ou no [mapa de comandos](../MAPA_DE_COMANDOS.md). Preserve volumes; parada normal não usa `docker compose down -v`.
