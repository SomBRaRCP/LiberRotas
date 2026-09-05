# Integração com o app_LiberRotas

O TRQ-BEC fica no backend. O aplicativo Expo, no Android/iOS ou na Web, atua como cliente e detentor de uma chave de dispositivo. O Firebase Authentication continua identificando a conta; a prova TRQ-BEC demonstra posse da chave registrada para aquele dispositivo e para aquela operação.

## Fluxo

1. O vendedor solicita na Vitrine um QR com a quantidade daquela venda.
2. O backend vincula e assina a quantidade à referência opaca.
3. O visitante consulta a prévia e pede o início da operação sobre `resource_ref`.
4. O backend cria a intenção autoritativa, envelope assinado, sessão e desafio de uso único.
5. O app assina `proof_message_b64u` com a chave do dispositivo.
6. O backend valida quantidade, saldo, envelope, intenção, audiência, tempo, prova de posse e anti-replay.
7. O motor contextual calcula cobertura/risco; a política retorna `ALLOW`, `STEP_UP`, `HOLD_OR_REVIEW` ou `DENY`.
8. A IA somente observa o ledger sanitizado e recomenda; ela não libera a operação.

O cliente pode transportar de 2 a 5 payloads individuais do mesmo vendedor em
`trq-bec-offer-bundle-v1`. Cada item continua tendo preview, operação, prova e
decisão próprios.

## Onde encaixar no projeto existente

Copie `mobile/contracts.ts` e `mobile/trqBecClient.ts` para, por exemplo:

```text
app_LiberRotas/
  src/
    security/trq_bec/
      contracts.ts
      trqBecClient.ts
      device-signer.ts      # Android/iOS: expo-secure-store
      device-signer.web.ts  # Web: WebCrypto + IndexedDB
```

O armazenamento depende da plataforma:

| Plataforma | Perfil | Implementação de laboratório |
|---|---|---|
| Android/iOS | `EXPO_SECURE_STORE_LAB` | seed Ed25519 protegida pelo `expo-secure-store` |
| Web | `WEB_CRYPTO_INDEXEDDB_LAB` | chave privada Ed25519 `CryptoKey` não exportável persistida no IndexedDB |

Na Web, a página precisa estar em HTTPS ou, no laboratório do próprio PC, em
`http://127.0.0.1`. A identidade é vinculada à origem completa do navegador. Por
isso, mudar protocolo, host ou porta cria outra chave; limpar os dados do site ou
o IndexedDB perde a chave não exportável.

Toda chave nova exige login Firebase recente, com `auth_time` de no máximo 5
minutos. Para visitante, toda chave nova de Web, Android/iOS, perfil de navegador
ou origem fica `ACTIVE` imediatamente e gera apenas um alerta. Para empreendedor
e instituição, toda chave nova, inclusive a primeira, fica `PENDING_APPROVAL`,
sem bloquear a sessão autenticada. Depois de 10 minutos, o backend a promove
automaticamente para `ACTIVE`. Repetir a mesma chave permanece idempotente.

O backend envia ao e-mail consultado no Firebase Admin um alerta com o botão
**Não fui eu!** para `/account/devices`. Se o acesso for legítimo, o titular
desconsidera a mensagem. Se não reconhecer, revisa os aparelhos e troca a senha.
O e-mail não contém token. O reenvio exige autenticação recente, respeita cooldown
de 60 segundos e não reinicia a contagem.

Perder a identidade local não apaga o registro autoritativo. A nova chave pode ser
cadastrada e liberada após o cooldown, enquanto a anterior permanece no inventário
até a revogação. Alterar a senha exige aviso de que dispositivos ativos, pendentes
e a sessão atual serão desconectados.

Os dois perfis continuam sendo de laboratório. `expo-secure-store` protege bytes
armazenados, mas não os transforma em chave atestada. Na Web, a não
exportabilidade reduz a extração acidental, porém um XSS na mesma origem ainda
pode solicitar assinaturas. Uma implantação de maior garantia exige controles
contra XSS e, no nativo, Android Keystore/Apple Secure Enclave com atestação.

## Firebase

O backend dedicado expõe os contratos usados pelo aplicativo:

- `POST /v1/trq-bec/devices/enroll`
- `POST /v1/trq-bec/coupons/issue`
- `GET /v1/marketplace/offers/{offer_id}/qr?quantity=N`
- `POST /v1/trq-bec/coupons/preview`
- `POST /v1/trq-bec/coupons/redeem/begin`
- `POST /v1/trq-bec/coupons/redeem/authorize`

Cada rota deve validar o Firebase ID token no servidor. O UID autenticado participa da intenção autoritativa, mas nunca substitui a prova de posse. Realtime Database/Firestore não deve armazenar chave privada, segredo de sessão, payload integral, token assinado ou prompt da IA.

## Primeiro recurso recomendado

Comece protegendo uma operação interna e reversível: acesso à área restrita do empreendedor ou publicação/alteração de um ponto/feira. Pagamento real e campos oficiais do Pix ficam fora do primeiro ciclo.
