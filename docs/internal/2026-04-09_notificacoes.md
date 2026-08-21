# 09/04/2026 - Notificacoes Sonoras

> Atualizacao 2026-08-21: este e o comportamento ORIGINAL do som. Hoje o beep/alarme
> so toca sobre as caixas Novos+Meus visiveis (camada ao vivo, unread da THREAD) e
> `wa_contacts.unread_count` passou a ser DERIVADO das threads — ver
> `docs/decisions/0011-unread-derivado-das-threads-e-sons-por-caixa.md` e
> `docs/internal/2026-08-21-diagnostico-alarme-sonoro.md`.

## Funcionalidades implementadas

### 1. Beep de nova mensagem (todos os usuarios)
- Quando o total de mensagens nao lidas aumenta, um beep curto (880Hz, 0.3s) toca automaticamente
- Usa Web Audio API como fallback, ou som personalizado configurado pelo admin
- Controlado pelo flag `notification_sound_enabled` em system_settings

### 2. Alarme repetitivo (departamentos configurados)
- Alarme sonoro (dois tons 660/880Hz) toca a cada 30 segundos enquanto houver mensagens nao visualizadas ha mais de N minutos
- Ativo apenas para operadores dos departamentos selecionados pelo admin
- O alarme para automaticamente quando todas as mensagens sao visualizadas
- Controlado por: `alarm_enabled`, `alarm_threshold_minutes`, `alarm_department_ids`

### 3. Painel admin de notificacoes
- Nova aba "Notificacoes" no modal de Administracao
- Configuracoes disponiveis:
  - Habilitar/desabilitar som de notificacao
  - Habilitar/desabilitar alarme
  - Tempo limite sem resposta (em minutos, padrao: 5)
  - Selecao de departamentos que recebem alarme
  - Upload de som personalizado para notificacao (MP3/WAV/OGG, max 500KB)
  - Upload de som personalizado para alarme
  - Botao "Testar" para ouvir os sons
  - Botao "Usar padrao" para remover som personalizado

## Arquivos modificados

### Backend
- `database_firestore.py`: Novos campos em `_DEFAULT_SYSTEM_SETTINGS` (notification_sound_enabled, alarm_enabled, alarm_threshold_minutes, alarm_department_ids, alarm_sound_path, notification_sound_path)
- `main.py`: Novo endpoint `POST /api/admin/upload-alarm-sound` para upload de sons, import de `_write_media_bytes`
- `media.py`: Subdiretorio `sounds` adicionado ao `ensure_media_dir()`

### Frontend
- `types.ts`: Campos de notificacao adicionados ao `SystemSettings`
- `CrmContext.tsx`: Dois novos useEffects (beep + alarme), refs para controle de audio
- `App.tsx`: Componente `NotificationsTab`, nova aba no `AdminSettingsModal`, import de `sendForm`

## Bugs encontrados durante analise

1. **Race condition no assume counter** (main.py:1266-1276) - sem transacao atomica entre check e decrement
2. **Import morto** (main.py:1280) - `fs_utcnow` importado mas nunca usado
3. **Snapshot sem filtro de visibilidade** (CrmContext.tsx:587-592) - operadores veem todos os contatos no modo snapshot
