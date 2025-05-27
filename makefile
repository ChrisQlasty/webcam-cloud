zip_lambdas:
	mkdir -p cloud_resources
	zip cloud_resources/lambda1.zip modules/lambda1.py
	zip cloud_resources/lambda2.zip modules/lambda2.py

# take models bucket from env
prep_model:
	#uv pip compile pyproject.toml --extra endpoint -o requirements_temp.txt
	tomlq -r '.project."optional-dependencies".endpoint[]' pyproject.toml > requirements_temp.txt
	grep -v 'torch>=' requirements_temp.txt > requirements_endpoint.txt 	
	rm requirements_temp.txt
	cd data && \
	wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt && \
	mkdir -p my_model/code && \
	mv yolo11n.pt my_model/ && \
	cp ../modules/inference.py my_model/code/ && \
	cp ../requirements_endpoint.txt my_model/requirements_endpoint.txt && \
	tar -czvf model.tar.gz -C my_model . && \
	aws s3 cp model.tar.gz s3://${TF_VAR_models_bucket}/model_ul/ && \
	rm model.tar.gz && rm -rf my_model

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