# Coexistence - Plano de Recomeço Limpo

## Estado atual (apos limpeza)
- Portfolio **Castro Intelligence** (provider, verificado, tem o App)
- Portfolio **Castro Operacoes WhatsApp** (cliente, verificado, SEM WABAs)
- Numero `+55 31 7195-7758` ativo no WhatsApp Business App no celular
- App Castro Intelligence CRM com `business_management` ativado
- System User `userfuncionapf` com token no portfolio Castro Intelligence
- Embedded Signup implementado no CRM com `featureType: "coexistence"`
- Cloud Run com 1GB de memoria

## O que aprendemos

1. O Coexistence via Embedded Signup provavelmente requer o app **publicado como Tech Provider**
2. A opcao "Adicionar um novo numero" sempre da erro "phone already registered" em modo dev
3. A opcao "Usar somente um nome de exibicao" cria numero virtual (serve para teste/publicacao)
4. Pre-verified numbers requer System User do MESMO portfolio da WABA
5. WABAs criadas pelo Embedded Signup ficam no portfolio do PROVIDER, nao do cliente

## Plano passo a passo

### Fase 1: Publicar o App (desbloqueia Coexistence)

1. Fazer Embedded Signup com "Usar somente um nome de exibicao" ou "Adicionar mais tarde"
2. Gravar video do fluxo para submissao
3. Completar a analise do app em developers.facebook.com
4. Publicar o app

### Fase 2: Configurar ambiente limpo

1. No portfolio **Castro Operacoes WhatsApp**:
   - NAO criar WABA manualmente
   - O Embedded Signup cria automaticamente

2. Garantir que o numero NAO esta em nenhuma WABA
   - Verificar em TODOS os portfolios

3. Garantir celular pronto:
   - WhatsApp Business App versao 2.24.17+
   - Nome de exibicao: "Castro Operacoes"
   - Numero ativo com uso organico

### Fase 3: Testar Coexistence (apos app publicado)

1. CRM > engrenagem > WhatsApp Coexistence > Iniciar Embedded Signup
2. Login com admin do portfolio Castro Operacoes WhatsApp
3. Selecionar portfolio: Castro Operacoes WhatsApp
4. WABA: Criar nova
5. Numero: Adicionar novo > +5531971957758
6. Deve aparecer opcao de QR Code (Coexistence)
7. Escanear QR Code no celular
8. Atualizar .env com novos valores

### Fase 4: Implementar webhooks

Pedir ao Claude para implementar:
- `smb_message_echoes`
- `smb_app_state_sync`
- `history`
