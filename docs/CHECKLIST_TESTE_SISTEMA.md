# Checklist de Teste — CRM Multi-Canal

URL: https://castro-crm-286866630844.southamerica-east1.run.app

## Restricoes Atuais

- Numero de teste Meta (+1 555-175-4802) so envia, nao recebe
- Token temporario (expira em horas, precisa de System User Token)
- Sem numero real conectado = sem inbound/webhook
- Destinatarios de teste: +55 31 98277-9779 e +55 31 98344-0484

---

## A. Login e Sessao

- [ ] Acessar a URL e ver tela de login
- [ ] Login com conta Google do dominio permitido
- [ ] Verificar que o nome e role aparecem no topo
- [ ] Logout funciona
- [ ] Login com conta fora do dominio e bloqueado

## B. Departamentos (Admin > Administracao > aba Departamentos)

- [ ] Ver departamentos existentes (Geral, Vendas, Suporte, Financeiro)
- [ ] Criar novo departamento (ex: "Cadastro")
- [ ] Editar nome de um departamento
- [ ] Editar descricao de um departamento
- [ ] Remover um departamento (confirmar no dialog)
- [ ] Verificar que o departamento removido nao aparece mais na lista

## C. Canais WhatsApp (Admin > Administracao > aba Canais WhatsApp)

- [ ] Ver o canal "Canal Principal" criado pelo bootstrap
- [ ] Verificar que mostra tipo "Cloud API" e status "Ativo"
- [ ] Verificar que nao aparece botao "Desativar" no canal standard

## D. Usuarios e Roles (painel lateral direito, secao Usuarios e Roles)

- [ ] Ver lista de operadores
- [ ] Editar role de um operador (admin/supervisor/operador)
- [ ] Editar departamento de um operador
- [ ] Salvar alteracoes

## E. Reatribuicao em Lote (painel lateral direito)

- [ ] Ver secao "Reatribuicao em lote" (apenas admin/supervisor)
- [ ] Selecionar operador de origem
- [ ] Escolher acao "Devolver ao bot"
- [ ] Escolher acao "Transferir para operador"
- [ ] Botao desabilitado quando campos obrigatorios vazios

## F. Envio de Mensagens (numero de teste)

- [ ] Selecionar um contato existente (ou esperar ter um)
- [ ] Enviar mensagem de texto
- [ ] Verificar que a mensagem chega no destinatario (+55 31 98277-9779)
- [ ] Enviar template hello_world
- [ ] Enviar imagem
- [ ] Enviar audio gravado
- [ ] Enviar documento
- [ ] Enviar localizacao

> Nota: Se nao houver contatos no sistema, crie um manualmente
> enviando um template via API ou aguarde o numero real ser conectado.

## G. Qualificacao de Contato

- [ ] Mudar qualificacao para "Em atendimento"
- [ ] Mudar para "Qualificado"
- [ ] Mudar para "Nao qualificado" — contato muda de aba
- [ ] Mudar para "Convertido" — sistema tenta enviar rating template
  - [ ] Se template nao existe na Meta, ver mensagem de aviso no response
- [ ] Verificar que "Sem classificacao" NAO aparece no dropdown
- [ ] Salvar notas no campo de texto

## H. Transferencia de Contato

- [ ] Selecionar operador destino
- [ ] Selecionar departamento destino
- [ ] Preencher motivo e resumo
- [ ] Transferir e verificar que contato mudou de operador
- [ ] Verificar mensagem de sistema na conversa

## I. Devolver ao Bot

- [ ] Selecionar contato atribuido a alguem
- [ ] Clicar "Devolver ao bot" (apenas admin/supervisor)
- [ ] Confirmar no dialog
- [ ] Verificar que contato voltou para aba "Novos"

## J. Dashboard (Configuracoes > Dashboard)

- [ ] Abrir o dashboard (admin/supervisor)
- [ ] Ver cards de resumo (zerados inicialmente)
- [ ] Alterar intervalo de datas
- [ ] Clicar "Atualizar"
- [ ] Clicar "Exportar CSV" — verificar que baixa arquivo
- [ ] Verificar que operadores comuns NAO veem o botao Dashboard

## K. Configuracoes do Sistema (Admin > Administracao > aba Sistema)

- [ ] Habilitar/desabilitar prefixo de mensagem
- [ ] Alterar cargos com permissao de prefixo
- [ ] Alterar limite de mensagens rapidas
- [ ] Adicionar mensagem rapida global
- [ ] Salvar configuracoes

## L. Mensagens Rapidas (Configuracoes > Mensagens rapidas)

- [ ] Adicionar atalho + mensagem
- [ ] Salvar
- [ ] Digitar "/" no campo de mensagem e ver sugestoes
- [ ] Selecionar sugestao e verificar que preenche o campo

## M. Tema e Interface

- [ ] Alternar dark/light mode
- [ ] Buscar contato pelo nome/telefone
- [ ] Filtrar por qualificacao na aba "Meus"
- [ ] Verificar badges de contagem nao-lidas nas abas

## N. Embedded Signup / Coexistence (quando Meta aprovar)

- [ ] Configuracoes > WhatsApp Coexistence
- [ ] Verificar que abre o modal com instrucoes
- [ ] Iniciar Embedded Signup (requer popup do Facebook)
- [ ] Verificar que o canal coexistence aparece em Administracao > Canais

---

## O que NAO da para testar agora (precisa de numero real)

- Recebimento de mensagens (webhook inbound)
- Contato aparecendo automaticamente em "Novos"
- Operador assumir contato da fila
- Auto-atribuicao de coexistence
- Captura de avaliacao (lead responde 1-10)
- Lead convertido retornando ao operador original
- Metricas reais no dashboard (pico de mensagens, por operador)
- Transcricao de audio inbound
