prep_inference_model:
	: ### Step 1: Dump dependencies from specific group from pyproject.toml
	tomlq -r '.project."optional-dependencies".endpoint[]' pyproject.toml > requirements_temp.txt
	: ### Step 2: Remove torch>= from the requirements_temp.txt as is already installed in the base image
	grep -v 'torch>=' requirements_temp.txt > requirements_endpoint.txt 	
	rm requirements_temp.txt
	cd data && \
	: ### Step 3: Download the YOLOv11n model weights
	wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt && \
	: ### Step 4: Create a directory structure for the model (see issues in Readme)
	mkdir -p my_model/code && \
	mv yolo11n.pt my_model/ && \
	cp ../modules/inference.py my_model/code/ && \
	cp ../requirements_endpoint.txt my_model/requirements_endpoint.txt && \
	tar -czvf model.tar.gz -C my_model . && \
	: ### Step 5: Upload the model to S3 bucket and clean up
	aws s3 cp model.tar.gz s3://${TF_VAR_models_bucket}/model_ul/ && \
	rm model.tar.gz && rm -rf my_model

prep_ecr_repo:
	aws ecr create-repository --repository-name ${docker_image_name} --region ${TF_VAR_region}

prep_endpoint_image:	
	: ### Step 1: Build Your Docker Image
	docker buildx build --platform=linux/amd64 -f $(Dockerfile_name) -t ${docker_image_name}:latest . && \
	: ### Step 2: Tag Your Docker Image for ECR
	docker tag ${docker_image_name}:latest ${TF_VAR_aws_account_id}.dkr.ecr.${TF_VAR_region}.amazonaws.com/${docker_image_name}:latest && \
	: ### Step 3: Push the Docker Image to ECR
	docker push ${TF_VAR_aws_account_id}.dkr.ecr.${TF_VAR_region}.amazonaws.com/${docker_image_name}:latest


prep_lambda:
	mkdir -p cloud_resources
	zip cloud_resources/lambda1.zip modules/lambda1.py

aws_apply:
	cd terraform && \
	terraform validate && \
	terraform plan && \
	terraform apply

aws_destroy:
	aws s3 rm s3://${TF_VAR_input_bucket} --recursive && \
	aws s3 rm s3://${TF_VAR_processed_bucket} --recursive && \
	cd terraform && \
	terraform destroy -auto-approve 