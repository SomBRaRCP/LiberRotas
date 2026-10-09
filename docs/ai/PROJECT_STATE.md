# Estado do projeto

LiberRotas é uma plataforma para aproximar visitantes, feiras, empreendedores e instituições da economia solidária. O piloto prioriza consulta de feiras, localização, divulgação de produtos e atividades e canais de contato.

## Componentes

- `mobile_app/`: Expo, React Native, Web e TypeScript; Firebase Authentication para identidade e Firestore nos usos definidos pelo projeto.
- `backend_trq_bec/`: API FastAPI, PostgreSQL, Redis e Firebase Admin; mídia privada em Google Cloud Storage.
- Docker executa a Web e os serviços locais; Cloudflare Tunnel fornece exposição pública.
- TRQ-BEC é um componente experimental de pesquisa, não tecnologia criptográfica certificada. A continuidade do produto não depende de sua validação científica.

## Estado e foco

Web e API estão implementadas. A migração do workspace para o SSD E: foi concluída; a validação registrada em 30/09/2026 inclui testes, respostas HTTP e abertura do feed com sessão existente. Consulte o [registro da migração](../../backend_trq_bec/docs/MIGRACAO_SSD_2026-09-30.md) apenas para evidências ou operação. Esses resultados são pontuais, não garantia de disponibilidade atual.

Foco: usabilidade e preparação do piloto com usuários reais. Testes automatizados não comprovam experiência em celular físico, novo login, impacto econômico ou social. O provider pós-quântico permanece uma limitação experimental, sem autorização para contornar os controles existentes.

Próxima tarefa: consulte [docs/ai/NEXT.md](NEXT.md). Para enquadramento do produto, consulte [PRODUCT.md](PRODUCT.md).

Na aba Cupons, o vendedor toca na própria oferta para abrir o QR, escolhe a quantidade e consulta estoque, unidades vendidas e saldo institucional do produto. A baixa ocorre somente na confirmação do visitante; a instituição parceira é identificada pela filiação e pelo grupo da verba. Testes comerciais e navegação com sessão existente foram verificados em 08/10/2026; compra operacional com duas contas reais e leitura em celular físico continuam pendentes. Consulte [QR_VENDAS.md](QR_VENDAS.md) para arquivos, regras e evidências, sem repetir a investigação completa.

Na mesma aba, a conta visitante com permissão de resgate tem **Minhas compras**: histórico privado de resgates confirmados, vendedor/estabelecimento, produto, data, quantidade, gasto e economia. O PostgreSQL preserva os valores da compra; totais abrangem todo o histórico e separam moedas. Em 08/10/2026, testes completos, probe em PostgreSQL temporário e leitura/atualização do histórico com sessão visitante existente passaram. Não foi acompanhado o fluxo completo de compra em celular físico. Consulte [MINHAS_COMPRAS.md](MINHAS_COMPRAS.md) antes de investigar esse domínio novamente.

As telas sem menu inferior que oferecem **Perfil** também oferecem uma seta pequena **Voltar** ao lado: gerenciador, Vitrine (inclusive perfil não encontrado), conversa e leitor de QR (inclusive permissão da câmera e conclusão). O [HeaderBackButton](../../mobile_app/src/components/header-back-button.tsx) usa o histórico do Expo Router e, sem tela anterior, o destino autorizado de Perfil/Painel. No leitor, permanece bloqueado durante a autorização do resgate. Para localizar todos os usos, pesquisar `HeaderBackButton` em `mobile_app/src/app/`. Em 08/10/2026, build, TypeScript, lint, 66 testes do app e 7 do emulador Firestore passaram; retorno no gerenciador/Vitrine, abertura direta e cabeçalho com largura de 390 pixels foram conferidos no navegador.
