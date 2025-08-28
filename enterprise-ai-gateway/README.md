# Enterprise AI Gateway on Google Cloud Run

> **FastAPI application for centralized LLM provider access with enterprise authentication and cost control**

## What Is This?

A FastAPI application running on Google Cloud Run that provides centralized access to multiple LLM providers (Azure OpenAI, AWS Bedrock, Google Vertex AI). Handles enterprise authentication, usage tracking, and cost management.

### Why Cloud Run + FastAPI for AI workloads?
- **Automatic scaling** - Handles variable AI traffic without configuration
- **Pay-per-request pricing** - Cost scales with actual usage  
- **Async request handling** - Efficient for concurrent LLM requests and streaming
- **Native GCP integration** - Works with existing Google Cloud infrastructure

### Problem: Distributed LLM Access
- LLM API keys distributed across teams and applications
- No visibility into AI service costs by team or project
- Direct API access bypasses enterprise security controls
- Multiple provider integrations duplicated across services
- No usage governance or audit trail

### Solution: Centralized AI Gateway
```
Apps/Users → AI Gateway → LLM Providers
     ↓           ↓            ↓
[SSO Auth]  [Routing]   [Azure OpenAI]
[Quotas]    [Caching]   [AWS Bedrock] 
[Logging]   [Failover]  [Google Vertex]
```

## Features

### Authentication & Authorization
- SSO integration (Google, Okta, Azure AD)
- Service account authentication for applications  
- Internal network trust for secure environments
- Per-user and per-department usage quotas

### Multi-Provider Support
- Azure OpenAI (GPT-4, GPT-3.5-turbo)
- AWS Bedrock (Claude, Llama models)
- Google Vertex AI (Gemini, PaLM models)
- Automatic failover between providers
- Cost-based routing optimization

### Enterprise Operations  
- Usage tracking and cost allocation
- Request/response audit logging
- Prometheus metrics and monitoring
- Automatic scaling with Cloud Run
- VPC isolation and security controls

### Developer Integration
- OpenAI-compatible REST API
- Streaming response support
- Client libraries for JavaScript and Python
- Automatic API documentation

## Architecture Role

### Position in API Infrastructure
```
┌─────────────────────────────────────────────────────────┐
│                 API Management Layer                    │
├─────────────────────────────────────────────────────────┤
│  REST APIs         │  AI Gateway     │  External APIs   │
│  GraphQL           │  LLM Routing    │  Partner APIs    │
│  Microservices     │  ML Models      │  SaaS APIs       │
└─────────────────────────────────────────────────────────┘
```

Complements existing API infrastructure by handling AI/ML-specific concerns:
- Integrates with existing SSO and authentication systems
- Uses standard observability tools (Prometheus, Grafana)
- Follows established API gateway patterns
- Works within existing network and security policies

### Responsibility Split
| Existing API Management | AI Gateway |
|-------------------------|------------|
| REST/GraphQL routing | LLM provider routing |
| Traditional rate limiting | Token-based rate limiting |
| API key lifecycle | LLM provider key management |
| Standard monitoring | AI usage and cost tracking |

## Cost Analysis

### Cost Comparison (Monthly)
| Approach | Monthly Cost | Infrastructure | Why So Different? |
|----------|--------------|----------------|------------------|
| **DIY Development** | $15,000+ | Kubernetes + Load Balancers | 6-12 months dev time, ongoing maintenance, dedicated ops team |
| **Apigee + Kubernetes** | $3,375 | GKE Cluster + Apigee License | $2,500 Apigee license + $875 cluster costs, always running |
| **Cloud Run AI Gateway** | $80 | Serverless (pay-per-request) | Only pay for actual request processing time (100ms billing) |

**Example: 1M requests/month breakdown:**
```
Traditional (Apigee + K8s):  Always-on infrastructure = $3,375
Cloud Run:                   1M × 500ms × $0.0000024 = $80
Savings:                     $3,295/month (97% reduction)
```

## Quick Start

### 1. Deploy
```bash
# Clone and configure
git clone <repository>
cd enterprise-ai-gateway

# Configure your environment
cp deployment/terraform/terraform.tfvars.example deployment/terraform/terraform.tfvars
# Edit: SSO settings, LLM provider keys, domain

# Deploy everything
make deploy-production
```

### 2. Integrate
```javascript
// Replace direct OpenAI calls
const response = await fetch('https://api.openai.com/v1/chat/completions', {
  headers: { 'Authorization': 'Bearer sk-...' }  // ❌ Direct API key
});

// With AI Gateway - use your SSO token instead
const response = await fetch('https://ai-gateway.company.com/v1/chat/completions', {
  headers: { 'Authorization': 'Bearer ' + userSSOToken }  // ✅ Enterprise auth
});
```

## Architecture

### Cloud Run + FastAPI Stack
```
Internet → Global Load Balancer → Cloud Run (FastAPI) → LLM Providers
              ↓                         ↓                    ↓
        [Cloud Armor DDoS]        [Automatic Scaling]   [Azure OpenAI]
        [SSL Termination]         [VPC Connector]       [AWS Bedrock]
        [Global CDN]              [Secret Manager]      [Google Vertex]
                                  [Memorystore Redis]
```

**Why Cloud Run + FastAPI works well for AI Gateway:**

**FastAPI Benefits:**
- Async/await native - Handle concurrent LLM requests efficiently
- Automatic API docs - Built-in Swagger/OpenAPI for integration
- Type safety - Pydantic models prevent runtime errors
- Streaming support - Native Server-Sent Events for real-time responses

**Cloud Run Benefits:**
- Instant scaling - 0→1000+ instances in seconds for traffic spikes
- Pay-per-request - Only pay for actual compute time (100ms granularity)
- Sub-second cold starts - Python + Cloud Run optimizations
- No infrastructure - No Kubernetes clusters or servers to manage

### Authentication Patterns

**SSO Integration (for humans):**
```javascript
const ssoToken = await googleAuth.getAccessToken();
const aiResponse = await aiGateway.chat(messages, { token: ssoToken });
```

**Service Accounts (for applications):**
```python
client = AIGatewayClient(
    account_id="backend-service-prod",
    secret=os.environ["AI_GATEWAY_SECRET"]
)
response = await client.chat_completion(messages)
```

**Network Trust (for internal services):**
```bash
curl https://ai-gateway.internal/v1/chat/completions \
  -H "X-Service-Name: recommendation-engine" \
  -d '{"model":"gpt-4","messages":[...]}'
```

## What's Included

### Production-Ready Application
- FastAPI application with async performance and automatic API docs
- Cloud Run deployment with instant scaling and pay-per-request pricing
- Multi-provider LLM integration (Azure OpenAI, AWS Bedrock, Google Vertex)
- Enterprise authentication (SSO, service accounts, network trust)
- Usage tracking, quotas, and cost management
- Comprehensive error handling and monitoring

### Infrastructure & Deployment
- Complete Terraform configurations for Google Cloud
- Docker containers with security hardening
- Load balancers, SSL certificates, and CDN
- Monitoring, alerting, and logging setup
- Security policies (Cloud Armor, VPC, IAM)

### Client Integration Examples
- JavaScript/React with SSO integration
- Python async client for backend services
- cURL examples for testing and debugging

### Documentation
- Step-by-step deployment instructions
- Architecture guides and best practices
- Security and compliance documentation  
- Troubleshooting and operations runbooks

## Common Questions

### "How does this compare to building our own?"
- **Development time**: 6-12 months → 1 day
- **Infrastructure**: Kubernetes clusters + load balancers → Cloud Run (serverless)
- **Operational overhead**: High (cluster management, scaling, monitoring) → Zero (fully managed)
- **Security compliance**: Months of implementation → Inherited from Google Cloud
- **Multi-provider support**: Complex integration work → FastAPI app with built-in providers

### "What about vendor lock-in?"
- Multi-provider from day one - Azure, AWS, Google supported
- Standard APIs - OpenAI-compatible, easy to migrate
- Open source approach - You own and control the code
- Cloud-agnostic patterns - Can be adapted to other cloud providers

### "How does this integrate with existing API platform?"
- Complementary, not competitive - Handles AI/LLM workloads specifically
- Uses existing auth systems - Plugs into your SSO, LDAP, etc.
- Standard observability - Prometheus metrics, structured logging
- API-first design - RESTful interfaces, standard HTTP patterns

## Next Steps

1. **[Read the Deployment Guide](ENTERPRISE-DEPLOYMENT-GUIDE.md)** for step-by-step instructions
2. **[Review the Architecture](ARCHITECTURE.md)** for technical details  
3. **[Check out Examples](examples/)** for integration patterns
4. **Deploy and test** in your environment

---

**Support:**
- **Documentation**: Complete guides in this repository
- **Issues**: Open GitHub issues for bugs or feature requests  
- **Discussions**: Use GitHub Discussions for questions

*Built for API teams who need AI infrastructure that's simple, secure, and cost-effective.*