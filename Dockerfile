FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8765 \
    DATA_DIR=/data \
    UPLOAD_DIR=/uploads \
    PUBLISHING_ENABLED=false
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && useradd --create-home --uid 10001 publishflow
COPY backend/ ./backend/
COPY --from=frontend /web/dist ./frontend/dist
COPY LICENSE README.md .env.example ./
RUN mkdir -p /app/data /app/uploads /data /uploads \
    && chown -R publishflow:publishflow /app/data /app/uploads /data /uploads
USER publishflow
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3)" || exit 1
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host \"$APP_HOST\" --port \"$APP_PORT\""]
