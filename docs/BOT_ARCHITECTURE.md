# Arquitetura do Bot — Guia para Implementacao Futura

## Visao Geral

O CRM suporta um canal "standard" com flag `is_bot_enabled=true`.
Novos leads que chegam neste canal ficam com `assigned_to=null` e
`qualification="novo"`, aparecendo na fila "Novos" para os operadores.

O bot devera interceptar essas mensagens antes dos operadores e
responder automaticamente ate que o lead solicite atendimento humano
ou o bot decida encaminhar para um departamento.

## Como o Bot se Conecta

### Opcao A: Servico externo (recomendado)

1. Criar um servico separado que escuta a colecao Firestore `castro_crm_wa_messages`
   via snapshot listener.
2. Filtrar mensagens onde:
   - `direction == "inbound"`
   - O contato associado tem `assigned_to == null`
   - O canal tem `is_bot_enabled == true` (consultar `castro_crm_channels`)
3. Processar a mensagem com IA/regras e responder via `POST /api/wa/send` ou
   diretamente pela Graph API usando as credenciais do canal.
4. Quando o bot decidir encaminhar, chamar:
   - `POST /api/wa/assume/{contact_id}` (auto-atribuir a um operador)
   - Ou atualizar `department_id` no contato para rotear ao departamento correto

### Opcao B: Integrar diretamente no webhook

1. No `webhook.py`, apos `save_wa_message`, verificar se o contato nao tem operador
   e o canal tem `is_bot_enabled`.
2. Chamar uma funcao `bot_process_message(contact, message)`.
3. A funcao responde via Graph API e decide se deve encaminhar.

## Campos Relevantes

### Canal (colecao `channels`)
- `is_bot_enabled: bool` — indica se o bot opera neste canal
- `default_department_id: int` — departamento padrao para novos leads

### Contato (colecao `wa_contacts`)
- `assigned_to: null` — contato na fila do bot (sem operador)
- `assigned_to: int` — contato assumido por operador (bot para de responder)
- `qualification: "novo"` — lead novo, candidato a atendimento do bot
- `department_id: int` — departamento para onde o bot roteou o lead

## Fluxo Tipico

```
Lead envia mensagem
  → Webhook salva mensagem com assigned_to=null
  → Bot detecta mensagem (Firestore listener ou webhook hook)
  → Bot responde com menu/opcoes
  → Lead escolhe "Falar com Financeiro"
  → Bot atualiza department_id do contato para "Financeiro"
  → Bot opcionalmente chama assume para atribuir a um operador do setor
  → Operador ve o lead em "Meus Atendimentos"
```

## Endpoint "Devolver ao Bot"

Quando admin/supervisor quer devolver um contato para o bot:
- `POST /api/wa/contact/{contact_id}/return-to-bot`
- Reseta `assigned_to=null`, `qualification="novo"`
- O bot volta a responder para este contato

## Notas de Implementacao

- Use a colecao `castro_crm_channels` para descobrir token e phone_number_id do canal
- O `channel_service.py` tem funcoes prontas: `get_channel()`, `get_send_credentials()`
- Para enviar mensagens como bot, use `save_wa_message()` com `operator_id=None`
- O campo `visibility` pode ser usado para msgs do bot que nao devem aparecer no CRM
