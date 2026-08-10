# Pendências do agente CX (Val) — para o Dev IA (Izael)

**Data:** 2026-07-30 · **Contexto:** tenant `varizemed` em produção no Castro CRM
desde 29/07, rodando o agente `5fa69ea1-bc68-445b-9d20-d72265aaaf36`
(projeto `castro-ia`, região `us-central1`).

> **Atualização 2026-08-10:** itens **2 e 3 estão ✅ resolvidos** (marcados no
> corpo). O único item vivo é o **1**, como higiene: params escalares — o CRM
> já desembrulha os dois formatos, então nada está quebrado; vale sobretudo se
> você for mexer nos presets agora. A parte de ambientes do item 3 **evoluiu**:
> a produção do `varizemed` roda o environment `75028a25-…` (`val-5.0.1`)
> desde 10/08, e o tenant de teste está **temporariamente** apontado pro mesmo
> environment (validação de 09/08) — antes de você editar o Draft, peça ao
> Rafael pra devolver o `varizemed-test` pro Draft, senão você edita sem ter
> onde testar. A frente nova (aviso de horário comercial) está em
> `docs/CX_HORARIO_COMERCIAL_DEV_IA.md` — é ela que te destrava agora.

Três pendências, em ordem de importância. As duas primeiras vieram de conversa
real de produção do dia 29/07 (mensagens de sistema gravadas no CRM).

---

## 1. Os session params passaram a sair como STRUCT (regressão de 29/07)

> **⚠ STATUS 2026-07-31: mitigado no CRM; shape do agente INDETERMINADO.**
> O handoff real de hoje saiu 100% limpo (QUENTE alcançado, linhas certas),
> mas isso não prova que o agente voltou a mandar escalares — o unwrap do
> conector (rev `castro-crm-00068-2kb`) normaliza os dois formatos, e por
> LGPD o CRM não loga os params crus, então de fora não dá pra distinguir.
> Para o CRM o assunto está encerrado; a recomendação de params escalares
> segue valendo como higiene para futuros consumidores do agente.

**O que observamos:** até 23/07 o agente devolvia cada session param como
escalar (`user_name: "Timmy"`). Nas conversas de 29/07 no tenant `varizemed`,
o MESMO agente passou a devolver cada param embrulhado num struct com a
própria chave dentro:

```
user_name:          {"user_name": "Timmy"}
wants_appointment:  {"wants_appointment": true}
user_symptom:       {"user_symptom": "..."}
```

**Efeito no CRM (antes do nosso fix):** o resumo do operador saía com
`Nome: {'user_name': 'Timmy'}`, e a classificação de temperatura nunca
chegava a QUENTE (os booleans embrulhados não eram reconhecidos) — todo
lead virava MORNO ou FRIO.

**O que já fizemos do nosso lado:** o conector do CRM agora **desembrulha**
esses structs na entrada (defensivo, 1 entrada com a própria chave → valor
interno), então o CRM funciona com os DOIS formatos. Mas vale você conferir
**o que mudou no agente** por volta de 23-29/07 (playbook/parameter presets/
generator que passou a gravar o param como objeto), porque:

- structs de 2+ chaves NÃO são desembrulhados (não temos como adivinhar);
- outros consumidores futuros do agente (fora o CRM) vão tropeçar no mesmo shape.

**Ideal:** o agente voltar a setar params escalares (string/bool), como a
documentação do próprio Router descrevia.

## 2. O agente parou de setar `handoff_summary`

> **✅ RESOLVIDO 2026-07-31.** Handoff real no tenant `varizemed` às 15:58 UTC
> saiu com a linha `Resumo: Paciente ... Motivo da transferencia: paciente
> pediu atendente.` — texto narrativo que só o agente pode produzir, servido
> pelo environment pinado. Item fechado com evidência em produção.

Nos handoffs de teste de 21-23/07 (`varizemed-test`), o resumo do operador
terminava com a linha **`Resumo: <texto narrativo da Val>`** — que vem do
session param `handoff_summary`. Nos 2 handoffs reais de 29/07 (`varizemed`)
essa linha **não veio**: o agente não está mais preenchendo `handoff_summary`
no momento da transferência.

É justamente a parte narrativa que o atendente mais usa. Pedido: reativar o
preenchimento de `handoff_summary` no step de transferência do playbook
(1-3 frases: quem é, o que quer, o que já foi validado).

## 3. Publicar versão + ambiente do agente (produção está no DRAFT)

> **✅ RESOLVIDO 2026-07-31.** O Izael criou o environment
> `6bdfaeed-6dd3-445c-b32a-4e1f85ab32dd` e o CRM de produção do tenant
> `varizemed` já aponta pra ele (validado com DetectIntent antes do apontamento;
> `settings.ai.environment_id` gravado via merge, cache de tenants renova em
> ~60s). O tenant interno de teste ("Castro Intelligence SAC") segue no
> **Draft** de propósito — é onde as edições do agente são testadas antes de
> virar versão nova. Fluxo de promoção e rollback abaixo continuam valendo.

**Atenção a uma confusão de nomes:** `5fa69ea1-bc68-445b-9d20-d72265aaaf36`
é o **AGENT ID**, não um environment. Environment é um recurso separado
dentro do agente (`.../agents/<AGENT_ID>/environments/<ENVIRONMENT_ID>`),
e hoje o campo `environment_id` do tenant está **vazio** — ou seja, o CRM
de produção fala com o **Draft** do agente.

Consequência prática: **qualquer edição salva no console entra em produção
na hora**, sem promoção. Foi exatamente assim que o item 1 entrou em prod
sem ninguém perceber.

**O que precisamos de você (no console do Dialogflow CX):**

1. Em **Agent → Versions**: criar uma versão a partir do Draft atual
   (depois de resolver os itens 1 e 2, de preferência).
2. Em **Agent → Environments**: criar um environment `production` apontando
   para essa versão.
3. Nos passar o **ENVIRONMENT ID** (o UUID do environment, visível na URL ou
   via API `projects.locations.agents.environments.list`).

**O que fazemos do nosso lado ao receber o ID** (fica registrado aqui):

```powershell
$env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
$env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
./.venv/Scripts/python.exe -m scripts.set_tenant_ai --tenant varizemed `
    --gcp-project castro-ia --location us-central1 `
    --agent-id 5fa69ea1-bc68-445b-9d20-d72265aaaf36 `
    --environment-id <ENVIRONMENT_ID> `
    --handoff-bot-key sac `
    --lgpd-notice "<texto atual>" --lgpd-policy-version varizemed-2026-07 `
    --core-version val-05 --yes
```

Fluxo de mudança dali em diante: editar no Draft → testar no simulador do
console (ou no tenant interno de teste, que pode continuar no Draft) →
criar versão nova → apontar o environment `production` pra ela. Rollback =
apontar o environment de volta pra versão anterior.

---

*Gerado a partir da verificação de 29-30/07 (workflow de 5 agentes + leitura
read-only do Firestore de prod). Referências no CRM: conector
`bot_engine_dialogflow.py` (unwrap + montagem do agent_path), resumo
`bot_service._cx_handoff_details`, temperatura `lead_temperature.py`.*
