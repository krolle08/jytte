FROM python:3.12-slim

WORKDIR /jytte

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docs ./docs
# View preferences, not application code: config/ai_visibility.yml says
# which /ai overlap pairs have already been ruled on. Baked in so the
# image is self-contained, and bind-mounted in compose so editing the
# file takes effect without a rebuild.
COPY config ./config
# Tests live in the image because that is where the dependencies are:
# aiosqlite and friends are not installed on the host, so the salary and
# transfer suites can only run here.
COPY tests ./tests

ENV PYTHONUNBUFFERED=1 \
    JYTTE_DATA_DIR=/data \
    JYTTE_TASKS_PATH=/data/obsidian-tasks \
    JYTTE_DB_PATH=/data/jytte.db

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
