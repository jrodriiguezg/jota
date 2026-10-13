FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    JOTA_STT_ENGINE=faster_whisper \
    JOTA_ORB_ENABLED=false \
    JOTA_TRAY=false \
    JOTA_MODELS_DIR=/app/models

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    ffmpeg \
    curl \
    git \
    libgomp1 \
    libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        fastapi>=0.110.0 \
        "uvicorn[standard]>=0.28.0" \
        pydantic \
        httpx \
        websockets \
        python-multipart \
        faster-whisper \
        requests \
        zeroconf \
        docker \
        soundfile \
        numpy \
        scipy \
        cryptography>=42.0.0 \
        pyyaml>=6.0

RUN pip install --no-cache-dir llama-cpp-python \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu || \
    CMAKE_ARGS="-DGGML_AVX2=ON -DGGML_FMA=ON" pip install --no-cache-dir llama-cpp-python

RUN pip install --no-cache-dir piper-tts || true

COPY pyproject.toml /app/
COPY jota /app/jota
COPY bridge /app/bridge

RUN pip install --no-cache-dir -e . --no-deps

RUN mkdir -p /app/data /app/models

EXPOSE 8765

CMD ["uvicorn", "bridge.server:app", "--host", "0.0.0.0", "--port", "8765"]
