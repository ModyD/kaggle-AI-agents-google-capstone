#!/bin/bash
# =============================================================================
# Cloud Run Deployment Script
# Enterprise Security Incident Triage & Autonomous Runbook Agent
# =============================================================================

set -e

# Configuration (override with environment variables)
SERVICE_NAME="${SERVICE_NAME:-security-agent}"
PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-us-central1}"
IMAGE_NAME="${IMAGE_NAME:-gcr.io/${PROJECT_ID}/${SERVICE_NAME}}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check required environment variables
check_requirements() {
    if [ -z "$PROJECT_ID" ]; then
        log_error "PROJECT_ID environment variable is required"
        echo "Usage: PROJECT_ID=your-project-id ./cloudrun_deploy.sh"
        exit 1
    fi

    # Check if gcloud is installed
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI is not installed. Please install it first."
        exit 1
    fi

    # Check if authenticated
    if ! gcloud auth print-identity-token &> /dev/null; then
        log_error "Not authenticated with gcloud. Run 'gcloud auth login' first."
        exit 1
    fi

    log_info "Requirements check passed"
}

# Build the container image
build_image() {
    log_info "Building container image: ${IMAGE_NAME}"

    # Option 1: Build with Cloud Build (recommended for CI/CD)
    if [ "${USE_CLOUD_BUILD:-false}" = "true" ]; then
        log_info "Using Cloud Build..."
        gcloud builds submit --tag "${IMAGE_NAME}" --project "${PROJECT_ID}" .
    else
        # Option 2: Build locally and push
        log_info "Building locally with Docker..."
        docker build -t "${IMAGE_NAME}" .

        log_info "Pushing image to GCR..."
        docker push "${IMAGE_NAME}"
    fi

    log_info "Image built and pushed successfully"
}

# Deploy to Cloud Run
deploy_service() {
    log_info "Deploying to Cloud Run: ${SERVICE_NAME}"

    # Environment variables to pass to Cloud Run
    # For secrets, use Secret Manager references: --set-secrets=VAR=secret-name:version
    ENV_VARS=""
    ENV_VARS="${ENV_VARS}FRONTEND_URL=${FRONTEND_URL:-https://your-frontend.vercel.app},"
    ENV_VARS="${ENV_VARS}USE_STUB_LLM=${USE_STUB_LLM:-false},"
    ENV_VARS="${ENV_VARS}GOOGLE_CLOUD_PROJECT=${PROJECT_ID},"
    ENV_VARS="${ENV_VARS}GOOGLE_CLOUD_LOCATION=${REGION}"

    # Deploy command
    gcloud run deploy "${SERVICE_NAME}" \
        --image "${IMAGE_NAME}" \
        --platform managed \
        --region "${REGION}" \
        --project "${PROJECT_ID}" \
        --allow-unauthenticated \
        --memory 512Mi \
        --cpu 1 \
        --timeout 60s \
        --concurrency 80 \
        --min-instances 0 \
        --max-instances 10 \
        --set-env-vars "${ENV_VARS}"

    log_info "Deployment successful"
}

# Get the service URL
get_service_url() {
    SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
        --platform managed \
        --region "${REGION}" \
        --project "${PROJECT_ID}" \
        --format 'value(status.url)')

    echo "${SERVICE_URL}"
}

# Run smoke tests
smoke_test() {
    SERVICE_URL=$(get_service_url)
    log_info "Running smoke tests against: ${SERVICE_URL}"

    # Test 1: Health check
    log_info "Testing /health endpoint..."
    HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" "${SERVICE_URL}/health")
    HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -n1)
    BODY=$(echo "$HEALTH_RESPONSE" | head -n-1)

    if [ "$HTTP_CODE" = "200" ]; then
        log_info "Health check passed: $BODY"
    else
        log_error "Health check failed with status $HTTP_CODE"
        exit 1
    fi

    # Test 2: Triage endpoint
    log_info "Testing /triage endpoint..."
    TRIAGE_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -X POST "${SERVICE_URL}/triage" \
        -H "Content-Type: application/json" \
        -d '{"features": {"failed_logins_last_hour": 50, "suspicious_file_activity": true}}')
    HTTP_CODE=$(echo "$TRIAGE_RESPONSE" | tail -n1)
    BODY=$(echo "$TRIAGE_RESPONSE" | head -n-1)

    if [ "$HTTP_CODE" = "200" ]; then
        log_info "Triage test passed: $BODY"
    else
        log_error "Triage test failed with status $HTTP_CODE"
        log_error "Response: $BODY"
        exit 1
    fi

    # Test 3: Flow simulation
    log_info "Testing /flow/simulate endpoint..."
    FLOW_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -X POST "${SERVICE_URL}/flow/simulate" \
        -H "Content-Type: application/json" \
        -d '{"incident_id": "TEST-001", "features": {"failed_logins_last_hour": 25, "process_spawn_count": 50}}')
    HTTP_CODE=$(echo "$FLOW_RESPONSE" | tail -n1)

    if [ "$HTTP_CODE" = "200" ]; then
        log_info "Flow simulation test passed"
    else
        log_error "Flow simulation test failed with status $HTTP_CODE"
        exit 1
    fi

    log_info "All smoke tests passed!"
}

# Print service information
print_info() {
    SERVICE_URL=$(get_service_url)

    echo ""
    echo "=========================================="
    echo "Deployment Complete!"
    echo "=========================================="
    echo ""
    echo "Service URL: ${SERVICE_URL}"
    echo ""
    echo "Endpoints:"
    echo "  - Health:    ${SERVICE_URL}/health"
    echo "  - Docs:      ${SERVICE_URL}/docs"
    echo "  - OpenAPI:   ${SERVICE_URL}/openapi.json"
    echo "  - Triage:    POST ${SERVICE_URL}/triage"
    echo "  - Flow:      POST ${SERVICE_URL}/flow/simulate"
    echo ""
    echo "Example curl command:"
    echo "  curl -X POST ${SERVICE_URL}/triage \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d '{\"features\": {\"failed_logins_last_hour\": 50}}'"
    echo ""
}

# Main execution
main() {
    log_info "Starting Cloud Run deployment..."

    check_requirements
    build_image
    deploy_service
    smoke_test
    print_info

    log_info "Deployment completed successfully!"
}

# Run main function
main "$@"
