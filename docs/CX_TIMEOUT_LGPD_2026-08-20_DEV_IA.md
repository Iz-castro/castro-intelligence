# Val — deadline estourado no 1º turno pós-aceite LGPD (lead real ficou sem resposta) — para o Dev IA

**Data:** 2026-08-20 · **Agente:** `5fa69ea1-bc68-445b-9d20-d72265aaaf36`
(projeto `castro-ia`, `us-central1`) · **Tenant afetado:** `varizemed` (clínica real)

**Resumo em uma linha:** hoje 14:02 BRT um lead REAL aceitou a LGPD e a
primeira pergunta dele **chegou ao agente** (log do próprio Dialogflow), mas o
turno levou **78s até o primeiro sinal do tool `val-memory`** e morreu em
**DEADLINE_EXCEEDED aos ~109s** sem nunca gerar resposta. O CRM aguentou o
orçamento de 60s e respondeu o fallback de instabilidade. Levantou-se a
hipótese de que "o aceite não chegou no agente" — **refutada com o log do
Google**; o problema é latência **dentro do turno do agente**.

---

## 1. Contexto de versão

A produção aponta hoje pro environment **`05267e69-9632-444c-b009-b6069a7474e2`**
(conferido em `settings.ai` do tenant em prod agora à tarde). Confirma pra
gente QUAL versão da Val é essa e quando foi publicada.

Do lado do CRM, desde 18/08 o conector dá **60s de orçamento por turno**
(era 15s) e **não reenvia em read-timeout** (evita turno duplicado na sessão).

## 2. Evidência (timestamps em UTC; BRT = −3)

Sessão **`5538999772873`** (lead real, interesse em tratamento de varizes —
número completo com o Rafael/Izael):

| UTC | o que houve |
|---|---|
| 16:59:09 | inbound: *"Olá! Tenho interesse no tratamento de varizes e queria mais informações."* — o gate LGPD **local do CRM** responde o aviso (não vai ao agente) |
| 17:02:09 | lead **aceita a LGPD** (botão); prova gravada no CRM |
| **17:02:11.33** | **a request DetectIntent ENTRA no Dialogflow** — log `dialogflow-runtime.googleapis.com/requests` no `castro-ia`, com `queryInput.text` = a pergunta acima e `lgpd_consent: true` nos params, sessão `…/environments/05267e69…/sessions/5538999772873` |
| 17:03:11 | CRM estoura os 60s de orçamento (read-timeout; sem reenvio, por design) |
| 17:03:12 | lead recebe *"Desculpe, estamos com uma instabilidade momentânea…"* |
| 17:03:29 e 17:03:54 | tool **`val-memory`** (Cloud Run `us-west1`, rev `val-memory-00003-w4x`) loga processamento da sessão — ou seja, **78s depois da request** o agente ainda estava no meio do turno |
| **17:04:00.47** | Dialogflow encerra o turno com **`code: 4` (DEADLINE_EXCEEDED)** — *"Resend the request with a higher deadline"* — **~109s de turno, sem resposta** |
| 17:04:13 | mais uma execução do `val-memory` **depois** do deadline |

O lead não reenviou nada desde então (estado: pergunta sem resposta).

## 3. Leitura dos fatos

- **Entrega ok, aceite ok.** O "aceite" nunca trafega como texto: o gate LGPD
  é local no CRM e o agente recebe `lgpd_consent=true` como session param em
  TODO turno, mais a primeira pergunta como texto do turno. Ambos chegaram —
  o log é do Dialogflow, não do nosso conector.
- **O gargalo é antes do tool:** 78s entre a request e o primeiro log do
  `val-memory` — tempo queimado no LLM/roteamento do playbook. E mesmo depois
  disso o turno não fechou: o próprio Google desistiu aos ~109s.
- A execução do `val-memory` às 17:04:13 (**pós-deadline**) sugere retry
  interno ou chamada duplicada de tool no playbook — vale conferir.
- É o mesmo perfil da cauda lenta que motivou o aumento de 15s→60s no
  conector (~7% dos turnos passavam de 15s) — só que esse caso passou até do
  teto do Google.

## 4. Onde olhar (lado do agente — não temos acesso)

1. **Conversation history** da sessão `5538999772873`, hoje 17:02–17:04 UTC:
   qual passo/geração consumiu os 78s iniciais;
2. Latência/logs do **`val-memory`** e do LLM do playbook nessa janela
   (cold start do Cloud Run? quota do modelo?);
3. Por que houve execução de tool **após** o DEADLINE_EXCEEDED (retry?);
4. p95 de latência por turno do environment `05267e69` — esse caso é cauda
   rara ou padrão da versão atual?

## 5. O que o CRM fez (comportamento correto, por design)

60s de orçamento → read-timeout sem reenvio → fallback educado ao lead →
`cx_fail_count=1` (a próxima falha consecutiva vira handoff automático pra
Recepção). Quando o lead escrever de novo, o turno segue normal com
`lgpd_consent=true` — a prova fica no CRM e a Val não re-pergunta a LGPD.

## 6. O que precisamos de você

1. Diagnóstico do turno (§4): por que 78s antes do primeiro tool e turno
   >109s;
2. Qual versão da Val é o environment `05267e69` e se algo publicado
   recentemente explica a latência;
3. Se a resposta for "latência estrutural do playbook": precisamos combinar
   uma meta de latência por turno — o conector não pode esperar mais que
   ~60s (a Meta reentrega o webhook e o lead abandona a conversa).
