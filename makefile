zip_lambdas:
	mkdir -p cloud_resources
	zip cloud_resources/lambda1.zip modules/lambda1.py
	zip cloud_resources/lambda2.zip modules/lambda2.py

aws_apply:
	cd terraform && \
	terraform validate && \
	terraform plan && \
	terraform apply

aws_destroy:
	aws s3 rm s3://qla-income --recursive && \
	aws s3 rm s3://qla-processed --recursive && \
	cd terraform && \
	terraform destroy -auto-approve 