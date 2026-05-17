# ADR 0001 — Prevenir Embedded Signup duplicado pro mesmo numero coexistence

- **Status:** Proposed (aguardando discussao com a equipe)
- **Data:** 2026-05-11
- **Autores:** Rafa + Claude (analise inicial)
- **Relacionado:** `embedded_signup_exchange` em [main.py:3042](../../main.py#L3042),
  `create_channel` em [channel_service.py:208](../../channel_service.py#L208),
  `upsert_phone_routing` em [tenant_service.py:219](../../tenant_service.py#L219).

## Contexto

Hoje o endpoint `POST /api/admin/embedded-signup/exchange` aceita signup
coexistence sem validar se o `phone_number_id` retornado pela Meta ja
esta vinculado a um canal ativo no tenant.

Cenario reproduzivel:
1. Operador Izael (coex owner do numero +55 31 7195-7758) faz signup em D-0.
   Canal `#1` criado, `phone_routing/1055982807598158 → channel_id=1`.
2. Supervisor Rafael, por engano (achando que vai conectar um numero
   novo), executa Embedded Signup escolhendo a **mesma WABA + mesmo
   numero** em D-1.

Comportamento atual:

- Token exchange + debug_token + phone_numbers da Meta retornam o
  mesmo `waba_id` e `phone_number_id`.
- `create_channel` gera `channel_id=3` paralelo ao `#1` (sem checagem).
- `upsert_phone_routing` faz `set(merge=True)` sobrescrevendo o
  routing global: a partir desse instante todo webhook inbound para
  o numero do Izael resolve para o canal `#3` (do Rafael).
- Cache `_channels_by_phone_id` (last-write-wins) tambem aponta para
  `#3` apos o proximo refresh.
- Canal `#1` permanece `is_active=True` em paralelo, com token antigo
  de Izael.
- Sync `smb_app_data` (history + state_sync) e disparado novamente —
  Meta pode aceitar (novo signup) e webhooks `history`/`smb_app_state_sync`
  chegam apontando para `#3`, criando conversations duplicadas com
  `conversation_id = "3__{wa_id}"` enquanto as antigas `"1__{wa_id}"`
  ficam orfas.

Impacto operacional para o Izael (operador legitimo):

| Fluxo | Resultado |
|---|---|
| Cliente manda mensagem | Webhook routea para `#3`. Izael nao ve (sidebar dele filtra por owner_user_id em `get_channels_for_user`). |
| Izael responde do celular (smb_echo) | Webhook routea para `#3`. Mensagem salva com `channel_owner_user_id=Rafael` e `operator_id=Rafael` — auditoria vira mentirosa. |
| Conversations antigas (`"1__..."`) | Orfas: nao recebem inbound novo, ficam congeladas. |
| Izael responde uma thread antiga pelo CRM | `get_send_credentials(channel_id=1)` ainda funciona enquanto o token velho nao expirar / Meta nao invalidar. Race condition. |

Falha silenciosa: nem Rafael nem Izael recebem aviso. Rafael acha que
conectou um numero novo; Izael nao entende por que mensagens pararam.

## Decisao proposta

Adicionar checagem de duplicata em `embedded_signup_exchange` antes do
`create_channel`. Se ja existe canal **ativo** com o mesmo
`phone_number_id`, retornar **HTTP 409 Conflict** com mensagem
estruturada.

```python
existing = get_channel_by_phone_id(phone_number_id)
if existing and existing.get("is_active"):
    raise HTTPException(
        status_code=409,
        detail={
            "code": "channel_already_connected",
            "message": (
                f"Numero {display_phone} ja esta conectado ao canal "
                f"#{existing['id']} (owner: {existing.get('owner_user_id')})."
            ),
            "existing_channel_id": existing["id"],
            "existing_owner_user_id": existing.get("owner_user_id"),
            "hint": (
                "Para trocar o owner, use o endpoint de transferencia "
                "de ownership. Para refazer o signup do zero, desative "
                "o canal existente primeiro."
            ),
        },
    )
```

O frontend deve interpretar o 409 e oferecer ao admin dois caminhos:

1. **Transferir ownership** — endpoint dedicado (a criar) que reusa o
   canal `#1`, troca apenas `owner_user_id` + `access_token` + dispara
   novo subscribe_apps com o token do solicitante. Util quando o
   operador saiu da empresa e supervisor quer migrar o numero.
2. **Cancelar** — admin entendeu que escolheu o numero errado e refaz.

Discussao pendente com a equipe: se a opcao (1) deve ser exposta na
mesma UI do signup, em uma tela separada de "gerenciar canais", ou
exigir confirmacao adicional (ex.: codigo enviado pro WhatsApp do
owner atual).

## Alternativas consideradas

1. **Manter como esta (overwrite silencioso).**
   - Pro: zero codigo novo.
   - Con: bug operacional grave + violacao do principio de
     responsabilizacao LGPD (auditoria fica mentirosa porque mensagens
     do Izael ficam atribuidas ao Rafael).

2. **409 sem caminho de migracao.**
   - Pro: simples, defensivo, resolve o cenario de erro humano.
   - Con: nao cobre o caso legitimo de troca de owner (operador
     saiu da empresa, supervisor precisa assumir).

3. **409 + endpoint dedicado de transferencia de ownership (proposta).**
   - Pro: cobre erro humano + caso legitimo. Reusa canal existente
     (preserva historico de conversations, audit_log, transfer_log).
   - Con: codigo adicional (endpoint de transferencia, UI nova). Exige
     decisao sobre fluxo de confirmacao para nao virar back-door.

4. **Permitir multiplos canais coex pro mesmo numero (cada operador
   tem seu canal).**
   - Pro: cada operador opera "seu" coex independente.
   - Con: nao faz sentido tecnico — Meta entrega webhook UMA VEZ por
     numero, entao so um canal pode receber. Multiplos canais ativos
     criariam corrida pela primeira chamada `subscribed_apps`.
     **Rejeitada.**

## Consequencias

### Positivas
- Falha **explicita** em vez de silenciosa.
- Auditoria volta a ser confiavel (mensagens do Izael nunca mais
  ficam com `operator_id=Rafael` por engano).
- Caminho legitimo de troca de owner ganha endpoint proprio, com
  audit_log dedicado (`CHANNEL_OWNERSHIP_TRANSFERRED`).
- Compliance LGPD: principio da responsabilizacao (art. 6º X) volta
  a ser cumprido — quem fez o que e rastreavel.

### Negativas / pontos de atencao
- Frontend precisa tratar o 409 com mensagem clara (sem isso o admin
  ve so "erro 409" e nao entende).
- Endpoint de transferencia precisa decidir como invalidar o token
  antigo do owner anterior (Meta nao oferece endpoint para revogar
  token de coex; depende do operador antigo desinstalar o Business
  app ou expirar naturalmente).
- Migracao: pode existir cenario em prod onde 2 canais com o mesmo
  `phone_number_id` ja coexistem (esperar nao, mas vale validar).
  Script de verificacao antes do deploy:
  ```python
  # Detecta canais duplicados por phone_number_id
  from channel_service import get_all_active_channels
  by_phone = {}
  for ch in get_all_active_channels():
      pid = (ch.get("phone_number_id") or "").strip()
      if not pid: continue
      by_phone.setdefault(pid, []).append(ch["id"])
  duplicates = {p: ids for p, ids in by_phone.items() if len(ids) > 1}
  ```

## Itens dependentes (fora do escopo desta ADR)

- Definir UX do frontend para o 409 (modal? toast? card persistente?).
- Definir UX do endpoint de transferencia de ownership (auto-trigger
  no 409? Tela separada em "Configuracoes do canal"?).
- Auditoria de quem **lia** mensagens (snapshot Firestore listener nao
  passa por endpoint, entao nao gera audit_log hoje). Relevante porque
  o modelo coex compartilhado amplia a superficie de leitura.
