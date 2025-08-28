# Enterprise LLM Proxy on Cloud Run - Complete Infrastructure
terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# ============== VARIABLES ==============

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "Primary deployment region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment (dev/staging/prod)"
  type        = string
  default     = "prod"
}

variable "domain" {
  description = "Domain for SSL certificate"
  type        = string
}

# LLM Provider configurations
variable "azure_openai_endpoint" {
  description = "Azure OpenAI endpoint URL"
  type        = string
  sensitive   = true
}

variable "azure_openai_key" {
  description = "Azure OpenAI API key"
  type        = string
  sensitive   = true
}

variable "aws_access_key" {
  description = "AWS access key for Bedrock"
  type        = string
  sensitive   = true
}

variable "aws_secret_key" {
  description = "AWS secret key for Bedrock"
  type        = string
  sensitive   = true
}

# Authentication configuration
variable "sso_provider" {
  description = "SSO provider (google, okta, azure_ad)"
  type        = string
  default     = "google"
}

variable "sso_client_id" {
  description = "SSO client ID"
  type        = string
}

variable "sso_tenant" {
  description = "SSO tenant (for Okta/Azure AD)"
  type        = string
  default     = ""
}

variable "notification_channels" {
  description = "Notification channels for alerts"
  type        = list(string)
  default     = []
}

# ============== PROVIDERS ==============

provider "google" {
  project = var.project_id
  region  = var.region
}

# ============== NETWORKING ==============

# VPC for private resources
resource "google_compute_network" "llm_proxy_vpc" {
  name                    = "llm-proxy-vpc-${var.environment}"
  auto_create_subnetworks = false
  
  description = "VPC for LLM Proxy service"
}

resource "google_compute_subnetwork" "llm_proxy_subnet" {
  name          = "llm-proxy-subnet-${var.environment}"
  network       = google_compute_network.llm_proxy_vpc.id
  region        = var.region
  ip_cidr_range = "10.0.0.0/24"
  
  description = "Subnet for LLM Proxy private resources"
  
  # Enable private Google access
  private_ip_google_access = true
}

# Serverless VPC Connector
resource "google_vpc_access_connector" "llm_proxy_connector" {
  name          = "llm-proxy-connector-${var.environment}"
  region        = var.region
  network       = google_compute_network.llm_proxy_vpc.name
  ip_cidr_range = "10.0.1.0/28"
  
  min_instances = var.environment == "prod" ? 3 : 2
  max_instances = var.environment == "prod" ? 10 : 5
  
  machine_type = var.environment == "prod" ? "e2-standard-4" : "e2-micro"
}

# ============== DATABASES & STORAGE ==============

# Redis for caching and rate limiting
resource "google_redis_instance" "llm_proxy_cache" {
  name               = "llm-proxy-cache-${var.environment}"
  tier               = var.environment == "prod" ? "STANDARD_HA" : "BASIC"
  memory_size_gb     = var.environment == "prod" ? 5 : 1
  region             = var.region
  redis_version      = "REDIS_7_0"
  
  authorized_network = google_compute_network.llm_proxy_vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  
  redis_configs = {
    maxmemory-policy = "allkeys-lru"
    notify-keyspace-events = "Ex"
  }
  
  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 3
        minutes = 0
      }
    }
  }
  
  labels = {
    environment = var.environment
    service     = "llm-proxy"
  }
}

# Firestore for user metadata and service accounts
resource "google_firestore_database" "llm_proxy_db" {
  name        = "llm-proxy-${var.environment}"
  location_id = "nam5"  # North America multi-region
  type        = "FIRESTORE_NATIVE"
  
  # Enable delete protection for production
  delete_protection_state = var.environment == "prod" ? "DELETE_PROTECTION_ENABLED" : "DELETE_PROTECTION_DISABLED"
}

# ============== SECRETS MANAGEMENT ==============

# Azure OpenAI credentials
resource "google_secret_manager_secret" "azure_openai_endpoint" {
  secret_id = "azure-openai-endpoint-${var.environment}"
  
  replication {
    auto {}
  }
  
  labels = {
    environment = var.environment
    provider    = "azure"
  }
}

resource "google_secret_manager_secret_version" "azure_openai_endpoint" {
  secret      = google_secret_manager_secret.azure_openai_endpoint.id
  secret_data = var.azure_openai_endpoint
}

resource "google_secret_manager_secret" "azure_openai_key" {
  secret_id = "azure-openai-key-${var.environment}"
  
  replication {
    auto {}
  }
  
  labels = {
    environment = var.environment
    provider    = "azure"
  }
}

resource "google_secret_manager_secret_version" "azure_openai_key" {
  secret      = google_secret_manager_secret.azure_openai_key.id
  secret_data = var.azure_openai_key
}

# AWS Bedrock credentials
resource "google_secret_manager_secret" "aws_access_key" {
  secret_id = "aws-access-key-${var.environment}"
  
  replication {
    auto {}
  }
  
  labels = {
    environment = var.environment
    provider    = "aws"
  }
}

resource "google_secret_manager_secret_version" "aws_access_key" {
  secret      = google_secret_manager_secret.aws_access_key.id
  secret_data = var.aws_access_key
}

resource "google_secret_manager_secret" "aws_secret_key" {
  secret_id = "aws-secret-key-${var.environment}"
  
  replication {
    auto {}
  }
  
  labels = {
    environment = var.environment
    provider    = "aws"
  }
}

resource "google_secret_manager_secret_version" "aws_secret_key" {
  secret      = google_secret_manager_secret.aws_secret_key.id
  secret_data = var.aws_secret_key
}

# Demo service account secret for testing
resource "google_secret_manager_secret" "demo_service_account_secret" {
  secret_id = "demo-service-account-secret-${var.environment}"
  
  replication {
    auto {}
  }
  
  labels = {
    environment = var.environment
    type        = "demo"
  }
}

resource "google_secret_manager_secret_version" "demo_service_account_secret" {
  secret      = google_secret_manager_secret.demo_service_account_secret.id
  secret_data = "demo-secret-key-${random_id.demo_secret.hex}"
}

resource "random_id" "demo_secret" {
  byte_length = 16
}

# ============== IAM & SERVICE ACCOUNTS ==============

# Cloud Run service account
resource "google_service_account" "cloud_run_sa" {
  account_id   = "llm-proxy-${var.environment}"
  display_name = "LLM Proxy Cloud Run Service Account"
  description  = "Service account for Cloud Run LLM Proxy - ${var.environment}"
}

# IAM roles for service account
resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_project_iam_member" "firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_project_iam_member" "vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_project_iam_member" "monitoring_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_project_iam_member" "trace_writer" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# ============== CLOUD RUN SERVICE ==============

resource "google_cloud_run_v2_service" "llm_proxy" {
  name     = "llm-proxy-${var.environment}"
  location = var.region
  
  template {
    service_account = google_service_account.cloud_run_sa.email
    
    # VPC connector for private resources
    vpc_access {
      connector = google_vpc_access_connector.llm_proxy_connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    
    # Scaling configuration
    scaling {
      min_instance_count = var.environment == "prod" ? 3 : 1
      max_instance_count = var.environment == "prod" ? 100 : 20
    }
    
    # Resource limits
    max_instance_request_concurrency = 1000
    timeout                          = "300s"
    
    containers {
      image = "gcr.io/${var.project_id}/llm-proxy:latest"
      
      resources {
        limits = {
          cpu    = var.environment == "prod" ? "4" : "2"
          memory = var.environment == "prod" ? "8Gi" : "4Gi"
        }
        
        cpu_idle = var.environment != "prod"  # Allow scale to zero for non-prod
      }
      
      # Environment variables
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      
      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.llm_proxy_cache.host
      }
      
      # SSO Configuration
      env {
        name  = "SSO_ENABLED"
        value = "true"
      }
      
      env {
        name  = "SSO_PROVIDER"
        value = var.sso_provider
      }
      
      env {
        name  = "SSO_CLIENT_ID"
        value = var.sso_client_id
      }
      
      env {
        name  = "SSO_TENANT"
        value = var.sso_tenant
      }
      
      # Provider Configuration
      env {
        name  = "AZURE_OPENAI_ENABLED"
        value = "true"
      }
      
      env {
        name  = "AWS_BEDROCK_ENABLED"
        value = "true"
      }
      
      env {
        name  = "AWS_REGION"
        value = "us-east-1"
      }
      
      env {
        name  = "VERTEX_AI_ENABLED"
        value = "true"
      }
      
      env {
        name  = "GCP_LOCATION"
        value = var.region
      }
      
      # Demo service account for testing
      env {
        name  = "DEMO_SERVICE_ACCOUNT_ID"
        value = "demo-client-${var.environment}"
      }
      
      # Network trust settings
      env {
        name  = "TRUST_INTERNAL_NETWORK"
        value = var.environment == "dev" ? "true" : "false"
      }
      
      env {
        name  = "INTERNAL_NETWORKS"
        value = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
      }
      
      # Logging
      env {
        name  = "LOG_LEVEL"
        value = var.environment == "dev" ? "DEBUG" : "INFO"
      }
      
      # Startup probe
      startup_probe {
        initial_delay_seconds = 15
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 6
        
        http_get {
          path = "/ready"
          port = 8080
        }
      }
      
      # Liveness probe
      liveness_probe {
        initial_delay_seconds = 30
        timeout_seconds       = 5
        period_seconds        = 30
        failure_threshold     = 3
        
        http_get {
          path = "/health"
          port = 8080
        }
      }
    }
  }
  
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
  
  labels = {
    environment = var.environment
    service     = "llm-proxy"
    version     = "2.0"
  }
}

# ============== LOAD BALANCER & SSL ==============

# Reserve static IP
resource "google_compute_global_address" "llm_proxy_ip" {
  name = "llm-proxy-ip-${var.environment}"
  
  description = "Static IP for LLM Proxy load balancer"
}

# SSL Certificate
resource "google_compute_managed_ssl_certificate" "llm_proxy_cert" {
  name = "llm-proxy-cert-${var.environment}"
  
  managed {
    domains = ["${var.environment == "prod" ? "" : "${var.environment}."}llm-proxy.${var.domain}"]
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

# Network Endpoint Group for Cloud Run
resource "google_compute_region_network_endpoint_group" "llm_proxy_neg" {
  name                  = "llm-proxy-neg-${var.environment}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  
  cloud_run {
    service = google_cloud_run_v2_service.llm_proxy.name
  }
}

# Backend service
resource "google_compute_backend_service" "llm_proxy_backend" {
  name = "llm-proxy-backend-${var.environment}"
  
  protocol    = "HTTPS"
  port_name   = "http"
  timeout_sec = 300
  
  backend {
    group = google_compute_region_network_endpoint_group.llm_proxy_neg.id
  }
  
  # Enable Cloud CDN for static responses
  enable_cdn = true
  cdn_policy {
    cache_mode                   = "CACHE_ALL_STATIC"
    default_ttl                  = 300
    max_ttl                      = 1800
    client_ttl                   = 300
    negative_caching             = true
    serve_while_stale            = 300
    
    negative_caching_policy {
      code = 404
      ttl  = 300
    }
    
    # Don't cache streaming responses
    bypass_cache_on_request_headers {
      header_name = "Accept"
    }
  }
  
  # Health check
  health_checks = [google_compute_health_check.llm_proxy_health.id]
  
  # Security policy
  security_policy = google_compute_security_policy.llm_proxy_security.id
  
  # Logging
  log_config {
    enable      = true
    sample_rate = var.environment == "prod" ? 0.1 : 1.0
  }
}

# Health check
resource "google_compute_health_check" "llm_proxy_health" {
  name = "llm-proxy-health-${var.environment}"
  
  timeout_sec         = 5
  check_interval_sec  = 30
  healthy_threshold   = 2
  unhealthy_threshold = 3
  
  https_health_check {
    port         = 443
    request_path = "/health"
  }
  
  log_config {
    enable = var.environment == "dev"
  }
}

# URL map
resource "google_compute_url_map" "llm_proxy_url_map" {
  name            = "llm-proxy-url-map-${var.environment}"
  default_service = google_compute_backend_service.llm_proxy_backend.id
  
  description = "URL map for LLM Proxy service"
}

# HTTPS proxy
resource "google_compute_target_https_proxy" "llm_proxy_https_proxy" {
  name             = "llm-proxy-https-proxy-${var.environment}"
  url_map          = google_compute_url_map.llm_proxy_url_map.id
  ssl_certificates = [google_compute_managed_ssl_certificate.llm_proxy_cert.id]
  
  description = "HTTPS proxy for LLM Proxy service"
}

# Global forwarding rule
resource "google_compute_global_forwarding_rule" "llm_proxy_forwarding" {
  name       = "llm-proxy-forwarding-${var.environment}"
  target     = google_compute_target_https_proxy.llm_proxy_https_proxy.id
  port_range = "443"
  ip_address = google_compute_global_address.llm_proxy_ip.address
  
  description = "Global forwarding rule for LLM Proxy"
}

# ============== CLOUD ARMOR SECURITY ==============

resource "google_compute_security_policy" "llm_proxy_security" {
  name = "llm-proxy-security-${var.environment}"
  
  description = "Cloud Armor security policy for LLM Proxy"
  
  # Default rule - allow all
  rule {
    action   = "allow"
    priority = "2147483647"
    
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    
    description = "Default allow rule"
  }
  
  # Rate limiting rule
  rule {
    action   = "rate_based_ban"
    priority = "1000"
    
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      
      rate_limit_threshold {
        count        = var.environment == "prod" ? 1000 : 100
        interval_sec = 60
      }
      
      ban_duration_sec = 600
    }
    
    description = "Global rate limiting"
  }
  
  # Block malicious IPs
  rule {
    action   = "deny(403)"
    priority = "100"
    
    match {
      expr {
        expression = "origin.region_code == 'CN' || origin.region_code == 'RU'"
      }
    }
    
    description = "Block high-risk regions"
  }
  
  # OWASP protection rules
  rule {
    action   = "deny(403)"
    priority = "200"
    
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-stable')"
      }
    }
    
    description = "Block XSS attacks"
  }
  
  rule {
    action   = "deny(403)"
    priority = "201"
    
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-stable')"
      }
    }
    
    description = "Block SQL injection"
  }
  
  # Adaptive protection for DDoS
  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
      rule_visibility = "STANDARD"
    }
  }
}

# ============== MONITORING & ALERTING ==============

# Uptime check
resource "google_monitoring_uptime_check_config" "llm_proxy_uptime" {
  display_name = "LLM Proxy Uptime - ${var.environment}"
  timeout      = "10s"
  period       = "60s"
  
  http_check {
    path         = "/health"
    port         = "443"
    use_ssl      = true
    validate_ssl = true
  }
  
  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = "${var.environment == "prod" ? "" : "${var.environment}."}llm-proxy.${var.domain}"
    }
  }
  
  content_matchers {
    content = "healthy"
    matcher = "CONTAINS_STRING"
  }
}

# Alert policy for high latency
resource "google_monitoring_alert_policy" "high_latency" {
  display_name = "LLM Proxy High Latency - ${var.environment}"
  combiner     = "OR"
  
  conditions {
    display_name = "Response latency > 5s"
    
    condition_threshold {
      filter = "metric.type=\"run.googleapis.com/request_latencies\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.llm_proxy.name}\""
      
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_PERCENTILE_95"
      }
      
      comparison = "COMPARISON_GT"
      threshold_value = 5000  # 5 seconds in milliseconds
      duration = "300s"
    }
  }
  
  notification_channels = var.notification_channels
  
  alert_strategy {
    auto_close = "1800s"
  }
  
  enabled = var.environment == "prod"
}

# Alert policy for high error rate
resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "LLM Proxy High Error Rate - ${var.environment}"
  combiner     = "OR"
  
  conditions {
    display_name = "Error rate > 5%"
    
    condition_threshold {
      filter = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.llm_proxy.name}\" AND metric.labels.response_code_class=\"5xx\""
      
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_RATE"
      }
      
      comparison = "COMPARISON_GT"
      threshold_value = 0.05
      duration = "300s"
    }
  }
  
  notification_channels = var.notification_channels
  
  alert_strategy {
    auto_close = "1800s"
  }
  
  enabled = var.environment == "prod"
}

# Alert for service account creation (security)
resource "google_monitoring_alert_policy" "service_account_creation" {
  display_name = "Unauthorized Service Account Activity - ${var.environment}"
  combiner     = "OR"
  
  conditions {
    display_name = "New service accounts created"
    
    condition_threshold {
      filter = "resource.type=\"gce_instance\" AND protoPayload.methodName=\"google.iam.admin.v1.CreateServiceAccount\""
      
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_COUNT_TRUE"
      }
      
      comparison = "COMPARISON_GT"
      threshold_value = 0
      duration = "60s"
    }
  }
  
  notification_channels = var.notification_channels
  
  enabled = var.environment == "prod"
}

# ============== OUTPUTS ==============

output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.llm_proxy.uri
}

output "load_balancer_ip" {
  description = "Global load balancer IP address"
  value       = google_compute_global_address.llm_proxy_ip.address
}

output "domain" {
  description = "Full domain name"
  value       = "${var.environment == "prod" ? "" : "${var.environment}."}llm-proxy.${var.domain}"
}

output "redis_host" {
  description = "Redis instance host"
  value       = google_redis_instance.llm_proxy_cache.host
  sensitive   = true
}

output "service_account" {
  description = "Service account email"
  value       = google_service_account.cloud_run_sa.email
}

output "demo_service_account_id" {
  description = "Demo service account ID for testing"
  value       = "demo-client-${var.environment}"
}

output "demo_service_account_secret" {
  description = "Demo service account secret (for testing only)"
  value       = random_id.demo_secret.hex
  sensitive   = true
}