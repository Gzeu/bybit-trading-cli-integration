FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create logs dir
RUN mkdir -p logs

# Non-root user
RUN useradd -m commander
USER commander

# Health check: verify imports load cleanly
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "from skills.bybit_account_commander.src.snapshot import build_snapshot; print('OK')" || exit 1

ENTRYPOINT ["python", "main.py"]
CMD ["--config", "config.yaml", "--interval", "300"]
