/**
 * Enterprise LLM Proxy - JavaScript/React Integration Example
 * Shows how to integrate with SSO authentication
 */

// ============== GOOGLE OAUTH INTEGRATION ==============

class GoogleSSOClient {
  constructor(clientId) {
    this.clientId = clientId;
    this.apiBase = 'https://llm-proxy.company.com';
    this.googleAuth = null;
  }

  async initialize() {
    // Load Google OAuth library
    await this.loadGoogleAPI();
    
    this.googleAuth = window.gapi.auth2.init({
      client_id: this.clientId,
      scope: 'openid email profile'
    });
  }

  loadGoogleAPI() {
    return new Promise((resolve) => {
      if (window.gapi) {
        resolve();
        return;
      }

      const script = document.createElement('script');
      script.src = 'https://apis.google.com/js/api.js';
      script.onload = () => {
        window.gapi.load('auth2', resolve);
      };
      document.head.appendChild(script);
    });
  }

  async signIn() {
    const authInstance = this.googleAuth;
    const user = await authInstance.signIn();
    const authResponse = user.getAuthResponse();
    
    return {
      accessToken: authResponse.access_token,
      idToken: authResponse.id_token,
      expiresAt: Date.now() + (authResponse.expires_in * 1000),
      user: {
        id: user.getBasicProfile().getId(),
        name: user.getBasicProfile().getName(),
        email: user.getBasicProfile().getEmail(),
        picture: user.getBasicProfile().getImageUrl()
      }
    };
  }

  async signOut() {
    await this.googleAuth.signOut();
  }

  async refreshToken() {
    const user = this.googleAuth.currentUser.get();
    await user.reloadAuthResponse();
    const authResponse = user.getAuthResponse();
    
    return {
      accessToken: authResponse.access_token,
      expiresAt: Date.now() + (authResponse.expires_in * 1000)
    };
  }
}

// ============== LLM CLIENT ==============

class LLMProxyClient {
  constructor(apiBase = 'https://llm-proxy.company.com') {
    this.apiBase = apiBase;
    this.auth = null;
  }

  setAuth(auth) {
    this.auth = auth;
  }

  async ensureValidToken() {
    if (!this.auth) {
      throw new Error('Not authenticated. Call setAuth() first.');
    }

    // Check if token is expiring soon (within 5 minutes)
    if (this.auth.expiresAt - Date.now() < 5 * 60 * 1000) {
      console.log('Token expiring soon, refreshing...');
      this.auth = await this.refreshToken();
    }

    return this.auth.accessToken;
  }

  async chatCompletion(messages, options = {}) {
    const token = await this.ensureValidToken();
    
    const payload = {
      model: options.model || 'gpt-4',
      messages: messages,
      temperature: options.temperature || 0.7,
      max_tokens: options.maxTokens,
      stream: options.stream || false,
      provider: options.provider  // Optional: force specific provider
    };

    const response = await fetch(`${this.apiBase}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(`LLM API Error: ${error.error?.message || response.statusText}`);
    }

    if (options.stream) {
      return this.handleStreamingResponse(response);
    }

    const result = await response.json();
    return result;
  }

  async *handleStreamingResponse(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') {
              return;
            }

            try {
              const chunk = JSON.parse(data);
              yield chunk;
            } catch (e) {
              console.warn('Failed to parse streaming chunk:', data);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  async getAvailableModels() {
    const token = await this.ensureValidToken();
    
    const response = await fetch(`${this.apiBase}/v1/models`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch models: ${response.statusText}`);
    }

    return response.json();
  }

  async getProviderStatus() {
    const token = await this.ensureValidToken();
    
    const response = await fetch(`${this.apiBase}/v1/providers`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch providers: ${response.statusText}`);
    }

    return response.json();
  }
}

// ============== REACT HOOKS ==============

// React Hook for LLM integration
function useLLMProxy() {
  const [client, setClient] = React.useState(null);
  const [isAuthenticated, setIsAuthenticated] = React.useState(false);
  const [user, setUser] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const ssoClient = React.useRef(null);

  React.useEffect(() => {
    // Initialize Google SSO
    const initSSO = async () => {
      ssoClient.current = new GoogleSSOClient('your-google-client-id');
      await ssoClient.current.initialize();
    };
    
    initSSO();
  }, []);

  const signIn = async () => {
    try {
      setLoading(true);
      setError(null);

      const auth = await ssoClient.current.signIn();
      
      const llmClient = new LLMProxyClient();
      llmClient.setAuth(auth);
      
      setClient(llmClient);
      setUser(auth.user);
      setIsAuthenticated(true);
    } catch (err) {
      setError(err.message);
      console.error('Sign in failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const signOut = async () => {
    try {
      await ssoClient.current.signOut();
      setClient(null);
      setUser(null);
      setIsAuthenticated(false);
    } catch (err) {
      setError(err.message);
      console.error('Sign out failed:', err);
    }
  };

  const chatCompletion = async (messages, options = {}) => {
    if (!client) {
      throw new Error('Not authenticated');
    }

    try {
      setError(null);
      return await client.chatCompletion(messages, options);
    } catch (err) {
      setError(err.message);
      throw err;
    }
  };

  return {
    client,
    isAuthenticated,
    user,
    loading,
    error,
    signIn,
    signOut,
    chatCompletion
  };
}

// ============== REACT COMPONENT EXAMPLE ==============

function ChatInterface() {
  const { 
    isAuthenticated, 
    user, 
    loading, 
    error, 
    signIn, 
    signOut, 
    chatCompletion 
  } = useLLMProxy();

  const [messages, setMessages] = React.useState([]);
  const [input, setInput] = React.useState('');
  const [isTyping, setIsTyping] = React.useState(false);

  const sendMessage = async () => {
    if (!input.trim() || isTyping) return;

    const userMessage = { role: 'user', content: input };
    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInput('');
    setIsTyping(true);

    try {
      const response = await chatCompletion(newMessages, {
        model: 'gpt-4',
        temperature: 0.7
      });

      const assistantMessage = response.choices[0].message;
      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      console.error('Chat completion failed:', err);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request.'
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="login-container">
        <h2>Enterprise LLM Assistant</h2>
        <p>Sign in with your company account to continue</p>
        <button onClick={signIn} disabled={loading}>
          {loading ? 'Signing in...' : 'Sign in with Google'}
        </button>
        {error && <p className="error">{error}</p>}
      </div>
    );
  }

  return (
    <div className="chat-container">
      <header className="chat-header">
        <h2>LLM Assistant</h2>
        <div className="user-info">
          <img src={user.picture} alt="Profile" className="profile-pic" />
          <span>{user.name}</span>
          <button onClick={signOut}>Sign Out</button>
        </div>
      </header>

      <div className="messages">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <strong>{msg.role === 'user' ? 'You' : 'Assistant'}:</strong>
            <p>{msg.content}</p>
          </div>
        ))}
        {isTyping && (
          <div className="message assistant">
            <strong>Assistant:</strong>
            <p>Typing...</p>
          </div>
        )}
      </div>

      <div className="input-container">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="Type your message..."
          disabled={isTyping}
        />
        <button onClick={sendMessage} disabled={!input.trim() || isTyping}>
          Send
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}
    </div>
  );
}

// ============== STREAMING EXAMPLE ==============

function StreamingChatExample() {
  const { chatCompletion, isAuthenticated } = useLLMProxy();
  const [response, setResponse] = React.useState('');
  const [isStreaming, setIsStreaming] = React.useState(false);

  const startStreaming = async () => {
    if (!isAuthenticated) return;

    setResponse('');
    setIsStreaming(true);

    try {
      const messages = [
        { role: 'user', content: 'Write a short story about AI helping humans' }
      ];

      const stream = await chatCompletion(messages, { 
        stream: true,
        model: 'gpt-4'
      });

      for await (const chunk of stream) {
        if (chunk.choices?.[0]?.delta?.content) {
          setResponse(prev => prev + chunk.choices[0].delta.content);
        }
      }
    } catch (err) {
      console.error('Streaming failed:', err);
      setResponse('Error: ' + err.message);
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="streaming-example">
      <button onClick={startStreaming} disabled={!isAuthenticated || isStreaming}>
        {isStreaming ? 'Streaming...' : 'Start Streaming Response'}
      </button>
      
      <div className="streaming-response">
        <pre>{response}</pre>
        {isStreaming && <span className="cursor">▋</span>}
      </div>
    </div>
  );
}

// ============== EXPORT FOR MODULE USAGE ==============

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    GoogleSSOClient,
    LLMProxyClient,
    useLLMProxy
  };
}

// ============== USAGE EXAMPLES ==============

/*
// Basic usage
const ssoClient = new GoogleSSOClient('your-client-id');
await ssoClient.initialize();

const auth = await ssoClient.signIn();
const llmClient = new LLMProxyClient();
llmClient.setAuth(auth);

const response = await llmClient.chatCompletion([
  { role: 'user', content: 'Hello!' }
]);

console.log(response.choices[0].message.content);

// React usage
function MyApp() {
  return (
    <div>
      <ChatInterface />
      <StreamingChatExample />
    </div>
  );
}
*/