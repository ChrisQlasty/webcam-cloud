
# Usage

Set environmental variables:

```ENV_STREAM_URL="https://???/live.m3u8?a???"```

Build Docker image:
```
cd webcam-cloud
docker build --build-arg ENV_STREAM_URL=$ENV_STREAM_URL \
             --target=production \
             -f Dockerfile \
             -t webcamcloud-2s:latest .
```


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
