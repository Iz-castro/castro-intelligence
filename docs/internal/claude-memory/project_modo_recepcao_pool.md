---
name: project-modo-recepcao-pool
description: "Modo Recepcao (pool compartilhada varizemed, ADR 0010) implementado 2026-08-04 — EM PROD desde 2026-08-05 (commits ate 266b112); pendencias e gotchas"
metadata: 
  node_type: memory
  type: project
  originSessionId: 03614748-df5e-43a4-88e6-33525fdd540a
  modified: 2026-08-19T02:38:44.533Z
---

Modo Recepcao (ADR 0010) **EM PRODUCAO: rev `castro-crm-00074-zrt` promovida 100% em 2026-08-05** apos canario completo no varizemed-test (4 ajustes de canario documentados no ADR; commits ate 266b112). Inclui: pool compartilhada, autoria por mensagem (`sent_by_name`), toggle RBAC `assumir_atendimento`, fechamento (manual/cron) devolve lead ao agente via `release_lead_to_bot` (Fase 2 do PLANO_MODELOS itens 6 e 9 ANTECIPADOS — hidratacao LGPD pelo contato inclusa), menu "Devolver a recepcao" (`return_contact_to_pool`), envio em orfa mid-bot carimba `bot_completed` (opcao A). Kill-switch: `PUT pool_mode=legacy`. Rollback: `--to-revisions castro-crm-00068-2kb=100`.

**Correcao 2026-08-09 (rev `castro-crm-00075-dnt`, 100%):** handoff que NINGUEM atendeu nao volta mais pro bot no auto-close. Bug: `release_lead_to_bot` zera `bot_completed`, e o filtro da aba Recepcao EXIGE `bot_completed` + a aba Bot so aparece pra admin/supervisor → lead de fim de semana sumia da fila e a Val o atendia do zero na segunda. Mecanismo: dois campos NOVOS em `wa_conversations` — `handoff_at` (gravado por `_persist_lead_temperature` no handoff CX e por `_finalize_bot` no builtin) e `last_human_outbound_at` (gravado por `save_wa_message` quando outbound tem `sender_user_id`); guard `_reception_handoff_unattended` compara os dois (sem reset — handoff novo invalida carimbo humano velho sozinho) e pula o fechamento. Teto `RECEPTION_UNATTENDED_RELEASE_DAYS` (env, default 7). Gates: sim_reception_flow 73, sim_cx_flow 118, sim_bot_flow 45. **Provado em prod**: 8 leads engolidos 08-09/08 restaurados (`bot_completed=True` + `handoff_at` + reabertos) e sobreviveram ao cron das 22:00Z. Commitado depois em `25f1f1f`, com emenda do ADR 0010 + diario em `192422c`. Metade positiva ("continua fechando o que deve", sobretudo legacy hubloc) ainda nao observada em prod. Rollback dos 8: `bot_completed=False` nos contatos [4,15,27,29,32,45,47,52].

**RETOMADA COMBINADA (PO, 2026-08-14):** o Rafael volta quando o dev de IA
terminar a ramificacao do horario no agente. Roteiro na volta: (1) dev testa
no DRAFT via `varizemed-test` (ja apontado pro draft); (2) publica environment
novo e manda o ID; (3) trocar `environment_id` do `varizemed` + `core_version`
no MESMO write (padrao dos scripts de troca em scratchpad — recriar; guard de
env-esperado + diff campo a campo); (4) validar: fora do expediente a Val diz
o horario VINDO de `retorno_previsto` (nunca hardcoded), dentro do expediente
sem aviso, handoff continua caindo na Recepcao (vigiar hints!), params
escalares. Tambem pendente do dev: frase de erro custom -> entra em
`settings.ai.cx_error_phrases` SEM deploy (blindagem rev 00080-rjd).

Frente "horario comercial" **FASE 1 EM PROD 2026-08-10** (rev `castro-crm-00077-5fd`, commit `5854c2c`): modulo novo `business_hours.py` = fonte unica dos 2 bots; tabela hardcoded por tenant (varizemed seg-qui 08-18 / sex 08-17, teste espelha; hubloc seg-sex 08-17; sem almoco); CX recebe `fora_do_expediente` + `retorno_previsto` em TODO turno (agente ignora ate o dev usar — spec `docs/CX_HORARIO_COMERCIAL_DEV_IA.md`, atualizada com tabela de valores; agente TEM que interpolar, nunca escrever hora no texto); aviso builtin da hubloc trocado do hardcoded 7h-17h pro calculo real 8h-17h (lead das 7h-7h59 passou a receber aviso — comportamento correto confirmado pelo PO: empresa abre 7h, atendimento 8h). Fail-safe: tenant sem tabela NUNCA e declarado fechado. Motivacao: a Val decidia horario sozinha no playbook — "ja encerrou por hoje / proximo dia util" as 07:32 de segunda e em fins de semana, saudacao com "8h as 18h" divergente (sexta e 17h). **FASE 2 pendente**: tabela pro `system_settings` + tela admin com calendario mensal clicavel e feriados por CHAVE (nao por data — data apodrece na virada do ano); API do modulo ja desenhada pra troca sem mudar callers. De carona na mesma rev: log `[SMB ECHO]` do webhook redigido (unica linha com telefone em claro).

**2026-08-17 (Rafael, commit `bb668f2`):** filtro por qualificacao na sidebar (Bot/Recepcao/Meus/Equipe) e dentro do picker "+"; "Carregar mais" tambem em Recepcao (pool sem dono, operador) e Bot/Recepcao (janela global, admin); picker "+" agora tambem na Recepcao (caminho oficial pra recepcionista achar lead ja atendido e devolvido ao bot — a caixa Recepcao NAO lista esses, `bot_completed=False`). Bug pre-existente corrigido de carona: form Qualificacao/Notas semeado so do top-50 ao vivo → thread hidratada abria em branco e Salvar APAGAVA notas. **Decisao de produto ABERTA:** Rafael perguntou se a recepcionista poderia ver a caixa Bot (hoje `canSeeAll` only; dados dela ja incluem a pool, rules permitem) — nao implementado, aguardando ele decidir. Alternativa B (Recepcao listar leads ja atendidos+devolvidos) = emenda do ADR 0010.

**2026-08-18 noite (deploy in-session, ver [[project-cx-timeout-60s]]):** em `pool_mode=reception` o webhook NAO reatribui mais "lead convertido que retornou" ao operador que converteu (regra legada do Hubloc, `[REROUTE]` em webhook.py) — Rafael testou com o numero dele (contato 193): a Val respondeu e no mesmo turno o lead grudou no "contato" (supervisor sem assumir), calando a Val nas msgs seguintes. Decisao do PO: **em Recepcao lead nao gruda em pessoa** (paciente volta pra duvida pequena e a Val resolve). Captura de nota 1-10 segue nos dois modos; legacy inalterado. Contato 193 devolvido ao bot (`return_contact_to_bot`).

Pendente pos-promocao: ligar `pool_mode=reception` na VARIZEMED REAL + perfil "Recepcao" + setor das 3 operadoras (conferir department_id do handoff na real antes); monitorar 1o ciclo do cron; varizemed-test tem bot_key `sac` duplicado (Suporte#3/Recepcao#5); misterio do login Edge (docs/internal/2026-08-05.md); contas de teste `teste.recepcao@`/`teste.operador@varizemed-test.com` ativas (desativar apos rollout).

**Why:** varizemed pediu 3 operadoras numa caixa compartilhada; ADR 0008 ("assumir pra falar") vale so como default por tenant agora.

**How to apply:**
- Pendencias (ordem): commit → deploy staging + promote por NOME → ligar `pool_mode=reception` no `varizemed-test` e rodar o roteiro do ADR → criar perfil "Recepcao" (`assumir_atendimento` OFF) pras 3 operadoras → ligar na varizemed real.
- Gate de validacao novo: `tools/sim_reception_flow.py` (39 asserts, exercita main/rbac/db reais). ⚠ contatos de fixture da pool precisam de `bot_completed: True`, senao o gate chama o `mark_human_active` REAL (tenta Firestore; ADC local aponta pro projeto VELHO de SP).
- Gotcha estrutural descoberto: **toda chave nova de `PERMISSION_CATALOG` pos-seed** fica ausente nos docs de perfil e o editor persistia False no 1o PUT (revogacao silenciosa + perfil_admin insalvavel). Fix = `_fill_missing_toggles` em `rbac.list_perfis` — o J-3 F1.1 (`registrar_revogacao_lgpd`) ja herda, mas conferir o default desejado por role no merge.
- [[project_bot_flow_e_pool_setor]] [[project_operator_isolation_lgpd]] [[project_varizemed_migration]]
