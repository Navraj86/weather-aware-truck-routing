# --- Build the React app -------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Django API + static frontend ----------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
# Pre-compress the bundle; WhiteNoise serves the .gz files to browsers that accept them.
RUN python -m whitenoise.compress /app/frontend/dist
RUN useradd --create-home app
USER app
EXPOSE 8000
# One process with threads: the work is I/O-bound (third-party APIs) and a single
# process shares the in-memory forecast cache across all requests.
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 120 --access-logfile -"]
