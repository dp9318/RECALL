import { useState, useEffect, useRef } from 'react';
import type { FormEvent, ChangeEvent } from 'react';
import { api, type ChatMessage, type ChatRequest, type ChatResponse, type MemoryReference, type Project } from '../api';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Avatar } from '../components/ui/Avatar';

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [sessionId, setSessionId] = useState<string>('');
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  useEffect(() => {
    // Load projects for context selector
    api.getProjects().then(res => setProjects(res.projects)).catch(console.error);
  }, []);
  
  const handleSend = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    
    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    };
    
    setMessages(prev => [...prev, userMessage]);
    const currentInput = input;
    setInput('');
    setLoading(true);
    setError(null);
    
    try {
      const request: ChatRequest = {
        query: currentInput,
        project_id: selectedProject || undefined,
        session_id: sessionId || undefined,
      };
      
      const response: ChatResponse = await api.sendChatMessage(request);
      
      const assistantMessage: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
        supporting_memories: response.supporting_memories,
      };
      
      setMessages(prev => [...prev, assistantMessage]);
      setSessionId(response.session_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
      // Add error message to chat
      const errorMessage: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content: `Sorry, I encountered an error: ${err instanceof Error ? err.message : 'Unknown error'}`,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };
  
  const handleNewChat = () => {
    setMessages([]);
    setSessionId('');
    setError(null);
  };
  
  return (
    <div className="h-full flex flex-col max-w-4xl mx-auto w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6 p-4 bg-surface rounded-xl border border-border">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Chat / Ask RECALL</h1>
          <p className="text-text-secondary mt-1">Query your persistent memory with natural language</p>
        </div>
        <div className="flex items-center gap-3">
          <Select
            value={selectedProject}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => setSelectedProject(e.target.value)}
            options={[
              { value: '', label: 'All Projects' },
              ...projects.map(p => ({ value: p.project_id, label: p.name })),
            ]}
            placeholder="Select project context"
            className="w-64"
          />
          <Button variant="outline" onClick={handleNewChat} disabled={messages.length === 0 && !loading}>
            <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Chat
          </Button>
        </div>
      </div>
      
      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-6 mb-6" role="log" aria-live="polite" aria-label="Chat messages">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <svg className="w-16 h-16 text-text-muted mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <h2 className="text-xl font-semibold text-text-primary mb-2">Start a conversation</h2>
            <p className="text-text-secondary max-w-md">
              Ask RECALL about your project memories, decisions, patterns, or any stored context.
              Select a project to narrow the search scope.
            </p>
            <div className="mt-6 flex flex-wrap gap-2 justify-center">
              {[
                'What did we decide about storage?',
                'Show me recent architecture decisions',
                'What are the active custom instructions?',
                'Any unresolved conflicts?',
              ].map((suggestion, i) => (
                <Button
                  key={i}
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setInput(suggestion);
                    handleSend(new Event('submit') as unknown as FormEvent<HTMLFormElement>);
                  }}
                >
                  {suggestion}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
            >
              <Avatar
                name={message.role === 'user' ? 'You' : 'RECALL'}
                size="sm"
                className="flex-shrink-0 mt-1"
              />
              <div className={`max-w-[80%] ${message.role === 'user' ? 'text-right' : ''}`}>
                <div
                  className={`
                    inline-block px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap
                    ${message.role === 'user'
                      ? 'bg-primary text-white rounded-tr-sm'
                      : 'bg-surface border border-border rounded-tl-sm'
                    }
                  `}
                >
                  {message.content}
                </div>
                <div className="flex items-center gap-2 mt-1.5 justify-end">
                  <time className="text-xs text-text-muted" dateTime={message.timestamp}>
                    {new Date(message.timestamp).toLocaleTimeString()}
                  </time>
                </div>
                
                {/* Supporting memories */}
                {message.supporting_memories && message.supporting_memories.length > 0 && (
                  <div className="mt-3 space-y-2" role="region" aria-label="Supporting memories">
                    {message.supporting_memories.map((mem, i) => (
                      <Card key={`${message.id}-${i}`} className="border-border/50">
                        <CardContent className="p-3">
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-sm text-text-primary flex-1">{mem.content}</p>
                            {mem.relevance_score && (
                              <Badge variant="outline" size="sm">
                                {(mem.relevance_score * 100).toFixed(0)}% relevant
                              </Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-2">
                            <Button variant="ghost" size="sm" asChild>
                              <a href={`/memories/${mem.memory_id}`} target="_blank" rel="noopener noreferrer">
                                View Memory
                              </a>
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>
      
      {/* Error display */}
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-error/10 border border-error/20 text-error text-sm" role="alert">
          {error}
        </div>
      )}
      
      {/* Input form */}
      <form onSubmit={handleSend} className="relative">
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
              placeholder="Ask RECALL anything about your project memory..."
              className={`
                w-full px-4 py-3 pr-12 rounded-xl border bg-surface text-text-primary
                placeholder:text-text-muted resize-none min-h-[56px] max-h-48
                focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent
                disabled:bg-gray-100 disabled:cursor-not-allowed
                transition-all duration-200
                ${error ? 'border-error' : 'border-border hover:border-primary/50'}
              `}
              rows={1}
              disabled={loading}
              aria-label="Chat input"
            />
            <Button
              type="submit"
              disabled={!input.trim() || loading}
              className="absolute right-2 top-1/2 -translate-y-1/2"
              aria-label={loading ? 'Sending...' : 'Send message'}
            >
              {loading ? (
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              )}
            </Button>
          </div>
        </div>
        <p className="text-xs text-text-muted mt-2 text-center">
          Press Enter to send, Shift+Enter for new line
        </p>
      </form>
    </div>
  );
}