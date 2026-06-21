# --- Stage 1: build the React SPA -------------------------------------------
FROM node:20-slim AS web
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig.json tsconfig.node.json ./
COPY public ./public
COPY src ./src
RUN npm run build            # -> /web/dist

# --- Stage 2: Python runtime serving API + SPA ------------------------------
FROM python:3.12-slim AS app
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PILOT_DB_PATH=/data/pilot.db \
    APP_DB_PATH=/data/app.db

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app
COPY config ./config
COPY docs ./docs
COPY scripts ./scripts
COPY entrypoint.sh ./
COPY --from=web /web/dist ./dist

RUN chmod +x entrypoint.sh && mkdir -p /data
EXPOSE 8000
CMD ["./entrypoint.sh"]
