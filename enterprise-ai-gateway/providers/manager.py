"""
LLM Provider Manager
Handles connections to Azure OpenAI, AWS Bedrock, and Google Vertex AI
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, AsyncGenerator, Any
import httpx
import boto3
from google.cloud import aiplatform
from google.oauth2 import service_account
import structlog

logger = structlog.get_logger()

class ProviderManager:
    """Manages connections and routing to LLM providers"""
    
    def __init__(self):
        self.providers = {}
        self.healthy_providers = set()
        self.last_health_check = {}
        
        # Provider configurations
        self.azure_config = {
            "enabled": os.environ.get("AZURE_OPENAI_ENABLED", "false") == "true",
            "endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
            "api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            "deployments": {
                "gpt-4": os.environ.get("AZURE_GPT4_DEPLOYMENT", "gpt-4"),
                "gpt-3.5-turbo": os.environ.get("AZURE_GPT35_DEPLOYMENT", "gpt-35-turbo"),
                "gpt-4-turbo": os.environ.get("AZURE_GPT4_TURBO_DEPLOYMENT", "gpt-4-turbo")
            }
        }
        
        self.bedrock_config = {
            "enabled": os.environ.get("AWS_BEDROCK_ENABLED", "false") == "true",
            "region": os.environ.get("AWS_REGION", "us-east-1"),
            "models": {
                "claude-2": "anthropic.claude-v2",
                "claude-instant": "anthropic.claude-instant-v1",
                "claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
                "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0"
            }
        }
        
        self.vertex_config = {
            "enabled": os.environ.get("VERTEX_AI_ENABLED", "false") == "true",
            "project": os.environ.get("GCP_PROJECT", ""),
            "location": os.environ.get("GCP_LOCATION", "us-central1"),
            "models": {
                "gemini-pro": "gemini-pro",
                "gemini-1.5-pro": "gemini-1.5-pro",
                "text-bison": "text-bison@001"
            }
        }
    
    async def initialize(self):
        """Initialize provider connections"""
        
        if self.azure_config["enabled"]:
            await self._initialize_azure()
        
        if self.bedrock_config["enabled"]:
            await self._initialize_bedrock()
        
        if self.vertex_config["enabled"]:
            await self._initialize_vertex()
        
        # Start health check loop
        asyncio.create_task(self._health_check_loop())
        
        logger.info(
            "provider_manager_initialized",
            enabled_providers=list(self.providers.keys())
        )
    
    async def _initialize_azure(self):
        """Initialize Azure OpenAI provider"""
        try:
            self.providers["azure"] = AzureOpenAIProvider(self.azure_config)
            await self._check_provider_health("azure")
            logger.info("azure_provider_initialized")
        except Exception as e:
            logger.error("azure_provider_init_failed", error=str(e))
    
    async def _initialize_bedrock(self):
        """Initialize AWS Bedrock provider"""
        try:
            self.providers["bedrock"] = BedrockProvider(self.bedrock_config)
            await self._check_provider_health("bedrock")
            logger.info("bedrock_provider_initialized")
        except Exception as e:
            logger.error("bedrock_provider_init_failed", error=str(e))
    
    async def _initialize_vertex(self):
        """Initialize Google Vertex AI provider"""
        try:
            self.providers["vertex"] = VertexAIProvider(self.vertex_config)
            await self._check_provider_health("vertex")
            logger.info("vertex_provider_initialized")
        except Exception as e:
            logger.error("vertex_provider_init_failed", error=str(e))
    
    async def select_provider(self, 
                            model: str, 
                            requested_provider: Optional[str] = None,
                            client_tier: str = "standard") -> str:
        """Select optimal provider for the request"""
        
        # If provider explicitly requested and available
        if requested_provider and requested_provider in self.healthy_providers:
            if await self._can_handle_model(requested_provider, model):
                return requested_provider
        
        # Find provider that can handle the model
        for provider_name, provider in self.providers.items():
            if provider_name in self.healthy_providers:
                if await self._can_handle_model(provider_name, model):
                    return provider_name
        
        # No healthy provider found
        available_providers = list(self.healthy_providers)
        raise Exception(f"No healthy provider found for model {model}. Available: {available_providers}")
    
    async def _can_handle_model(self, provider: str, model: str) -> bool:
        """Check if provider can handle the specified model"""
        
        if provider == "azure":
            return model in self.azure_config["deployments"]
        elif provider == "bedrock":
            return model in self.bedrock_config["models"]
        elif provider == "vertex":
            return model in self.vertex_config["models"]
        
        return False
    
    async def complete_chat(self,
                          provider: str,
                          messages: List[Dict],
                          model: str,
                          temperature: float = 0.7,
                          max_tokens: Optional[int] = None,
                          client_credentials: Dict = None) -> Dict:
        """Complete chat using specified provider"""
        
        if provider not in self.providers:
            raise Exception(f"Provider {provider} not available")
        
        if provider not in self.healthy_providers:
            raise Exception(f"Provider {provider} is not healthy")
        
        return await self.providers[provider].complete_chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            credentials=client_credentials
        )
    
    async def get_available_models(self) -> List[Dict]:
        """Get list of all available models across providers"""
        
        models = []
        
        for provider_name, provider in self.providers.items():
            if provider_name in self.healthy_providers:
                provider_models = await provider.get_models()
                for model in provider_models:
                    model["provider"] = provider_name
                    models.append(model)
        
        return models
    
    async def get_provider_status(self) -> Dict[str, Dict]:
        """Get status of all providers"""
        
        status = {}
        
        for provider_name, provider in self.providers.items():
            is_healthy = provider_name in self.healthy_providers
            last_check = self.last_health_check.get(provider_name)
            
            status[provider_name] = {
                "healthy": is_healthy,
                "last_health_check": last_check.isoformat() if last_check else None,
                "models": await provider.get_models() if is_healthy else []
            }
        
        return status
    
    async def _health_check_loop(self):
        """Periodic health check for all providers"""
        
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                tasks = []
                for provider_name in self.providers:
                    tasks.append(self._check_provider_health(provider_name))
                
                await asyncio.gather(*tasks, return_exceptions=True)
                
            except Exception as e:
                logger.error("health_check_loop_error", error=str(e))
    
    async def _check_provider_health(self, provider_name: str):
        """Check health of a specific provider"""
        
        try:
            provider = self.providers[provider_name]
            is_healthy = await provider.health_check()
            
            if is_healthy:
                if provider_name not in self.healthy_providers:
                    logger.info("provider_recovered", provider=provider_name)
                self.healthy_providers.add(provider_name)
            else:
                if provider_name in self.healthy_providers:
                    logger.warning("provider_unhealthy", provider=provider_name)
                self.healthy_providers.discard(provider_name)
            
            self.last_health_check[provider_name] = datetime.utcnow()
            
        except Exception as e:
            logger.error("provider_health_check_failed", provider=provider_name, error=str(e))
            self.healthy_providers.discard(provider_name)
    
    async def shutdown(self):
        """Cleanup resources"""
        
        for provider in self.providers.values():
            if hasattr(provider, 'close'):
                await provider.close()
        
        logger.info("provider_manager_shutdown")

# ============== PROVIDER IMPLEMENTATIONS ==============

class AzureOpenAIProvider:
    """Azure OpenAI provider implementation"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=f"{config['endpoint']}/openai/deployments",
            timeout=60.0,
            limits=httpx.Limits(max_keepalive_connections=20)
        )
    
    async def complete_chat(self, messages: List[Dict], model: str, 
                          temperature: float = 0.7, max_tokens: Optional[int] = None,
                          credentials: Dict = None) -> Dict:
        """Complete chat using Azure OpenAI"""
        
        deployment = self.config["deployments"].get(model)
        if not deployment:
            raise Exception(f"Model {model} not available in Azure")
        
        headers = credentials or {}
        headers.update({
            "Content-Type": "application/json",
            "api-version": self.config["api_version"]
        })
        
        payload = {
            "messages": messages,
            "temperature": temperature
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        response = await self.client.post(
            f"/{deployment}/chat/completions",
            headers=headers,
            json=payload
        )
        
        if response.status_code != 200:
            raise Exception(f"Azure OpenAI error: {response.status_code} {response.text}")
        
        return response.json()
    
    async def get_models(self) -> List[Dict]:
        """Get available Azure OpenAI models"""
        
        models = []
        for model_name, deployment in self.config["deployments"].items():
            models.append({
                "id": model_name,
                "object": "model",
                "owned_by": "azure-openai",
                "deployment": deployment
            })
        
        return models
    
    async def health_check(self) -> bool:
        """Check Azure OpenAI health"""
        
        try:
            # Try a simple completion
            headers = {
                "Content-Type": "application/json",
                "api-version": self.config["api_version"]
            }
            
            # Use first available deployment for health check
            deployment = list(self.config["deployments"].values())[0]
            
            payload = {
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 1
            }
            
            response = await self.client.post(
                f"/{deployment}/chat/completions",
                headers=headers,
                json=payload
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.debug("azure_health_check_failed", error=str(e))
            return False
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

class BedrockProvider:
    """AWS Bedrock provider implementation"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.session = None
    
    def _get_client(self, credentials: Dict = None):
        """Get Bedrock client with credentials"""
        
        if credentials:
            session = boto3.Session(
                aws_access_key_id=credentials.get("access_key"),
                aws_secret_access_key=credentials.get("secret_key"),
                region_name=self.config["region"]
            )
        else:
            # Use default credentials (IAM role, etc.)
            session = boto3.Session(region_name=self.config["region"])
        
        return session.client("bedrock-runtime")
    
    async def complete_chat(self, messages: List[Dict], model: str,
                          temperature: float = 0.7, max_tokens: Optional[int] = None,
                          credentials: Dict = None) -> Dict:
        """Complete chat using AWS Bedrock"""
        
        model_id = self.config["models"].get(model)
        if not model_id:
            raise Exception(f"Model {model} not available in Bedrock")
        
        client = self._get_client(credentials)
        
        # Convert messages to Claude format
        prompt = self._messages_to_claude_prompt(messages)
        
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "top_p": 1,
            "top_k": 250,
            "max_tokens_to_sample": max_tokens or 1000,
            "stop_sequences": ["\n\nHuman:"]
        }
        
        response = client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            body=json.dumps(payload)
        )
        
        result = json.loads(response["body"].read())
        
        # Convert to OpenAI format
        return {
            "id": f"bedrock-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "object": "chat.completion",
            "created": int(datetime.utcnow().timestamp()),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result["completion"]
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(result["completion"].split()),
                "total_tokens": len(prompt.split()) + len(result["completion"].split())
            }
        }
    
    def _messages_to_claude_prompt(self, messages: List[Dict]) -> str:
        """Convert OpenAI messages to Claude prompt format"""
        
        prompt = ""
        
        for message in messages:
            if message["role"] == "system":
                prompt += f"{message['content']}\n\n"
            elif message["role"] == "user":
                prompt += f"Human: {message['content']}\n\n"
            elif message["role"] == "assistant":
                prompt += f"Assistant: {message['content']}\n\n"
        
        prompt += "Assistant: "
        return prompt
    
    async def get_models(self) -> List[Dict]:
        """Get available Bedrock models"""
        
        models = []
        for model_name, model_id in self.config["models"].items():
            models.append({
                "id": model_name,
                "object": "model",
                "owned_by": "aws-bedrock",
                "model_id": model_id
            })
        
        return models
    
    async def health_check(self) -> bool:
        """Check Bedrock health"""
        
        try:
            client = self._get_client()
            # List available models as health check
            response = client.list_foundation_models()
            return "modelSummaries" in response
            
        except Exception as e:
            logger.debug("bedrock_health_check_failed", error=str(e))
            return False

class VertexAIProvider:
    """Google Vertex AI provider implementation"""
    
    def __init__(self, config: Dict):
        self.config = config
        if config["project"]:
            aiplatform.init(
                project=config["project"],
                location=config["location"]
            )
    
    async def complete_chat(self, messages: List[Dict], model: str,
                          temperature: float = 0.7, max_tokens: Optional[int] = None,
                          credentials: Dict = None) -> Dict:
        """Complete chat using Vertex AI"""
        
        model_name = self.config["models"].get(model)
        if not model_name:
            raise Exception(f"Model {model} not available in Vertex AI")
        
        # Import Vertex AI client
        from vertexai.generative_models import GenerativeModel
        
        vertex_model = GenerativeModel(model_name)
        
        # Convert messages to Vertex format
        prompt = self._messages_to_vertex_prompt(messages)
        
        response = vertex_model.generate_content(
            prompt,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens or 1000
            }
        )
        
        # Convert to OpenAI format
        return {
            "id": f"vertex-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "object": "chat.completion",
            "created": int(datetime.utcnow().timestamp()),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response.text
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(response.text.split()),
                "total_tokens": len(prompt.split()) + len(response.text.split())
            }
        }
    
    def _messages_to_vertex_prompt(self, messages: List[Dict]) -> str:
        """Convert OpenAI messages to Vertex AI prompt format"""
        
        prompt = ""
        
        for message in messages:
            if message["role"] == "system":
                prompt += f"System: {message['content']}\n"
            elif message["role"] == "user":
                prompt += f"User: {message['content']}\n"
            elif message["role"] == "assistant":
                prompt += f"Assistant: {message['content']}\n"
        
        return prompt
    
    async def get_models(self) -> List[Dict]:
        """Get available Vertex AI models"""
        
        models = []
        for model_name, model_id in self.config["models"].items():
            models.append({
                "id": model_name,
                "object": "model",
                "owned_by": "google-vertex",
                "model_id": model_id
            })
        
        return models
    
    async def health_check(self) -> bool:
        """Check Vertex AI health"""
        
        try:
            from vertexai.generative_models import GenerativeModel
            
            # Use first available model for health check
            model_name = list(self.config["models"].values())[0]
            model = GenerativeModel(model_name)
            
            # Simple test generation
            response = model.generate_content(
                "Hello",
                generation_config={"max_output_tokens": 1}
            )
            
            return bool(response.text)
            
        except Exception as e:
            logger.debug("vertex_health_check_failed", error=str(e))
            return False