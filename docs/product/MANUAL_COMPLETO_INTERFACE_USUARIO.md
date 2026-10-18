# Castro Intelligence — Manual completo da interface do usuário

**Versão:** 1.0 · **Data da análise:** 2 de outubro de 2026  
**Público:** operadores, supervisores, administradores da empresa e administradores da plataforma.  
**Base:** código disponível neste repositório, referência Git `6951f6f`, incluindo o estado local dos arquivos examinados.

## 1. Objetivo e alcance

Este documento descreve as telas, controles, campos, ações, fluxos e restrições da interface do Castro Intelligence. Abrange o CRM de atendimento e o portal separado de administração da plataforma.

A documentação foi conferida no frontend e nos respectivos caminhos de execução do backend. **Não é uma homologação do ambiente de produção:** não foram feitos login real, envio de mensagens, alteração de cadastros ou conexão de canais. Recursos existentes no código podem estar desativados para determinada empresa, depender de permissões ou exigir uma integração configurada.

Os nomes entre aspas correspondem aos rótulos da interface, com acentuação normalizada para facilitar a leitura. Alguns rótulos reais ainda aparecem sem acentos ou em inglês.

### 1.1 Como interpretar a disponibilidade

| Indicação | Significado |
|---|---|
| Disponível | Existe uma interface com ação implementada no código analisado. |
| Condicional | Depende de perfil, configuração da empresa, estado do atendimento ou integração. |
| Restrito à plataforma | Está no portal de superadmin, separado do CRM. |
| Sem interface | Pode existir em API, script ou planejamento, mas não há controle correspondente nas telas examinadas. |

### 1.2 Índice

1. Objetivo e alcance
2. Conceitos e organização da tela
3. Entrada, sessão e aparência
4. Perfis e permissões
5. Caixas de atendimento, filtros e leitura
6. Agenda e cadastro de contatos
7. Conversa e envio de mensagens
8. Operação do contato e do atendimento
9. Templates e reabertura individual
10. Fluxos de trabalho
11. Preferências, mensagens rápidas e tags
12. Administração da empresa
13. Conexão e gestão de WhatsApp
14. Reabertura em lote
15. Dashboard e exportação
16. Chat interno
17. Portal de administração da plataforma
18. Comportamentos condicionais e limitações
19. Referências e manutenção

## 2. Conceitos e organização da tela

### 2.1 Conceitos fundamentais

| Conceito | O que representa para o usuário |
|---|---|
| Empresa ou tenant | Ambiente da organização, com seus usuários, contatos, configurações e canais. |
| Contato ou lead | Cadastro da pessoa: nome, telefone, qualificação, notas, etiquetas e dono comercial. |
| Atendimento ou conversa | Conversa daquele contato em um canal WhatsApp específico. Tem responsável, mensagens, não lidas e situação próprios. |
| Dono do lead | Responsável pelo relacionamento comercial com o contato. |
| Dono do atendimento | Responsável pela conversa específica. Pode ser diferente do dono do lead. |
| Canal | Número WhatsApp conectado: Cloud API/Standard ou Coexistence. |
| Protocolo | Identificador do atendimento diário do lead, usado na consulta e no recibo de encerramento. |
| Qualificação | Situação ou resultado comercial do lead. É independente de a conversa estar aberta ou fechada. |
| Tag | Etiqueta aplicada ao contato para organização e filtros. |
| Takeover | Atendimento temporário de um lead de outro operador, principalmente em cenários Coexistence. |

Um contato pode aparecer em mais de uma linha na lista quando possui conversas em canais diferentes. Essas linhas não representam necessariamente cadastros duplicados: cada atendimento tem seu próprio histórico de canal, responsável e contador de mensagens não lidas.

### 2.2 Áreas da tela principal

| Área | Funcionalidades |
|---|---|
| Barra superior | Nome da empresa, usuário, e-mail/login, cargo, setor, tema, chat interno quando habilitado, configurações e saída. |
| Navegação lateral | Bot, Novos/Recepção, Meus, N/Q, Equipe e Backup, conforme acesso. |
| Lista de conversas | Busca, filtros, agenda, contadores, etiquetas, identificação do canal e seleção de atendimento. |
| Conversa central | Identificação do contato, contexto do atendimento, histórico, busca, ações de mensagens, anexos, texto, áudio e templates. |
| Painel Operação | Qualificação, notas, tags, transferência, gestão do dono, protocolos, conflitos e controles administrativos permitidos. |
| Janelas de configuração | Preferências, mensagens rápidas, tags, reabertura em lote, administração, perfis, WhatsApp e dashboard. |

Os cartões do painel Operação podem ser recolhidos e expandidos. Em telas com até 860 pixels de largura, o layout empilha os painéis, permite rolagem da página e transforma a navegação em uma faixa horizontal. Isso é adaptação do layout web; não há aplicativo móvel separado neste frontend.

## 3. Entrada, sessão e aparência

### 3.1 Autenticação

| Controle | Comportamento |
|---|---|
| Entrar com Google | Inicia a autenticação Google da conta fornecida pela empresa. |
| Entrar com e-mail/senha | Exibe campos de e-mail e senha e o botão Entrar. |
| Ocultar e-mail/senha | Recolhe o formulário alternativo. |
| Esqueci minha senha | Solicita recuperação para o e-mail informado; exige preencher o e-mail. |
| Verificação em duas etapas | Quando a conta exige autenticação adicional, solicita código de seis dígitos do aplicativo autenticador. |
| Verificar | Confirma o código; permanece desabilitado enquanto faltam dígitos ou a verificação está em andamento. |
| Cancelar | Cancela o desafio de autenticação em duas etapas. |
| Sair | Encerra a sessão no CRM. |

A tela inicial orienta a usar a conta fornecida pela empresa. Não há botão de cadastro público. Uma autenticação bem-sucedida no provedor ainda depende de autorização e associação à empresa para abrir o CRM.

O CRM possui a tela de **desafio** de autenticação em duas etapas. A interface para **cadastrar/remover** o autenticador descrita na seção 17 pertence ao portal superadmin.

### 3.2 Estados apresentados

- Carregamento inicial de Firebase e Firestore.
- Conexão/verificação em andamento, com prevenção de múltiplos cliques.
- Avisos de sucesso e mensagens de erro de autenticação.
- Tela de configuração inválida quando o backend não informa o modo de autenticação esperado.
- Área autenticada identificada pelo nome da empresa e pelos dados do usuário.

### 3.3 Aparência e mensagens de retorno

O botão de sol/lua alterna entre tema claro e escuro. A preferência é mantida no navegador. Ações operacionais exibem avisos como “Mensagem enviada”, “Atendimento transferido” ou mensagens de falha. No painel da conversa, os avisos podem ser dispensados pelo botão de fechar.

## 4. Perfis e permissões

O CRM combina **cargo** (`operador`, `supervisor`, `admin`) com **perfil de acesso**, que contém permissões por funcionalidade. Os perfis podem ser alterados pela empresa. Por isso, um recurso descrito neste documento pode não aparecer ou pode ser recusado ao executar uma ação.

O acesso geral à carteira da empresa exige, no frontend, cargo de administrador/supervisor e a permissão de ver todos os leads. Um operador não passa a enxergar toda a carteira apenas porque está no mesmo setor de outro operador.

As permissões e os padrões detalhados estão na subseção 4.1 abaixo. Além delas, permanecem válidas as regras de acesso ao contato, ao atendimento e ao canal. Alguns controles são exibidos de forma ampla, enquanto a validação específica ocorre no servidor.

### 4.1 Matriz dos perfis iniciais

**A matriz descreve os padrões iniciais do catálogo de permissões, não uma garantia fixa por cargo nem a existência de um botão para cada permissão.** “Sim” continua sujeito às regras do recurso. Perfis personalizados podem alterar esses padrões.

| Permissão do catálogo | Admin | Supervisor | Operador |
|---|:---:|:---:|:---:|
| Ver todos os leads/atendimentos | Sim | Sim | Não |
| Enviar mensagem em conversa própria | Sim | Sim | Sim |
| Enviar/intervir em qualquer conversa | Sim | Sim | Não |
| Assumir atendimento da fila | Sim | Sim | Sim |
| Assumir conversa do próprio número Coexistence | Sim | Não* | Sim |
| Assumir como supervisor | Sim | Sim | Não |
| Transferir atendimento | Sim | Sim | Sim |
| Fechar atendimento manualmente | Sim | Sim | Sim |
| Reabrir atendimento manualmente | Sim | Sim | Sim |
| Enviar nota interna | Sim | Sim | Não |
| Enviar template | Sim | Sim | Sim |
| Reatribuir dono do lead/devolver ao bot | Sim | Sim | Não |
| Qualificar lead | Sim | Sim | Sim |
| Gerenciar tags globais | Sim | Sim | Não |
| Filtrar agenda por tag | Sim | Sim | Não |
| Disparar reabertura em lote | Sim | Sim | Não |
| Editar nome declarado/apelido | Sim | Sim | Sim |
| Arquivar lead — sem controle localizado na UI atual | Sim | Sim | Sim |
| Adicionar contato manual | Sim | Sim | Sim |
| Exportar contatos/conversas — UI atual exporta contatos | Sim | Sim | Não |
| Gerenciar canais WhatsApp | Sim | Sim | Não |
| Desativar canais/descartar eventos de webhook | Sim | Não | Não |
| Autorizar Coexistence para operador | Sim | Sim | Não |
| Ver painel de conflitos | Sim | Sim | Não |
| Ver dashboard e uso | Sim | Sim | Não |
| Buscar protocolo | Sim | Sim | Não |
| Criar/editar usuários — UI atual tem edição limitada | Sim | Sim | Não |
| Desativar usuários — sem controle localizado na UI atual | Sim | Não | Não |
| Gerenciar perfis de acesso | Sim | Não | Não |
| Criar/editar setores | Sim | Sim | Não |
| Desativar setores | Sim | Não | Não |
| Alterar configurações do sistema | Sim | Não | Não |

\* O supervisor tem outra permissão para assumir como supervisão. A ausência do toggle específico de Coexistence não elimina todas as formas autorizadas de intervenção.

### 4.2 Regras de interpretação

- O administrador da **plataforma** usa portal separado; não é simplesmente um quarto cargo com visão de todos os clientes dentro do CRM.
- O perfil de sistema Administrador mantém todas as permissões ligadas. Perfis personalizados podem partir de uma base administrativa com regras próprias.
- Alguns menus exigem uma permissão mais ampla para abrir. Por exemplo, a administração exige configuração do sistema, mesmo que o usuário possua permissão isolada de gerenciar setores.
- A tela informa atualização de perfis aos usuários conectados, mas mudanças de cargo/credenciais podem exigir nova autenticação.
- O servidor impede mudanças do próprio cargo/perfil e restringe concessões de privilégios superiores aos de quem altera.
- O catálogo contém permissões para operações que hoje só existem em API ou ferramentas administrativas. Elas estão identificadas na matriz e na seção 18.

## 5. Caixas de atendimento, filtros e leitura

### 5.1 Caixas disponíveis

| Caixa | Conteúdo e condição |
|---|---|
| Bot | Conversas sem responsável cujo contato ainda está na etapa do bot, excluindo não qualificados e backups. Exige acesso amplo e bot habilitado. |
| Novos | Fila sem dono do lead e sem dono do atendimento. Com bot habilitado, inclui quem já terminou a etapa do bot. Operadores visualizam a fila compatível com seu setor ou sem setor. |
| Recepção | Nome da caixa Novos quando a empresa usa fila compartilhada. Permite atendimento de conversas elegíveis sem assumir, conforme as regras da seção 8. |
| Meus | Conversas atribuídas ao usuário, incluindo conversas Coexistence e excluindo backups. |
| N/Q | Conversas de contatos classificados como Não qualificado, dentro do acesso do usuário. |
| Equipe | Conversas atribuídas a outros operadores. Exige acesso amplo à carteira. |
| Backup | Conversas identificadas como histórico importado. Exige acesso amplo. Canal inativo resulta em leitura sem envio. |

As caixas são filtros operacionais. “Meus” não significa exclusivamente conversa aberta: a situação do atendimento também aparece no contexto da conversa. N/Q é um recorte pela qualificação e pode se sobrepor a outros recortes de responsabilidade.

### 5.2 Informações de cada conversa

- Foto disponível do contato ou inicial do nome.
- Nome de exibição e telefone.
- Data/hora da última mensagem.
- Qualificação do lead.
- Quantidade de mensagens não lidas daquela conversa.
- Identificação do canal e distinção entre Cloud API e Coexistence.
- Temperatura quente, morna ou fria, quando essa informação é produzida pela integração de IA.
- Na caixa Equipe, identificação e cor do operador responsável.

A lista prioriza canais Standard e, dentro dos grupos, as conversas mais recentes. O cabeçalho informa a quantidade de conversas carregadas que corresponde ao recorte, além do total de contatos consultado para a agenda. Quantidade de conversas e quantidade de contatos são medidas diferentes.

### 5.3 Busca e filtros da caixa

| Controle | Funcionamento |
|---|---|
| Buscar contato | Filtra as conversas carregadas por nome, telefone formatado, setor ou nome do responsável. Não substitui a pesquisa da agenda completa. |
| Qualificação | Em Bot, Novos/Recepção, Meus e Equipe: Todos, Novo, Em atendimento, Qualificado, Convertido, Não convertido e Não lidas. |
| Não lidas | Seleciona conversas com pendência de leitura e permite buscar outras não lidas mais antigas. A conversa selecionada continua visível após ser lida. |
| Tags | Botões de etiquetas globais e pessoais. Selecionar várias exige que o lead tenha **todas** elas; combina com os demais filtros. Há botão para limpar. |
| Canal em Meus | Aparece quando há mais de um canal nas conversas do usuário. Seleciona um canal por vez, com Standard como prioridade inicial; não oferece Todos. |
| Operador em Equipe | Todos os outros operadores ou um operador específico. |
| Canal em Equipe | Aparece quando o operador selecionado tem conversas em mais de um canal. |
| Só espiar | Administradores/supervisores podem abrir sem marcar como lida. A preferência é lembrada no navegador. |

Ao trocar de caixa, os filtros de qualificação e tags são limpos. A busca da caixa trabalha sobre o conjunto carregado; contatos antigos devem ser procurados na agenda ou por carregamento adicional.

### 5.4 Carregamento adicional

Inicialmente são renderizadas até 50 linhas da lista. Conforme o caso, o botão inferior mostra:

- **Mostrar mais:** revela mais conversas já carregadas.
- **Buscar conversas mais antigas:** consulta páginas adicionais da caixa suportada.
- **Buscar mais não lidas:** amplia o resultado específico de não lidas.
- **Carregando:** informa uma consulta em andamento.

Uma página pode não acrescentar linhas visíveis se todas as conversas retornadas forem excluídas pelos filtros. O número de itens na tela não deve ser tratado como total histórico definitivo.

### 5.5 Leitura, atualizações e sons

Abrir um atendimento normalmente marca como lidas as mensagens daquela conversa. O modo Só espiar preserva a pendência. Se uma conversa mudar de responsável e o usuário perder acesso, o chat é fechado.

O frontend recebe atualizações em tempo real quando a configuração permite, com consultas periódicas como alternativa. O som de mensagem nova e o alarme de atraso usam as conversas ao vivo de Novos/Recepção e Meus. Eles não representam um alarme de todos os contatos da empresa, nem apenas da aba atualmente selecionada.

O alarme depende de estar habilitado e de o setor do usuário fazer parte da configuração. Uma conversa com mensagens não lidas passa a ser considerada atrasada pelo tempo desde a última mensagem recebida do cliente, com alternativa para registros antigos. Enquanto houver pendência, o alarme pode se repetir a cada 30 segundos. O navegador precisa permitir reprodução de áudio.

## 6. Agenda e cadastro de contatos

### 6.1 Abrir e selecionar um contato

O botão de agenda nas caixas **Meus** e **Novos/Recepção** abre “Selecionar contato”. A janela permite pesquisar, filtrar, abrir uma conversa existente e criar contato manualmente.

Há duas implementações da agenda. A nova agenda depende de ativação por empresa ou usuário; o modo antigo permanece disponível.

### 6.2 Nova agenda paginada

| Funcionalidade | Comportamento |
|---|---|
| Agenda A–Z | Ordenação alfabética, páginas de 50 e botão Ver mais. Contatos sem nome ficam depois dos que têm nome. |
| Busca por nome | Pesquisa pelo começo do nome ou sobrenome, com no mínimo duas letras. Desconsidera diferenças de acentos e maiúsculas. |
| Busca por telefone | Aceita número completo, começo ou final, com no mínimo quatro dígitos, inclusive entrada com máscara. |
| Disparo da busca | Após breve pausa ao digitar ou ao pressionar Enter. |
| Resultado | Nome, telefone, qualificação, responsável e canal quando aplicável. |
| Filtro de qualificação | Inclui também Não qualificado. |
| Filtro por responsável | Para quem possui acesso amplo: Meus, operadores específicos ou Todos. |
| Filtro por tag | Uma etiqueta por vez, quando o recurso e a permissão estiverem ativos. |
| Limpar filtros | Remove restrições que estejam ocultando resultados da busca. |
| Modo antigo | “Carregar agenda completa (modo antigo)” vale para a abertura atual; uma nova abertura reavalia a configuração. |

**Regras da busca:** `sil` pode localizar Silva; `ilv` não é uma busca pelo começo da palavra. Não há correção aproximada de erros de digitação. Quando houver muitos resultados, a interface pede mais caracteres. Filtros de responsável e qualificação podem restringir os resultados retornados e a tela informa os itens ocultos.

O filtro por tag funciona sozinho: selecionar uma etiqueta limpa a busca, o responsável e a qualificação; usar esses outros filtros desativa a etiqueta. Ele consulta somente contatos do escopo permitido, inclusive cadastros sem conversa anterior.

### 6.3 Agenda no modo antigo

Carrega a lista completa permitida e filtra localmente por nome/telefone, qualificação e, para usuários autorizados, responsável. A primeira abertura pode ser mais demorada em agendas grandes. As regras da pesquisa indexada da nova agenda não devem ser presumidas nesse modo.

### 6.4 Criar contato manual

1. Abrir a agenda e clicar em **+ Novo contato**.
2. Preencher nome e telefone, ambos obrigatórios.
3. Se houver múltiplos canais ativos, escolher o canal desejado. Sem escolha explícita, o servidor tenta o canal padrão.
4. Clicar em **Criar contato**; também é possível Voltar ou Cancelar.
5. A conversa é aberta quando a operação termina com sucesso.

O tratamento de telefone no cadastro é orientado a números brasileiros, com normalização e DDI 55. Um contato já existente pode gerar conflito conforme sua atribuição. A criação depende da permissão específica, mesmo quando o botão aparece.

No modo tradicional, o cadastro pode assumir o lead para quem o cria, se esse usuário tiver permissão. No modo Recepção, a criação/abertura mantém a lógica de fila compartilhada. **Criar ou abrir um contato não envia uma mensagem ao cliente.** Sem mensagem recebida que permita envio livre, a interface orienta iniciar por template.

## 7. Conversa e envio de mensagens

### 7.1 Cabeçalho e contexto

Ao selecionar um atendimento, o painel mostra nome de perfil do WhatsApp ou telefone, apelido registrado, responsável, setor, qualificação, protocolo e início quando disponíveis, temperatura do lead e tags.

Uma faixa adicional informa dono do lead, número/canal da conversa, situação do takeover, atendimento fechado quando aplicável e papel do usuário naquela conversa. Canais removidos ou antigos recebem indicação própria.

No cabeçalho ficam Assumir atendimento, Buscar na conversa e o menu Mais opções. O menu contém Enviar template, Editar apelido, Fechar/Reabrir atendimento, Copiar protocolo quando houver e Devolver à recepção nos casos elegíveis.

### 7.2 Histórico de mensagens

- Mensagens recebidas, enviadas, de sistema e notas internas têm apresentação própria.
- Cada item pode exibir remetente, data/hora, conteúdo, tipo e situação de envio/entrega/leitura recebida da integração.
- Respostas mostram uma prévia da mensagem citada.
- Correções deixam indicação de “corrigida” na mensagem original.
- Mensagens anteriores são carregadas ao rolar para o topo, com aviso de carregamento.
- A busca na conversa filtra o **conteúdo textual das mensagens já carregadas** e mostra quantidade de resultados. Não é uma pesquisa global de todo o histórico armazenado nem de todas as transcrições.

A exibição de status pode ser desativada pela configuração da aplicação. A atribuição de cores na caixa Equipe auxilia a identificar autores/responsáveis e não indica presença online.

### 7.3 Texto e formatação

Digite no campo de mensagem e pressione Enter ou o botão de envio. Shift+Enter insere uma quebra de linha. Campos e botões indicam processamento durante o envio.

O visualizador interpreta a formatação WhatsApp: negrito, itálico, riscado, monoespaçado, blocos monoespaçados, citações e listas. URLs e e-mails reconhecidos tornam-se links.

| Atalho no campo | Efeito |
|---|---|
| Enter | Envia a mensagem; com sugestão rápida destacada, primeiro insere a sugestão no campo. |
| Shift+Enter | Nova linha. |
| Ctrl+B ou Cmd+B | Envolve/remove marcadores de negrito. |
| Ctrl+I ou Cmd+I | Envolve/remove marcadores de itálico. |
| Ctrl+Shift+X ou Cmd+Shift+X | Envolve/remove marcadores de riscado. |
| Ctrl+Shift+M ou Cmd+Shift+M | Envolve/remove marcadores de monoespaçado. |
| `/` no início | Abre sugestões de mensagens rápidas compatíveis com o atalho digitado. |
| Setas para cima/baixo | Navegam pelas sugestões rápidas. |
| Tab | Insere a sugestão destacada ou a primeira, sem enviar. |
| Escape | Fecha sugestões; também fecha a ampliação de mídia quando aberta. |

O prefixo de identificação configurado para o usuário pode ser acrescentado ao texto conforme cargo e preferências. A seção 18 registra a limitação atual do interruptor global de prefixo.

### 7.4 Responder, copiar e corrigir

| Ação no menu da mensagem | Resultado |
|---|---|
| Responder | Coloca uma referência da mensagem acima do campo de escrita. O envio seguinte inclui a citação; o X cancela a referência. |
| Copiar | Copia o conteúdo textual disponível para a área de transferência, sujeito ao suporte do navegador. |
| Corrigir | Para texto enviado ainda não corrigido, de autoria do usuário ou acessível à supervisão autorizada. Abre o texto para revisão. |

**Corrigir envia uma nova mensagem como resposta à original.** Não substitui nem apaga a mensagem no WhatsApp do cliente. O original é marcado como corrigido no CRM. Durante a correção, anexos e modo interno ficam bloqueados; o envio exige texto não vazio. O X cancela a correção.

Mensagens de sistema e notas internas não recebem esse menu de interação na tela atual.

### 7.5 Foto, vídeo e documento

O botão **+** abre o menu de anexos:

| Opção | Entrada e comportamento |
|---|---|
| Foto | Seleciona arquivo de imagem no dispositivo e envia. |
| Vídeo | Seleciona arquivo de vídeo e envia. |
| Documento | Seletor oferece PDF, DOC/DOCX, XLS/XLSX, TXT, ZIP e CSV. |
| Localização | Solicita a posição atual do navegador e envia latitude/longitude. |

A seleção de arquivo dispara o envio; não há editor de legenda ou etapa de prévia no compositor atual. O servidor aplica limite de 16 MB aos uploads de mídia e áudio, além das validações da integração. O campo de mensagem não funciona como legenda automática do anexo.

Localização exige autorização no navegador; não há mapa para escolher manualmente outro endereço. A interface informa quando a permissão é negada, a localização não é suportada ou a consulta expira.

### 7.6 Áudio

Com o campo vazio, o botão principal apresenta o microfone. Ao clicar, solicita autorização de gravação e mostra indicador, tempo decorrido e Cancelar. Durante a gravação, o botão principal finaliza e envia o áudio. Cancelar descarta a gravação.

É necessário suporte do navegador a microfone e gravação de mídia. Falhas de permissão, captura vazia ou envio aparecem como erro. A tela não oferece edição de áudio nem pré-escuta antes do envio.

### 7.7 Recebimento e abertura de mídia

| Conteúdo | Apresentação |
|---|---|
| Imagem e figurinha | Miniatura com ação para ampliar. |
| GIF ou mídia reconhecida como animação | Reprodução/miniatura apropriada e ampliação quando disponível. |
| Vídeo comum | Link “Baixar vídeo”, com nome do arquivo quando disponível. |
| Áudio | Reprodutor com controles. |
| Documento/outros arquivos | Link “Abrir arquivo” ou nome do arquivo. |
| Transcrição existente | Texto exibido abaixo do áudio. |
| Áudio sem transcrição | Botão Transcrever; mostra processamento e depende da disponibilidade do serviço. |

A ampliação de mídia pode ser fechada pelo botão, pelo fundo da janela ou por Escape. O vídeo comum da conversa usa link de download; não deve ser confundido com os vídeos/GIFs que abrem no visualizador.

### 7.8 Nota interna — sussurro

Usuários com permissão podem ativar o botão de nota interna. O campo fica destacado e passa a indicar que o cliente não verá o texto. Ao enviar, o sistema grava uma nota na conversa, identificando o autor; não envia esse **texto** à Meta.

Esse modo atende ao texto do compositor. Os controles de anexo/áudio usam caminhos próprios de envio: não se deve interpretar o modo interno como um canal de anexos privados. A interface não oferece anexos de nota interna.

### 7.9 Situações que impedem envio

- Canal inativo/removido: a área de escrita é substituída por aviso de somente leitura.
- Takeover pendente: solicita assumir temporariamente antes de responder.
- Contato sem mensagem recebida anterior: orienta usar template.
- Janela de envio livre vencida: o backend recusa o envio e orienta reabertura por template, mesmo que o campo de texto ainda esteja visível.
- Atendimento de outro responsável ou falta de permissão: a ação pode ser recusada pelo servidor.
- Falha de integração, upload, microfone ou localização: apresenta erro sem confirmação de envio.

A regra de 24 horas aqui descrita é a implementada pelo sistema a partir da última mensagem recebida. Não se trata de uma revisão das políticas comerciais atuais da Meta.

## 8. Operação do contato e do atendimento

### 8.1 Assumir e modo Recepção

**Modo tradicional:** o operador usa Assumir atendimento para tornar-se responsável antes de responder a uma conversa da fila, conforme permissão. A atribuição fica registrada e as caixas são atualizadas.

**Modo Recepção:** conversas sem dono em canais Standard podem ser respondidas na fila compartilhada por usuários autorizados, sem assumir. O sistema registra quem enviou cada mensagem. A regra não se estende a Coexistence. O botão Assumir continua disponível para perfis que possuam essa permissão.

O menu **Devolver à recepção** libera um lead atribuído para a fila compartilhada, sujeito à autorização do servidor. Essa ação não equivale a encerrar o atendimento nem a devolvê-lo ao bot.

### 8.2 Qualificação e notas

O cartão Qualificação contém um seletor, o campo Notas do atendimento e Salvar.

| Qualificação | Uso operacional |
|---|---|
| Novo | Entrada ainda sem interação humana registrada. |
| Em atendimento | Houve início da interação humana; pode ser promovido automaticamente a partir de Novo. |
| Qualificado | Lead considerado apto para avançar conforme o processo da empresa. |
| Não qualificado | Contato fora do perfil, spam, engano ou outro descarte. |
| Convertido | Resultado comercial/operacional alcançado. |
| Não convertido | Houve atendimento, mas o resultado esperado não foi alcançado. |

Salvar qualificação/notas altera o cadastro, não necessariamente encerra a conversa. O backend impede regressão de um lead já promovido para Novo por esse salvamento; as notas ainda podem ser atualizadas. Marcar Convertido não é, por si só, a ação que solicita avaliação: o pedido está associado ao encerramento.

### 8.3 Tags no contato

No cartão Tags, escolha uma sugestão ou digite uma nova etiqueta e pressione Enter ou **+**. Remova uma etiqueta pelo X. Clique em **Salvar tags** para persistir.

São permitidas até **12 tags por lead**. A interface evita repetição no mesmo contato. Etiquetas digitadas como novas podem ser registradas no catálogo pessoal do usuário. A definição global prevalece na apresentação quando há o mesmo identificador nos dois catálogos.

Tags também podem ser ajustadas no modal de encerramento. Alterar o rascunho de tags no painel sem salvar não é confirmação de alteração no cadastro.

### 8.4 Editar apelido

Em Mais opções → Editar apelido, informe o nome de uso interno e salve. Um valor vazio remove o apelido. O nome de perfil do WhatsApp continua sendo uma informação distinta. A operação depende da permissão de edição do nome declarado.

### 8.5 Transferir atendimento

O cartão Transferir atendimento exige escolher operador de destino e preencher um **resumo obrigatório**. Permite manter ou escolher setor e informar motivo. O botão fica indisponível sem destino ou resumo.

A transferência move **esta conversa**. O dono do lead permanece o mesmo. Após sucesso, a interface fecha a conversa transferida para o usuário que executou a ação e atualiza sua lista.

### 8.6 Reatribuir dono do lead

O cartão Reatribuir Lead (dono), para usuários autorizados, permite escolher o novo responsável e informar motivo opcional. A ação muda o dono comercial do contato e mantém os responsáveis dos atendimentos abertos.

### 8.7 Devolver ao bot

O botão no cartão de qualificação aparece para quem pode editar o dono do lead e quando há dono atribuído. Solicita confirmação antes de devolver o contato à fila do bot. É uma operação diferente de Devolver à recepção.

### 8.8 Atendimento temporário em Coexistence

Quando um cliente de outro operador escreve para o número de um segundo operador, o segundo pode receber um aviso de takeover pendente. A interface mostra quem é o dono do lead.

1. Clicar em **Assumir atendimento temporariamente**.
2. Revisar a saudação sugerida, que pode ser editada.
3. Escolher **Assumir e enviar**, **Assumir sem mensagem** ou Cancelar.
4. Atender sem transferir a propriedade do lead.
5. Usar **Encerrar e devolver** ao terminar a participação temporária.

O envio da saudação também está sujeito às regras normais de envio. O próprio dono do lead não precisa assumir temporariamente seu próprio contato.

### 8.9 Intervenção da supervisão

Usuários com autorização para enviar em qualquer atendimento podem atuar em conversas de outro responsável. A interface identifica a intervenção e informa a assinatura de supervisão no texto enviado. **Assumir como supervisor** torna esse usuário responsável pelo atendimento, preservando o dono do lead. O backend pode avisar o cliente quando houver janela de envio livre.

### 8.10 Encerrar e reabrir

No menu da conversa, **Fechar atendimento** muda para **Reabrir atendimento** quando a conversa está fechada.

Se o lead estiver Novo ou Em atendimento, fechar abre um modal com:

- Desfecho obrigatório: Convertido, Não convertido, Qualificado ou Não qualificado.
- Tags do lead, com possibilidade de ajuste.
- Notas já preenchidas com o conteúdo atual.
- Cancelar e Salvar e encerrar.

Sem desfecho, o sistema não conclui o encerramento. Se o lead já tem um desfecho, o menu pode encerrar diretamente. Fechar a conversa preserva a distinção entre estado operacional e resultado comercial.

Quando habilitado e aplicável, o encerramento aciona recibo/protocolo e pedido de avaliação. No modo Recepção, o encerramento devolve o lead ao agente de IA, preservando o histórico e o resultado. O fechamento por inatividade depende da configuração administrativa e de tarefas automáticas; não substitui a classificação feita pelo operador.

**Reabrir atendimento** altera sua situação no CRM. Isso não equivale a enviar um template nem restabelece sozinho a janela de envio livre.

### 8.11 Avaliação do atendimento

Quando a configuração de solicitação de avaliação estiver ativa e o envio for elegível, o recibo pode oferecer Ruim, Bom e Excelente. O painel do contato apresenta a avaliação registrada para usuários com acesso amplo de supervisão. O operador comum não recebe um controle para editar a avaliação do cliente.

### 8.12 Busca por protocolo

Usuários autorizados podem consultar um protocolo completo no cartão Buscar protocolo. A tela informa contato, telefone, situação, setor, dia, se o protocolo foi informado e quem encerrou, quando registrado. Também mostra quantidade de mensagens e uma lista resumida por data, direção e conteúdo.

O formato apresentado é `YYYYMMDD-{contact_id}-SETOR`. A prévia textual de cada mensagem é limitada a 200 caracteres; essa consulta não é uma exportação integral da conversa.

### 8.13 Conflitos de atendimento

O painel identifica leads com dois ou mais atendimentos ativos atribuídos a operadores diferentes. Mostra nome/telefone, dono do lead, operadores, canais e não lidas. **Atualizar** refaz a consulta; clicar num atendimento abre a conversa correspondente na visão Equipe.

O painel é de consulta e navegação. Não oferece um botão de resolução automática; a correção operacional usa transferência ou reatribuição conforme o caso.

### 8.14 Reatribuição em lote

O cartão permite selecionar operador de origem e uma das ações:

- Devolver ao bot os contatos daquele operador.
- Transferir para outro operador, escolhido como destino.

**Executar reatribuição** exige confirmação e retorna a quantidade processada. O destino não pode ser o próprio operador de origem na seleção. Essa ferramenta muda responsabilidade em lote; não é a campanha de envio de templates descrita na seção 14.

## 9. Templates e reabertura individual

### 9.1 Escolher e enviar template

Em Mais opções → Enviar template, a janela consulta os templates aprovados da conta WhatsApp associada ao canal da conversa.

| Controle | Uso |
|---|---|
| Categorias ALL, MARKETING, UTILITY, AUTHENTICATION | Filtram a lista de modelos retornados. |
| Lista de templates | Exibe nome, categoria e idioma. |
| Preview | Apresenta cabeçalho textual, corpo, rodapé e textos de botões existentes. |
| Variáveis | Campos para preencher os parâmetros textuais de cabeçalho/corpo. |
| Enviar template | Disponível após selecionar o modelo e preencher as variáveis exigidas. |
| Cancelar/Fechar | Encerra a janela sem enviar. |

Se não houver template aprovado, a tela oferece um link para o WhatsApp Manager. A criação e aprovação do modelo acontecem fora desse seletor do CRM.

O formulário atual monta parâmetros **textuais**. A presença de um template com cabeçalho de imagem/vídeo/documento ou parâmetros especiais de botão não significa que exista um campo correspondente para preenchê-los na tela.

### 9.2 Templates de reabertura

Modelos reconhecidos pelo sistema como reabertura utilizam nome do cliente e data da última conversa preenchidos automaticamente. A prévia informa esses valores; o servidor os recalcula no envio. O botão muda para **Enviar reabertura** e exige uma conversa aberta na interface como alvo.

O envio de template e a alteração da situação do atendimento são ações relacionadas, mas distintas. Um template enviado não deve ser interpretado como resposta do cliente nem como autorização automática para qualquer envio livre posterior.

## 10. Fluxos de trabalho

### 10.1 Atender um novo contato no modo tradicional

1. Entrar na caixa Novos e localizar uma conversa.
2. Abrir o histórico, conferir canal, contato e contexto.
3. Assumir atendimento, se necessário e permitido.
4. Responder por texto, mensagem rápida, áudio, anexo ou template conforme a janela.
5. Registrar notas e tags relevantes.
6. Ajustar o desfecho e fechar quando o trabalho estiver concluído.

### 10.2 Atender na Recepção

1. Abrir a caixa Recepção.
2. Selecionar uma conversa Standard elegível da fila compartilhada.
3. Responder sem assumir quando o perfil e o estado permitirem.
4. Registrar a qualificação, notas e tags.
5. Encerrar com desfecho. O fluxo pode devolver o lead ao agente de IA.
6. Se o lead foi assumido e deve voltar à equipe sem encerrar, usar Devolver à recepção.

### 10.3 Procurar um cliente que não aparece na caixa

1. Abrir a agenda em Meus ou Novos/Recepção.
2. Pesquisar pelo começo do nome/sobrenome ou por telefone na nova agenda.
3. Rever filtros e a indicação de resultados ocultos.
4. Abrir o contato encontrado.
5. Conferir o número/canal antes de enviar.

### 10.4 Iniciar conversa com um cadastro manual

1. Criar o contato pela agenda com nome, telefone e canal.
2. Abrir Enviar template.
3. Selecionar modelo aprovado e preencher variáveis.
4. Conferir a prévia e enviar.
5. Continuar o atendimento conforme o retorno do cliente e as regras de envio.

### 10.5 Passar o atendimento a outra pessoa

1. Escolher Transferir atendimento no painel Operação.
2. Selecionar destino, setor se necessário, motivo e resumo obrigatório.
3. Transferir e conferir a confirmação.
4. Se também for necessário mudar a propriedade comercial, um usuário autorizado usa Reatribuir Lead separadamente.

### 10.6 Revisar a operação como supervisor

1. Abrir Equipe e filtrar operador/canal.
2. Ativar Só espiar para preservar a pendência de leitura, quando desejado.
3. Consultar mensagens, qualificação, tags e avaliação disponível.
4. Usar nota interna para orientação textual ou intervenção assinada para falar com o cliente.
5. Consultar conflitos, protocolos e dashboard conforme a necessidade.

## 11. Preferências, mensagens rápidas e tags

### 11.1 Menu de configurações

| Opção | Acesso pela interface |
|---|---|
| Chat | Usuário autenticado; campos de prefixo dependem do cargo autorizado. |
| Mensagens rápidas | Usuário autenticado. |
| Tags de leads | Usuário autenticado; edição global tem permissão própria. |
| Reabertura em lote | Permissão de reabrir em lote. |
| Administração | Permissão de gerenciar configurações do sistema. |
| Perfis de acesso | Permissão de gerenciar perfis. |
| WhatsApp Coexistence | Permissão de gerenciar canais ou autorização individual Coexistence. |
| Conectar número (Cloud API) | Permissão de gerenciar canais. |
| Dashboard | Permissão de ver dashboard/uso. |

O menu pode ser fechado por novo clique ou clique fora. As janelas possuem Fechar e fechamento pelo fundo. Não há confirmação geral de descarte de edição em todas essas janelas; é necessário usar Salvar para persistir formulários, ressalvada a persistência imediata do upload de som.

### 11.2 Chat — prefixo pessoal

Quando o cargo estiver autorizado, a janela oferece **Usar prefixo**, nome de identificação e Salvar. O texto comum enviado pode receber `Nome: mensagem`. Sem nome preenchido, o prefixo não é acrescentado.

Quem não tem cargo autorizado vê informação de indisponibilidade. Notas internas e correções seguem caminhos próprios e não recebem o prefixo pelo mesmo mecanismo. A validação das mensagens rápidas pessoais pode impedir o salvamento conjunto das preferências pessoais se houver um item incompleto.

### 11.3 Mensagens rápidas pessoais

Cada cartão contém número de ordem, **título**, **atalho**, **mensagem** e Remover. O título identifica a opção na configuração e nas sugestões; não integra o texto enviado ao cliente.

| Ação/regra | Efeito |
|---|---|
| Adicionar | Abre um cartão vazio, enquanto o limite e a validade dos cartões permitirem. |
| Editar | Altera título, atalho ou texto do cartão. |
| Remover | Retira o cartão do rascunho. |
| Salvar | Valida e persiste a lista pessoal. |
| Campos obrigatórios | O editor exige título, atalho e mensagem preenchidos. |
| Atalhos repetidos | São recusados dentro da mesma lista; comparação ignora maiúsculas e trata `atalho` e `/atalho` como equivalentes. |
| Cartão incompleto/duplicado | Recebe aviso, impede adicionar mais e bloqueia salvamento. |
| Limite pessoal | Configurado pela empresa; o padrão inicial do código é 20. |

O editor não possui busca, importação, ordenação manual ou envio direto. Para usar uma mensagem, digite `/` no compositor, escolha a sugestão, revise e envie. Globais e pessoais participam da lista de sugestões; a seleção **preenche o campo**, sem envio imediato.

### 11.4 Catálogos de tags

“Tags de leads” contém **Minhas tags** e, mediante permissão, **Tags globais do tenant**. Cada grupo possui edição e salvamento próprios.

| Campo/ação | Comportamento |
|---|---|
| Nome da tag | Rótulo apresentado na interface. |
| Cor | Seletor de cor da etiqueta. |
| Adicionar tag | Acrescenta um item ao rascunho do catálogo. |
| Remover | Retira a definição do catálogo em edição. |
| Salvar | Valida nomes/cores/duplicidades e apresenta resultado no modal. |

Limites do servidor: **100 tags pessoais**, **200 globais**, rótulo com até **60 caracteres** e identificador normalizado com até **40 caracteres**. A normalização usa minúsculas, remove acentos e transforma espaços em hífens. Renomear uma definição existente preserva seu identificador.

O catálogo pessoal alimenta as sugestões do usuário; o global, as da equipe. Remover uma definição de catálogo não é uma ação de limpeza em massa das etiquetas já aplicadas aos contatos. Aplicação e remoção no lead são feitas no cartão Tags ou no encerramento.

## 12. Administração da empresa

### 12.1 Administração — Sistema

| Configuração | Efeito ou campo disponível |
|---|---|
| Prefixo global | Interruptor salvo nas configurações; ver ressalva de execução na seção 18. |
| Cargos com prefixo | Seleção de admin, supervisor e operador. |
| Máximo de mensagens rápidas pessoais | Campo numérico com indicação de 1 a 100; usado pelo editor pessoal. |
| Mensagens rápidas globais | Mesmo editor de título, atalho e mensagem, compartilhado pela empresa. Não recebe o limite pessoal na interface. |
| Bot de atendimento | Liga/desliga o fluxo automático; desligado, a orientação da tela é direcionar entradas para Novos. |
| Modo da fila | Exclusivo: assumir para falar. Recepção: atender conversas Standard elegíveis sem dono. |
| Aviso de espera | Habilita uma mensagem automática para quem permanece na fila sem operador. |
| Tempo do aviso | Entre 5 e 240 minutos. |
| Texto do aviso | Até 1.000 caracteres, com contador. Obrigatório para habilitar. |
| Nova agenda para todos | Ativa a agenda paginada para a empresa. |
| Nova agenda por usuário | Botões para liberação individual de operadores, mesmo com a ativação geral desligada. |
| Limpar canário | Remove a lista de liberações individuais da nova agenda. |
| Filtro por tag na nova agenda | Ativação independente; o uso também exige permissão no perfil. |
| Salvar configurações do sistema | Persiste as alterações e valida as mensagens rápidas globais. |

O aviso de espera é verificado pela rotina automática aproximadamente a cada cinco minutos, respeita o expediente configurado e a janela de envio, e foi implementado para um envio por ciclo de espera. O usuário não dispõe nesta aba de editor de dias/horários/feriados nem de botão para disparar a rotina manualmente.

O texto explicativo do botão de bot ainda menciona coleta de nome, equipamento e setor. Empresas com agente de IA específico podem ter outra conversa automática: a aba não é um editor desse roteiro.

### 12.2 Administração — Departamentos

A lista apresenta nome, descrição e associação ao setor do bot, quando existente.

| Operação | Campos e regras |
|---|---|
| Criar | Nome obrigatório, descrição opcional e setor do bot. |
| Setor do bot | Nenhum, Comercial, Financeiro, Administrativo ou SAC. |
| Editar | Abre os campos na própria linha; Salvar aplica e Cancelar abandona a edição. |
| Remover | Pede confirmação e desativa o departamento no servidor. |

O nome não pode ficar vazio. Criar/editar e desativar têm permissões específicas, além do acesso à janela Administração. Não há controle de reativação ou ordenação manual nesta tela.

### 12.3 Administração — Canais WhatsApp

Apresenta nome, telefone ou identificador do número, tipo, indicação Bot, operador proprietário quando encontrado e situação do canal. O caminho usual de listagem retorna os canais ativos permitidos.

**Desativar** aparece para canais que não são Standard, pede confirmação e depende da permissão de desativar canais. A conexão de novos números usa o fluxo separado da seção 13.

Esta aba não oferece edição de nome, token, proprietário, prioridade, ativação do bot por canal, reativação ou sincronização manual de histórico.

### 12.4 Administração — Notificações

| Grupo | Controles |
|---|---|
| Mensagem nova | Habilitar som, enviar/trocar arquivo, testar e usar som padrão. |
| Alarme de atraso | Habilitar, configurar minutos de espera, departamentos que recebem o alarme, arquivo próprio, testar e usar padrão. |
| Avaliação pós-atendimento | Ativar solicitação de avaliação no encerramento manual. |
| Fechamento por inatividade | Habilitar/desabilitar o fechamento automático. |

O seletor de som aceita MP3, WAV, OGG e WebM; o servidor valida tipo e tamanho de até **500 KB**. **Enviar um arquivo de som já persiste a nova configuração no servidor.** Testar apenas reproduz localmente. Alterar interruptores, departamentos, minutos e Usar padrão exige Salvar configurações do sistema.

O campo de alarme indica faixa de 1 a 60 minutos, mas o manipulador da interface não aplica um teto rígido de 60; esse rótulo não deve ser interpretado como validação completa. O funcionamento do alarme está descrito na seção 5.5.

A descrição do fechamento automático informa verificação em rotina de 30 minutos para atendimentos sem mensagem há mais de 24 horas. Há tratamento de segurança para contatos entregues à recepção que seguem sem resposta humana por sete dias. Desligar o fechamento por inatividade não deve ser interpretado como desativar toda e qualquer rotina de liberação ao bot.

### 12.5 Perfis de acesso

A janela lista os perfis e distingue sistema, padrão inicial e personalizado. Selecionar um perfil abre nome, descrição e permissões agrupadas em Visibilidade, Atendimento, Lead, Canais, Auditoria e Gestão.

| Ação | Comportamento |
|---|---|
| Novo perfil | Exige nome e permite base Operador, Supervisor ou Administrador. |
| Editar | Altera nome, descrição e permissões individuais quando o perfil permite. |
| Salvar | Exige nome preenchido e envia a configuração do perfil. |
| Excluir | Disponível para perfil personalizado; pede confirmação. Perfis padrão/de sistema e perfis em uso por usuário ativo não podem ser excluídos. |

O perfil de sistema mantém nome e permissões bloqueados; sua descrição pode ser editada. A lista de permissões é fornecida pelo sistema: não há criação de novas chaves de permissão por essa tela.

Trocar o perfil selecionado reinicia o rascunho sem confirmação de descarte. A mensagem de sucesso informa propagação aos conectados em até um minuto; mudanças de cargo/autenticação ainda podem exigir nova sessão.

### 12.6 Usuários e Roles / Operadores

No painel Operação, o cartão depende da permissão de gerenciar usuários. Exibe nome, e-mail, cargo e indicação de autorização Coexistence.

| Controle | Ação |
|---|---|
| Editar | Com permissão de gerenciar perfis, permite cargo, perfil de acesso ou padrão do cargo, e setor ou Sem setor. |
| Salvar / X | Aplica ou cancela a edição do usuário. |
| Coex | Com permissão, informa número corporativo e autoriza o operador a executar a conexão Coexistence. |
| Revogar Coex | Remove a autorização individual. Não há confirmação adicional nesse controle. |
| Reset | Zera o contador operacional de assumir contatos do usuário; não redefine senha. |

Ao trocar cargo, a seleção explícita de perfil é limpa. O telefone de autorização Coexistence é reduzido a dígitos e a interface exige pelo menos dez dígitos antes de chamar o servidor.

Este cartão **não** oferece criar usuário, editar nome/e-mail, definir senha ou excluir/desativar conta. A existência de permissões e endpoints com esses nomes não implica que estejam acessíveis por esta interface.

## 13. Conexão e gestão de WhatsApp

### 13.1 Dois caminhos de conexão

| Caminho | Acesso e finalidade |
|---|---|
| WhatsApp Coexistence | Gerenciador de canais ou operador individualmente autorizado; fluxo de conexão associado ao WhatsApp Business App. |
| Conectar número (Cloud API) | Gerenciador de canais; fluxo de conexão Standard para gestão pelo CRM. |

As janelas apresentam requisitos e orientações e abrem o cadastro incorporado da Meta em uma janela externa. Coexistence menciona aplicativo, portfólio e QR; Cloud API menciona migração, pagamento e PIN conforme o fluxo. São instruções existentes no produto, não uma verificação independente das exigências atuais da Meta.

### 13.2 Etapas e retorno

1. Carregar a configuração autenticada e o componente da Meta.
2. Iniciar a conexão e aguardar o preenchimento da janela externa.
3. Receber os dados de autorização e configurar a integração no servidor.
4. Apresentar sucesso ou erro.

O sucesso pode apresentar identificador da conta WhatsApp, identificador do número, número, nome verificado, status, plataforma, qualidade e situação da inscrição do webhook. Cloud API informa a criação do canal.

Em falha, pode haver diagnóstico copiável com evento, etapa, código e identificadores de sessão, além de **Tentar novamente**. Esses dados servem à investigação da conexão.

O fluxo de sucesso Coexistence ainda contém instruções técnicas de configuração do servidor e pode apresentar um campo de credencial retornada. A tela não deve ser tratada como um fluxo inteiramente concluído sem conferir seu resultado; nenhum valor sensível é reproduzido neste manual.

### 13.3 Aviso de pagamento da conta WhatsApp

Para usuários com acesso ao dashboard, a aplicação pode consultar a situação de pagamento do primeiro canal Standard ativo. Quando há confirmação de ausência de método de pagamento, mostra um aviso, um link **Configurar agora** para a área de cobrança da Meta e um botão de dispensar.

Falhas na própria consulta de cobrança estão suprimidas pelo código atual. Portanto, ausência do aviso não comprova que a verificação foi concluída ou que todos os canais estão regularizados. O CRM não possui formulário próprio de cartão ou gestão de faturas nessa área.

## 14. Reabertura em lote

### 14.1 Público implementado

A janela exige permissão de reabrir em lote. Ao abrir, calcula automaticamente uma prévia dos leads com qualificação **Em atendimento** e condições elegíveis para retomada.

**O código atual não possui seletor de público Recepção/Bot.** Ele não usa dono do lead, fase do bot ou estado da conversa como seleção principal desse público. A ampliação descrita no plano de reabertura do repositório ainda não está implementada nesta interface.

O cálculo considera a última mensagem recebida e exclui contatos conforme janela de 24 horas, ausência de data válida, intervalo mínimo entre tentativas, opt-out, consentimento revogado, arquivamento, backup, canal inválido/inativo/Coexistence ou falta de template aprovado. Tentativa anterior sem resposta pode colocar o contato no grupo de encerramento sem novo envio; contatos já resolvidos por lote anterior ficam fora.

O intervalo padrão entre tentativas é 24 horas, configurável no servidor. O cálculo atual exclui consentimento revogado, mas não exige aceite LGPD registrado nem verifica a versão vigente da política.

### 14.2 Prévia

| Informação/controle | Uso |
|---|---|
| Receberão a retomada | Total elegível antes do limite informado para o disparo. |
| Serão encerrados sem novo envio | Contatos classificados como tentativa anterior sem resposta. |
| Setor de destino das respostas | Distribuição dos elegíveis por setor, incluindo Sem setor. |
| Fora do lote | Motivos de exclusão com respectivas quantidades. |
| Ver amostra / Ocultar amostra | Até 20 contatos, com identificador e nome. Não permite marcar/desmarcar destinatários. |
| Atualizar prévia | Refaz o cálculo e fecha uma confirmação pendente. |

A distribuição por setor considera todos os elegíveis, não apenas os primeiros dentro do limite. O corte do lote segue a ordem da varredura; não há ordenação manual, filtro por setor ou escolha individual nessa tela.

### 14.3 Disparo

A seção de disparo aparece quando existe pelo menos um envio ou encerramento elegível.

1. Informar **Limite de envios**, de 1 a 250. O padrão do servidor é 100, sujeito à configuração.
2. Clicar em **Disparar lote** para abrir a confirmação.
3. Conferir máximo de envios, encerramentos previstos e aviso de cobrança apresentado pela interface.
4. Confirmar disparo ou Cancelar.

Cancelar nessa etapa apenas fecha a confirmação antes de iniciar. O template é resolvido por canal; não há seletor de modelo nessa janela. O backend recalcula os elegíveis ao iniciar, então o resultado pode diferir da prévia. Outro lote ativo impede um novo disparo.

### 14.4 Acompanhamento

A tela mostra Executando, Lote concluído, Lote abortado ou Lote interrompido sem progresso, com enviados/planejados, encerrados/planejados, falhas e motivo quando disponível. O progresso pode avançar em blocos: os contadores são persistidos aproximadamente a cada dez envios e a cada 25 encerramentos. **Nova prévia** permite iniciar novo planejamento após o resultado.

Fechar a janela não cancela o processamento. Não há botão para cancelar um lote iniciado, histórico de lotes ou retomada explícita do acompanhamento após reabrir a tela. O identificador acompanhado fica no estado da janela atual.

O sistema pode abortar por retenção de qualidade da integração ou sucessão de falhas. O envio de template do lote não reabre imediatamente a conversa nem a reposiciona por recência; a retomada depende da resposta do cliente.

### 14.5 Limites relevantes

- Encerramentos sem novo envio têm teto separado de **250 contatos por lote**; o total previsto na interface pode ser maior que o executado.
- O acompanhamento considera interrupção após cinco minutos sem progresso; a trava de concorrência possui prazo distinto, de duas horas. Pode haver intervalo em que o lote pareça interrompido e um novo disparo ainda seja bloqueado.
- Não há teto diário configurável por tela, segmentação Recepção/Bot, limite por contato em 90 dias nem cancelamento em execução na implementação examinada.
- A prévia não é seleção de destinatários nem garantia de entrega. Retorno de sucesso do envio não equivale à resposta do cliente.

## 15. Dashboard e exportação

### 15.1 Período e indicadores

O **Dashboard de Auditoria** exige permissão de ver dashboard/uso. Oferece data inicial, data final, Atualizar e Exportar CSV. O intervalo inicial vai da data atual menos 30 dias até a data atual. Abrir a janela ou alterar as datas recarrega a consulta.

| Indicador/seção | Conteúdo apresentado |
|---|---|
| Leads recebidos | Métrica diária registrada para o período. |
| Leads assumidos | Métrica de atribuição registrada. |
| Mensagens recebidas | Quantidade agregada de entradas. |
| Mensagens enviadas | Quantidade agregada de saídas. |
| Total de mensagens | Soma das recebidas e enviadas. |
| Pico de mensagens por meia hora | Gráfico de barras das faixas com ocorrências; quantidade ao apontar para a barra. |
| Por operador | Operador, Recebidas, Enviadas e Assumidos, quando a API retorna registros. |
| Avaliações de atendimento | Contato, Nota, Operador e Data, quando existem avaliações no período. |

As avaliações usam a data de recebimento da avaliação. O operador exibido é derivado do responsável registrado na conversão, não necessariamente de quem encerrou ou enviou a última mensagem. Registros antigos sem rótulo podem aparecer na escala numérica legada, enquanto os novos usam Ruim/Bom/Excelente.

Não há filtros por operador, setor, canal, qualificação ou tipo de mensagem, nem detalhamento ao clicar nos cartões. Seções de gráfico/tabelas sem registros são ocultadas. Não há validação específica de data inicial posterior à final na tela.

### 15.2 Exportar CSV

O botão exporta **cadastros de contatos**, incluindo arquivados, filtrados pela data do primeiro registro. Não exporta os mesmos agregados do dashboard, o gráfico, a tabela de avaliações ou o histórico integral de mensagens.

O arquivo recebe nome no formato `export_INICIO_FIM.csv`. Colunas:

| Campo | Conteúdo |
|---|---|
| id / wa_id | Identificadores do contato e do WhatsApp. |
| display_name / phone_formatted | Nome e telefone. |
| qualification / tags | Qualificação e etiquetas, separadas por ponto e vírgula no campo tags. |
| assigned_to / assigned_name | Identificador e nome do responsável. |
| department_name | Setor. |
| channel_id / source_channel_type | Canal e tipo de origem. |
| rating | Avaliação registrada. |
| first_seen_at / last_message_at | Primeiro registro e última mensagem. |
| notes | Notas do contato. |

A exportação exige permissão específica de exportar contatos, além do acesso ao dashboard. Sem registros, o código retorna arquivo vazio, sem cabeçalho.

### 15.3 Limitações verificadas no código

**Os totais precisam de validação antes de uso gerencial.** A identificação de documentos de métricas por operador não coincide com o formato usado na gravação. Para os identificadores numéricos usuais, isso pode tratar métricas de operador como globais, duplicar somas e deixar a tabela Por operador vazia.

As faixas de meia hora são gravadas em UTC e a interface não identifica nem converte esse fuso. Também há uma limitação no download: o botão não verifica a permissão específica antes de aparecer e o código não valida o status HTTP antes de salvar o arquivo. Um erro de autorização pode ser baixado com extensão CSV.

Esses pontos foram identificados por leitura dos caminhos de gravação e consulta. Não foram corrigidos nesta entrega documental nem medidos em dados reais de produção.

## 16. Chat interno

### 16.1 Acesso e conversas

Quando a integração Google Chat está habilitada, a barra superior oferece **Chat Interno**. Abre um painel lateral com conversas de espaços e acesso às mensagens.

| Controle/informação | Comportamento |
|---|---|
| Lista | Nome do espaço, última mensagem ou Sem mensagens, data/hora e não lidas do usuário. |
| Selecionar conversa | Abre o histórico e solicita marcação como lida. |
| Voltar | Retorna à lista e limpa seleção, mensagens e rascunho. |
| Fechar | X, botão superior ou clique fora recolhem o painel. A seleção/rascunho podem permanecer ao reabrir. |
| Lista vazia | Orienta adicionar o bot do CRM a um espaço do Google Chat. |

O listener da lista acompanha até 50 conversas, ordenadas por última mensagem. Contadores de cada conversa usam `99+` quando necessário.

### 16.2 Mensagens

O painel apresenta texto, imagens e áudio com controles, além de remetente e data/hora. O compositor envia somente **texto**. Enter envia e Shift+Enter quebra linha. O botão é bloqueado para conteúdo vazio ou envio em andamento; no sucesso, o campo é limpo e recupera o foco.

Não há criação de espaço, busca, paginação de histórico, upload, gravação de áudio, resposta citada, edição ou exclusão de mensagem nessa interface.

### 16.3 Limites do painel

- O contador global do botão superior está fixado em zero no código atual; os contadores por conversa existem.
- O listener consulta as 100 mensagens mais recentes da coleção e depois filtra a conversa selecionada. Não há garantia de 100 mensagens por conversa ou de histórico completo.
- Erros de carregamento, envio e leitura podem ser silenciosos. Se o envio falha, o rascunho permanece.
- A presença de exibição de mídia recebida não significa que o compositor ofereça envio desse tipo de mídia.

## 17. Portal de administração da plataforma

Este é um portal separado, identificado como **Castro Superadmin**. Seu público é a administração da plataforma, não a equipe de atendimento de cada empresa.

### 17.1 Login e autenticador

| Tela/ação | Funcionalidade |
|---|---|
| Entrar com Google | Autenticação pela conta Google autorizada. |
| Entrar com e-mail | Campos de e-mail/senha e botão de entrada. |
| Verificar MFA | Código de seis caracteres, Confirmar e Cancelar. |
| Cadastrar autenticador | Exibe chave para inclusão manual em aplicativo TOTP, conta e emissor Castro Superadmin. |
| Confirmar e ativar | Valida o código do aplicativo, cadastra o segundo fator, limpa a chave da tela e pede novo login. |
| Sair | Encerra a sessão. |

A conta precisa ser reconhecida como superadmin ativo; o serviço aplica a exigência de segundo fator no ambiente implantado. Conta sem autorização recebe aviso e sai. A tela não oferece QR code, códigos de recuperação ou Esqueci minha senha.

### 17.2 Criar empresa

| Campo | Regras |
|---|---|
| Slug/ID | Obrigatório, 3 a 64 caracteres, começa com letra minúscula, aceita letras minúsculas, números e hífen. Deve ser único. |
| Nome | Obrigatório, não pode ficar vazio após remover espaços externos. |
| CNPJ | Opcional e textual; não há validação de dígitos verificadores no fluxo auditado. |
| Plano | Professional por padrão ou AI Custom/IA dedicada. |
| E-mail do administrador | Obrigatório; usado no provisionamento inicial. |
| Domínios permitidos | Lista separada por vírgulas. Converte para minúsculas, remove espaços externos e `@` inicial, elimina duplicidades e desconsidera provedores públicos. |

Se os domínios ficarem vazios na criação, o sistema usa o domínio do administrador quando for elegível. Um domínio já vinculado a outra empresa ativa é recusado. O ID não pode ser alterado posteriormente.

**Criar tenant** inicia o cadastro e o provisionamento de estruturas iniciais, perfis, setores e administrador. O retorno distingue empresa criada de administrador provisionado. É possível criar a empresa e receber aviso de falha no provisionamento do administrador; o sucesso não deve ser interpretado automaticamente como acesso pronto para essa conta.

### 17.3 Listar e editar empresas

A lista inclui empresas ativas e inativas, com ID, nome, plano, domínios e Editar. Não possui busca, filtros ou paginação.

Editar preenche um formulário e permite alterar nome, CNPJ, plano, domínios e **Tenant ativo**. Salvar aplica; Cancelar fecha o editor. O administrador inicial e o ID não são editáveis nessa tela. Planos legados, como Enterprise AI, podem aparecer como valor atual preservado, embora não sejam opções normais de criação.

Domínios vazios na edição removem o roteamento por domínio. Essa regra difere do preenchimento automático usado na criação.

### 17.4 Ativação e desativação

Desmarcar Tenant ativo silencia o bot e remove o roteamento de login por domínio. **Não bloqueia, por si só, usuários que já possuem vínculo de autenticação com a empresa.** A própria tela orienta que o corte de acesso exige tratar os usuários.

Não há exclusão definitiva de empresa, administração das contas dos clientes, impersonação, alternador para entrar no CRM de outro tenant ou consulta visual da auditoria global. Cadastro/revogação de superadmins, configuração de agente IA e cobrança não possuem controles neste portal.

### 17.5 Retornos e limitações

Erros de dados, ID em uso, domínio em conflito, empresa inexistente, falta de autorização e falha de auditoria obrigatória podem impedir a operação. O editor trata falhas de rede e reabilita Salvar; a criação não possui a mesma proteção completa e pode manter o botão desabilitado após uma falha de rede.

## 18. Comportamentos condicionais e limitações

### 18.1 Quadro de disponibilidade

| Recurso | Condição/limitação |
|---|---|
| Carteira completa, Equipe e Backup | Exigem cargo de supervisão/admin e permissão de acesso amplo. |
| Bot | Depende de ativação da empresa e integração configurada. |
| Temperatura do lead | Só aparece quando há informação gravada pela integração de IA. |
| Recepção compartilhada | Configuração da empresa; resposta à fila não cobre Coexistence. |
| Nova agenda | Liberação geral ou individual. |
| Filtro de tag na agenda | Nova agenda ativa, interruptor próprio e permissão do perfil. |
| Templates | Modelos aprovados disponíveis no canal e suporte aos parâmetros pelo formulário. |
| Transcrição | Botão existente, mas execução depende do serviço habilitado/disponível. |
| Sons | Configurações, setor quando aplicável e política de reprodução do navegador. |
| Áudio/localização | Recursos e permissões do navegador. |
| Chat interno | Integração Google Chat habilitada e espaços disponíveis. |
| Avaliação | Configuração ativa, encerramento elegível e resposta do cliente. |
| Reabertura em lote | Permissão, contatos elegíveis, canal Standard e templates compatíveis. |

### 18.2 Diferenças que exigem atenção

| Ação ou informação | Interpretação correta |
|---|---|
| Transferir atendimento | Muda responsável da conversa específica. |
| Reatribuir lead | Muda dono comercial; preserva os donos dos atendimentos. |
| Devolver à recepção | Libera para fila compartilhada sem representar encerramento. |
| Devolver ao bot | Retorna ao fluxo automático. |
| Fechar atendimento | Altera estado operacional; o resultado comercial tem campo próprio. |
| Reabrir atendimento | Reabre no CRM; não restaura automaticamente a janela WhatsApp. |
| Corrigir mensagem | Envia nova resposta citando a original. |
| Busca da caixa | Filtra conversas carregadas. |
| Busca da agenda nova | Pesquisa o cadastro permitido além das conversas recentes. |
| Busca na conversa | Filtra texto das mensagens já carregadas. |
| Exportar CSV | Exporta contatos por primeiro registro, não métricas/histórico completo. |
| Reset do operador | Zera contador de assumir, não senha. |
| Remover departamento | Desativa o setor. |
| Desativar tenant | Não revoga automaticamente vínculos de usuários existentes. |

### 18.3 Controles com comportamento parcial no código atual

1. **Prefixo global:** o interruptor é salvo, mas o envio textual consulta prefixo pessoal, nome e cargos permitidos sem consultar o interruptor global. Não é um desligamento global efetivo garantido pelo caminho atual.
2. **Permissões e botões:** algumas ações aparecem antes da validação específica no servidor, como criação manual, qualificação, exportação e controles administrativos. Um botão visível pode resultar em acesso negado.
3. **Dashboard:** classificação de agregados por operador, fuso do gráfico e validação do download CSV têm as ressalvas da seção 15.3.
4. **Google Chat:** contador geral, limite do histórico e erros silenciosos têm as ressalvas da seção 16.3.
5. **Reabertura em lote:** não há cancelamento em execução nem histórico retomável pela janela, e há limites diferentes para envio, encerramento e concorrência.
6. **Sons:** envio de arquivo persiste imediatamente; outras alterações dependem de Salvar.
7. **Cadastro de empresa:** pode terminar sem administrador provisionado, e uma falha de rede pode deixar o botão de criação desabilitado.
8. **Conexão Coexistence:** a tela de sucesso ainda contém orientações técnicas e conteúdo de credencial que exigem revisão do resultado da configuração.

Esses registros descrevem o estado observado. Não significam que todas as falhas tenham ocorrido no ambiente real nem que foram corrigidas na elaboração do manual.

### 18.4 Recursos sem controle encontrado nas interfaces examinadas

- Arquivar/restaurar contato por botão no CRM atual, apesar de referências em documentação antiga e permissões no catálogo.
- Criar/desativar usuários, redefinir senhas de terceiros ou editar e-mail/nome pelo cartão Operadores.
- Gerenciar prompt, modelo, credenciais de IA, horários semanais e feriados pelo frontend React.
- Campanhas com públicos Recepção/Bot, cancelamento em execução e teto diário pela janela atual de reabertura.
- Exportar conversa integral, PDF de atendimento, anexos em lote ou os gráficos do dashboard.
- Criar/aprovar templates da Meta dentro do seletor de envio do CRM.
- Agendar uma mensagem individual, apagar mensagem enviada para todos, editar a original no WhatsApp ou encaminhar mensagem por um controle dedicado.
- Enviar anexos privados como nota interna.
- Criar espaços Google Chat, pesquisar o histórico completo ou enviar mídia pelo chat interno.
- Excluir tenant, administrar superadmins, acessar como outro usuário ou consultar auditoria global pelo portal superadmin.

APIs, scripts e planos podem oferecer ou prever parte dessas operações. Isso não as transforma em funcionalidades da interface entregue ao usuário.

## 19. Referências e manutenção

### 19.1 Fontes principais

Os arquivos abaixo foram usados para verificar as telas e seus efeitos. Os nomes de componentes ajudam a localizar cada área mesmo quando a numeração de linhas mudar.

| Área | Fonte e referência funcional |
|---|---|
| Login, topo, navegação | [App.tsx](../../frontend/src/App.tsx): LoginScreen, TopBar, NavBar. |
| Agenda e lista | [App.tsx](../../frontend/src/App.tsx): NewContactModal, ContactList; [CrmContext.tsx](../../frontend/src/context/CrmContext.tsx): filtros, paginação e consultas da agenda. |
| Conversa e operação | [App.tsx](../../frontend/src/App.tsx): ChatPanel, MessageMedia, CloseAttendanceModal, DetailPanel, ContactTagsCard. |
| Templates | [App.tsx](../../frontend/src/App.tsx): TemplatePickerModal; [main.py](../../main.py): envio e reabertura. |
| Configurações e canais | [App.tsx](../../frontend/src/App.tsx): SettingsModals, TagsSettingsModal, AdminSettingsModal, NotificationsTab, WhatsAppSignupModal, BillingHealthBanner. |
| Mensagens rápidas | [QuickMessagesEditor.tsx](../../frontend/src/components/settings/QuickMessagesEditor.tsx) e [quickMessages.ts](../../frontend/src/utils/quickMessages.ts). |
| Formatação | [WaText.tsx](../../frontend/src/components/chat/WaText.tsx) e [waFormat.ts](../../frontend/src/utils/waFormat.ts). |
| Perfis e acesso | [rbac.py](../../rbac.py), [auth.py](../../auth.py), [main.py](../../main.py) e PerfisAcessoModal em [App.tsx](../../frontend/src/App.tsx). |
| Reabertura em lote | ReopenBatchModal em [App.tsx](../../frontend/src/App.tsx); cálculo e execução em [main.py](../../main.py) e [database_firestore.py](../../database_firestore.py). |
| Dashboard e exportação | DashboardModal em [App.tsx](../../frontend/src/App.tsx); `dashboard_summary`, `export_data`, `increment_audit_metrics` e `get_audit_metrics` em [main.py](../../main.py) / [database_firestore.py](../../database_firestore.py). |
| Chat interno | [InternalChatPanel.tsx](../../frontend/src/components/gchat/InternalChatPanel.tsx). |
| Portal superadmin | [index.html](../../superadmin_web/index.html), [superadmin_main.py](../../superadmin_main.py), [tenant_service.py](../../tenant_service.py) e [tenant_bootstrap.py](../../tenant_bootstrap.py). |
| Adaptação visual | [styles.css](../../frontend/src/styles.css). |

### 19.2 Materiais complementares

- [Guia de qualificação e fechamento](GUIA_OPERADORES_QUALIFICACAO_FECHAMENTO.md).
- [Guia de mensagens rápidas](GUIA_OPERADORES_MENSAGENS_RAPIDAS.md).
- [Guia da nova agenda e busca](GUIA_OPERADORES_PICKER_BUSCA.md).
- [Plano de reabertura Recepção/Bot](../PLANO_REABERTURA_LOTE_BOT_RECEPCAO.md), usado para distinguir proposta de implementação disponível.

### 19.3 Critérios de atualização

Revisar este documento quando houver mudança de tela, permissão, regra de atribuição, parâmetro de configuração, limite de envio/exportação ou ativação de uma funcionalidade atualmente planejada. A confirmação de disponibilidade em uma empresa específica deve considerar sua versão implantada, permissões, configurações e integrações.

**Histórico:** versão 1.0 — inventário funcional do código local em 02/10/2026; inclui funcionalidades condicionais e limitações verificadas por leitura, sem alterações funcionais no aplicativo.

