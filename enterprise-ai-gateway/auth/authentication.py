"""
Enterprise Authentication Module for LLM Proxy
Separates client authentication from LLM provider credentials
"""

import os
import jwt
import json
import hashlib
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.cloud import secretmanager, firestore
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest
import boto3
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()

# ============== DATA MODELS ==============

@dataclass
class ClientIdentity:
    """Represents an authenticated client"""
    id: str
    name: str
    email: Optional[str]
    auth_method: str  # 'sso', 'service_account', 'internal_network'
    department: Optional[str]
    cost_center: Optional[str]
    quota_tier: str  # 'unlimited', 'high', 'standard', 'limited'
    permissions: list[str]
    metadata: dict

@dataclass
class UsageQuota:
    """Client usage quotas"""
    requests_per_minute: int
    requests_per_day: int
    tokens_per_day: int
    max_tokens_per_request: int
    allowed_models: list[str]
    allowed_providers: list[str]

# ============== CLIENT AUTHENTICATION ==============

class EnterpriseAuthenticator:
    """
    Handles client authentication to the proxy service.
    Supports SSO, service accounts, and internal network trust.
    """
    
    def __init__(self):
        self.project_id = os.environ.get("GCP_PROJECT", "")
        self.db = firestore.Client() if self.project_id else None
        self.security = HTTPBearer(auto_error=False)
        
        # SSO configuration
        self.sso_enabled = os.environ.get("SSO_ENABLED", "true") == "true"
        self.sso_provider = os.environ.get("SSO_PROVIDER", "google")  # google, okta, azure_ad
        self.sso_tenant = os.environ.get("SSO_TENANT", "")
        self.sso_client_id = os.environ.get("SSO_CLIENT_ID", "")
        
        # Network trust configuration
        self.trust_internal_network = os.environ.get("TRUST_INTERNAL_NETWORK", "false") == "true"
        self.internal_networks = os.environ.get("INTERNAL_NETWORKS", "10.0.0.0/8,172.16.0.0/12").split(",")
    
    async def authenticate_request(self, 
                                   request: Request,
                                   credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> ClientIdentity:
        """
        Main authentication entry point.
        Tries different auth methods in order of preference.
        """
        
        # 1. Try SSO token (preferred for humans)
        if credentials and credentials.scheme == "Bearer":
            try:
                return await self.verify_sso_token(credentials.credentials)
            except Exception as e:
                logger.debug("sso_auth_failed", error=str(e))
        
        # 2. Try service account (preferred for applications)
        if service_account_header := request.headers.get("X-Service-Account"):
            try:
                return await self.verify_service_account(service_account_header, request)
            except Exception as e:
                logger.debug("service_account_auth_failed", error=str(e))
        
        # 3. Try internal network trust (for internal services)
        if self.trust_internal_network:
            if client := await self.verify_internal_network(request):
                return client
        
        # 4. No valid authentication found
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please use SSO token or service account.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    async def verify_sso_token(self, token: str) -> ClientIdentity:
        """Verify SSO token from enterprise identity provider"""
        
        if not self.sso_enabled:
            raise HTTPException(403, "SSO authentication not enabled")
        
        if self.sso_provider == "google":
            return await self._verify_google_token(token)
        elif self.sso_provider == "okta":
            return await self._verify_okta_token(token)
        elif self.sso_provider == "azure_ad":
            return await self._verify_azure_ad_token(token)
        else:
            raise HTTPException(500, f"Unknown SSO provider: {self.sso_provider}")
    
    async def _verify_google_token(self, token: str) -> ClientIdentity:
        """Verify Google OAuth2 token"""
        try:
            # Verify token with Google
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://oauth2.googleapis.com/tokeninfo?access_token={token}"
                )
                
                if response.status_code != 200:
                    raise HTTPException(401, "Invalid Google token")
                
                token_info = response.json()
                
                # Verify audience
                if token_info.get("aud") != self.sso_client_id:
                    raise HTTPException(401, "Invalid token audience")
                
                # Get user info
                user_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if user_response.status_code != 200:
                    raise HTTPException(401, "Could not fetch user info")
                
                user_info = user_response.json()
                
                # Look up user in database for additional metadata
                user_doc = await self._get_user_metadata(user_info["email"])
                
                return ClientIdentity(
                    id=user_info["id"],
                    name=user_info["name"],
                    email=user_info["email"],
                    auth_method="sso_google",
                    department=user_doc.get("department"),
                    cost_center=user_doc.get("cost_center"),
                    quota_tier=user_doc.get("quota_tier", "standard"),
                    permissions=user_doc.get("permissions", ["llm.chat"]),
                    metadata={"picture": user_info.get("picture")}
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("google_token_verification_failed", error=str(e))
            raise HTTPException(401, "Token verification failed")
    
    async def verify_service_account(self, auth_header: str, request: Request) -> ClientIdentity:
        """
        Verify service account credentials.
        Format: 'ServiceAccount <account_id>:<signature>'
        """
        try:
            if not auth_header.startswith("ServiceAccount "):
                raise HTTPException(401, "Invalid service account format")
            
            parts = auth_header[15:].split(":")
            if len(parts) != 2:
                raise HTTPException(401, "Invalid service account credentials")
            
            account_id, signature = parts
            
            # Get service account from database
            account_doc = await self._get_service_account(account_id)
            if not account_doc:
                raise HTTPException(401, "Unknown service account")
            
            # Verify signature
            expected_signature = self._generate_signature(
                account_id,
                account_doc["secret"],
                request.method,
                str(request.url),
                request.headers.get("X-Request-Timestamp", "")
            )
            
            if signature != expected_signature:
                raise HTTPException(401, "Invalid service account signature")
            
            # Check timestamp to prevent replay attacks
            if timestamp := request.headers.get("X-Request-Timestamp"):
                request_time = datetime.fromisoformat(timestamp)
                if abs((datetime.utcnow() - request_time).total_seconds()) > 300:
                    raise HTTPException(401, "Request timestamp too old")
            
            return ClientIdentity(
                id=account_id,
                name=account_doc["name"],
                email=account_doc.get("email"),
                auth_method="service_account",
                department=account_doc.get("department"),
                cost_center=account_doc.get("cost_center"),
                quota_tier=account_doc.get("quota_tier", "high"),
                permissions=account_doc.get("permissions", ["llm.chat"]),
                metadata={"application": account_doc.get("application")}
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("service_account_verification_failed", error=str(e))
            raise HTTPException(401, "Service account verification failed")
    
    def _generate_signature(self, account_id: str, secret: str, method: str, url: str, timestamp: str) -> str:
        """Generate HMAC signature for service account"""
        import hmac
        
        message = f"{method}:{url}:{timestamp}:{account_id}"
        signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    async def _get_user_metadata(self, email: str) -> dict:
        """Get additional user metadata from database"""
        if not self.db:
            return {}
        
        try:
            doc = self.db.collection("users").document(email).get()
            return doc.to_dict() if doc.exists else {}
        except Exception as e:
            logger.warning("user_metadata_fetch_failed", email=email, error=str(e))
            return {}
    
    async def _get_service_account(self, account_id: str) -> Optional[dict]:
        """Get service account from database"""
        if not self.db:
            # Fallback to environment variables for demo
            if account_id == os.environ.get("DEMO_SERVICE_ACCOUNT_ID"):
                return {
                    "name": "Demo Service Account",
                    "secret": os.environ.get("DEMO_SERVICE_ACCOUNT_SECRET"),
                    "quota_tier": "high",
                    "permissions": ["llm.chat"]
                }
            return None
        
        try:
            doc = self.db.collection("service_accounts").document(account_id).get()
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            logger.error("service_account_fetch_failed", account_id=account_id, error=str(e))
            return None

# ============== PROVIDER CREDENTIALS ==============

class LLMProviderCredentials:
    """
    Manages credentials for LLM providers.
    These are NEVER exposed to clients - only used internally.
    """
    
    def __init__(self):
        self.project_id = os.environ.get("GCP_PROJECT", "")
        self.secret_client = secretmanager.SecretManagerServiceClient() if self.project_id else None
        
        # Cache credentials at startup
        self._azure_key = None
        self._aws_credentials = None
        self._gcp_credentials = None
        self._load_credentials()
    
    def _load_credentials(self):
        """Load all provider credentials at startup"""
        
        # Azure OpenAI
        if os.environ.get("AZURE_OPENAI_ENABLED") == "true":
            self._azure_key = self._get_secret("azure-openai-key")
            logger.info("azure_credentials_loaded")
        
        # AWS Bedrock
        if os.environ.get("AWS_BEDROCK_ENABLED") == "true":
            aws_key = self._get_secret("aws-access-key")
            aws_secret = self._get_secret("aws-secret-key")
            self._aws_credentials = {
                "access_key": aws_key,
                "secret_key": aws_secret,
                "region": os.environ.get("AWS_REGION", "us-east-1")
            }
            logger.info("aws_credentials_loaded")
        
        # Google Vertex AI
        if os.environ.get("VERTEX_AI_ENABLED") == "true":
            # Vertex uses the service account credentials automatically
            self._gcp_credentials = True
            logger.info("gcp_credentials_loaded")
    
    def _get_secret(self, secret_id: str) -> str:
        """Retrieve secret from Secret Manager"""
        
        # Try Secret Manager first
        if self.secret_client and self.project_id:
            try:
                name = f"projects/{self.project_id}/secrets/{secret_id}/versions/latest"
                response = self.secret_client.access_secret_version(request={"name": name})
                return response.payload.data.decode("UTF-8")
            except Exception as e:
                logger.warning("secret_manager_fetch_failed", secret_id=secret_id, error=str(e))
        
        # Fallback to environment variables
        env_var = secret_id.upper().replace("-", "_")
        if value := os.environ.get(env_var):
            return value
        
        logger.error("secret_not_found", secret_id=secret_id)
        return ""
    
    async def get_provider_auth(self, provider: str) -> dict:
        """Get authentication for a specific provider"""
        if provider == "azure":
            return {"api-key": self._azure_key}
        elif provider == "bedrock":
            return self._aws_credentials
        elif provider == "vertex":
            return {}  # Uses service account automatically
        else:
            raise ValueError(f"Unknown provider: {provider}")

# ============== DEPENDENCY INJECTION ==============

# Global instances (initialized in main.py)
authenticator: Optional[EnterpriseAuthenticator] = None
provider_credentials: Optional[LLMProviderCredentials] = None

def init_auth():
    """Initialize authentication components"""
    global authenticator, provider_credentials
    
    authenticator = EnterpriseAuthenticator()
    provider_credentials = LLMProviderCredentials()
    
    logger.info("authentication_initialized")

async def get_current_client(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> ClientIdentity:
    """FastAPI dependency to get current authenticated client"""
    if not authenticator:
        raise HTTPException(500, "Authentication not initialized")
    
    return await authenticator.authenticate_request(request, credentials)