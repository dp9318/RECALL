export interface Project {
  project_id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  memory_count: number;
  session_count: number;
}

export interface ProjectListResponse {
  projects: Project[];
  total: number;
}

export interface Session {
  session_id: string;
  project_id: string;
  project_name?: string;
  started_at: string;
  ended_at?: string;
  message_count: number;
  memory_captures: number;
}

export interface SessionListResponse {
  sessions: Session[];
  total: number;
}

export interface Stats {
  total_memories: number;
  active_memories: number;
  total_projects: number;
  total_sessions: number;
  total_instructions: number;
  active_instructions: number;
  unresolved_conflicts: number;
  semantic_index_status: 'healthy' | 'degraded' | 'rebuilding' | 'unavailable';
  last_indexed_at?: string;
  database_connected: boolean;
  chromadb_connected: boolean;
  local_llm_available: boolean;
}