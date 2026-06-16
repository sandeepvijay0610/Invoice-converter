# ---- Stage 1: builder -----------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt


# ---- Stage 2: runtime -----------------------------------------------
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="//opt/venv/bin:$PATH"

RUN useradd --create-home --shell /bin/bash appuser
RUN mkdir -p /tmp/ingestor && chown appuser:appuser /tmp/ingestor
ENV OUTPUT_DIR=/tmp/ingestor

WORKDIR /app
COPY --chown=appuser:appuser pipeline/ ./pipeline/
COPY --chown=appuser:appuser main.py ./

USER appuser

# FIX #15: Healthcheck now imports only lightweight config instead of the
# full orchestrator (which would trigger InferenceWorker init and OpenAI
# client construction on every health probe).
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from pipeline.config import MODEL_NAME; print('OK')"

ENTRYPOINT ["python", "main.py"]
