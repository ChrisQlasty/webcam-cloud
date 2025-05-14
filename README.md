
# Usage

## Prerequisities:

1. AWS IAM user set up
2. Configured AWS CLI client (```aws configure```)
3. Environmental variables, eg.:

```
ENV_STREAM_URL="https://www.youtube.com/watch?v=abcdefghijk"
ENV_REGION_NAME="eu-north-1"
ENV_BUCKET_NAME="webcam-live"
AWS_ACCOUNT_ID="012345678910"
```


## Setting everything up

### Step 0: Create your bucket
```
aws s3 mb s3://$ENV_BUCKET_NAME --region $ENV_REGION_NAME
```

### Step 1: Build Your Docker Image
```
cd webcam-cloud
docker build --build-arg ENV_STREAM_URL=$ENV_STREAM_URL \
             --build-arg ENV_REGION_NAME=$ENV_REGION_NAME \
             --build-arg ENV_BUCKET_NAME=$ENV_BUCKET_NAME \
             --target=production \
             -f Dockerfile_Lambda \
             -t webcam_cloud_lambda:latest . \
             --no-cache
```

Test it locally with your credentials to simulate Lambda:
```
docker run -v ~/.aws:/root/.aws -p 9000:8080 webcam_cloud_lambda:latest
```
and in separate terminal window run:
```
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{}'
```

### Step 2: Create an ECR Repository
```
aws ecr create-repository --repository-name webcam_cloud_lambda --region $ENV_REGION_NAME
```

### Step 3: Authenticate Docker to AWS ECR
```
echo $(aws ecr get-login-password --region $ENV_REGION_NAME) | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$ENV_REGION_NAME.amazonaws.com
```

### Step 4: Tag Your Docker Image for ECR
```
docker tag webcam_cloud_lambda:latest $AWS_ACCOUNT_ID.dkr.ecr.$ENV_REGION_NAME.amazonaws.com/webcam_cloud_lambda:latest

```

### Step 5: Push the Docker Image to ECR
```
docker push $AWS_ACCOUNT_ID.dkr.ecr.$ENV_REGION_NAME.amazonaws.com/webcam_cloud_lambda:latest

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
