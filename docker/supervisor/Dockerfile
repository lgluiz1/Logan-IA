FROM python:3.11-slim-bookworm

WORKDIR /app

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[all]" 2>/dev/null || \
    pip install --no-cache-dir \
    "redis[hiredis]>=5.0" \
    "pyyaml>=6.0" \
    "aiohttp>=3.9" \
    "obd>=0.7" \
    "pyserial-asyncio>=0.6" \
    "prometheus-client>=0.20"

# Copia código
COPY core/ /app/core/
COPY drivers/ /app/drivers/
COPY workers/ /app/workers/
COPY services/ /app/services/
COPY config/ /app/config/
COPY data/ /app/data/
COPY scripts/ /app/scripts/
COPY main.py /app/

# Cria diretórios
RUN mkdir -p /app/db /app/logs

CMD ["python", "-u", "main.py"]
