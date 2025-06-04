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
3. Quota > 0 for batch transform job for selected machine type (eg. ml.m5.large) [see Service Quotas @ AWS]
4. Colima (for Mac) and Docker installed
5. Terraform installed
6. uv installed, .venv activated and synced (```uv sync --only-dev```)
7. Environmental variables, eg.:

```
ENV_STREAM_URL="https://www.youtube.com/watch?v=abcdefghijk"
TF_VAR_region="eu-north-1"
TF_VAR_input_bucket="input-bucket"
TF_VAR_processed_bucket="processed-bucket"
TF_VAR_models_bucket="models-bucket"
TF_VAR_aws_account_id="012345678910"
TF_VAR_lambda1="lambda-1-name"
TF_VAR_lambda2="lambda-2-name"
TF_VAR_db_table="table-name"
TF_VAR_obj_det_image="obj-det-image"
TF_VAR_lambda2_image="lambda2-image"
TF_VAR_obj_det_model="object-det-model"
```


## Setting everything up

1. Prepare SageMaker inference model
```
# Create bucket to store model
aws s3api create-bucket --bucket ${TF_VAR_models_bucket} --region ${TF_VAR_region} --create-bucket-configuration LocationConstraint=${TF_VAR_region} && \

make prep_inference_model
```

2. Build Endpoint Docker image and push to ECR
```
# Authenticate Docker to AWS ECR
echo $(aws ecr get-login-password --region $TF_VAR_region) | docker login --username AWS --password-stdin $TF_VAR_aws_account_id.dkr.ecr.$TF_VAR_region.amazonaws.com && \  

echo $(aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 763104351884.dkr.ecr.us-east-1.amazonaws.com) && \  

make prep_ecr_repo docker_image_name=$TF_VAR_obj_det_image && \
make prep_endpoint_image Dockerfile_name=Dockerfile_Endpoint docker_image_name=$TF_VAR_obj_det_image
```

3. Build Lambda2 Docker image and push to ECR
```
# Authenticate Docker to AWS ECR
echo $(aws ecr get-login-password --region $TF_VAR_region) | docker login --username AWS --password-stdin $TF_VAR_aws_account_id.dkr.ecr.$TF_VAR_region.amazonaws.com && \  

make prep_ecr_repo docker_image_name=$TF_VAR_lambda2_image && \
make prep_endpoint_image Dockerfile_name=Dockerfile_Lambda docker_image_name=$TF_VAR_lambda2_image
```

4. Prepare code for AWS Lambda
```
make prep_lambda
```

5. Set up services with Terraform
```
make aws_apply
```

6. Run frames grabbing and initialize project
```
uv sync --extra grabber
python modules/grabber.py
```

Issues:
---
I. Custom Docker image for SageMaker batch transform job
 - packing code to model.tar.gz is mandatory [GitHub issue](https://github.com/aws/sagemaker-pytorch-inference-toolkit/issues/61#issuecomment-665980501)
