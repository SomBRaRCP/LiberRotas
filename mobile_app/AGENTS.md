# Frontend LiberRotas

Complemente o [AGENTS.md raiz](../AGENTS.md); não releia o contexto já carregado.

## Localizar e alterar

1. Identifique a tela em `src/app/`, o componente em `src/components/` e o domínio em `src/features/`.
2. Localize testes relacionados em `tests/`. Para transporte, consulte `src/api/http-client.ts`; para sessão, localize o trecho relevante em `src/context/` e `src/services/`.
3. Altere apenas o fluxo necessário. Preserve navegação Expo Router, autenticação, interfaces públicas e fachadas compatíveis.

Firebase Web SDK atende o cliente; Firebase Admin pertence ao backend. Firestore e Authentication têm papéis diferentes. O cliente não confirma fatos comerciais. Leia a [matriz de autoridade](../backend_trq_bec/docs/DATA_AUTHORITY_MATRIX.md) quando a mudança envolver dados.

## Verificar

Execute em `mobile_app/`, usando o arquivo de teste afetado:

```powershell
npm.cmd test -- tests/directory-api.test.ts
npm.cmd run typecheck
npm.cmd run lint
```

O teste acima é exemplo do diretório; escolha o correspondente à tarefa. Não rode a suíte inteira automaticamente para uma mudança pequena.

Mudança ampla ou entrega funcional: execute `npm.cmd test`, as checagens acima e `npm.cmd run test:firestore` para a validação completa com emulador. Confira build/dispositivo conforme [BUILD_MOBILE.md](BUILD_MOBILE.md). Vitest sem emulador não valida regras Firestore; Web não comprova funcionamento no celular.
