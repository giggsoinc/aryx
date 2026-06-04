# Aryx worker image — 12-factor, slim Python base. Portable across
# ECS / EKS / OCI (orchestrator chosen at rollout, not build time).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Streamlit theme config — must live at /app/.streamlit so the UI process
# (started from WORKDIR=/app) picks it up instead of falling back to the
# browser's prefers-color-scheme (which renders dark and kills sidebar
# contrast against our light gradient).
COPY .streamlit ./.streamlit

CMD ["python", "-m", "aryx"]
