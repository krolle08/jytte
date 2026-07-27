FROM python:3.12-slim

WORKDIR /jytte

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docs ./docs

ENV PYTHONUNBUFFERED=1 \
    JYTTE_DATA_DIR=/data \
    JYTTE_TASKS_PATH=/data/obsidian-tasks \
    JYTTE_DB_PATH=/data/jytte.db

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
