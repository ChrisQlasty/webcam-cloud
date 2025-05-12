
# Usage

## Prerequisities:

1. Environmental variables, eg.:

```
ENV_STREAM_URL="https://???/live.m3u8?a???"
ENV_REGION_NAME="eu-north-1"
```

2. Configure your AWS client
```
aws configure
```
... and continue setting it up.

## Setting everything up

Build Docker image:
```
cd webcam-cloud
docker build --build-arg ENV_STREAM_URL=$ENV_STREAM_URL \
             --build-arg ENV_REGION_NAME=$ENV_REGION_NAME \
             --target=production \
             -f Dockerfile \
             -t webcamcloud-2s:latest . \
             --no-cache
```

Test it locally with your credentials:
```
docker run -v ~/.aws:/root/.aws -i -t webcamcloud-2s:latest
```


---
---
---

1. Installation
```
# please install uv first
uv sync
source .venv/bin/activate
pre-commit install 
```

2. Required env variables
```
ENV_STREAM_URL="https://?????/live.m3u8??????"
```

# Setting up description
1. Project initialization with uv  
```uv init webcam-cloud```
2. Add ruff as default formatter  
```uv add --dev ruff```
