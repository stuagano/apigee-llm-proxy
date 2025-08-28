#!/bin/bash
set -e

# Enterprise LLM Proxy - Deployment Script
# Automates the complete deployment process

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project)}
REGION=${REGION:-us-central1}
ENVIRONMENT=${ENVIRONMENT:-prod}
IMAGE_NAME="llm-proxy"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    log_info "Checking requirements..."
    
    # Check if gcloud is installed
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if terraform is installed
    if ! command -v terraform &> /dev/null; then
        log_error "Terraform is not installed. Please install it first."
        exit 1
    fi
    
    # Check if docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install it first."
        exit 1
    fi
    
    # Check if project is set
    if [ -z "$PROJECT_ID" ]; then
        log_error "GCP project not set. Run 'gcloud config set project YOUR_PROJECT' first."
        exit 1
    fi
    
    log_success "All requirements met"
}

setup_gcp_project() {
    log_info "Setting up GCP project: $PROJECT_ID"
    
    # Enable required APIs
    log_info "Enabling required APIs..."
    gcloud services enable \
        run.googleapis.com \
        compute.googleapis.com \
        redis.googleapis.com \
        secretmanager.googleapis.com \
        firestore.googleapis.com \
        monitoring.googleapis.com \
        artifactregistry.googleapis.com \
        vpcaccess.googleapis.com \
        cloudbuild.googleapis.com \
        --project=$PROJECT_ID
    
    # Create Artifact Registry repository
    log_info "Creating Artifact Registry repository..."
    if ! gcloud artifacts repositories describe $IMAGE_NAME \
        --location=$REGION \
        --project=$PROJECT_ID &> /dev/null; then
        
        gcloud artifacts repositories create $IMAGE_NAME \
            --repository-format=docker \
            --location=$REGION \
            --description="LLM Proxy container images" \
            --project=$PROJECT_ID
    else
        log_info "Artifact Registry repository already exists"
    fi
    
    # Configure Docker authentication
    log_info "Configuring Docker authentication..."
    gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet
    
    log_success "GCP project setup complete"
}

validate_config() {
    log_info "Validating configuration..."
    
    # Check if terraform.tfvars exists
    if [ ! -f "deployment/terraform/terraform.tfvars" ]; then
        log_error "terraform.tfvars not found"
        log_info "Please copy deployment/terraform/terraform.tfvars.example to deployment/terraform/terraform.tfvars and customize it"
        exit 1
    fi
    
    # Validate terraform configuration
    cd deployment/terraform
    terraform init -input=false
    terraform validate
    cd ../..
    
    log_success "Configuration validated"
}

build_and_push_image() {
    log_info "Building and pushing Docker image..."
    
    local image_url="${REGION}-docker.pkg.dev/${PROJECT_ID}/${IMAGE_NAME}/${IMAGE_NAME}"
    local git_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")
    
    # Build image
    log_info "Building image: $image_url:$git_hash"
    docker build \
        -f deployment/docker/Dockerfile \
        -t "${image_url}:latest" \
        -t "${image_url}:${git_hash}" \
        .
    
    # Push image
    log_info "Pushing image to Artifact Registry..."
    docker push "${image_url}:latest"
    docker push "${image_url}:${git_hash}"
    
    log_success "Image built and pushed: ${image_url}:latest"
}

deploy_infrastructure() {
    log_info "Deploying infrastructure with Terraform..."
    
    cd deployment/terraform
    
    # Initialize terraform
    terraform init -input=false
    
    # Plan deployment
    log_info "Planning infrastructure changes..."
    terraform plan \
        -var="project_id=$PROJECT_ID" \
        -var="region=$REGION" \
        -var="environment=$ENVIRONMENT" \
        -out=plan.tfplan
    
    # Apply deployment
    log_info "Applying infrastructure changes..."
    terraform apply -input=false plan.tfplan
    
    cd ../..
    
    log_success "Infrastructure deployed"
}

wait_for_service() {
    log_info "Waiting for service to be ready..."
    
    local service_url=$(cd deployment/terraform && terraform output -raw service_url)
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        log_info "Health check attempt $attempt/$max_attempts..."
        
        if curl -f "${service_url}/health" &> /dev/null; then
            log_success "Service is ready!"
            return 0
        fi
        
        sleep 10
        attempt=$((attempt + 1))
    done
    
    log_error "Service did not become ready within expected time"
    return 1
}

show_deployment_info() {
    log_info "Deployment completed successfully!"
    echo
    echo "=============================================="
    echo "         DEPLOYMENT INFORMATION"
    echo "=============================================="
    echo
    
    cd deployment/terraform
    
    local service_url=$(terraform output -raw service_url)
    local domain=$(terraform output -raw domain)
    local load_balancer_ip=$(terraform output -raw load_balancer_ip)
    local service_account=$(terraform output -raw service_account)
    
    echo "🌍 Service URL:       $service_url"
    echo "🌐 Domain:            https://$domain"
    echo "📍 Load Balancer IP:  $load_balancer_ip"
    echo "🔐 Service Account:   $service_account"
    echo
    echo "🧪 Test Commands:"
    echo "   Health Check:      curl https://$domain/health"
    echo "   Available Models:  curl https://$domain/v1/models -H 'Authorization: Bearer YOUR_TOKEN'"
    echo
    echo "📊 Monitoring:"
    echo "   Dashboard: https://console.cloud.google.com/run/detail/$REGION/llm-proxy-$ENVIRONMENT/metrics?project=$PROJECT_ID"
    echo "   Logs:      gcloud logging read 'resource.type=cloud_run_revision' --limit=50 --project=$PROJECT_ID"
    echo
    echo "📚 Next Steps:"
    echo "   1. Configure DNS: Point $domain to $load_balancer_ip"
    echo "   2. Wait for SSL certificate provisioning (5-10 minutes)"
    echo "   3. Set up user authentication in Firestore"
    echo "   4. Configure client applications"
    echo
    
    cd ../..
    
    # Show demo service account info if available
    if terraform output demo_service_account_secret &> /dev/null; then
        local demo_account_id=$(terraform output -raw demo_service_account_id)
        local demo_secret=$(terraform output -raw demo_service_account_secret)
        
        echo "🔑 Demo Service Account (for testing):"
        echo "   Account ID: $demo_account_id"
        echo "   Secret:     $demo_secret"
        echo
        echo "   Test with:"
        echo "   export LLM_PROXY_ACCOUNT_ID='$demo_account_id'"
        echo "   export LLM_PROXY_SECRET='$demo_secret'"
        echo "   python examples/python/service_account_client.py"
        echo
    fi
    
    cd deployment/terraform
}

run_tests() {
    log_info "Running post-deployment tests..."
    
    local domain=$(cd deployment/terraform && terraform output -raw domain)
    
    # Test health endpoint
    log_info "Testing health endpoint..."
    if curl -f "https://$domain/health" &> /dev/null; then
        log_success "Health check passed"
    else
        log_error "Health check failed"
        return 1
    fi
    
    # Test models endpoint (this will fail without auth, but should return 401, not 500)
    log_info "Testing models endpoint (expecting 401)..."
    local status=$(curl -s -o /dev/null -w "%{http_code}" "https://$domain/v1/models")
    if [ "$status" = "401" ]; then
        log_success "Models endpoint correctly requires authentication"
    else
        log_warning "Models endpoint returned status $status (expected 401)"
    fi
    
    log_success "Basic tests completed"
}

cleanup_on_error() {
    log_error "Deployment failed. Cleaning up..."
    
    # Clean up terraform state if needed
    if [ -f "deployment/terraform/plan.tfplan" ]; then
        rm -f deployment/terraform/plan.tfplan
    fi
    
    # Note: We don't automatically destroy infrastructure on error
    # because it might contain valuable state or partial deployments
    log_info "Manual cleanup may be required. Check the Terraform state."
}

# Main deployment flow
main() {
    log_info "Starting Enterprise LLM Proxy deployment..."
    echo "Project: $PROJECT_ID"
    echo "Region: $REGION"
    echo "Environment: $ENVIRONMENT"
    echo
    
    # Set error handler
    trap cleanup_on_error ERR
    
    # Run deployment steps
    check_requirements
    setup_gcp_project
    validate_config
    build_and_push_image
    deploy_infrastructure
    
    # Wait for service and run tests
    if wait_for_service; then
        run_tests
        show_deployment_info
    else
        log_error "Service deployment failed"
        exit 1
    fi
    
    log_success "🎉 Deployment completed successfully!"
}

# Handle command line arguments
case "$1" in
    "setup")
        check_requirements
        setup_gcp_project
        ;;
    "build")
        build_and_push_image
        ;;
    "deploy")
        validate_config
        deploy_infrastructure
        ;;
    "test")
        run_tests
        ;;
    "info")
        show_deployment_info
        ;;
    "")
        main
        ;;
    *)
        echo "Usage: $0 [setup|build|deploy|test|info]"
        echo
        echo "Commands:"
        echo "  setup   - Set up GCP project and enable APIs"
        echo "  build   - Build and push Docker image"
        echo "  deploy  - Deploy infrastructure with Terraform"
        echo "  test    - Run post-deployment tests"
        echo "  info    - Show deployment information"
        echo "  (none)  - Run complete deployment"
        exit 1
        ;;
esac