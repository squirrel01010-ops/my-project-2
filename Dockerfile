# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 PORT=8080 DB_PATH=/data/bot.db BACKUP_DIR=/data/backups \
    REQUIRE_DISCORD=1
WORKDIR /app
COPY requirements.lock ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.lock; else pip install --no-cache-dir -r requirements.lock; fi
COPY game_motion.py app.py core.py games.py poker.py social.py social_bot.py bot.py backup.py run.py runtime_health.py ./
COPY public/ ./public/
RUN mkdir -p /data && chmod 700 /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 CMD ["python", "runtime_health.py"]
CMD ["python", "run.py"]
