# This is a legacy Dockerfile in terms of this project as is not compatible with AWS' Lambda
# ---- Stage BUILDER ----
FROM python:3.10-bookworm AS builder

# install uv
ADD https://astral.sh/uv/install.sh /install.sh
RUN chmod -R 655 /install.sh && /install.sh && rm /install.sh

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /webcam-cloud

COPY ./pyproject.toml .

# install no-dev dependencies quickly with uv
RUN uv sync --no-dev

    
# ---- Stage PRODUCTION ----
FROM python:3.10-slim-bookworm AS production

# use and set ENV_STREAM_URL
ARG ENV_STREAM_URL
ARG ENV_REGION_NAME
ARG ENV_BUCKET_NAME
ENV ENV_STREAM_URL=$ENV_STREAM_URL
ENV ENV_REGION_NAME=$ENV_REGION_NAME
ENV ENV_BUCKET_NAME=$ENV_BUCKET_NAME

WORKDIR /webcam-cloud
COPY . .

# use just installed dependencies from the builder stage
COPY --from=builder /webcam-cloud/.venv .venv

# Set up environment variables for production
ENV PATH="/webcam-cloud/.venv/bin:$PATH"

CMD ["python", "-m", "modules.webcam_retriever"]