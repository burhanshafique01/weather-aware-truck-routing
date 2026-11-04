# --- 1. Build the React app -------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Django API that also serves the built app ---------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_DEBUG=false

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
COPY --from=web /app/frontend/dist /app/frontend/dist
RUN python manage.py collectstatic --noinput

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# Threads let one worker overlap the slow upstream calls (routing, weather).
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 8 --timeout 120 --access-logfile -"]
