# ADR 0016: Encaminhamento e mensagem fixada por conversa

Data: 2026-11-13. Status: mergeado no develop com a emenda da revisao (abaixo), sem deploy.

## Contexto

O menu da bolha precisa permitir selecionar varias mensagens para encaminhar e
destacar uma mensagem por prazo determinado. O mesmo contato pode ter conversas
em canais diferentes; operacao e historico precisam respeitar esse recorte.

## Decisao

- Encaminhar usa `POST /api/wa/send` com `forward_message_id`, um envio por mensagem,
  em ordem cronologica. O servidor le o conteudo original; texto fornecido pelo
  cliente nao substitui a origem. Texto e templates sao enviados como texto;
  imagem, audio, video/GIF, documento, figurinha e localizacao preservam o tipo.
- Origem e destino passam por `_require_contact_access` antes da resolucao que
  pode criar uma thread. A origem tambem verifica posse da thread quando o lead
  pertence a outro operador. Notas internas, mensagens de sistema e `admin_only`
  nao podem ser encaminhadas/fixadas. Backup continua restrito a privilegiados.
- Destino usa os gates atuais de envio: RBAC, posse/Recepcao, coex e janela de 24h.
  O middleware de Ver como bloqueia encaminhar, fixar e desfixar.
- Midia e lida do Storage e recebe um novo upload com as credenciais do numero
  de destino, pelo mesmo emissor de `/api/wa/send-media`. O `media_id` original
  nunca e reutilizado. A nova mensagem referencia o arquivo ja persistido.
- A mensagem enviada recebe `is_forwarded=true`, preservado nos ecos e na
  whitelist de `normalization.ts`. O selo "Encaminhada" existe apenas no CRM.
- Cada `wa_conversations` possui no maximo um `pinned_message` com `message_id`,
  `preview`, `expires_at` UTC e `pinned_by`. Nova fixacao substitui a anterior.
  Prazos: 24h, 7 dias ou 30 dias. Fixar nao envia mensagem nem reabre atendimento,
  altera recencia, zera nao-lido ou silencia o bot. A expiracao oculta a faixa;
  nao exige cron/backfill de documentos existentes.
- `POST /api/wa/messages/{id}/pin` grava a fixacao;
  `DELETE /api/wa/conversation/{id}/pin` remove. Ambos exigem acesso e permissao
  de escrita do operador. Fixacao e compartilhada com quem acessa a thread.
- `GET /api/wa/messages/{id}/context` busca uma janela limitada em torno da
  mensagem: ate 11 anteriores/incluindo o marco e 11 posteriores/incluindo o
  marco, com deduplicacao e autorizacao. O frontend destaca a bolha e oferece
  "Voltar as recentes"; nenhum full-scan de historico e feito.
- Se houver falha no encaminhamento, os envios confirmados saem da selecao e os
  restantes podem ser tentados novamente. Trocar de thread interrompe os envios
  seguintes; uma requisicao ja em curso pode terminar. Falha de transporte sem
  resposta pode deixar o resultado do ultimo envio incerto, como no envio atual.

## Emenda da revisao (2026-11-13, antes do merge)

Revisao adversarial do PR #8 (5 lentes + verificador). Ajustes aplicados no merge:

- **Origem estrita.** Encaminhar, fixar, desfixar e ler o contexto exigem, para operador
  comum, a thread que ele atende ou a pool de verdade (`_require_transfer_source_access`),
  mesmo sendo o Dono do Lead. O atalho do dono liberava a thread coex de outra vendedora
  com o mesmo cliente. O frontend desabilita as acoes fora desse escopo (`canActOnThread`).
- **Destino nunca pelo coex de outra pessoa** (`_require_forward_destination_channel`),
  inclusive para a gestao. O picker so lista threads por numero da empresa ou pelo coex
  do proprio usuario. Contato sem thread na tela sai pelo canal de criacao so se ele for
  permitido; senao, pelo numero da empresa. A linha mostra "Sai por ...".
- **Picker sem a camada crua do listener.** A busca local usa as mesmas listas das caixas
  (Meus, Novos e, para a gestao, Equipe/Bot/NQ). Exige 2 caracteres para a pool e nunca
  rotula pelo `wa_id` uma thread cujo contato o operador nao ve. A thread orfa de lead
  alheio exibia o telefone.
- **Nao encaminhaveis:** template (o `content` e o rotulo `[template: nome] params`, com
  dados de quem recebeu), toque em botao interativo (`content` = id do botao; marca nova
  `interactive_reply` gravada pelo webhook) e clique de avaliacao (`is_rating_message`).
  Fixar template continua permitido.
- **Efeitos so depois do que pode falhar.** Ordem do encaminhamento: janela de 24h, gate de
  envio em `dry_run` (mesma decisao, sem efeitos), leitura da midia de origem e so entao o
  gate de verdade, que na Recepcao silencia a Val e limpa takeover. Assim a midia (ate
  16 MB) nao e baixada para um envio que seria recusado. A midia e lida por
  `get_media_stream`: tamanho antes de baixar, 404 para objeto inexistente e 503 para falha
  do storage. Encaminhamento exige `conversation_id` (pelo `contact_id` o resolve faria
  upsert da thread no canal de criacao antes de qualquer recusa).
- Gate do destino decide pelo tipo do CANAL resolvido. Canal fora do cache: faz refresh antes
  (como o `get_send_credentials`); canal que nao resolve: 409. Toques de botao gravados antes
  da marca (`lgpd_aceitar`/`lgpd_recusar`) tambem sao recusados.
- Midia: mime sem parametro (`audio/ogg; codecs=opus` -> `audio/ogg`) e extensao coerente no
  novo upload. Documento leva `filename` no envio (vale tambem para `/api/wa/send-media`).
  Audit de midia encaminhada com `source_id`.
- Localizacao: sem assinatura de supervisao (viraria o nome do local) e sem `name` vazio.
- **Contexto da fixada:** duas consultas independentes, sem `limit_to_last`. Na
  google-cloud-firestore 2.19, `get()` com `limit_to_last` inverte in place os `Order`
  compartilhados entre queries derivadas e nao troca os cursores; o lado anterior trazia as
  11 PRIMEIRAS mensagens da conversa. O indice ASC novo continua necessario.
- **Status `failed` antes do save:** o save do envio passou ao threadpool e um webhook de
  status processado durante o POST/save nao achava a mensagem. O `failed` e reaplicado
  DENTRO do request do webhook (1 s e 3 s, antes do 200): fora dele o Cloud Run estrangula
  a CPU e um timer podia nunca disparar. Os demais status nao, para nao regredir um status
  mais novo.
- Trecho da fixada: quando a recencia da THREAD muda (`last_message_at` do doc da conversa:
  cliente respondeu ou operador enviou) ou a busca e digitada, volta as recentes com aviso
  neutro. Nao usa o fim de `messages` (por contato, 1o snapshot pode chegar depois e
  clique admin_only nao aparece). Fora do escopo estrito, "Ir para a mensagem" orienta a
  rolar em vez de chamar o `/context` (403). Falha no `/context` desarma o salto; erro do
  fixar aparece dentro do dialogo; foco volta ao gatilho; o atalho de guias fica bloqueado
  (captura no window) com dialogo aberto. Um lote interrompido pela troca de conversa avisa
  quantas foram.
- Picker: se a lista de canais da sessao veio vazia (falha do `/api/admin/channels`), busca
  de novo; enquanto os numeros forem desconhecidos, contato sem thread fica desabilitado.
- Decisoes do PO (13/11): todo operador com acesso ao chat pode encaminhar (sem chave de
  perfil nem flag), e a fixacao dura ate o prazo escolhido, sobrevivendo a encerramento,
  devolucao ao bot e transferencia. A janela mostra "De: origem -> Para: destino".

## Alternativas

Uma rota de envio independente duplicaria gates de canal/Recepcao e foi descartada.
Guardar a fixacao no contato misturaria canais do mesmo cliente. Buscar todo o
historico para localizar a fixada aumentaria custo e latencia.

## Validacao e liberacao

Testes locais: `tools/sim_message_actions.py` (handlers, gates, midia, persistencia,
contexto e prazos), `node tools/sim_message_actions.mjs` (normalizacao, selecao,
falha parcial/retry, expiracao, resposta atrasada e somente leitura), build do
frontend e simuladores existentes de Recepcao, Ver como e guias de conversa.
HTTP, Meta, Storage e Firestore foram simulados; nao houve envio real.

Antes de liberar, aplicar o novo indice de `firestore.indexes.json`:
`wa_messages` / COLLECTION / `conversation_id ASC, timestamp_wa ASC`.
O Firestore inverte a consulta de `limit_to_last` para buscar o lado posterior;
o indice DESC do outro lado ja existe. Nenhum backfill/rules novos sao necessarios.
Verificar o layout e o envio em ambiente de homologacao. No Ver como, a faixa e
visivel; a busca extra de contexto fora da janela carregada permanece indisponivel,
preservando a allowlist de leituras do transporte aprovado.
