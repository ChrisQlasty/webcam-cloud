# ---- Stage BUILDER ----
FROM python:3.10-bookworm AS builder

# install uv
ADD https://astral.sh/uv/install.sh /install.sh
RUN chmod -R 655 /install.sh && /install.sh && rm /install.sh

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /webcam-cloud

COPY ./pyproject.toml .

# install dependencies quickly with uv
RUN uv sync --no-dev

# ---- Stage FFMPEG ----
FROM jrottenberg/ffmpeg:snapshot-alpine as ffmpeg
    
# ---- Stage PRODUCTION ----
FROM python:3.10-slim-bookworm AS production

# Copy ffmpeg binaries
COPY --from=ffmpeg /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg /usr/local/bin/ffprobe /usr/local/bin/ffprobe

# Make sure they're executable (usually already are)
RUN chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe

WORKDIR /webcam-cloud
COPY . .

# use just installed dependencies
COPY --from=builder /webcam-cloud/.venv .venv

CMD ["python", "modules/webcam-retriever.py"]