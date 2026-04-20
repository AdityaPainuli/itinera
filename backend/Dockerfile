# Portable backend image — used by Fly.io and any Docker-based host.
# Render uses the native Python builder (see /render.yaml) and ignores this file.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first so layer caches across code edits.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Most PaaS providers (Fly, Railway, Cloud Run) inject $PORT. Default to 8000
# for local `docker run` use.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
