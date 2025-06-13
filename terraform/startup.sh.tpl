#!/bin/bash
exec > >(tee /var/log/user-data.log | logger -t user-data) 2>&1

IMAGE="${aws_account_id}.dkr.ecr.${region}.amazonaws.com/${dash_image}:latest"
RUN_PARAMS="--name dash_app -d -p 8050:8050"
ECR_LOGIN="aws ecr get-login-password --region ${region} | docker login --username AWS --password-stdin ${aws_account_id}.dkr.ecr.${region}.amazonaws.com"

yum update -y
amazon-linux-extras install docker -y
service docker start
systemctl enable docker
usermod -a -G docker ec2-user

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Login to ECR
eval "$ECR_LOGIN"

# Pull and run the Dash app
docker pull "$IMAGE"
docker run $RUN_PARAMS "$IMAGE"

# Add cron job to pull & run on reboot
(
  crontab -l 2>/dev/null;
  echo "@reboot bash -c 'until docker info > /dev/null 2>&1; do sleep 5; done; \
    aws ecr get-login-password --region ${region} | docker login --username AWS --password-stdin ${aws_account_id}.dkr.ecr.${region}.amazonaws.com && \
    docker pull ${aws_account_id}.dkr.ecr.${region}.amazonaws.com/${dash_image}:latest && \
    docker run -d -p 8050:8050 ${aws_account_id}.dkr.ecr.${region}.amazonaws.com/${dash_image}:latest'"
) | crontab -
