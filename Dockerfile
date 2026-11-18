# Aryx worker image — 12-factor, slim Python base. Portable across
# ECS / EKS / OCI (orchestrator chosen at rollout, not build time).
# License: Business Source License 1.1 (see /LICENSE in the source repo).
FROM python:3.13-slim

LABEL org.opencontainers.image.title="Aryx Lite" \
      org.opencontainers.image.vendor="Giggso Inc." \
      org.opencontainers.image.licenses="BUSL-1.1" \
      org.opencontainers.image.source="https://github.com/giggsoinc/aryx"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# tesseract-ocr: pytesseract is only a wrapper — without the binary, OCR of
# images embedded in pptx/pdf/docx silently returns "" (errors are swallowed).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# PII gate model, baked in at build time. Presidio otherwise downloads a
# ~400 MB model on the FIRST document ingest (see aryx/pipeline/pii.py), which
# stalls/fails uploads on slow or offline hosts. Must match ARYX_PII_SPACY_MODEL.
RUN python -m spacy download en_core_web_sm

COPY src/ ./src/

CMD ["python", "-m", "aryx"]
