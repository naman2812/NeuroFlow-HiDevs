.PHONY: security-scan

IMAGE_NAME ?= neuroflow-api:latest

security-scan:
	@echo "Scanning image $(IMAGE_NAME) for CRITICAL vulnerabilities..."
	trivy image --severity CRITICAL --exit-code 1 $(IMAGE_NAME)
