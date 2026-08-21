# 09/04/2026 - Bug Fixes + Bot + Coexistence

> Atualizacao 2026-08-21: (1) o filtro de visibilidade por "mesmo departamento" foi
> REVERTIDO — operador comum ve so proprios + pool sem dono, NUNCA por `department_id`
> (CLAUDE.md > Invariantes); (2) a liberacao do Embedded Signup/coexistence para todos
> os operadores foi revertida em 12/04/2026, voltando a admin/supervisor (ver
> `2026-04-12.md` §3); (3) o MENU de setores do bot builtin foi removido em
> 2026-07-24 (o estado legado `ask_sector` segue honrado no codigo).

## Bug Fixes

### 1. Race condition no assume counter (CORRIGIDO)
- `database_firestore.py`: `decrement_assume_counter` e `increment_assume_counter` agora usam `@firestore.transactional` para garantir atomicidade
- Novo import: `from google.cloud import firestore`

### 2. Import morto (CORRIGIDO)
- `main.py`: Movido `from firestore_common import document as fs_document, utcnow as fs_utcnow` para o topo do modulo
- Removidos os dois imports locais redundantes dentro de funcoes

### 3. Snapshot sem filtro de visibilidade (CORRIGIDO)
- `firestore.rules`: Regra de `wa_contacts` agora usa filtro por role:
  - Admin/supervisor: veem todos
  - Operadores: veem contatos atribuidos a si, sem atribuicao, ou do mesmo departamento
  - Usa campo `assigned_to_uid` (ja gravado pelo backend)

## Bot de Atendimento (NOVO)

### Arquivo: `bot_service.py`
Adaptado do `modelo bot.py` para funcionar como state machine via WhatsApp:
- Estados: `ask_name` -> `ask_equipment` -> `ask_sector` -> done
- Deteccao inteligente: nome, equipamento, setor por numero ou palavra-chave
- Mapeia setores do bot para departamentos do CRM automaticamente
- Estado armazenado em Firestore: `bot_states/{contact_id}`
- Ao finalizar, grava resumo no contato e mensagem de sistema

### Integracao no webhook
- `webhook.py`: Apos salvar mensagem inbound, se bot ativo e contato sem operador, processa pelo bot
- Nova funcao `_send_bot_reply()`: envia resposta do bot via WhatsApp API e salva no banco

### Frontend
- Nova view "Bot" no NavBar (visivel apenas para admin/supervisor quando bot ativo)
- Contatos no bot ficam separados dos "Novos"
- Quando bot finaliza, contato move para "Novos" (bot_completed = true)
- Quando bot desabilitado, tudo cai direto em "Novos"

### Configuracao admin
- Toggle "Habilitar bot" na aba Sistema do menu Administracao
- Campo `bot_enabled` em system_settings

## Coexistence para Operadores (LIBERADO)

### Mudancas
- `App.tsx`: Botao "WhatsApp Coexistence" visivel para todos (era so admin)
- `App.tsx`: WhatsAppSignupModal renderiza para todos (era so admin)
- `main.py`: Endpoints `/api/admin/embedded-signup/config` e `/exchange` liberados para todos os usuarios autenticados (eram admin/supervisor)

### O que ja funcionava
- Operadores ja podiam ver e usar canais coexistence atribuidos a eles (via `get_channels_for_user`)
- Contatos de outros operadores via coexistence continuam ocultos no Equipe para operadores normais (regra de privacidade mantida)

## Arquivos modificados
- `database_firestore.py` - transacoes atomicas, bot_enabled em settings
- `main.py` - imports limpos, coexistence liberado
- `webhook.py` - integracao do bot, funcao _send_bot_reply
- `bot_service.py` - NOVO: servico de bot
- `media.py` - subdir sounds
- `firestore.rules` - filtro de visibilidade
- `frontend/src/types.ts` - bot_enabled, bot_completed, bot_setor_nome, ActiveView
- `frontend/src/context/CrmContext.tsx` - botContacts, botUnread, filtragem
- `frontend/src/App.tsx` - NavBar Bot, toggle admin, coexistence liberado
- `frontend/src/utils/normalization.ts` - bot_completed, bot_setor_nome
