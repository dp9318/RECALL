import type {
  Memory,
  MemoryListResponse,
  MemoryQuery,
  CustomInstruction,
  CustomInstructionListResponse,
  CreateCustomInstructionRequest,
  UpdateCustomInstructionRequest,
  Conflict,
  ConflictListResponse,
  Project,
  ProjectListResponse,
  CreateProjectRequest,
  Session,
  SessionListResponse,
  CreateSessionRequest,
  Stats,
  ChatRequest,
  ChatResponse,
  HealthStatus,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

export function createApiError(message: string, status: number, response?: Response): Error {
  const error = new Error(message);
  (error as Error & { status: number; response?: Response }).status = status;
  (error as Error & { status: number; response?: Response }).response = response;
  return error;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw createApiError(
      `API error: ${response.status} ${response.statusText} - ${errorText}`,
      response.status,
      response
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json();
}

const apiClient = {
  // Health
  async getHealth(): Promise<HealthStatus> {
    const response = await fetch(`${API_BASE_URL}/health`);
    return handleResponse(response);
  },

  // Memories
  async getMemories(query: MemoryQuery = {}): Promise<MemoryListResponse> {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        params.append(key, String(value));
      }
    });
    const response = await fetch(`${API_BASE_URL}/memories?${params.toString()}`);
    return handleResponse(response);
  },

  async getMemory(id: string): Promise<Memory> {
    const response = await fetch(`${API_BASE_URL}/memories/${id}`);
    return handleResponse(response);
  },

  async createMemory(memory: Omit<Memory, 'memory_id' | 'created_at' | 'updated_at'>): Promise<Memory> {
    const response = await fetch(`${API_BASE_URL}/memories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(memory),
    });
    return handleResponse(response);
  },

  async updateMemory(id: string, updates: Partial<Memory>): Promise<Memory> {
    const response = await fetch(`${API_BASE_URL}/memories/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    return handleResponse(response);
  },

  async deleteMemory(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/memories/${id}`, {
      method: 'DELETE',
    });
    return handleResponse(response);
  },

  // Custom Instructions
  async getCustomInstructions(projectId?: string): Promise<CustomInstructionListResponse> {
    const params = projectId ? `?project_id=${projectId}` : '';
    const response = await fetch(`${API_BASE_URL}/custom-instructions${params}`);
    return handleResponse(response);
  },

  async createCustomInstruction(request: CreateCustomInstructionRequest): Promise<CustomInstruction> {
    const response = await fetch(`${API_BASE_URL}/custom-instructions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    return handleResponse(response);
  },

  async updateCustomInstruction(id: string, updates: UpdateCustomInstructionRequest): Promise<CustomInstruction> {
    const response = await fetch(`${API_BASE_URL}/custom-instructions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    return handleResponse(response);
  },

  async deleteCustomInstruction(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/custom-instructions/${id}`, {
      method: 'DELETE',
    });
    return handleResponse(response);
  },

  // Conflicts
  async getConflicts(projectId?: string): Promise<ConflictListResponse> {
    const params = projectId ? `?project_id=${projectId}` : '';
    const response = await fetch(`${API_BASE_URL}/conflicts${params}`);
    return handleResponse(response);
  },

  // Projects
  async getProjects(): Promise<ProjectListResponse> {
    const response = await fetch(`${API_BASE_URL}/projects`);
    return handleResponse(response);
  },

  async createProject(request: CreateProjectRequest): Promise<Project> {
    const response = await fetch(`${API_BASE_URL}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    return handleResponse(response);
  },

  // Sessions
  async getSessions(projectId?: string): Promise<SessionListResponse> {
    const params = projectId ? `?project_id=${projectId}` : '';
    const response = await fetch(`${API_BASE_URL}/sessions${params}`);
    return handleResponse(response);
  },

  async createSession(request: CreateSessionRequest): Promise<Session> {
    const response = await fetch(`${API_BASE_URL}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    return handleResponse(response);
  },

  // Stats
  async getStats(): Promise<Stats> {
    const response = await fetch(`${API_BASE_URL}/stats`);
    return handleResponse(response);
  },

  // Chat
  async sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
    const response = await fetch(`${API_BASE_URL}/context/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    return handleResponse(response);
  },

  // Context compact
  async compactContext(projectId: string): Promise<{ success: boolean; message: string }> {
    const response = await fetch(`${API_BASE_URL}/context/compact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId }),
    });
    return handleResponse(response);
  },
};

export default apiClient;
export type { Memory, MemoryListResponse, MemoryQuery } from '../types';