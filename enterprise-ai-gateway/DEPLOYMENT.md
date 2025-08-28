# Deployment Guide - Enterprise AI Gateway

## Quick Start

### Prerequisites
- Google Cloud Project
- Docker installed locally
- gcloud CLI configured

### 1. Clone and Setup
```bash
git clone <repository-url>
cd enterprise-ai-gateway

# Set your GCP project
gcloud config set project YOUR_PROJECT_ID

# Set up GCP services and container registry
make setup
```

### 2. Build and Deploy to Cloud Run
```bash
# Build and push container
make build

# Deploy to Cloud Run (manual for now)
gcloud run deploy enterprise-ai-gateway \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/ai-gateway/enterprise-ai-gateway:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 100
```

### 3. Test Deployment
```bash
# Get the Cloud Run URL
SERVICE_URL=$(gcloud run services describe enterprise-ai-gateway --platform=managed --region=us-central1 --format="value(status.url)")

# Test health endpoint
curl $SERVICE_URL/health

# Test chat endpoint (placeholder response)
curl -X POST $SERVICE_URL/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Development Setup

### Local Development
```bash
# Install dependencies
make install

# Run development server
make dev

# Test locally
curl http://localhost:8080/health
```

### Docker Development
```bash
# Build and run locally
make build
make deploy-local

# Test
make test
```

## Production Deployment

### Full Infrastructure (TODO)
For production deployment with Terraform, authentication, and all features:

1. Set up authentication providers (Google SSO, Okta, etc.)
2. Configure LLM provider credentials (Azure OpenAI, AWS Bedrock, etc.) 
3. Deploy infrastructure with Terraform
4. Configure monitoring and alerting

See the complete package files for full implementation details.

## Current Status

This is a **minimal working version** with:
✅ FastAPI application structure
✅ Cloud Run deployment
✅ Basic endpoints (/health, /v1/chat/completions, /v1/models)
✅ Placeholder responses
✅ Production-ready Docker container
✅ Development tooling

**TODO for full implementation:**
- Authentication system (SSO, service accounts)
- LLM provider integrations (Azure, AWS, Google)
- Redis caching and rate limiting
- Terraform infrastructure
- Monitoring and observability
- Complete client examples

This gives you a working foundation to build upon!