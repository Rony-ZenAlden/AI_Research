FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/.hf_cache \
    TRANSFORMERS_OFFLINE=0

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        # WeasyPrint runtime deps (Pango / Cairo / GDK-PixBuf + a default font)
        libpango-1.0-0 libpangoft2-1.0-0 libcairo2 \
        libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only PyTorch first (~200MB instead of ~800MB GPU build).
# sentence-transformers, listed in requirements.txt, will see torch is already
# installed and won't try to pull the GPU version.
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

COPY . /app

RUN mkdir -p /app/staticfiles /app/media /app/.hf_cache /app/exports

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "NeuroSeek_AI.asgi:application"]
