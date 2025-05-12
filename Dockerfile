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

    
# ---- Stage PRODUCTION ----
FROM python:3.10-slim-bookworm AS production

RUN apt-get -y update
RUN apt-get -y upgrade
RUN apt-get install -y ffmpeg

ARG ENV_STREAM_URL
ENV ENV_STREAM_URL=$ENV_STREAM_URL

WORKDIR /webcam-cloud
COPY . .

# use just installed dependencies
COPY --from=builder /webcam-cloud/.venv .venv

CMD ["python", "modules/webcam-retriever.py"]