export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  supporting_memories?: MemoryReference[];
}

export interface MemoryReference {
  memory_id: string;
  content: string;
  relevance_score?: number;
}

export interface ChatRequest {
  query: string;
  project_id?: string;
  session_id?: string;
}

export interface ChatResponse {
  response: string;
  supporting_memories: MemoryReference[];
  session_id: string;
}

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  api_version: string;
  database_connected: boolean;
  chromadb_connected: boolean;
  local_llm_available: boolean;
  timestamp: string;
}