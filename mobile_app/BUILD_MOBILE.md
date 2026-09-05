# Compilação Android e iOS

Execute os comandos deste documento em `F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\mobile_app`.

O app usa Expo SDK 57, React Native 0.86.3 e identificador `com.sombrarcp.liberrotas` para Android e iOS. `eas.json` define os ambientes `preview` e `production`; `preview` gera APK para instalação interna. Não altere o identificador depois de distribuir o app sem avaliar a migração.

## Preparação da conta

Em 04/09/2026, `eas whoami` retornou `Not logged in`. A configuração local está preparada, mas nenhum APK/AAB foi compilado ou enviado a uma loja nesta retomada.

```powershell
eas.cmd login
eas.cmd whoami
eas.cmd init
```

Faça o login diretamente no seu terminal. `eas init` associa o aplicativo à sua conta e grava o `extra.eas.projectId` real em `app.json`. Confira a conta e o projeto exibidos antes de confirmar. Não invente esse identificador nem coloque senha ou token em `app.json`.

## Configuração pública do Firebase

No painel do projeto em `expo.dev`, abra **Environment variables**, escolha o ambiente `preview` e cadastre os seis nomes de `EXPO_PUBLIC_FIREBASE_*` listados em `.env.example`, com os valores do Firebase Web App usado na homologação. Cadastre também `EXPO_PUBLIC_TRQ_BEC_API_URL=https://api.liberrotas.com.br` e `EXPO_PUBLIC_TRQ_BEC_ALLOW_LEGACY_DEMO=false`. Configure `production` separadamente antes de usá-lo.

As variáveis públicas entram no JavaScript do aplicativo. Use visibilidade **Plain text** ou **Sensitive** conforme a organização do projeto; **Secret** não serve para valores públicos que precisam participar da resolução de configuração. A conta de serviço Firebase Admin permanece somente no backend. `.env.local` é ignorado pelo Git e não substitui a configuração do build remoto.

## Gerar e instalar o APK

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npx.cmd expo-doctor
eas.cmd build --platform android --profile preview
```

O EAS pode solicitar a configuração da chave de assinatura e utilizar a cota de builds da conta. Baixe o APK pelo link gerado, instale no aparelho de homologação e valide câmera, galeria, localização, QR, SecureStore e os fluxos com duas contas distintas. O comando abaixo gera AAB para uma futura distribuição; publicar na loja é uma etapa separada:

```powershell
eas.cmd build --platform android --profile production
```

Para iOS, use `eas.cmd build --platform ios --profile preview` depois de configurar conta Apple, assinatura e aparelhos de teste. Windows não oferece simulador iOS.

## Limite da validação atual

`npx.cmd expo export --platform android --output-dir ../tmp/android-export-20260904` foi aprovado e gerou bytecode Hermes. Isso verifica o bundle JavaScript; não compila um APK e não comprova recursos nativos no aparelho. O bloqueio `LAB_ED25519_PQ_BLOCKED` permanece: o TRQ-BEC continua acadêmico/experimental.

Referências: [configuração EAS](https://docs.expo.dev/build/eas-json/), [variáveis de ambiente EAS](https://docs.expo.dev/eas/environment-variables/) e [Expo SDK 57](https://expo.dev/changelog/sdk-57).
