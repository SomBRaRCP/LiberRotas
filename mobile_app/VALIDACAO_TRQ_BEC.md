# Validação do cliente móvel e Web TRQ-BEC

**Data de revisão técnica:** 1 de setembro de 2026  
**Aplicativo:** LiberRotas 1.1.0  
**Base móvel:** Expo `57.0.19`/SDK 57, React Native `0.86.3` e React `19.2.3`  
**Escopo:** Android/iOS e Web, identidade de dispositivo, marketplace, QR
individual/combinado, quantidade e resgate online.

O fluxo que estes testes protegem está explicado em
[`../backend_trq_bec/docs/FLUXO_TRQ_BEC.md`](../backend_trq_bec/docs/FLUXO_TRQ_BEC.md).

## Verificações do frontend

Execute na pasta `mobile_app`:

```powershell
npm test
npx tsc --noEmit
npm run lint
npx expo-doctor
npx expo install --check
npx expo config --type public
```

As regras Firestore usam uma suíte separada, executada com JDK 21 e o emulador local:

```powershell
npm run test:firestore
```

Esse comando não integra a contagem do Vitest, não usa o projeto Firebase real e não tem uma quantidade de asserts fixada neste documento.

Para conferir a exportação Web usada em produção:

```powershell
$env:EXPO_NO_DOTENV = "1"
$env:EXPO_PUBLIC_TRQ_BEC_API_URL = "https://api.liberrotas.com.br"
npx expo export --platform web --output-dir dist --clear
Remove-Item Env:EXPO_NO_DOTENV
Remove-Item Env:EXPO_PUBLIC_TRQ_BEC_API_URL
```

O `package.json` possui suíte Vitest para as fronteiras HTTP, marketplace, QR e
resgate. Ela reduz regressões de contrato, mas não substitui câmera, navegação e
teste real em aparelho.

Resultado atualizado em 01/09/2026:

| Verificação | Resultado |
|---|---|
| `npm test` | aprovado; 34 testes em 9 arquivos |
| `npm run test:firestore` | aprovado separadamente no emulador local |
| `npx.cmd tsc --noEmit` | aprovado |
| `npm.cmd run lint` | aprovado |
| `npx.cmd expo install --check` | aprovado; dependências compatíveis com o Expo SDK 57 |
| `npx.cmd expo-doctor` | aprovado; 21/21 verificações |
| `npm.cmd audit --omit=dev` | 3 moderadas; 0 altas e 0 críticas na árvore de produção |

As três vulnerabilidades moderadas pertencem à cadeia transitiva upstream do `expo-router`. Não use `npm audit fix --force`, pois a troca automática proposta é incompatível com a árvore Expo atual. A configuração pública e a exportação Web estática também foram aprovadas.

## Contratos conferidos no cliente

- produto com preço em centavos e estoque autoritativo;
- ativação em massa com estoque individual e exclusão operacional de produtos;
- emissão de uma oferta por produto selecionado, com proposta inicial de 8 horas;
- QR individual `trq-bec-offer-v1` com `quantity`;
- assinatura `quantity_proof_b64u` obrigatória quando a quantidade é maior que 1;
- QR combinado `trq-bec-offer-bundle-v1` com 2 a 5 ofertas do mesmo vendedor;
- preview de cada item sem efeito comercial;
- `begin` com operação, sessão, desafio e mensagem exata para assinatura;
- prova Ed25519 local sobre `proof_message_b64u`;
- `authorize` separado para cada cupom do QR combinado;
- totais e quantidades exibidos antes e depois da confirmação;
- fechamento automático do QR do vendedor quando `redeemed_count` aumenta.

## Controles mantidos

1. O scanner limita e valida o JSON antes de chamar a API.
2. Todas as chamadas protegidas enviam Firebase ID token.
3. A chave nativa fica no SecureStore; a chave Web não exportável fica no
   IndexedDB. Nenhuma chave privada vai para o AsyncStorage.
4. Função, preço, desconto, estoque, quantidade autorizada e decisão final não
   são aceitos como autoridade do frontend.
5. Alterar a quantidade no QR invalida sua assinatura.
6. Cada payload de um QR combinado conserva operação e decisão independentes.
7. Erro de rede, timeout ou recusa do backend falha de forma fechada.
8. Todo novo dispositivo de empreendedor ou instituição fica `PENDING_APPROVAL` por 10 minutos e não participa
   de operação protegida durante esse período.
9. O e-mail é somente um alerta **Não fui eu!** e não contém token de autorização.
10. Alterar senha revoga dispositivos ativos/pendentes e sessões Firebase.

## Teste ponta a ponta recomendado

1. Use um empreendedor `ACTIVE` e um visitante, ambos autenticados.
2. Confirme que as duas identidades de dispositivo estão `ACTIVE`.
3. Cadastre dois produtos e ative estoques diferentes.
4. Emita duas ofertas com descontos diferentes.
5. Na Vitrine, informe quantidades diferentes e gere um QR combinado.
6. No visitante, confira quantidades, preço unitário, totais e economia.
7. Confirme o resgate e verifique o resultado de cada cupom.
8. No vendedor, confirme fechamento automático, estoque reduzido pela quantidade
   e vendidos atualizados.
9. Gere um novo QR para outro visitante e confirme que o saldo remanescente é
   respeitado.
10. Tente adulterar quantidade ou usar quantidade acima do saldo e confirme a
    recusa.

## Limites conhecidos

- uma pessoa resgata cada oferta no máximo uma vez;
- um QR combinado acelera a leitura, mas não torna o commit de vários cupons uma
  transação única; a interface precisa mostrar falha parcial;
- a identidade Web é separada por protocolo, host e porta;
- dispositivos de empreendedor ou instituição são ativados depois de 10 minutos mesmo se o e-mail
  não for entregue;
- um XSS na mesma origem pode solicitar assinaturas enquanto a página estiver
  aberta;
- câmera e galeria exigem teste em aparelho físico;
- pagamento, estorno, decisão por IA, resgate offline e PQC de produção estão
  fora da Fase 1.
