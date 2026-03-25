# Guia de Implementacao - Faster Whisper no CRM

## Objetivo

Migrar a transcricao de audio do projeto de `Google Cloud Speech-to-Text` para `Faster Whisper`, usando como base o modulo enviado em `transcription (1).py`.

A meta desta migracao e:

- remover custo por minuto de API de STT
- manter o mesmo fluxo da aplicacao
- preservar os endpoints e o frontend atuais
- rodar a transcricao dentro do proprio servico no Cloud Run

## Premissas Deste Guia

Este guia assume o seguinte contexto do projeto:

- backend em FastAPI
- deploy em Cloud Run
- `ffmpeg` ja instalado no container
- `main.py`, `webhook.py` e a UI ja consomem a interface atual do modulo `transcription_service.py`
- o arquivo enviado foi escrito para ser uma substituicao quase direta do modulo atual

Este guia parte do modelo inicial abaixo, porque e exatamente o padrao do arquivo enviado:

- `WHISPER_MODEL_SIZE=base`
- `WHISPER_DEVICE=cpu`
- `WHISPER_COMPUTE_TYPE=int8`

## Arquivos Afetados

Arquivos que entram diretamente nesta migracao:

- `transcription_service.py`
- `requirements.txt`
- `.env.example`
- `start.example.ps1`
- `deploy.ps1`
- `deploy.sh`

Arquivos que provavelmente nao precisam mudar na primeira fase:

- `main.py`
- `webhook.py`
- frontend

## Como o Modulo Enviado se Encaixa no Sistema

O arquivo enviado preserva as tres funcoes usadas hoje pelo sistema:

- `init_speech_client()`
- `get_speech_client()`
- `transcribe_audio_bytes(...)`

Isso e importante porque o restante da aplicacao ja chama essa interface:

- `main.py` inicializa o servico no startup
- `main.py` usa a transcricao on-demand em `/api/wa/messages/{id}/transcribe`
- `webhook.py` usa a transcricao automatica em audios inbound

Na pratica, isso significa que a migracao pode ser feita sem mudar a API publica nem o frontend. O ponto principal e trocar a implementacao interna do modulo.

## O Que o Modulo Faz

O modulo enviado trabalha assim:

1. carrega o modelo Whisper uma vez em memoria
2. recebe os bytes do audio
3. converte o arquivo para WAV 16kHz mono via `ffmpeg`
4. chama `model.transcribe(...)`
5. junta os segmentos retornados em uma string unica
6. devolve a transcricao para o fluxo atual

Compatibilidades preservadas:

- continua aceitando `media_mime`
- continua aceitando `language_code`
- continua aceitando `timeout_s`, mesmo que ele nao controle a inferencia do Whisper
- continua retornando `""` em caso de falha

## Alteracoes Necessarias

### 1. Dependencias Python

Hoje o `requirements.txt` contem o cliente do Google Speech, mas nao contem `faster-whisper`.

Alteracao recomendada:

- adicionar `faster-whisper`
- manter `google-cloud-speech` apenas durante a janela de migracao, se quiser rollback rapido
- depois da validacao, remover `google-cloud-speech` se ele nao for mais usado

Exemplo de direcao:

```txt
faster-whisper
```

Observacao:

- o projeto ja instala `ffmpeg` no `Dockerfile`, entao essa parte da cadeia ja esta coberta

### 2. Substituir o Modulo de Transcricao

O caminho mais simples e substituir o conteudo de `transcription_service.py` pela implementacao do arquivo enviado.

Abordagem recomendada:

1. copiar a logica de `transcription (1).py`
2. salvar no arquivo `transcription_service.py`
3. manter o nome das funcoes publicas

Com isso, `main.py` e `webhook.py` continuam funcionando sem alteracao estrutural.

### 3. Variaveis de Ambiente

Adicionar as variaveis abaixo ao runtime:

```env
FEATURE_AUDIO_TRANSCRIPTION=true
STT_LANGUAGE_CODE=pt-BR
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

Notas:

- `STT_LANGUAGE_CODE=pt-BR` continua util porque o modulo converte isso para `pt`
- `FEATURE_AUDIO_TRANSCRIPTION` continua sendo a chave que liga o recurso
- o arquivo enviado foi pensado para iniciar bem em CPU com `base + int8`

Arquivos que precisam refletir essas variaveis:

- `.env.example`
- `start.example.ps1`
- `deploy.ps1`
- `deploy.sh`

Importante:

- hoje os scripts de deploy enviam para o Cloud Run uma lista fechada de env vars
- portanto, nao basta definir `WHISPER_MODEL_SIZE`, `WHISPER_DEVICE` e `WHISPER_COMPUTE_TYPE` no ambiente local
- essas tres variaveis tambem precisam ser adicionadas nas listas `envVars` de `deploy.ps1` e `ENV_VARS` de `deploy.sh`

### 4. Credenciais Google

Com Faster Whisper, a transcricao nao depende mais do Google Speech-to-Text.

Isso significa:

- a permissao `roles/speech.client` deixa de ser necessaria para STT
- `GOOGLE_APPLICATION_CREDENTIALS` deixa de ser necessario para a transcricao

Mas cuidado:

- isso nao significa remover credenciais Google do projeto inteiro
- Firestore, Storage, Firebase Admin e outras partes ainda podem depender da identidade do ambiente

Observacao importante sobre os scripts atuais:

- hoje `deploy.ps1` e `deploy.sh` ainda associam `FEATURE_AUDIO_TRANSCRIPTION=true` com a ativacao do `speech.googleapis.com`
- eles tambem concedem `roles/speech.client` quando a feature esta ligada

No rollout minimo, isso pode continuar assim sem quebrar nada, apenas com permissao sobrando.

No rollout recomendado, vale desacoplar:

- `FEATURE_AUDIO_TRANSCRIPTION=true` para ligar a funcionalidade
- um provider explicito, por exemplo `AUDIO_TRANSCRIPTION_PROVIDER=faster_whisper`

Com isso, o deploy deixa de tratar toda transcricao como Google Speech.

## Ajustes Recomendados no Cloud Run

### Configuracao Inicial Recomendada

Para o primeiro rollout em producao, a recomendacao e:

- `--cpu 1`
- `--memory 1Gi`
- `--concurrency 1`
- `--min-instances 0`
- `--max-instances 3`
- `--timeout 300`

Motivo:

- `base + cpu + int8` e um bom ponto de partida em custo e estabilidade
- `1Gi` da folga maior para o modelo, Python, buffers temporarios e conversao WAV
- `concurrency 1` evita disputa forte de CPU entre transcricoes simultaneas

### Quando Subir para 2Gi

Considere `2Gi` se aparecer algum destes sinais:

- OOM no Cloud Run
- latencia muito alta durante picos
- necessidade de testar modelo maior no futuro
- varias transcricoes sequenciais elevando uso de memoria

Para `base` em CPU, `1Gi` e o ponto de partida mais equilibrado. `2Gi` e mais uma margem de seguranca do que uma necessidade imediata.

## Cold Start

Com `min-instances=0`, o Cloud Run pode encerrar todas as instancias quando o servico fica ocioso.

Quando chega uma nova requisicao depois disso, a plataforma precisa:

1. subir o container
2. iniciar a app FastAPI
3. carregar o modelo Whisper em memoria
4. eventualmente baixar o modelo se ele ainda nao estiver presente no filesystem daquela instancia

Impacto pratico:

- a primeira transcricao apos idle tende a ser mais lenta
- o tempo de startup entra no tempo ativo cobrado
- como o filesystem local do Cloud Run e efemero, novas instancias podem repetir esse aquecimento

Se a experiencia do operador ficar ruim por causa da primeira transcricao, existem dois caminhos:

- manter `min-instances=0` e aceitar cold start em troca de menor custo
- subir para `min-instances=1` e pagar por uma instancia aquecida

## Concurrency

O deploy atual usa `concurrency=40`, mas isso nao e o ideal para transcricao local em CPU.

Motivos:

- o container sobe com um unico worker Uvicorn
- a transcricao e trabalho intensivo de CPU
- `ffmpeg` e o proprio Whisper competem por recursos
- muitas requisicoes simultaneas na mesma instancia podem elevar muito a latencia

Para esse caso, a recomendacao pratica e:

- comecar com `concurrency=1`
- testar `concurrency=2` apenas se a carga real justificar
- evitar `concurrency` alta enquanto o modelo rodar em CPU

## Passo a Passo de Implementacao

### Etapa 1 - Preparar a aplicacao

1. adicionar `faster-whisper` ao `requirements.txt`
2. substituir `transcription_service.py` pela logica do modulo enviado
3. manter o resto do backend sem alteracoes estruturais

### Etapa 2 - Configurar runtime

Definir no ambiente:

```env
FEATURE_AUDIO_TRANSCRIPTION=true
STT_LANGUAGE_CODE=pt-BR
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

### Etapa 3 - Ajustar o deploy

Revisar o deploy para iniciar com:

```txt
--memory 1Gi
--cpu 1
--concurrency 1
--min-instances 0
--max-instances 3
--timeout 300
```

Garantir tambem que o Cloud Run receba:

```env
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

### Etapa 4 - Fazer deploy

Executar o fluxo normal de deploy do projeto com `deploy.ps1` ou `deploy.sh`.

### Etapa 5 - Validar logs

Conferir se aparece log equivalente a:

```txt
Faster Whisper carregado | modelo=base | device=cpu | compute=int8
```

Se isso nao aparecer, a inicializacao do modelo falhou.

## Checklist de Validacao

Depois do deploy, validar os cenarios abaixo:

- abrir a aplicacao sem erro no startup
- transcrever um audio existente pelo botao `Transcrever`
- receber um audio inbound e confirmar transcricao automatica
- verificar se o texto aparece na bolha do chat
- validar audios em `ogg`, `webm`, `mp3` e `mp4`, se fizerem parte do fluxo real
- confirmar que o campo `transcription` esta sendo salvo corretamente
- acompanhar memoria e latencia no Cloud Run

## Observabilidade Recomendada

Monitorar estes sinais apos a entrada em producao:

- tempo medio de transcricao
- memoria por instancia
- numero de cold starts
- erros de `ffmpeg`
- erros de carregamento do modelo
- erros de timeout
- falhas de transcricao com retorno vazio

Se houver aumento de latencia ou instabilidade:

- subir memoria para `2Gi`
- reduzir concorrencia
- considerar `min-instances=1`

## Riscos Conhecidos

### Download do Modelo no Primeiro Uso

Se o modelo nao vier empacotado na imagem, a primeira instancia pode gastar tempo adicional baixando pesos do modelo.

Isso afeta:

- latencia inicial
- tempo ativo cobrado
- previsibilidade do startup

### Filesystem Efemero

O cache local da instancia nao deve ser tratado como persistente.

Isso significa que:

- uma nova instancia pode precisar aquecer de novo
- o modelo nao deve depender de armazenamento local permanente

### Disputa de CPU

Em CPU, transcricao simultanea demais tende a degradar a experiencia mais do que ajudar.

Por isso o valor inicial recomendado e `concurrency=1`.

## Estrategia de Rollout

Recomendacao de rollout em duas fases:

### Fase 1 - Troca controlada

- manter a feature ligada apenas no ambiente de validacao
- usar `base + cpu + int8`
- Cloud Run com `1Gi` e `concurrency=1`

### Fase 2 - Producao

- liberar para producao
- acompanhar logs e metricas por alguns dias
- subir para `2Gi` apenas se os dados mostrarem necessidade

## Estrategia de Rollback

Se houver problema em producao:

1. restaurar o conteudo anterior de `transcription_service.py`
2. voltar para `google-cloud-speech`
3. redeployar a revisao anterior

Como a interface publica do modulo e a mesma, o rollback e simples.

## Recomendacao Final

Para este projeto, o melhor ponto de partida e:

- Faster Whisper
- modelo `base`
- `cpu`
- `int8`
- Cloud Run com `1Gi`
- `concurrency=1`
- `min-instances=0`

Esse setup equilibra:

- custo baixo
- risco tecnico controlado
- pouca mudanca de arquitetura
- chance alta de funcionar bem com o fluxo atual

Se a equipe quiser latencia mais previsivel, o primeiro ajuste a testar e:

- `min-instances=1`

Se a equipe quiser mais folga operacional, o segundo ajuste a testar e:

- `memory=2Gi`
