# Checklist de entrega limpa

> Revisado em **01/09/2026**.

> Nunca apague `.git`, `node_modules`, ambientes virtuais ou outros diretórios diretamente do workspace original. O script abaixo monta uma cópia separada e segura.

O repositório oficial é privado: [SomBRaRCP/LiberRotas](https://github.com/SomBRaRCP/LiberRotas). O GitHub mantém commits, branches e histórico. A pasta `.git` não entra no ZIP acadêmico, de forma intencional; o ZIP contém a entrega, não o histórico do repositório.

## Gerar os pacotes

Na raiz `F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3`, execute:

```powershell
.\scripts\build-academic-package.ps1 -Force
```

- [ ] Confirmar que o script terminou com `Entrega concluida`.
- [ ] Conferir `PACKAGE_REPORT.md` e `SHA256SUMS.txt` na pasta de saída.
- [ ] Enviar o ZIP `Source` quando forem necessários código-fonte e instruções.
- [ ] Enviar o ZIP `Web_Deploy` somente para hospedagem estática.
- [ ] Não enviar `.env.local`, `.env.backend`, service account, chaves privadas ou tokens.
- [ ] Confirmar que `.git` não está no ZIP e que o histórico está preservado no GitHub privado.

## Testar o Source extraído

- [ ] Entrar na pasta `mobile_app` extraída e rodar `npm ci`.
- [ ] Rodar `npm test` e confirmar os `34` testes Vitest.
- [ ] Com JDK 21 disponível, rodar separadamente `npm run test:firestore`; não somar essa suíte à contagem Vitest nem fixar uma quantidade de asserts.
- [ ] Rodar `npx expo install --check`, `npx expo-doctor`, `npm run lint` e `npx tsc --noEmit`.
- [ ] Confirmar Expo `57.0.19`/SDK 57, React Native `0.86.3`, React `19.2.3` e Expo Doctor `21/21`.
- [ ] Rodar `npm audit --omit=dev` e registrar o estado esperado: `3` moderadas e `0` altas ou críticas, provenientes da cadeia upstream do `expo-router`; não usar `npm audit fix --force`.
- [ ] Rodar `npx expo start --port 8082` e testar login, cadastro, Feed único, imagem, comentários, mensagens, mapa, Vitrine, QR individual/combinado e quantidade.
- [ ] Confirmar que novos uploads aceitam somente JPEG, PNG ou WebP e rejeitam vídeo/outros arquivos.
- [ ] Confirmar QR combinado com 2 a 5 ofertas, resultado por cupom e fechamento automático na tela do vendedor.
- [ ] Confirmar no Console que Firebase Authentication por e-mail/senha está ativado.

## Conferir o backend extraído

- [ ] Entrar em `backend_trq_bec`, preparar a venv e rodar `.\.venv\Scripts\python.exe -m pytest tests -q`.
- [ ] Confirmar `197 testes` e `63 subtestes` aprovados.
- [ ] Confirmar o contrato OpenAPI com `94` caminhos e `106` operações.

O ZIP extraído não é um repositório Git e isso não representa perda do histórico. Para consultar ou continuar o desenvolvimento com commits, use o workspace original ou clone o repositório privado; não execute `git init` apenas para transformar a cópia acadêmica em outro repositório sem histórico.
