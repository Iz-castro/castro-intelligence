# Schema Firestore — Val × Castro Chat

**Documentação técnica · Integração Val**
Dados disponíveis hoje no Firestore para qualificação de leads (quente / morno / frio) no Castro Chat
Belo Horizonte, MG — 18 de julho de 2026 · v01

---

## 1. Resumo executivo

> **Decisão de escopo:** a classificação de leads (quente / morno / frio) será implementada inteiramente no Castro Chat, lendo dados que o Firestore já contém hoje. Nenhuma ação nova, tool nova ou mudança de comportamento é adicionada à Val neste momento.

Este documento mapeia exatamente o que existe hoje no banco Firestore compartilhado entre a Val (Dialogflow CX) e o Castro Chat — coleções, campos, quem escreve cada um, e o que é calculado durante a conversa mas não chega a ser persistido. O objetivo é dar ao time do Castro Chat o material completo para desenhar a lógica de qualificação sem depender de nenhuma mudança no agente.

> **Principal ponto de atenção:** "endereço perguntado" e "preço mostrado" não existem como campos estruturados hoje — só como texto natural dentro das respostas da Val. A seção 5 detalha o porquê e a seção 6 propõe uma leitura híbrida (parâmetros estruturados + varredura de texto) que resolve isso sem tocar na Val.

---

## 2. Arquitetura em uma frase

A Val roda em Dialogflow CX e usa duas tools próprias — **VarizemedRouter** (regras de negócio da clínica) e **VarizemedMemory** (persistência) — que leem e escrevem no mesmo banco Firestore (`database val-4`) que o Castro Chat também usa para gravar mensagens, status de atendimento e atribuição de atendente. **O Firestore é a fonte de verdade compartilhada** entre os dois sistemas; não há chamada direta de um sistema para o outro.

---

## 3. Estrutura de dados no Firestore

```
database:  val-4          (env var FIRESTORE_DATABASE, default)
prefixo:   ""             (env var FIRESTORE_PREFIX, namespace opcional)
coleções:  conversations, conversation_history
```

### 3.1 `conversations/{user_id}`

Documento por paciente (`user_id` = telefone em E.164). Campos gravados por dois sistemas diferentes:

| Campo | Escrito por | Tipo | Descrição |
|---|---|---|---|
| `updated_at` | Val | timestamp | Última sincronização de estado (`sync_session_state`) |
| `last_sync_at` | Val | timestamp | Idem, redundante para auditoria |
| `session_parameters` | Val | map | Subconjunto filtrado dos parâmetros de sessão — ver seção 4 |
| `last_message_text` | Castro Chat | string | Texto da última mensagem da conversa |
| `last_in_from` | Castro Chat | string | Canal/direção da última mensagem |
| `status` | Castro Chat | string | Estado da conversa no pipeline do Castro Chat |
| `handoff_active` | Castro Chat | bool | Se está em atendimento humano no momento |
| `assignee` | Castro Chat | string | Atendente responsável, quando houver |

*Estes cinco últimos campos (`last_message_text`, `last_in_from`, `status`, `handoff_active`, `assignee`) são lidos pela tool VarizemedMemory mas nunca escritos por ela — a origem é o próprio pipeline do Castro Chat. Isso confirma que o Castro Chat já tem escrita direta neste mesmo documento.*

### 3.2 `conversations/{user_id}/messages` (subcoleção)

Histórico de mensagens da conversa, também de escrita do Castro Chat (a Val só lê, via `get_conversation_messages`).

| Campo (schema atual) | Fallback (schema legado) | Descrição |
|---|---|---|
| `text` | `content` | Conteúdo da mensagem |
| `by` / `direction` | `role` | Quem enviou: paciente (`in`/`user`) ou Val/atendente (`out`/`assistant`) |
| `ts` | `timestamp` | Data/hora da mensagem |

### 3.3 `conversation_history/{user_id}`

Resumo de longo prazo, escrito pela Val ao final de uma conversa (`save_conversation_summary`).

| Campo | Tipo | Descrição |
|---|---|---|
| `summary` | string | Resumo da conversa gerado pela Val |
| `key_points` | array | Pontos-chave da conversa |
| `updated_at` | timestamp | Data do último resumo salvo |
| `session_snapshot` | map | Foto do `session_parameters` relevante no momento do resumo (mesmo filtro da seção 4) |
| `previous_summaries` | array | Até 5 resumos anteriores, para histórico |

---

## 4. `session_parameters` — o que realmente persiste hoje

A Val calcula dezenas de sinais a cada turno de conversa, mas só uma lista fixa de **19 chaves** (`RELEVANT_KEYS`, em `main.py`) é filtrada e gravada no Firestore pela `sync_session_state`. Tudo que não está nesta lista é calculado e descartado ao fim do turno — não sobra rastro no banco.

| Parâmetro | Tipo | Origem | Uso para qualificação de lead |
|---|---|---|---|
| `user_name` | string | Provável — playbook/LLM (não localizado no router.py) | Identifica o paciente |
| `user_symptom` | string | Provável — playbook/LLM | Sintoma relatado |
| `user_insurance` | string | Router — `classify_user_intent` | Convênio mencionado |
| `user_insurance_type` | string | Provável — playbook/LLM | Classificação do convênio |
| `user_specialty` | string | Router — `classify_user_intent` (via `detected_specialty`) | Especialidade de interesse — sinal de engajamento (morno+) |
| `user_preferred_doctor` | string | Router — `classify_user_intent` | Médico preferido, se mencionado |
| `wants_appointment` | bool | Router — `classify_user_intent` | Sinal mais forte de lead quentíssimo |
| `wants_treatment` | bool | Router — `classify_user_intent` | Interesse em tratamento específico |
| `wants_consult_only` | bool | Provável — playbook/LLM | Quer só consulta, sem tratamento |
| `conversation_summary` | string | Router — `save_conversation_summary` (fallback) | Contexto textual da conversa |
| `handoff_summary` | string | Router — `generate_handoff_summary` (fluxo) | Resumo preparado para atendente humano |
| `handoff_request` | string/bool | Provável — playbook/LLM | Pedido explícito de atendimento humano |
| `previous_intent` | string | Provável — playbook/LLM | Última intenção classificada |
| `conversation_stage` | string | Provável — playbook/LLM | Etapa da conversa |
| `intent_type` | string | Router — `classify_user_intent` (via `detected_intent_type`) | Tipo de intenção do turno |
| `turn_count` | int | Provável — playbook/LLM | Nº de turnos — proxy de engajamento (lead frio = baixo) |
| `insurance_validated` | bool | Router — `validate_insurance` | Convênio já foi checado — sinal de lead quente |
| `tratamentos_ja_mencionados` | array | Entrada do playbook (consumido, não gerado, pelo router) | Tratamentos já discutidos |
| `has_greeted` | bool | Provável — playbook/LLM | Se a saudação inicial já ocorreu |
| `is_business_hours` | bool | Router — múltiplas ações | Horário comercial no momento do turno |

*"Provável — playbook/LLM" marca os campos cuja origem não foi encontrada no `router.py` nem no `main.py` — o valor mais provável é que sejam definidos diretamente pelas Instructions do Playbook. Vale confirmar com quem mantém essas Instructions antes de depender desses campos em regras críticas.*

---

## 5. Sinais calculados pela Val, mas não persistidos hoje

> **Gap conhecido:** estes campos existem dentro do turno de conversa (o `router.py` os calcula e devolve), mas não estão em `RELEVANT_KEYS` — nunca chegam ao Firestore. Se a lógica de qualificação do Castro Chat tentar ler qualquer um deles via `session_parameters`, vai encontrar vazio.

| Campo | Calculado em | Por que importaria para lead scoring |
|---|---|---|
| `clinic_info_retrieved` | `get_clinic_info` | "Endereço perguntado" — não persiste |
| `treatment_found` | `get_treatment_info` | Se o tratamento buscado existe na clínica |
| `insurance_disposition` | `validate_insurance` | aceito / não_aceito / alerta / requer_autorizacao — esfria ou aquece automaticamente |
| `insurance_accepted` | `validate_insurance` | Convênio aceito ou não |
| `insurance_type` | `validate_insurance` | Classificação do convênio validado |
| `insurance_alert` | `validate_insurance` | Convênio do grupo secundário (requer atenção) |
| `insurance_requires_handoff` | `validate_insurance` | Já indica necessidade de atendente humano |
| `doctor_group` | `validate_insurance` | Grupo de médicos aplicável |
| `scheduling_route` | `determine_scheduling_route` | Rota de agendamento decidida |
| `next_action` | `determine_turn_route` | Próxima ação sugerida ao Playbook |
| `confidence_level` | `classify_user_intent` | Confiança da classificação do turno (high/medium/low) |
| `detected_keywords` | `classify_user_intent` | Palavras-chave que geraram a classificação |
| `doctors_found` | `get_doctors_by_specialty` | Quantidade de médicos retornados na busca |

> **"Preço mostrado" não é um gap — nunca existiu.** Diferente dos campos acima, o valor do tratamento nunca foi estruturado como dado em nenhum momento: ele é montado como texto pronto dentro da resposta ao paciente (`_generate_text`) e nunca vira um campo como `price_shown`. Não há como recuperar isso de `session_parameters` hoje — só do texto da mensagem em si.

---

## 6. Abordagem recomendada para o Castro Chat

Combinar as duas fontes que já existem no mesmo documento do Firestore, sem depender de nenhum campo que falte:

- **`session_parameters`** (seção 4) para sinais de intenção confiáveis: `wants_appointment`, `wants_treatment`, `insurance_validated`, `user_treatment`, `user_specialty`, `turn_count`, `has_greeted`.
- **Texto bruto** (`last_message_text` e a subcoleção `messages`, ambos de escrita do próprio Castro Chat) para sinais de conteúdo que a Val não estrutura: menção a valores (R$), menção a endereço, palavras de reclamação/urgência.

Exemplo ilustrativo da combinação (lógica de referência, não é código de produção):

```python
doc = db.collection("conversations").document(user_id).get().to_dict()
params = doc.get("session_parameters", {})
messages = doc.get("messages", [])  # ou subcoleção, conforme acesso do Castro Chat

price_mentioned = any("R$" in m["text"] for m in messages if m["by"] in ("val", "assistant"))
address_given = any(k in m["text"].lower() for m in messages
                    for k in ("endereço", "fica na", "avenida"))

if params.get("wants_appointment"):
    lead = "quentissimo"
elif params.get("insurance_validated") or price_mentioned:
    lead = "quente"
elif params.get("user_treatment") or params.get("user_specialty"):
    lead = "morno"
else:
    lead = "frio"
```

---

## 7. Registro para decisão futura (não é uma recomendação de ação agora)

Caso o time decida, mais adiante, que vale a pena estruturar algum dos campos da seção 5 (ex.: `insurance_disposition` ou `clinic_info_retrieved`), a mudança do lado da Val é pontual e não envolve nenhuma decisão nova para a LLM: é adicionar a chave em `RELEVANT_KEYS` (`main.py`) e no bloco de merge já existente em `format_success_response` (`formatters.py`), que já calcula esses valores hoje. Fica registrado aqui só como referência — nenhuma ação está planejada neste momento.

---

## 8. Apêndice técnico

| Item | Valor |
|---|---|
| Database Firestore | `val-4` (env var `FIRESTORE_DATABASE`) |
| Namespace opcional | `FIRESTORE_PREFIX` (vazio por padrão) |
| Coleção principal | `conversations` |
| Coleção de histórico | `conversation_history` |
| Fuso horário | America/Sao_Paulo (UTC-3), aplicado nos timestamps formatados |
| Tool responsável pela escrita (Val) | VarizemedMemory (`main.py`) |
| Tool responsável pelas regras de negócio (Val) | VarizemedRouter (`router.py`, dentro do compilado) |
