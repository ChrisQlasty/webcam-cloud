# webcam-cloud
---
![AWS](https://img.shields.io/badge/cloud-AWS-FF9900?logo=amazon-aws&logoColor=white)
![Terraform](https://img.shields.io/badge/IaC-Terraform-623CE4?logo=terraform&logoColor=white)
![YouTube](https://img.shields.io/badge/Stream%20from-YouTube-red?logo=youtube&logoColor=white)
![Docker](https://img.shields.io/badge/Container-Docker-2496ED?logo=docker&logoColor=white)
![PyTorch](https://img.shields.io/badge/ML-PyTorch-EE4C2C?logo=pytorch&logoColor=white)
![uv (Astral)](https://img.shields.io/badge/Package%20Manager-uv-0095FF?logo=python&logoColor=white)
![Ruff](https://img.shields.io/badge/linter-ruff-007ACC?logo=python&logoColor=white)
![Pre-commit](https://img.shields.io/badge/linter-pre--commit-FE6F6F)
![Makefile](https://img.shields.io/badge/build-Makefile-6E6E6E)

# Usage

## Prerequisities:

1. AWS IAM user set up
2. Configured AWS CLI client (```aws configure```)
3. Environmental variables, eg.:

```
ENV_STREAM_URL="https://www.youtube.com/watch?v=abcdefghijk"
TF_VAR_region="eu-north-1"
TF_VAR_input_bucket="input_bucket"
TF_VAR_processed_bucket="processed_bucket"
TF_VAR_aws_account_id="012345678910"
TF_VAR_lambda1="lambda_1_name"
TF_VAR_lambda2="lambda_2_name"
TF_VAR_db_table="table_name"
```


## Setting everything up

### Step 0: Create your bucket
```
aws s3 mb s3://$TF_VAR_input_bucket --region $TF_VAR_region
```

### Step 1: Build Your Docker Image
```
cd webcam-cloud
docker build --build-arg ENV_STREAM_URL=$ENV_STREAM_URL \
             --build-arg TF_VAR_region=$TF_VAR_region \
             --build-arg TF_VAR_input_bucket=$TF_VAR_input_bucket \
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
aws ecr create-repository --repository-name webcam_cloud_lambda --region $TF_VAR_region
```

### Step 3: Authenticate Docker to AWS ECR
```
echo $(aws ecr get-login-password --region $TF_VAR_region) | docker login --username AWS --password-stdin $TF_VAR_aws_account_id.dkr.ecr.$TF_VAR_region.amazonaws.com
```

### Step 4: Tag Your Docker Image for ECR
```
docker tag webcam_cloud_lambda:latest $TF_VAR_aws_account_id.dkr.ecr.$TF_VAR_region.amazonaws.com/webcam_cloud_lambda:latest
```

### Step 5: Push the Docker Image to ECR
```
docker push $TF_VAR_aws_account_id.dkr.ecr.$TF_VAR_region.amazonaws.com/webcam_cloud_lambda:latest

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
