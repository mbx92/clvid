FROM node:24.15.0-bookworm-slim@sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d AS javascript
FROM javascript AS remotion-build
WORKDIR /workspace/services/remotion
COPY services/remotion/package.json services/remotion/package-lock.json ./
RUN npm ci
RUN npm run browser:install \
    && browser="$(find node_modules/.remotion -type f -name headless_shell | head -n 1)" \
    && if [ -z "$browser" ]; then browser="$(find node_modules/.remotion -type f -name chrome-headless-shell | head -n 1)"; fi \
    && test -n "$browser" && ln -s "$browser" chrome-headless-shell
COPY services/remotion/ ./
COPY services/backend/fonts/NotoSans-Regular.ttf ../backend/fonts/NotoSans-Regular.ttf
COPY services/backend/fonts/OFL.txt ../backend/fonts/OFL.txt
RUN npm run build

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
ENV REMOTION_BROWSER_EXECUTABLE=/opt/remotion/chrome-headless-shell
ENV LD_LIBRARY_PATH="/app/.venv/lib/python3.12/site-packages/nvidia/cublas/lib:/app/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib:/app/.venv/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib"
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 ca-certificates espeak-ng \
    libnss3 libdbus-1-3 libatk1.0-0 libgbm1 libasound2 libxrandr2 libxkbcommon0 \
    libxfixes3 libxcomposite1 libxdamage1 libatk-bridge2.0-0 libpango-1.0-0 libcairo2 libcups2 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.13.6 \
    && groupadd --gid 10001 clipper && useradd --uid 10001 --gid clipper --create-home clipper \
    && mkdir -p /app /data/media /data/whisper /opt/story-local && chown -R clipper:clipper /app /data /opt/story-local
WORKDIR /app
COPY --chown=clipper:clipper services/backend/pyproject.toml services/backend/uv.lock ./
COPY --chown=clipper:clipper infra/story-local-requirements.txt /opt/story-local-requirements.txt
USER clipper
ARG WITH_CUDA=0
ARG WITH_LOCAL_STUDIO=0
RUN if [ "$WITH_LOCAL_STUDIO" = "1" ]; then \
      uv venv /opt/story-local --python /usr/local/bin/python && \
      if [ "$WITH_CUDA" = "1" ]; then torch_index=https://download.pytorch.org/whl/cu126; else torch_index=https://download.pytorch.org/whl/cpu; fi && \
      uv pip install --no-cache --python /opt/story-local/bin/python torch==2.8.0 --index-url "$torch_index" && \
      uv pip install --no-cache --python /opt/story-local/bin/python -r /opt/story-local-requirements.txt; \
    fi
RUN --mount=type=cache,id=clipper-uv,target=/home/clipper/.cache/uv,uid=10001,gid=10001,sharing=locked \
    if [ "$WITH_CUDA" = "1" ]; then uv sync --frozen --no-dev --extra transcription --extra gpu --no-install-project; else uv sync --frozen --no-dev --extra transcription --no-install-project; fi
COPY --chown=clipper:clipper services/backend/ ./
RUN --mount=type=cache,id=clipper-uv,target=/home/clipper/.cache/uv,uid=10001,gid=10001,sharing=locked \
    if [ "$WITH_CUDA" = "1" ]; then uv sync --frozen --no-dev --extra transcription --extra gpu; else uv sync --frozen --no-dev --extra transcription; fi
COPY --from=remotion-build --chown=clipper:clipper /workspace/services/remotion /opt/remotion
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
