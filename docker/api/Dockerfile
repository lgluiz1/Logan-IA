FROM python:3.11-slim-bookworm

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.110" \
    "uvicorn[standard]>=0.27" \
    "redis[hiredis]>=5.0" \
    "pyyaml>=6.0"

COPY api/ /app/api/
COPY core/ /app/core/
COPY services/ /app/services/

RUN mkdir -p /app/db

EXPOSE 8080

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
