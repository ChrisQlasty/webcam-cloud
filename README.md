
# Usage

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
