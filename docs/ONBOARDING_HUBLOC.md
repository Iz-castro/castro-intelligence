# Onboarding Hubloc — Passo a passo operacional

Guia para colocar a Hubloc em produção no Castro Intelligence CRM. Cobre
três cenários: A) Hubloc usa WABA própria já em Cloud API standard;
B) Hubloc usa WABA própria em modo Coexistence (depende da aprovação
da Meta no segundo App Review); C) Plano B — criar app Meta separado
em modo Development se a Meta demorar.

## 1. Pré-requisitos da Meta

Antes de qualquer ação no CRM, valide na conta Meta:

### 1.1. Business Manager (Meta Business Suite)

- [ ] Hubloc tem Business Portfolio criado em [business.facebook.com](https://business.facebook.com).
- [ ] Verificação da empresa (Business Verification) **concluída e aprovada**.
- [ ] Pelo menos 1 admin vinculado ao portfólio.

### 1.2. WhatsApp Business Account (WABA)

- [ ] WABA criada e vinculada ao portfólio Hubloc.
- [ ] Número de telefone cadastrado e verificado na WABA.
- [ ] **Método de pagamento configurado** em
      [business.facebook.com/wa/manage/billing](https://business.facebook.com/wa/manage/billing/).
      Sem isso, templates de marketing/utility falham com erro `#131009`.
      O CRM mostra banner vermelho automaticamente quando este passo
      está pendente.
- [ ] Display name do número está no padrão Hubloc (visível em
      "Phone Numbers" do WhatsApp Manager).

### 1.3. Templates aprovados

- [ ] Template "boas-vindas" (utility) aprovado.
- [ ] Template "confirmação de visita" (utility) aprovado.
- [ ] Template "reabertura de atendimento" (utility) aprovado.
- [ ] Template "newsletter" (marketing) aprovado, se for fazer broadcast.
- [ ] Template `hello_world` é o padrão de teste (já existe em qualquer WABA).

### 1.4. App Castro Intelligence CRM (provider)

- [ ] App `1434723791183375` em modo **Live** após aprovação do App Review da Meta.
- [ ] Permissões Advanced Access aprovadas em
      `whatsapp_business_messaging`, `whatsapp_business_management`,
      `business_management`. **Status atual: aguardando 2ª submissão.**

## 2. Setup no CRM (cenário A — Cloud API standard)

Pré-condição: WABA Hubloc já em Cloud API standard (número está na nuvem,
não no celular).

### 2.1. Conectar a WABA via Embedded Signup

1. Logar no CRM como admin (`teste1@centralloc.com.br` ou outro admin).
2. Menu superior → engrenagem → **WhatsApp Coexistence**.
3. Clicar em **"Iniciar conexão"** no popup.
4. No popup da Meta:
   - Logar com conta Facebook do admin Hubloc (precisa ter role
     no portfólio Hubloc).
   - Escolher portfólio Hubloc.
   - Escolher **"Criar uma conta WhatsApp Business"** (cenário A) — não
     "Conectar um app do WhatsApp Business" (cenário B Coexistence).
   - Selecionar WABA + número Hubloc existentes.
   - Concluir.
5. Backend cria o canal automaticamente. Verificar em
   **Configurações > Administração > Canais**.

### 2.2. Cadastrar setores (departamentos)

1. **Configurações > Administração > Setores**.
2. Criar:
   - **Vendas** (bot_key: `comercial`)
   - **Financeiro** (bot_key: `financeiro`)
   - **Pós-venda / Atendimento** (bot_key: `sac`)
   - **Administrativo** (bot_key: `administrativo`)
3. Definir setor padrão (Vendas geralmente).

### 2.3. Cadastrar operadores

1. **Configurações > Administração > Usuários**.
2. Para cada corretor/atendente:
   - Email (deve estar autorizado em `ALLOWED_FIREBASE_EMAILS` ou domínio).
   - Display name.
   - Setor.
   - Role (operador, supervisor ou admin).
3. Operador faz primeiro login → completa perfil.

### 2.4. Configurar bot (opcional)

Se quiserem usar o bot de qualificação:
1. **Configurações > Administração > Bot** (ou via Firestore direto, se UI
   ainda não existe).
2. Habilitar bot no setting global.
3. Mapear `bot_setor` → `department_id` para encaminhamento automático.

### 2.5. Mensagens rápidas

Cada operador configura suas próprias em **Configurações > Mensagens rápidas**.
Atalhos sugeridos:
- `/visita` → "Olá, podemos confirmar sua visita ao imóvel para {data}?"
- `/parabens` → "Parabéns pela compra! Seu corretor é {nome}."
- `/financ` → "Encaminho ao financeiro para tratar pagamento."

### 2.6. Smoke test pré go-live

- [ ] Mande WhatsApp do seu celular pessoal pro número Hubloc.
- [ ] Mensagem aparece no CRM (view "Novos").
- [ ] Operador clica "Assumir" e responde.
- [ ] Resposta chega no celular.
- [ ] Operador transfere pra outro setor.
- [ ] Operador destinatário vê na view "Meus".
- [ ] Operador envia template aprovado.
- [ ] Cliente recebe template formatado.
- [ ] Admin abre dashboard, vê métricas.

## 3. Setup cenário B — Coexistence (aguarda aprovação Meta)

**Status atual: bloqueado.** App Castro Intelligence CRM precisa de
Advanced Access em `whatsapp_business_messaging` e
`whatsapp_business_management` antes do popup de Coexistence aceitar
qualquer número.

Quando aprovar, fluxo será:
1. Admin Hubloc clica "Conectar WhatsApp" → escolhe **"Conectar um app
   do WhatsApp Business"** no popup.
2. Escaneia QR no WhatsApp Business app no celular OU seleciona número
   já vinculado.
3. Backend recebe code, finaliza signup, cria canal coexistence.
4. CRM passa a sincronizar com o celular: mensagens enviadas pelo app
   móvel aparecem no CRM (`smb_message_echoes`) e vice-versa.

## 4. Plano B — App Meta separado em modo Development

Se aprovação da Meta demorar muito (>2 semanas), pode-se criar **um
segundo app Meta dedicado à Hubloc em modo Development** para
desbloquear operação imediata via Cloud API standard.

### Por que funciona

Em modo Development, qualquer operação requer que o usuário tenha role
no app (Admin/Developer/Tester). Como Hubloc é um cliente fechado
(operadores conhecidos), todos podem ser cadastrados como Tester no
app dev. Não precisa Advanced Access.

### Setup do app dev

1. Em [developers.facebook.com](https://developers.facebook.com), criar
   novo app **"Hubloc CRM Dev"** vinculado ao portfólio Hubloc (não
   Castro Intelligence).
2. Ativar produto WhatsApp Business Platform.
3. Em **Roles > Roles**, adicionar email Facebook de cada operador
   Hubloc como Tester.
4. Em **App Review > Permissions and Features**, manter Standard
   Access (suficiente para usuários com role).
5. Configurar webhook URL → mesmo do CRM atual:
   `https://castro-crm-XXX.run.app/webhook`.
6. Configurar verify token → mesmo `WHATSAPP_VERIFY_TOKEN` do .env.
7. Assinar webhook fields: `messages`, `message_template_status_update`,
   `account_update`.

### Configuração no CRM

O CRM aceita múltiplos canais simultaneamente. Adicionar no Cloud Run
um secret/var **`WHATSAPP_TOKEN_HUBLOC`** com o token do app dev.
Criar canal manualmente no Firestore via Admin SDK (script) ou via
Embedded Signup do app dev (que funciona normal em Standard Access para
testers).

### Limitações

- Modo Development só funciona para usuários **adicionados como Role
  no app**. Não escala para clientes externos.
- Limites de mensagens são reduzidos (~50/dia em algumas categorias).
- **Apenas solução temporária** até aprovação do app principal.

## 5. Após aprovação da Meta (migração final)

Quando o App Review aprovar Advanced Access:

1. **Promover staging → prod**: deploy das mudanças da Fase 2 (multi-tenant
   + sub-threads) na revisão `castro-crm` de produção.
2. **Wipe controlado** do Firestore prod, recriando tenant Hubloc com
   subcoleção `tenants/hubloc/...`. Cuidado para preservar dados em
   trânsito de operações ativas.
3. **Re-onboarding** dos canais Hubloc — pelo CRM novo, escolhendo
   Coexistence quando fizer sentido (corretores que querem manter número
   no celular) ou Cloud API quando for número da empresa.
4. **Comunicar operadores** sobre o novo fluxo (badges de canal na lista
   de conversas, painel de perfil unificado, etc).

## 6. Checklist final pré go-live

- [ ] WABA Hubloc com método de pagamento ativo.
- [ ] Templates aprovados na Meta (mínimo 3 utility).
- [ ] CRM em prod com canal Hubloc cadastrado e ativo.
- [ ] Pelo menos 4 operadores cadastrados (Vendas/Financeiro/Suporte/Admin).
- [ ] Setores configurados.
- [ ] Webhook respondendo (testar via curl signed manual).
- [ ] Smoke test bidirectional (mensagem chega + sai).
- [ ] Template send funcionando.
- [ ] Banner billing-aware NÃO aparece (significa pagamento ok).
- [ ] Dashboard admin abre sem erros.
- [ ] Bot configurado (se for usar) ou desabilitado explicitamente.

## 7. Suporte

- **Bug operacional**: GitHub Issues do repo
  [castro-intelligence](https://github.com/Iz-castro/castro-intelligence).
- **Bug Meta** (templates rejeitados, billing, etc): WhatsApp Manager
  da Hubloc → suporte direto Meta.
- **Onboarding técnico**: Castro Intelligence — `contato@castrointelligence.com.br`.
