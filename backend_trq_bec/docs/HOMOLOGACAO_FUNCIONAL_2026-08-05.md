# Homologação funcional segura — 05/08/2026

Esta matriz separa evidência automatizada, verificação Web local e o que ainda
depende de contas e aparelho físico. Um teste automatizado aprovado não é
registrado como se câmera, GPS ou permissões reais tivessem sido testados.

## Resultado registrado

| Fluxo | Evidência atual | Estado |
|---|---|---|
| Empreendedor cria produto e oferta | testes de criação, emissão, catálogo e resgate do backend | aprovado automaticamente |
| Empreendedor cria, encerra e exclui a própria feira | teste de API com autoria e permissão atuais | aprovado automaticamente |
| Empreendedor publica somente um ponto e exclui o próprio ponto | testes de limite, autoria e remoção transacional no backend | aprovado automaticamente; tela real pendente |
| Instituição abre o próprio perfil e exclui a própria feira | teste de API cobre instituição proprietária; outra instituição recebe `403` | aprovado automaticamente; tela real pendente |
| Visitante lê e resgata QR | emissão, preview, desafio, prova e resgate transacional cobertos | aprovado automaticamente; câmera real pendente |
| Outra conta acessa recurso alheio | feira, produto, logo e mídia recusados com `403` | aprovado automaticamente |
| Página pública, login e cadastro Web | aberta em `http://127.0.0.1:8081`, sem erro no console | aprovado na Web local |
| Câmera, galeria, localização, imagens e logout | exige Expo Go e permissões do Android/iOS | pendente em aparelho físico |

Comandos executados na pasta `backend_trq_bec`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Resultado: `194 passed, 63 subtests passed`.

Na pasta `mobile_app`:

```powershell
npm.cmd test -- --run
npx.cmd tsc --noEmit
npm.cmd run lint
```

Resultado: `34` testes, TypeScript e ESLint aprovados.

## Roteiro obrigatório no aparelho físico

Use duas contas de homologação sem dados reais: uma empreendedora ou
institucional e uma visitante. O celular precisa acessar a API pública HTTPS;
`127.0.0.1` no telefone aponta para o próprio telefone, não para este PC.

1. Na raiz do workspace, inicie a pilha com `.\INICIAR_LIBERROTAS.ps1`.
2. Em outro PowerShell, entre em `mobile_app` e execute
   `npx.cmd expo start --port 8082 --lan --clear`.
3. Abra no Expo Go e confirme que a URL da API exibida pelo app usa HTTPS.
4. Na conta empreendedora, cadastre produto com imagem, emita oferta e abra o QR.
5. Publique uma feira usando GPS, capa e intervalo curto; abra seu perfil e
   confirme que o botão **Excluir feira** aparece somente para o autor.
6. Na conta institucional, abra **Painel Institucional > Perfil institucional**,
   envie um logo e abra o perfil público. Se houver feira criada pela instituição,
   confirme a exclusão no próprio perfil.
7. Na conta visitante, permita a câmera, leia o QR, confira o preview e conclua o
   resgate uma única vez. Uma repetição não pode gerar nova baixa de estoque.
8. Ainda como visitante, tente alterar ou excluir produto, feira e mídia alheios;
   a interface não deve oferecer a ação e a API deve recusar chamada forjada.
9. Negue e depois permita câmera, galeria e localização para conferir mensagens
   compreensíveis. Teste uma imagem JPEG/PNG/WebP e uma maior que 5 MB.
10. Toque em **Sair**, tente voltar para a tela protegida e confirme o retorno ao
    login. Feche e reabra o Expo Go para verificar que a sessão não reaparece.

Registre modelo do aparelho, versão do Android/iOS, versão do Expo Go, data,
contas de teste por apelido e resultado de cada passo. Não registre senhas,
tokens Firebase, QR completo, URLs assinadas ou chaves.

## Critério de aceite

A homologação física só pode ser marcada como concluída quando os dez passos
acima tiverem evidência no aparelho-alvo. Até lá, o estado correto do projeto é
**regressão automática aprovada, homologação física pendente**.
