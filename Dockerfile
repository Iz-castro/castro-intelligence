FROM node:22-slim AS frontend-build

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-baixa o modelo Faster Whisper para dentro da imagem. Sem isto, cada
# instancia em cold-start baixava o modelo do HuggingFace Hub em runtime
# (dentro do startup event do FastAPI), bloqueando o bind na porta 8080 e
# estourando o startup probe do Cloud Run (DEADLINE_EXCEEDED) -> cascata de
# 500/503/429. Incidente 2026-06-03. Mudar WHISPER_MODEL_SIZE exige rebuild.
ARG WHISPER_MODEL_SIZE=base
ENV WHISPER_MODEL_SIZE=${WHISPER_MODEL_SIZE} \
    HF_HOME=/opt/hf-cache
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL_SIZE}', device='cpu', compute_type='int8')"
# A partir daqui o runtime usa apenas o cache embutido — nunca acessa a rede
# do HF (evita HEAD requests lentos/rate-limited mesmo com o modelo em cache).
ENV HF_HUB_OFFLINE=1

COPY . .
COPY --from=frontend-build /frontend_dist ./frontend_dist

RUN mkdir -p /app/media/images /app/media/audio /app/media/video \
    /app/media/documents /app/media/stickers /app/media/avatars /app/logs

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
