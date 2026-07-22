FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "kokoro" \
    "fastapi>=0.110" \
    "uvicorn[standard]>=0.27" \
    "soundfile>=0.12" \
    "numpy>=1.26"

COPY kokoro_server.py /app/

RUN mkdir -p /app/models /app/cache

EXPOSE 8880

CMD ["python", "-u", "kokoro_server.py"]
