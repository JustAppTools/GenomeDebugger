FROM node:22-alpine AS interface
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=10000 \
    GENOMEDEBUGGER_RESOURCES=/app GENOMEDEBUGGER_STATIC_DIR=/app/frontend/dist \
    GENOMEDEBUGGER_DEPLOYMENT=public-free GENOMEDEBUGGER_MAX_DB_MB=16
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && useradd --create-home --uid 10001 genome
COPY backend/app/ /app/backend/app/
COPY fixtures/ /app/fixtures/
COPY scripts/serve-hosted.py /app/scripts/serve-hosted.py
COPY --from=interface /build/frontend/dist/ /app/frontend/dist/
USER genome
EXPOSE 10000
CMD ["python", "/app/scripts/serve-hosted.py"]
