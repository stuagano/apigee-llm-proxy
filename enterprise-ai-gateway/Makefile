# Enterprise AI Gateway - Makefile

# Variables
PROJECT_ID ?= $(shell gcloud config get-value project)
REGION ?= us-central1
ENVIRONMENT ?= prod
IMAGE_NAME = enterprise-ai-gateway
REPOSITORY = $(REGION)-docker.pkg.dev/$(PROJECT_ID)/ai-gateway

# Colors for output
RED = \033[0;31m
GREEN = \033[0;32m
YELLOW = \033[0;33m
BLUE = \033[0;34m
NC = \033[0m # No Color

.PHONY: help setup build deploy test clean

help: ## Show this help message
	@echo "$(BLUE)Enterprise AI Gateway - Available Commands$(NC)"
	@echo "=========================================="
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "$(YELLOW)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Set up GCP project and enable APIs
	@echo "$(BLUE)Setting up GCP project...$(NC)"
	@if [ -z "$(PROJECT_ID)" ]; then \
		echo "$(RED)Error: PROJECT_ID not set. Run 'gcloud config set project YOUR_PROJECT' first$(NC)"; \
		exit 1; \
	fi
	
	@echo "$(YELLOW)Enabling required APIs...$(NC)"
	gcloud services enable \
		run.googleapis.com \
		compute.googleapis.com \
		secretmanager.googleapis.com \
		artifactregistry.googleapis.com \
		--project=$(PROJECT_ID)
	
	@echo "$(YELLOW)Creating Artifact Registry repository...$(NC)"
	gcloud artifacts repositories create ai-gateway \
		--repository-format=docker \
		--location=$(REGION) \
		--description="AI Gateway container images" \
		--project=$(PROJECT_ID) || true
	
	gcloud auth configure-docker $(REGION)-docker.pkg.dev
	@echo "$(GREEN)✓ Setup complete!$(NC)"

build: ## Build and push Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	
	docker build -t $(REPOSITORY)/$(IMAGE_NAME):latest .
	docker push $(REPOSITORY)/$(IMAGE_NAME):latest
	
	@echo "$(GREEN)✓ Image built and pushed$(NC)"

deploy-local: ## Run locally with Docker
	@echo "$(BLUE)Running locally...$(NC)"
	docker run -p 8080:8080 --env ENVIRONMENT=development $(REPOSITORY)/$(IMAGE_NAME):latest

test: ## Test the application
	@echo "$(BLUE)Testing application...$(NC)"
	curl -f http://localhost:8080/health || echo "$(RED)Health check failed$(NC)"
	@echo "$(GREEN)✓ Tests complete$(NC)"

clean: ## Clean up local files
	@echo "$(BLUE)Cleaning up...$(NC)"
	docker system prune -f
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

# Quick development commands
dev: ## Run development server
	@echo "$(BLUE)Starting development server...$(NC)"
	uvicorn main:app --reload --host 0.0.0.0 --port 8080

install: ## Install dependencies
	pip install -r requirements.txt

lint: ## Lint code
	@echo "$(BLUE)Linting code...$(NC)"
	flake8 . --max-line-length=120 --exclude=venv,env
	@echo "$(GREEN)✓ Linting complete$(NC)"

format: ## Format code
	@echo "$(BLUE)Formatting code...$(NC)"
	black . --line-length=120
	@echo "$(GREEN)✓ Formatting complete$(NC)"