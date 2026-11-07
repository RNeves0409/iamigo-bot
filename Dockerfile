# syntax=docker/dockerfile:1
# iAmigo — Bot de lembretes Telegram (runtime Docker)
#
# Build:   docker build -t iamigo:bot .
# Run:     docker compose up -d          (compose no repositório raiz)
#
# Ambiente (via .env, copiar de .env.example):
#   TELEGRAM_BOT_TOKEN   token do bot (@BotFather)
#   TELEGRAM_USER_ID     seu user id no Telegram
#   OLLAMA_BASE_URL      automaticamente http://ollama:11434 (rede compose)
#   OLLAMA_MODEL         modelo Ollama a carregar (ex.: llama3.1:8b)
#   IAMIGO_DB_PATH       caminho do SQLite dentro do container
#                        (default /var/lib/iamigo/agenda.db, volume iamigo-data)
#
# O banco é montado em /var/lib/iamigo (volume iamigo-data), como no deploy
# produção. O caminho é também o padrão de db/connection.py.

FROM python:3.14-slim

WORKDIR /app

# Dependências do sistema (apenas o que o runtime/healthcheck precisa)
RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Ambiente virtual (requirements.txt vazio: só módulos padrão do Python)
RUN python -m venv /opt/iamigo/venv
ENV PATH="/opt/iamigo/venv/bin:$PATH"

# Código-fonte
COPY . /app

# Dados persistentes: volume iamigo-data vinculado em /var/lib/iamigo
RUN mkdir -p /var/lib/iamigo

WORKDIR /app

# Healthcheck leve: banco SQLite acessível dentro do container
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=120s \
    CMD python3 -c "import sqlite3,sys; sqlite3.connect('/var/lib/iamigo/agenda.db').execute('SELECT 1'); sys.exit(0)" \
        || exit 1

# Logs para stderr (capturado pelo Docker com json-file)
CMD ["python", "main.py"]
