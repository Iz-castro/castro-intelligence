# ADR 0002 — LGPD em canal coexistence compartilhado por multiplos operadores

- **Status:** Proposed (aguardando discussao com a equipe + assessoria juridica)
- **Data:** 2026-05-11
- **Autores:** Rafa + Claude (analise inicial)
- **Relacionado:** [CLAUDE.md §2 (Compliance LGPD)](../../CLAUDE.md),
  [ADR 0001](0001-prevenir-coex-signup-duplicado.md),
  `_check_conv_send_permission` em [main.py:1136](../../main.py#L1136),
  modelo `channel_owner_user_id` vs `sender_user_id` em `wa_messages`.

> **Atualizacao 2026-06-03:** a visibilidade por `department_id` foi **removida**
> do isolamento (commit `ddcfb69`). O operador comum agora ve **apenas** contatos/
> conversas atribuidos a si ou em pool/fila — nunca por departamento. O
> compartilhamento de canal coex segue via **transferencia de thread**
> (`assigned_to`), nao por departamento. O "modelo operacional ativo" descrito
> abaixo reflete o estado de 2026-05-11. Ver [docs/internal/2026-06-03.md](../internal/2026-06-03.md).

## Contexto

O sistema suporta dois tipos de canal:

- **Standard (Cloud API):** numero da empresa via Meta API direta.
  Compartilhado por todos os operadores. Sem coex.
- **Coexistence:** numero pessoal/Business do operador, conectado via
  Embedded Signup. O `owner_user_id` do canal e a pessoa fisica que
  fez o signup e tem o app no celular.

O **modelo operacional ativo** permite que multiplos operadores usem
o mesmo canal coex via transferencia de thread:

1. Supervisor (ou operador "owner") registra coex — vira `channel.owner_user_id`.
2. Threads sao criadas com `assigned_to` no operador atual.
3. Quando o operador transfere a thread (ex.: Izael → Maria),
   `conversation.assigned_to` muda para Maria.
4. Maria envia normalmente: `_check_conv_send_permission`
   ([main.py:1136-1148](../../main.py#L1136-L1148)) so checa
   `assigned_to == current_user.id`, **nao** valida ownership do canal.
5. Send usa as credenciais do canal coex do Izael (token dele); cliente
   ve mensagem chegando do numero do Izael.
6. Mensagem salva com `channel_owner_user_id=Izael` + `sender_user_id=Maria`.

**Resultado:** o numero pessoal do Izael e operado por toda a equipe
designada, com auditoria interna preservada pelos campos duplos.

Sob a LGPD (Lei 13.709/2018), esse modelo levanta quatro pontos de
atencao concretos identificados abaixo. **Este ADR nao pretende ser
parecer juridico** — registra os riscos tecnicos para a equipe levar
a assessoria juridica e tomar decisao informada.

## Pontos de atencao identificados

### 1. Identidade do remetente perante o titular (art. 6º VI — transparencia, boa-fe)

**Risco:** o cliente recebe mensagem do numero pessoal do Izael
("Izael Castro — +55 31 7195-7758" no WhatsApp), mas pode estar
interagindo com a Maria respondendo pelo CRM. Para o titular, e Izael.

Cria expectativa falsa de pessoalidade que pode violar o principio
da boa-fe + transparencia. Especialmente sensivel quando o cliente
compartilha info pessoal acreditando estar falando com individuo
especifico (relacao comercial recorrente).

**Mitigacao tecnica proposta:** assinatura automatica no fim das
mensagens enviadas por quem **nao e** o owner. Backend ja tem os
dois campos separados; basta detectar `sender_user_id != channel_owner_user_id`
no `wa_send` e prefixar ou sufixar:

```
— Maria, equipe Hubloc
```

Esforco baixo, protecao alta.

### 2. Acesso ao historico apos transferencia (art. 6º I — finalidade)

**Risco:** quando thread e transferida do A pro B, B passa a ler
todo historico anterior. Cliente confidenciou info ao A esperando
ficar so com ele.

**Avaliacao LGPD:** se o titular consentiu com "atendimento Hubloc"
(nao com "atendimento exclusivo do Izael"), a troca interna de
operador **mantem** a finalidade. Nao ha violacao **se** a politica
de privacidade for clara.

**Mitigacao:**
- **Politica de Privacidade da Hubloc** deve declarar expressamente:
  "Seu atendimento e prestado por equipe da Hubloc. O historico de
  conversa pode ser acessado por outros operadores autorizados ao
  longo do atendimento."
- **Mensagem de sistema visivel pro cliente** quando troca de
  operador real (nao apenas no log interno):
  > "Ola! Sou a Maria, vou continuar seu atendimento a partir de agora."

  Sistema ja tem `insert_transfer_system_message` ([main.py:2517](../../main.py#L2517))
  pra log interno; podemos opcionalmente enviar uma mensagem real
  pro cliente via Meta API quando a transferencia for entre operadores
  humanos (nao bot↔humano).

### 3. Numero pessoal do operador como ferramenta de trabalho (risco trabalhista + LGPD secundario)

**Cenario:** o numero +55 31 7195-7758 e do Izael pessoa fisica.
Quando ele sai da empresa, o chip sai com ele. Threads ficam orfas;
clientes acreditam que "o atendimento da Hubloc sumiu". Pior: Izael
pode continuar tendo o app no celular dele com todo o historico
exportado/visivel.

**Risco LGPD adicional:** se o operador sai e mantem dados pessoais
dos clientes da Hubloc no celular dele, a Hubloc (controladora) perdeu
controle sobre dados de titulares — possivel violacao do principio
da seguranca (art. 6º VII) e da prestacao de contas (art. 6º X).

**Mitigacoes possiveis (combinaveis, nao excludentes):**

- **Contratual:** contrato de trabalho/PJ define o numero como
  ferramenta de trabalho, exige devolucao do chip + remocao do
  Business app no desligamento. Assessoria juridica precisa
  ratificar.
- **Operacional:** numero idealmente em CNPJ da Hubloc, com chip
  fornecido pela empresa, atribuido ao operador.
- **Tecnica:** preferir canal **standard** (Cloud API) como default
  e usar coex apenas quando o caso de uso justifica (operador que ja
  tem relacionamento estabelecido com clientes naquele numero).
  Coex e a excecao, nao a regra.
- **Procedural:** no desligamento, executar wipe do tenant na parte
  do operador + revogar acesso + se possivel re-vincular o numero a
  outro operador (sera coberto por endpoint da [ADR 0001](0001-prevenir-coex-signup-duplicado.md)).

### 4. Audit de leitura passiva esta incompleto (art. 6º X — responsabilizacao)

**Estado atual:** `audit_log` registra mutacoes (send, transfer,
mark-read). Mas o snapshot Firestore que carrega 50 conversations +
mensagens **nao passa pelo backend** — vai client→Firestore direto via
SDK. **Nao gera audit log.**

**Risco LGPD:** principio da responsabilizacao exige demonstrar quem
acessou dado pessoal. No modelo coex compartilhado, "quem leu o que"
importa mais do que em standard (porque mais gente tem acesso
potencial).

**Mitigacoes:**

- **Firestore rules estritas** (frente WIP em
  `firestore-rules-staging-strict.wip`): nega leitura no nivel da rule
  para threads onde `request.auth.uid != assigned_to`. Investigacao
  pendente (ver [RETOMAR.md §0.B](../internal/RETOMAR.md)).
- **Audit log de leitura via heartbeat:** UI envia POST
  `/api/wa/conversation/{id}/opened` quando operador abre uma thread;
  backend registra `CONVERSATION_OPENED` no audit_log. Esforco baixo,
  cobre o gap sem deixar de usar snapshot listener.
- **Endpoint LGPD dedicado:** `GET /api/admin/lgpd/access-report?wa_id={x}`
  retorna lista cronologica de "quem fez o que" naquele titular
  (mensagens enviadas, transfers, leituras se houver heartbeat).
  Atende solicitacao formal de titular sob art. 18.

## Decisao proposta

Aprovar as 4 frentes de mitigacao acima como **plano de adequacao**,
priorizadas por severidade × esforco:

| # | Frente | Severidade | Esforco | Prioridade |
|---|---|---|---|---|
| 1 | Assinatura `— {nome}, equipe Hubloc` quando `sender != owner` | Medio | Baixo | **Alta** |
| 2 | Mensagem de sistema visivel pro cliente em transferencia humano↔humano | Medio | Baixo | **Alta** |
| 3a | Politica de Privacidade declarando atendimento em equipe | Alto | Medio (juridico) | **Obrigatoria antes de escalar coex** |
| 3b | Contrato definindo numero coex como ferramenta de trabalho | Alto | Medio (juridico/RH) | **Obrigatoria antes de escalar coex** |
| 4 | Firestore rules estritas (retomar WIP) | Alto | Alto | Media |
| 5 | Audit log de leitura via heartbeat | Medio | Baixo-Medio | Media |
| 6 | Endpoint `/api/admin/lgpd/access-report` | Alto | Alto | Media |
| 7 | Preferir standard sobre coex quando possivel | Estrutural | Politica | Continuo |

Itens 3a/3b sao **pre-requisitos juridicos** antes de onboardar
clientes #2+ em modelo coex compartilhado. Sem politica clara, a
Hubloc esta exposta a queixa de titular alegando expectativa de
pessoalidade.

## Alternativas consideradas

1. **Nao adotar nenhuma mitigacao — manter modelo atual.**
   - Pro: zero codigo + zero politica nova.
   - Con: exposicao LGPD nao mitigada. Risco juridico e reputacional
     em incidente real. **Rejeitada.**

2. **Proibir coex compartilhado — uma thread, um operador.**
   - Pro: simplifica modelo, alinha melhor com expectativa de
     pessoalidade do titular.
   - Con: quebra caso de uso real (operador de ferias, plantao,
     escala). Operacionalmente inviavel. **Rejeitada.**

3. **Adotar as 4 frentes (proposta).**
   - Pro: mantem modelo operacional, reduz exposicao em multiplas
     dimensoes, deixa caminho claro pra resposta a incidente.
   - Con: requer combinacao de mudanca tecnica + politica/juridica.
     Nao e algo que codigo sozinho resolve.

## Consequencias

### Positivas
- Auditoria interna **e** externa mais defensaveis em caso de
  fiscalizacao ANPD ou queixa de titular.
- Modelo coex compartilhado continua viavel sob LGPD com mitigacoes
  combinadas.
- Direitos do titular (art. 18: acesso, correcao, eliminacao,
  portabilidade) ganham caminho tecnico via endpoint dedicado.

### Negativas / pontos de atencao
- Algumas frentes exigem **decisao juridica externa** (politica de
  privacidade, contrato com operador) — equipe tecnica nao decide
  sozinha.
- Audit de leitura via heartbeat aumenta volume de writes no Firestore
  (cada abertura de thread = 1 write). Custo modesto mas existe.
- Assinatura automatica pode "poluir" mensagens curtas (cliente recebe
  "OK — Maria, equipe Hubloc" pra um "OK" do operador). Pode-se omitir
  em mensagens onde sender == owner (mais comum).

## Itens dependentes (fora do escopo desta ADR)

- Reuniao com assessoria juridica para validar texto da Politica de
  Privacidade + clausula contratual sobre numero como ferramenta.
- Definir gatilho do heartbeat (so quando thread fica aberta > N
  segundos? Toda abertura?).
- Definir UX da assinatura automatica (sufixo? aviso visivel no
  compositor pra Maria saber que sua mensagem sera assinada?).
- Roadmap completo de adequacao LGPD (DPIA — relatorio de impacto a
  protecao de dados — se aplicavel; nomeacao de encarregado pela
  Hubloc; canal de comunicacao com titular).
