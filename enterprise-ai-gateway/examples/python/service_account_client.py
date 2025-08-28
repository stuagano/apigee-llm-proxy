"""
Enterprise LLM Proxy - Python Service Account Client
Example of how to integrate backend services using service account authentication
"""

import os
import hmac
import hashlib
import base64
import json
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional, AsyncGenerator
import httpx
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ServiceAccountAuth:
    """Handles service account authentication for LLM Proxy"""
    
    def __init__(self, account_id: str, secret: str):
        self.account_id = account_id
        self.secret = secret
    
    def generate_signature(self, method: str, url: str, timestamp: str) -> str:
        """Generate HMAC-SHA256 signature for service account authentication"""
        message = f"{method}:{url}:{timestamp}:{self.account_id}"
        signature = hmac.new(
            self.secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def get_auth_headers(self, method: str, url: str) -> Dict[str, str]:
        """Get authentication headers for a request"""
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        signature = self.generate_signature(method, url, timestamp)
        
        return {
            'X-Service-Account': f'ServiceAccount {self.account_id}:{signature}',
            'X-Request-Timestamp': timestamp,
            'Content-Type': 'application/json'
        }


class LLMProxyClient:
    """Client for Enterprise LLM Proxy with service account authentication"""
    
    def __init__(
        self,
        base_url: str,
        account_id: str,
        secret: str,
        timeout: float = 60.0
    ):
        self.base_url = base_url.rstrip('/')
        self.auth = ServiceAccountAuth(account_id, secret)
        
        # Create HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
        
        logger.info(f"Initialized LLM Proxy client for {base_url}")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    async def health_check(self) -> Dict:
        """Check service health"""
        response = await self.client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    async def get_available_models(self) -> List[Dict]:
        """Get list of available models for this service account"""
        url = f"{self.base_url}/v1/models"
        headers = self.auth.get_auth_headers('GET', '/v1/models')
        
        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        return result.get('data', [])
    
    async def get_provider_status(self) -> Dict:
        """Get status of LLM providers"""
        url = f"{self.base_url}/v1/providers"
        headers = self.auth.get_auth_headers('GET', '/v1/providers')
        
        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        
        return response.json()
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
        stream: bool = False
    ) -> Dict:
        """
        Complete a chat conversation
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (e.g., 'gpt-4', 'claude-2', 'gemini-pro')
            temperature: Creativity level (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            provider: Optional specific provider ('azure', 'bedrock', 'vertex')
            stream: Whether to stream the response
            
        Returns:
            Chat completion response or async generator for streaming
        """
        url = f"{self.base_url}/v1/chat/completions"
        headers = self.auth.get_auth_headers('POST', '/v1/chat/completions')
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        if provider:
            payload["provider"] = provider
        
        logger.info(f"Sending chat completion request: model={model}, messages={len(messages)}")
        
        if stream:
            return self._stream_completion(url, headers, payload)
        else:
            response = await self.client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            # Log usage information
            if 'usage' in result:
                usage = result['usage']
                logger.info(
                    f"Chat completion: {usage.get('total_tokens', 0)} tokens, "
                    f"latency={result.get('metadata', {}).get('latency_ms', 0)}ms"
                )
            
            return result
    
    async def _stream_completion(
        self, 
        url: str, 
        headers: Dict[str, str], 
        payload: Dict
    ) -> AsyncGenerator[Dict, None]:
        """Handle streaming chat completion"""
        
        async with self.client.stream('POST', url, headers=headers, json=payload) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    data = line[6:]  # Remove 'data: ' prefix
                    
                    if data == '[DONE]':
                        break
                    
                    try:
                        chunk = json.loads(data)
                        yield chunk
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse streaming chunk: {data}")
                        continue
    
    async def simple_completion(self, prompt: str, model: str = "gpt-4") -> str:
        """Simple text completion - just returns the response text"""
        messages = [{"role": "user", "content": prompt}]
        
        response = await self.chat_completion(messages, model=model)
        return response['choices'][0]['message']['content']
    
    async def conversation(
        self, 
        conversation_history: List[Dict[str, str]], 
        user_message: str,
        model: str = "gpt-4"
    ) -> tuple[str, List[Dict[str, str]]]:
        """
        Continue a conversation and return both response and updated history
        
        Returns:
            (response_text, updated_conversation_history)
        """
        # Add user message to history
        messages = conversation_history + [{"role": "user", "content": user_message}]
        
        response = await self.chat_completion(messages, model=model)
        assistant_message = response['choices'][0]['message']['content']
        
        # Update conversation history
        updated_history = messages + [{"role": "assistant", "content": assistant_message}]
        
        return assistant_message, updated_history


# ============== USAGE EXAMPLES ==============

async def basic_example():
    """Basic usage example"""
    
    # Initialize client with service account credentials
    async with LLMProxyClient(
        base_url="https://llm-proxy.company.com",
        account_id="backend-service-prod",
        secret="your-service-account-secret"
    ) as client:
        
        # Check health
        health = await client.health_check()
        print(f"Service health: {health}")
        
        # Get available models
        models = await client.get_available_models()
        print(f"Available models: {[m['id'] for m in models]}")
        
        # Simple completion
        response = await client.simple_completion(
            "Explain quantum computing in simple terms"
        )
        print(f"Response: {response}")


async def conversation_example():
    """Multi-turn conversation example"""
    
    async with LLMProxyClient(
        base_url="https://llm-proxy.company.com",
        account_id="backend-service-prod", 
        secret="your-service-account-secret"
    ) as client:
        
        # Start conversation
        history = [
            {"role": "system", "content": "You are a helpful coding assistant."}
        ]
        
        # First user message
        response1, history = await client.conversation(
            history, 
            "How do I create a REST API in Python?",
            model="gpt-4"
        )
        print(f"Assistant: {response1}")
        
        # Follow-up question
        response2, history = await client.conversation(
            history,
            "What about error handling?",
            model="gpt-4"
        )
        print(f"Assistant: {response2}")
        
        # Show full conversation history
        print("\nFull conversation:")
        for msg in history:
            print(f"{msg['role']}: {msg['content'][:100]}...")


async def streaming_example():
    """Streaming response example"""
    
    async with LLMProxyClient(
        base_url="https://llm-proxy.company.com",
        account_id="backend-service-prod",
        secret="your-service-account-secret"
    ) as client:
        
        messages = [
            {"role": "user", "content": "Write a short poem about technology"}
        ]
        
        print("Streaming response:")
        response_text = ""
        
        stream = await client.chat_completion(messages, stream=True)
        async for chunk in stream:
            if chunk.get('choices') and chunk['choices'][0].get('delta', {}).get('content'):
                content = chunk['choices'][0]['delta']['content']
                response_text += content
                print(content, end='', flush=True)
        
        print(f"\n\nComplete response length: {len(response_text)} characters")


async def multi_provider_example():
    """Example using different providers"""
    
    async with LLMProxyClient(
        base_url="https://llm-proxy.company.com",
        account_id="backend-service-prod",
        secret="your-service-account-secret"
    ) as client:
        
        prompt = "What is the capital of France?"
        
        # Try different providers
        providers = ['azure', 'bedrock', 'vertex']
        
        for provider in providers:
            try:
                response = await client.simple_completion(
                    prompt, 
                    model="gpt-4" if provider == 'azure' else "claude-2"
                )
                print(f"{provider}: {response}")
                
            except Exception as e:
                print(f"{provider} failed: {e}")


async def batch_processing_example():
    """Process multiple requests efficiently"""
    
    async with LLMProxyClient(
        base_url="https://llm-proxy.company.com",
        account_id="backend-service-prod",
        secret="your-service-account-secret"
    ) as client:
        
        # List of prompts to process
        prompts = [
            "Summarize: The quick brown fox jumps over the lazy dog.",
            "Translate to French: Hello, how are you?",
            "Generate a creative title for a blog post about AI.",
            "Write a haiku about programming."
        ]
        
        # Process all prompts concurrently
        tasks = [
            client.simple_completion(prompt, model="gpt-3.5-turbo") 
            for prompt in prompts
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Request {i+1} failed: {result}")
            else:
                print(f"Request {i+1}: {result}")


# ============== CONFIGURATION HELPERS ==============

def load_config_from_env() -> tuple[str, str, str]:
    """Load configuration from environment variables"""
    
    base_url = os.getenv('LLM_PROXY_URL', 'https://llm-proxy.company.com')
    account_id = os.getenv('LLM_PROXY_ACCOUNT_ID')
    secret = os.getenv('LLM_PROXY_SECRET')
    
    if not account_id or not secret:
        raise ValueError(
            "Missing required environment variables: "
            "LLM_PROXY_ACCOUNT_ID and LLM_PROXY_SECRET"
        )
    
    return base_url, account_id, secret


def create_client_from_env() -> LLMProxyClient:
    """Create client using environment variables"""
    base_url, account_id, secret = load_config_from_env()
    return LLMProxyClient(base_url, account_id, secret)


# ============== CLI INTERFACE ==============

async def cli_interface():
    """Simple CLI for testing the client"""
    
    try:
        base_url, account_id, secret = load_config_from_env()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please set LLM_PROXY_ACCOUNT_ID and LLM_PROXY_SECRET environment variables")
        return
    
    async with LLMProxyClient(base_url, account_id, secret) as client:
        print("Enterprise LLM Proxy - CLI Interface")
        print("Type 'quit' to exit\n")
        
        conversation_history = []
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    break
                
                if not user_input:
                    continue
                
                print("Assistant: ", end='', flush=True)
                
                # Stream the response
                messages = conversation_history + [{"role": "user", "content": user_input}]
                
                response_text = ""
                stream = await client.chat_completion(messages, stream=True)
                
                async for chunk in stream:
                    if chunk.get('choices') and chunk['choices'][0].get('delta', {}).get('content'):
                        content = chunk['choices'][0]['delta']['content']
                        response_text += content
                        print(content, end='', flush=True)
                
                print()  # New line after response
                
                # Update conversation history
                conversation_history = messages + [{"role": "assistant", "content": response_text}]
                
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'cli':
        # Run CLI interface
        asyncio.run(cli_interface())
    else:
        # Run examples
        print("Running examples...")
        asyncio.run(basic_example())
        print("\n" + "="*50 + "\n")
        asyncio.run(conversation_example())
        print("\n" + "="*50 + "\n")
        asyncio.run(streaming_example())
        print("\n" + "="*50 + "\n")
        asyncio.run(batch_processing_example())