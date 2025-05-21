zip_lambdas:
	mkdir -p cloud_resources
	zip cloud_resources/lambda1.zip modules/lambda1.py
	zip cloud_resources/lambda2.zip modules/lambda2.py

# take models bucket from env
prep_model:
	cd data && \
	wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt && \
	tar -czvf model.tar.gz yolo11n.pt && \
	aws s3 cp model.tar.gz s3://${TF_VAR_models_bucket}/model_ul/ && \
	rm yolo11n.pt && rm model.tar.gz

aws_apply:
	cd terraform && \
	terraform validate && \
	terraform plan && \
	terraform apply

aws_destroy:
	aws s3 rm s3://${TF_VAR_input_bucket} --recursive && \
	aws s3 rm s3://${TF_VAR_processed_bucket} --recursive && \
	aws s3 rm s3://${TF_VAR_models_bucket} --recursive && \
	cd terraform && \
	terraform destroy -auto-approve 