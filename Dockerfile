FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies for PostgreSQL, WeasyPrint (Cairo, Pango) and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ML-9: CPU-only torch + sentence-transformers, and the USER-bge-m3 weights baked into the image
# so EMBEDDINGS=local needs no network at runtime (about 2.3 GB).
ENV HF_HOME=/opt/hf-cache
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install "sentence-transformers>=3.0" \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('deepvk/USER-bge-m3', device='cpu')"

COPY . .

RUN chmod +x /app/docker-entrypoint.sh 2>/dev/null || true

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
