# ADR 0016: Encaminhamento e mensagem fixada por conversa

Data: 2026-11-13. Status: implementado localmente, sem deploy.

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
