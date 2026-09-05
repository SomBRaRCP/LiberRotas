# LiberRotas — roteiro de evolução

> O nome do arquivo foi mantido para não quebrar referências antigas. O
> conteúdo descreve o LiberRotas atual; o roteiro FeiTUR V3 original foi
> superado.

## Estado atual

Concluído no workspace:

1. Firebase Authentication por e-mail/senha e sessão com `onAuthStateChanged`.
2. Entrada única; Visitante e Empreendedor são escolhidos somente no cadastro.
3. Funções, status e permissões resolvidos pelo backend.
4. Painéis de Administrador, Suporte, Segurança e Instituição.
5. Feed único, pesquisa, compartilhamento, comentários, respostas e curtidas.
6. Edição/exclusão de conteúdo próprio.
7. Imagens JPEG/PNG/WebP em armazenamento privado; vídeo oculto nesta fase.
8. Mensagens privadas com imagem, bloqueio e chamados do Suporte.
9. Mapa interativo, pontos e feiras publicados somente por Empreendedor.
10. Produtos e estoques com ativação/exclusão em massa.
11. Ofertas gerenciadas na Vitrine, QR individual/combinado e quantidade
    assinada.
12. Resgate online com dispositivo, desafio, anti-replay e commit transacional.
13. Grupos, filiações, relatórios e eventos institucionais com verba.
14. Visitante com liberação imediata e alerta; todo novo dispositivo de empreendedor ou instituição com cooldown de 10 minutos e alerta **Não fui eu!**.

## Próximas validações

### 1. Fluxo comercial em dois aparelhos

- gerar QR individual com quantidade maior que `1`;
- gerar QR combinado com 2 a 5 ofertas;
- conferir fechamento automático na tela do vendedor;
- conferir estoque, vendidos, totais e resultado parcial.

### 2. Mídia e comunidade

- publicar imagens com resoluções e proporções diferentes;
- abrir imagens e foto do perfil no visualizador com zoom;
- testar imagem privada em conversa;
- testar autoria para editar/excluir post e comentário;
- confirmar que novos uploads rejeitam vídeo e outros arquivos.

### 3. Instituição

- criar grupo, convidar e filiar empreendedor;
- criar evento com divisão igual;
- ajustar cota por vendedor e produto;
- ativar, usar cupons, encerrar e emitir relatório;
- confirmar isolamento entre instituições.

### 4. Operação e segurança

- validar entrega SMTP e o link **Não fui eu!**;
- confirmar ativação automática depois de 10 minutos;
- validar troca de senha com revogação de dispositivos e sessões;
- revisar regras Firestore, credenciais GCS e restrições de chaves antes de
  qualquer piloto público.

## Evoluções futuras

- vídeo e outros anexos com processamento, limites e política própria;
- upload remoto de avatar, capa e imagens de produto;
- notificações de mensagens, feiras e cupons;
- mapa nativo quando houver requisito acadêmico e orçamento;
- pedidos sem pagamento na Fase 2;
- pagamentos somente na Fase 3, com provedor e webhook autoritativos;
- pós-quântico apenas com provider auditado;
- IA somente em modo observador até existir validação específica.
