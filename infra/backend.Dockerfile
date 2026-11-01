FROM node:24.15.0-bookworm-slim@sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d AS javascript
FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
ENV LD_LIBRARY_PATH="/app/.venv/lib/python3.12/site-packages/nvidia/cublas/lib:/app/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib:/app/.venv/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib"
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.13.6 \
    && groupadd --gid 10001 clipper && useradd --uid 10001 --gid clipper --create-home clipper \
    && mkdir -p /app /data/media /data/whisper && chown -R clipper:clipper /app /data
WORKDIR /app
COPY --chown=clipper:clipper services/backend/pyproject.toml services/backend/uv.lock ./
USER clipper
ARG WITH_CUDA=0
RUN --mount=type=cache,id=clipper-uv,target=/home/clipper/.cache/uv,uid=10001,gid=10001,sharing=locked \
    if [ "$WITH_CUDA" = "1" ]; then uv sync --frozen --no-dev --extra transcription --extra gpu --no-install-project; else uv sync --frozen --no-dev --extra transcription --no-install-project; fi
COPY --chown=clipper:clipper services/backend/ ./
RUN --mount=type=cache,id=clipper-uv,target=/home/clipper/.cache/uv,uid=10001,gid=10001,sharing=locked \
    if [ "$WITH_CUDA" = "1" ]; then uv sync --frozen --no-dev --extra transcription --extra gpu; else uv sync --frozen --no-dev --extra transcription; fi
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
