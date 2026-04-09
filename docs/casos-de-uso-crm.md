# Casos de Uso - Castro Intelligence CRM WhatsApp

**Atualizado em:** 2026-04-08
**Objetivo:** Documentar os fluxos de atendimento do CRM multi-canal para revisao com a equipe.

---

## Fluxo 1: Cliente Novo Envia Primeira Mensagem

### Contexto
Um cliente que nunca entrou em contato antes envia uma mensagem pelo WhatsApp para o numero da empresa.

### Passo a Passo

**1. Cliente envia mensagem no WhatsApp**
- O cliente digita uma mensagem para o numero da empresa (ex: "Ola, gostaria de informacoes sobre locacao").
- A Meta recebe a mensagem e envia um webhook para o servidor do CRM.

**2. Sistema recebe e processa o webhook**
- O backend valida a assinatura do webhook (HMAC-SHA256).
- Cria um novo contato no Firestore com os dados:
  - Nome do perfil do WhatsApp
  - Numero de telefone formatado
  - Qualificacao: "novo"
  - Atribuicao: nenhuma (fila aberta)
  - Departamento: nenhum
  - Contador de nao-lidas: 1
- Salva a mensagem com direcao "inbound" e status "received".

**3. CRM atualiza em tempo real para todos os atendentes**
- O snapshot do Firestore detecta o novo contato.
- Todos os atendentes conectados veem o novo contato aparecer no topo da lista de conversas.
- Um badge com "1" aparece no contato indicando mensagem nao lida.

**4. Atendente visualiza o contato na fila**
- Na barra lateral (sidebar) "Conversas", o novo contato aparece com:
  - Inicial do nome (ou avatar se tiver)
  - Nome do perfil WhatsApp
  - Numero de telefone formatado
  - Chip "Sem setor" (nao atribuido a nenhum departamento)
  - Badge de nao-lida
  - Horario da ultima mensagem

---

## Fluxo 2: Atendente Abre e Responde uma Conversa

### Contexto
O atendente ve o novo contato na fila e decide iniciar o atendimento.

### Passo a Passo

**1. Atendente clica no contato na sidebar**
- O sistema carrega as ultimas 50 mensagens da conversa.
- As mensagens nao-lidas sao marcadas como "read" automaticamente.
- O badge de nao-lidas desaparece.

**2. Tela do chat exibe a conversa**
- No topo do chat aparece o banner do contato com:
  - Nome do cliente
  - Numero de telefone
  - Atribuicao atual ("Fila aberta" se ninguem assumiu)
  - Protocolo de atendimento (se houver)
  - Chip do departamento
  - Chip da qualificacao atual
- A area de mensagens mostra o historico com:
  - Mensagens do cliente (alinhadas a esquerda)
  - Mensagens do atendente (alinhadas a direita)
  - Mensagens de sistema (centralizadas, ex: transferencias)
  - Horario de cada mensagem
  - Status de entrega (enviado / entregue / lido)
- Na parte inferior, o campo de digitacao com:
  - Area de texto para digitar a mensagem
  - Botao de anexar (clipe) com submenu
  - Botao de enviar / gravar audio

**3. Atendente assume o atendimento**
- Clica no botao "Assumir" no painel lateral direito.
- O sistema:
  - Atribui o contato ao atendente
  - Gera um protocolo de atendimento (ex: "ATD-20260321-143022-001")
  - Registra a data/hora de inicio do atendimento
  - Insere uma mensagem de sistema na conversa: "Atendimento assumido por [Nome]"
- O banner do chat atualiza mostrando o nome do atendente e o protocolo.

**4. Atendente digita e envia uma mensagem de texto**
- Digita a mensagem no campo de texto.
- Pressiona Enter ou clica no botao de enviar.
- O sistema:
  - Envia a mensagem para a Meta Cloud API
  - Salva no Firestore com status "sent"
  - A mensagem aparece instantaneamente no chat (alinhada a direita)
- A Meta entrega ao cliente e envia webhooks de status:
  - "sent" -> icone de check simples
  - "delivered" -> icone de check duplo
  - "read" -> icone de check duplo azul
- O status atualiza em tempo real no chat do atendente.

**5. Cliente responde**
- A resposta do cliente aparece automaticamente no chat do atendente via snapshot.
- O contador de nao-lidas NAO incrementa porque o atendente ja esta com a conversa aberta.

---

## Fluxo 3: Envio de Midia (Imagem, Video, Documento)

### Contexto
O atendente precisa enviar uma imagem, video ou documento para o cliente.

### Passo a Passo

**1. Atendente clica no botao de anexar (clipe)**
- Um submenu aparece com as opcoes:
  - Imagem (abre seletor de arquivos, filtro: imagens)
  - Video (abre seletor de arquivos, filtro: videos)
  - Documento (abre seletor de arquivos, qualquer tipo)
  - Localizacao (usa GPS do navegador)

**2. Atendente seleciona um arquivo**
- Escolhe o arquivo no explorador de arquivos do computador.
- O sistema:
  - Faz upload do arquivo para o backend
  - Backend faz upload para a Meta via Media API
  - Meta processa e entrega ao cliente
  - Mensagem salva no Firestore com caminho da midia
- A imagem/video aparece inline no chat com preview.
- Documentos aparecem como link clicavel.

**3. Cliente envia uma imagem ou video**
- A midia aparece inline no chat do atendente.
- Imagens podem ser ampliadas clicando (abre lightbox).
- Videos podem ser reproduzidos diretamente no chat.

---

## Fluxo 4: Gravacao e Envio de Audio

### Contexto
O atendente quer enviar uma mensagem de voz ao cliente.

### Passo a Passo

**1. Atendente clica no botao de microfone**
- O navegador solicita permissao para acessar o microfone (primeira vez).
- Ao conceder, a gravacao inicia imediatamente.
- O botao muda para um indicador de gravacao com contador de segundos.

**2. Durante a gravacao**
- O contador mostra o tempo de gravacao em segundos.
- O atendente pode:
  - Clicar no botao de enviar (icone muda para "enviar") para finalizar e enviar
  - Clicar no botao de cancelar (X) para descartar a gravacao

**3. Atendente finaliza e envia**
- A gravacao para.
- O sistema:
  - Captura o audio em formato WebM/Opus
  - Envia ao backend
  - Backend converte de WebM para OGG/Opus via FFmpeg (requisito da Meta)
  - Faz upload para a Meta
  - Meta entrega ao cliente como mensagem de voz
- O audio aparece no chat com player inline.

**4. Cliente envia um audio**
- O audio aparece no chat com player inline.
- Abaixo do player, um botao "Transcrever" permite converter o audio em texto usando Google Speech-to-Text (se habilitado).
- Apos a transcricao, o texto aparece abaixo do player permanentemente.

---

## Fluxo 5: Qualificacao do Contato

### Contexto
O atendente precisa classificar o contato conforme o estagio do atendimento.

### Passo a Passo

**1. Atendente abre o painel de detalhes do contato**
- Clica no menu de 3 pontos no canto superior do chat.
- Seleciona "Detalhes" ou o painel lateral direito ja esta visivel.

**2. Atendente altera a qualificacao**
- No painel de detalhes, encontra o campo "Qualificacao" com as opcoes:
  - **Novo** - Cliente acabou de entrar em contato
  - **Em atendimento** - Conversa ativa em andamento
  - **Qualificado** - Cliente com potencial de conversao
  - **Nao qualificado** - Cliente sem perfil para o servico
  - **Convertido** - Cliente fechou negocio

**3. Atendente adiciona observacoes**
- Campo de texto livre para anotacoes (ex: "Cliente interessado em locacao de betoneira para obra em Curitiba. Orcamento enviado.").
- Clica em "Salvar".
- O chip de qualificacao atualiza no banner do chat e na lista de contatos.

---

## Fluxo 6: Transferencia de Atendimento

### Contexto
O atendente precisa transferir o contato para outro operador ou departamento (ex: transferir do Comercial para o Suporte).

### Passo a Passo

**1. Atendente abre o formulario de transferencia**
- No painel lateral do chat, encontra a secao "Transferir atendimento".

**2. Preenche os dados da transferencia**
- **Para qual operador:** Seleciona o operador de destino na lista.
- **Para qual departamento:** Seleciona o departamento (opcional).
- **Motivo:** Campo de texto curto (ex: "Cliente precisa de suporte tecnico").
- **Resumo do atendimento:** Campo de texto obrigatorio com o resumo do que foi tratado ate o momento (ex: "Cliente solicitou orcamento para locacao de 3 betoneiras. Orcamento enviado por email. Aguardando aprovacao do financeiro do cliente.").

**3. Atendente confirma a transferencia**
- Clica em "Transferir".
- O sistema:
  - Atualiza a atribuicao do contato para o novo operador
  - Atualiza o departamento do contato
  - Insere uma mensagem de sistema na conversa com os detalhes da transferencia
  - Registra no log de transferencias (wa_transfer_log)
  - Gera um novo protocolo de atendimento
  - Registra no log de auditoria

**4. Novo operador recebe o contato**
- O contato aparece na fila do novo operador em tempo real (via snapshot).
- Ao abrir a conversa, o novo operador ve:
  - Todo o historico de mensagens anteriores
  - A mensagem de sistema com o resumo da transferencia
  - O protocolo anterior e o novo

**5. Historico de transferencias**
- No painel de detalhes do contato, a secao "Historico de transferencias" mostra todas as movimentacoes:
  - De quem -> Para quem
  - De qual departamento -> Para qual departamento
  - Motivo e resumo
  - Data e hora
  - Quem realizou a transferencia

---

## Fluxo 7: Arquivamento e Restauracao de Contato

### Contexto
O atendimento foi concluido e o atendente deseja arquivar a conversa para manter a fila limpa.

### Passo a Passo

**1. Atendente arquiva o contato**
- No painel de detalhes, clica em "Arquivar conversa".
- O contato desaparece da lista de conversas ativas.
- Os dados e historico sao preservados no Firestore.

**2. Restauracao (se necessario)**
- Se o cliente enviar uma nova mensagem, o contato pode ser restaurado.
- Tambem e possivel restaurar manualmente pelo painel de administracao.
- Ao restaurar, o contato volta a aparecer na fila com todo o historico preservado.

---

## Fluxo 8: Visibilidade por Perfil (Admin vs Operador)

### Contexto
Diferentes perfis tem diferentes niveis de visibilidade das conversas.

### Regras de Visibilidade

**Administrador / Supervisor:**
- Ve TODAS as conversas de todos os operadores e departamentos.
- Pode assumir qualquer conversa.
- Pode transferir conversas entre operadores.
- Acessa painel de administracao de usuarios.

**Operador:**
- Ve apenas conversas atribuidas a si mesmo.
- Ve conversas na fila aberta (sem atribuicao).
- Ve conversas do seu departamento.
- Pode assumir conversas da fila aberta.
- NAO ve conversas atribuidas a outros operadores de outros departamentos.

---

## Fluxo 9: Login e Autenticacao

### Passo a Passo

**1. Atendente acessa a URL do CRM**
- O sistema exibe a tela de login com o botao "Entrar com Google".
- Uma mensagem indica qual dominio de email e aceito (ex: "Use sua conta centralloc.com.br").

**2. Atendente clica em "Entrar com Google"**
- Popup do Google aparece para selecionar a conta.
- O atendente seleciona sua conta corporativa.

**3. Sistema valida o acesso**
- Verifica se o email esta na lista de permitidos ou no dominio autorizado.
- Se e o primeiro acesso:
  - Cria automaticamente o usuario no sistema
  - Atribui o perfil de "operador" por padrao
  - Cria o perfil de operador no Firestore
- Se ja tem conta:
  - Sincroniza os dados do perfil
  - Atualiza ultimo login

**4. CRM carrega**
- A interface do CRM aparece com:
  - Barra superior: nome do usuario, email, role, botao de tema, botao de sair
  - Sidebar: lista de conversas
  - Area central: chat (vazio ate selecionar uma conversa)

---

## Fluxo 10: Busca de Contatos

### Passo a Passo

**1. Atendente digita no campo de busca**
- No topo da sidebar, existe um campo de texto "Buscar contato".
- A busca filtra em tempo real pelo nome ou numero do contato.
- A lista de conversas atualiza instantaneamente conforme o atendente digita.

**2. Resultado da busca**
- Apenas os contatos que correspondem ao filtro sao exibidos.
- Ao limpar o campo, a lista completa retorna.

---

## Fluxo 11: Envio de Localizacao

### Passo a Passo

**1. Atendente clica em Anexar > Localizacao**
- O navegador solicita permissao de geolocalizacao (primeira vez).
- O GPS do dispositivo captura a posicao atual.

**2. Sistema envia a localizacao**
- As coordenadas (latitude e longitude) sao enviadas via Meta API.
- O cliente recebe um pin de localizacao no WhatsApp.
- No chat do CRM, a mensagem aparece como "Localizacao enviada".

---

## Fluxo 12: Scroll Infinito (Paginacao de Mensagens)

### Contexto
O contato tem um historico longo de mensagens e o atendente precisa ver mensagens antigas.

### Passo a Passo

**1. Atendente abre a conversa**
- As ultimas 50 mensagens sao carregadas automaticamente.

**2. Atendente rola para cima (scroll up)**
- Ao atingir o topo da lista, o sistema carrega automaticamente as proximas 50 mensagens mais antigas.
- As mensagens sao adicionadas ao topo da lista sem perder a posicao atual de leitura.

**3. Comportamento continuo**
- O processo se repete conforme o atendente continua rolando para cima.
- Todas as mensagens ja carregadas permanecem na tela.

---

## Resumo Visual dos Estados do Contato

```
[Cliente envia msg] --> Qualificacao: NOVO
                        Atribuicao: Fila aberta
                        Badge: 1 nao-lida
        |
        v
[Atendente assume] --> Qualificacao: EM ATENDIMENTO
                       Atribuicao: Nome do atendente
                       Protocolo: ATD-XXXXXXXX-XXXXXX-XXX
        |
        v
[Conversa em andamento] --> Troca de mensagens texto/midia/audio
        |
        |--- [Transferencia] --> Novo operador assume
        |                        Novo protocolo gerado
        |                        Historico preservado
        |
        v
[Atendente qualifica] --> QUALIFICADO ou NAO QUALIFICADO ou CONVERTIDO
        |
        v
[Atendente arquiva] --> Conversa sai da fila ativa
                        Dados preservados no Firestore
        |
        v
[Cliente envia nova msg] --> Contato pode ser restaurado
                             Historico completo disponivel
```

---

## Elementos da Interface (Referencia para Revisao)

### Barra Superior (Topbar)
- Logo "Hubloc CRM"
- Nome e email do atendente logado
- Chip com o cargo (admin / supervisor / operador)
- Indicador de modo (Snapshot / Polling)
- Botao de alternar tema (claro/escuro)
- Botao "Sair"

### Sidebar (Lista de Conversas)
- Campo de busca
- Seletor de modo de transporte (Snapshot / Polling)
- Lista de contatos com:
  - Avatar ou inicial do nome
  - Nome do contato
  - Numero de telefone
  - Departamento (chip)
  - Badge de nao-lidas
  - Horario da ultima mensagem

### Area de Chat
- Banner do contato (nome, telefone, atribuicao, protocolo, qualificacao)
- Botoes de acao (Assumir, menu 3 pontos)
- Area de mensagens com scroll
- Compositor de mensagens:
  - Campo de texto (Enter envia, Shift+Enter quebra linha)
  - Botao anexar (imagem, video, documento, localizacao)
  - Botao enviar / gravar audio (muda conforme contexto)

### Painel Lateral Direito (Detalhes)
- Info do canal (Cloud API ou Coexistence + nome do canal)
- Badge de avaliacao (1-10, color-coded, apenas admin/supervisor)
- Qualificacao (select + notas + salvar)
- Botao "Devolver ao bot" (admin/supervisor, quando contato atribuido)
- Botao "Assumir atendimento"
- Formulario de transferencia
- Historico de transferencias
- Secao "Reatribuicao em lote" (admin/supervisor)
- Botao "Arquivar conversa"

---

## Fluxo 13: Mensagem Chega no Numero Coexistence do Operador

### Contexto
O operador Timmy tem um numero WhatsApp Business pessoal conectado ao CRM via coexistence. Um cliente antigo envia mensagem para o numero do Timmy.

### Passo a Passo

**1. Cliente envia mensagem para o numero do Timmy**
- A Meta envia webhook com o `phone_number_id` do numero do Timmy.

**2. Webhook resolve o canal**
- `channel_service` identifica o canal coexistence pelo `phone_number_id`.
- `upsert_wa_contact` auto-atribui o contato ao Timmy (`owner_user_id` do canal).
- Qualificacao muda para "em_atendimento".

**3. Contato aparece em "Meus Atendimentos" do Timmy**
- Outros operadores NAO veem este contato (filtro de coexistence).
- Admin/Supervisor ve na aba "Equipe" com badge "coex".

**4. Timmy responde pelo CRM**
- O sistema usa o token e phone_number_id do canal coexistence para enviar.
- Timmy tambem pode responder pelo celular (mensagem ecoa no CRM via `smb_message_echoes`).

---

## Fluxo 14: Avaliacao Pos-Conversao

### Contexto
O operador fechou negocio com um cliente e marca como "Convertido".

### Passo a Passo

**1. Operador marca o contato como "Convertido"**
- No painel de qualificacao, seleciona "Convertido" e salva.

**2. Sistema envia template de avaliacao**
- Envia template `rating_request` via WhatsApp (1-10).
- Mensagem de avaliacao tem `visibility: admin_only` — operadores NAO veem.
- Se o template nao existe na Meta, a conversao ocorre normalmente sem rating.

**3. Cliente responde com um numero de 1 a 10**
- Webhook captura a resposta automaticamente.
- Nota gravada no contato (`rating: 7`).
- Resposta tambem marcada como `admin_only`.

**4. Admin/Supervisor ve a avaliacao**
- No DetailPanel: badge de rating color-coded (verde 7+, amarelo 4-6, vermelho 1-3).
- No Dashboard: tabela de avaliacoes com contato, nota, operador e data.
- Operadores comuns NAO veem a nota nem as mensagens de avaliacao.

---

## Fluxo 15: Lead Convertido Retornante

### Contexto
Um cliente que ja fechou negocio envia nova mensagem meses depois.

### Passo a Passo

**1. Cliente envia mensagem**
- Webhook detecta que o contato tem `qualification: "convertido"`.

**2. Se tem rating pendente e responde com numero 1-10**
- Sistema captura a nota (Fluxo 14).

**3. Se nao eh rating (mensagem normal)**
- Sistema reatribui ao `original_operator_id` (operador que primeiro atendeu).
- Muda qualificacao para "em_atendimento".
- Contato aparece em "Meus Atendimentos" do operador original.

---

## Fluxo 16: Devolver Contato ao Bot

### Contexto
Admin precisa devolver um contato para a fila de novos leads (ex: operador errou ao assumir).

### Passo a Passo

**1. Admin seleciona o contato**
- Abre o painel de detalhes do contato.

**2. Clica em "Devolver ao bot"**
- Confirma no dialog.
- Sistema reseta: `assigned_to=null`, `qualification="novo"`.
- Insere mensagem de sistema na conversa.

**3. Contato volta para aba "Novos"**
- Qualquer operador pode assumir novamente.

---

## Fluxo 17: Reatribuicao em Lote (Operador Sai da Empresa)

### Contexto
O operador Timmy saiu da empresa. Admin precisa redistribuir seus contatos.

### Passo a Passo

**1. Admin abre secao "Reatribuicao em lote"**
- No painel lateral direito do CRM.

**2. Seleciona operador de origem (Timmy)**
- Lista mostra todos os operadores.

**3. Escolhe a acao**
- **"Devolver ao bot"** — todos contatos do Timmy voltam para "Novos".
- **"Transferir para operador X"** — todos contatos vao para outro operador.

**4. Confirma e executa**
- Sistema processa todos os contatos em lote.
- Mensagem de sistema inserida em cada conversa.
- Log de auditoria registra a reatribuicao.

---

## Fluxo 18: Dashboard de Auditoria

### Contexto
Admin/Supervisor quer ver metricas de atendimento e desempenho da equipe.

### Passo a Passo

**1. Abre o Dashboard**
- Menu de configuracoes (engrenagem) > Dashboard.

**2. Seleciona intervalo de datas**
- Padrao: ultimos 30 dias.

**3. Visualiza metricas**
- Cards: leads recebidos, leads assumidos, mensagens recebidas/enviadas, total.
- Grafico de barras: pico de mensagens por meia hora.
- Tabela por operador: mensagens e leads assumidos.
- Tabela de avaliacoes: contato, nota, operador, data.

**4. Exporta dados**
- Botao "Exportar CSV" baixa arquivo com todos os contatos e metadados.

---

## Fluxo 19: Gerenciamento de Departamentos

### Contexto
Admin precisa criar novos setores ou reorganizar a estrutura.

### Passo a Passo

**1. Abre Administracao > aba Departamentos**
- Menu de configuracoes > Administracao > aba Departamentos.

**2. CRUD de departamentos**
- Criar: nome + descricao.
- Editar: alterar nome ou descricao.
- Remover: confirma no dialog (desativa, nao deleta).

**3. Atribuir operadores a departamentos**
- Na secao "Usuarios e Roles", editar o departamento de cada operador.

---

## Resumo Visual dos Estados do Contato (atualizado)

```
[Lead envia msg no numero standard]
    --> Qualificacao: NOVO
        Atribuicao: Fila aberta (bot futuro)
        Canal: standard
        |
        v
[Lead envia msg no numero coexistence do Timmy]
    --> Qualificacao: EM ATENDIMENTO
        Atribuicao: Timmy (auto)
        Canal: coexistence
        |
        v
[Operador assume / auto-atribuido]
    --> original_operator_id gravado
        Protocolo: ATD-XXXXXXXX-XXXXXX-XXX
        |
        v
[Conversa em andamento]
    |--- [Transferencia] --> Novo operador/departamento
    |--- [Devolver ao bot] --> Volta para "Novos"
    |
    v
[Operador qualifica]
    --> QUALIFICADO | NAO QUALIFICADO | CONVERTIDO
        |
        v (se convertido)
[Rating enviado] --> Cliente responde 1-10
        |
        v
[Lead convertido retorna] --> Reatribuido ao operador original
```
