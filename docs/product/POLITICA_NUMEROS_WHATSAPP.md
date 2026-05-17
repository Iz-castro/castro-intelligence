# Política de uso de números WhatsApp no CRM

**Última atualização:** 2026-05-15
**Aplica-se a:** todos os clientes (tenants) do Castro Intelligence CRM
**Tenant de referência atual:** Hubloc

---

## Regra geral

Operadores e supervisores **só podem onboardar no CRM números
WhatsApp da empresa (WABA corporativa)**. Não é permitido vincular
número WhatsApp pessoal — seja celular pessoal do colaborador, seja
linha pré-paga não cadastrada no Business Manager da empresa.

Esta restrição vale tanto pro fluxo **standard** (Cloud API com número
exclusivo do bot) quanto pro fluxo **coexistence** (WhatsApp Business
app do operador conectado via Embedded Signup).

---

## Motivação

### 1. Proteção do titular (LGPD)

O CRM registra cada mensagem com `channel_owner_user_id` (dono físico
do número) e `sender_user_id` (quem digitou). Quando um operador deixa
a empresa, o histórico precisa migrar pra outro colaborador sem
ambiguidade sobre titularidade dos dados pessoais dos clientes.

Se o número for pessoal, a empresa perde a base legal pra reter o
histórico — porque o titular do canal não é mais funcionário, e o
número não pertencia à empresa em primeiro lugar.

### 2. Continuidade operacional

Número da empresa fica no Business Manager da Hubloc, com método de
pagamento, WABA cadastrada e templates aprovados pela Meta. Mesmo
quando o colaborador sai, o número permanece — basta transferir a
conta WhatsApp Business app pro próximo operador.

Número pessoal vai embora com o colaborador. Cliente final perde
histórico, atendimentos em aberto ficam órfãos.

### 3. Auditoria e responsabilidade

Toda mensagem enviada via CRM aparece como tendo sido enviada pelo
**número da empresa**. Se o número for pessoal, isso confunde o
cliente final ("quem me mandou foi a empresa ou foi o Fulano?") e
dilui a responsabilidade jurídica em caso de disputa.

### 4. Compliance Meta

Política de uso da WhatsApp Business Platform exige que o número
esteja registrado em conta WABA com identidade verificada. Números
pessoais usados como canal de atendimento corporativo violam ToS.

---

## O que é permitido

- ✅ Número WhatsApp corporativo da Hubloc (WABA da empresa).
- ✅ Linha celular dedicada à equipe comercial, cadastrada no Business
  Manager da Hubloc com responsável legal definido.
- ✅ Múltiplos números WABA da Hubloc atendendo departamentos
  diferentes (vendas, locação, pós-venda).

## O que NÃO é permitido

- ❌ Celular pessoal do colaborador (mesmo que ele use pra trabalho
  hoje).
- ❌ Número de outra empresa do grupo que não seja a Hubloc.
- ❌ Pré-pago não cadastrado no Business Manager.
- ❌ Número fixo (landline) — WhatsApp Business não oferece migração
  oficial a partir disso.

---

## Procedimento de onboarding de número novo

1. Hubloc cadastra a linha no nome da CNPJ no Business Manager
   próprio.
2. Linha é vinculada à WABA da Hubloc.
3. Operador instala o WhatsApp Business app no aparelho corporativo
   (ou usa Cloud API direto, sem app).
4. Admin do CRM faz Embedded Signup pelo CRM → autoriza Castro
   Intelligence (Tech Provider) → canal aparece como `channel_id #N`.
5. Mensagens passam a fluir nos dois sentidos (CRM ↔ WhatsApp app)
   automaticamente.

---

## Em caso de descumprimento

Se um número pessoal for onboardado por engano:

1. Remover o canal pelo CRM (admin) ou solicitar suporte.
2. O histórico das mensagens já recebidas permanece no Firestore mas
   o canal não recebe nem envia novas mensagens.
3. Operador deve criar pedido formal pra empresa ativar linha
   corporativa.

Não é possível "reverter" um número onboardado: depois que entra,
fica como histórico. Mas dá pra desativar o canal pra parar o fluxo.

---

## Implicações no produto

- Telas de onboarding (Embedded Signup) devem exibir aviso explícito:
  "Use apenas números WhatsApp da empresa".
- Setup checklist `/setup` (Fase 3.5 pendente) inclui passo
  "Confirmar que número pertence à empresa".
- Admin do CRM tem visibilidade pra desativar canal a qualquer
  momento via UI.
