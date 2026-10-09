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

// Mock data
const mockMemories: Memory[] = [
  {
    memory_id: 'mem-001',
    project_id: 'proj-001',
    project_name: 'RECALL Core',
    memory_type: 'decision',
    content: 'SQLite is the canonical source of truth for all persistent data. ChromaDB is derived and rebuildable.',
    status: 'active',
    importance: 95,
    provenance: 'Architecture decision recorded during initial design phase',
    lineage: {},
    created_at: '2026-01-15T10:30:00Z',
    updated_at: '2026-01-15T10:30:00Z',
    tags: ['architecture', 'database', 'core'],
  },
  {
    memory_id: 'mem-002',
    project_id: 'proj-001',
    project_name: 'RECALL Core',
    memory_type: 'fact',
    content: 'The local LLM (1B-3B parameters) is used only for bounded conflict arbitration, never for direct memory mutation.',
    status: 'active',
    importance: 90,
    provenance: 'PRD section 5: Conflict Resolution',
    lineage: {},
    created_at: '2026-01-16T14:20:00Z',
    updated_at: '2026-01-16T14:20:00Z',
    tags: ['llm', 'conflict', 'architecture'],
  },
  {
    memory_id: 'mem-003',
    project_id: 'proj-001',
    project_name: 'RECALL Core',
    memory_type: 'pattern',
    content: 'Memory records should always include provenance/source reference and lineage metadata for traceability.',
    status: 'active',
    importance: 85,
    provenance: 'Development rules documented in ARCHITECTURE.md',
    lineage: {},
    created_at: '2026-01-18T09:15:00Z',
    updated_at: '2026-01-18T09:15:00Z',
    tags: ['pattern', 'traceability', 'metadata'],
  },
  {
    memory_id: 'mem-004',
    project_id: 'proj-002',
    project_name: 'Frontend Dashboard',
    memory_type: 'decision',
    content: 'Frontend uses React + Tailwind CSS + Vite. API communication through HTTP/JSON only.',
    status: 'active',
    importance: 88,
    provenance: 'TECH_STACK.md and FRONTEND.md module contract',
    lineage: {},
    created_at: '2026-02-01T11:00:00Z',
    updated_at: '2026-02-01T11:00:00Z',
    tags: ['frontend', 'tech-stack', 'react'],
  },
  {
    memory_id: 'mem-005',
    project_id: 'proj-002',
    project_name: 'Frontend Dashboard',
    memory_type: 'constraint',
    content: 'Frontend must never directly access SQLite, ChromaDB, or the local LLM. All operations through API contracts.',
    status: 'active',
    importance: 92,
    provenance: 'DEVELOPMENT_RULES.md - Frontend Rules section',
    lineage: {},
    created_at: '2026-02-03T16:45:00Z',
    updated_at: '2026-02-03T16:45:00Z',
    tags: ['constraint', 'security', 'architecture'],
  },
  {
    memory_id: 'mem-006',
    project_id: 'proj-001',
    project_name: 'RECALL Core',
    memory_type: 'preference',
    content: 'Prefer small, focused dependencies. Do not add another primary database or memory index without ADR approval.',
    status: 'active',
    importance: 75,
    provenance: 'TECH_STACK.md - Dependency Discipline',
    lineage: {},
    created_at: '2026-01-20T13:30:00Z',
    updated_at: '2026-01-20T13:30:00Z',
    tags: ['dependency', 'architecture', 'guidelines'],
  },
];

const mockInstructions: CustomInstruction[] = [
  {
    instruction_id: 'inst-001',
    scope: 'global',
    content: 'Always preserve memory lineage and provenance. Never delete historical evidence without explicit user confirmation.',
    active: true,
    created_at: '2026-01-10T08:00:00Z',
    updated_at: '2026-01-10T08:00:00Z',
    version: 1,
  },
  {
    instruction_id: 'inst-002',
    scope: 'project',
    project_id: 'proj-001',
    project_name: 'RECALL Core',
    content: 'When resolving conflicts, prefer explicit user instructions over inferred memory. Use local LLM only as last resort.',
    active: true,
    created_at: '2026-01-12T10:00:00Z',
    updated_at: '2026-01-12T10:00:00Z',
    version: 1,
  },
  {
    instruction_id: 'inst-003',
    scope: 'project',
    project_id: 'proj-002',
    project_name: 'Frontend Dashboard',
    content: 'Dashboard UI should prioritize clarity over density. Use clear loading, empty, and error states for all data views.',
    active: false,
    created_at: '2026-02-01T09:00:00Z',
    updated_at: '2026-02-01T09:00:00Z',
    version: 1,
  },
];

interface ConflictMemory {
  memory_id: string;
  content: string;
  status: 'preferred' | 'superseded' | 'conflicting' | 'abstained';
  confidence?: number;
}

interface ConflictResolution {
  preferred_memories: string[];
  superseded_memories: string[];
  reason: string;
  deterministic: boolean;
  local_model_used: boolean;
  confidence?: number;
}

const mockConflicts: Conflict[] = [
  {
    conflict_id: 'conf-001',
    project_id: 'proj-001',
    project_name: 'RECALL Core',
    status: 'resolved',
    conflicting_memories: [
      { memory_id: 'mem-001', content: 'SQLite is the canonical source of truth...', status: 'preferred', confidence: 0.98 },
      { memory_id: 'mem-007', content: 'ChromaDB should be the primary database for all queries...', status: 'superseded', confidence: 0.12 },
    ],
    resolution: {
      preferred_memories: ['mem-001'],
      superseded_memories: ['mem-007'],
      reason: 'Explicit architecture decision in ARCHITECTURE.md establishes SQLite as canonical. ChromaDB is derived.',
      deterministic: true,
      local_model_used: false,
      confidence: 0.98,
    },
    detected_at: '2026-01-15T11:00:00Z',
    resolved_at: '2026-01-15T11:05:00Z',
  },
  {
    conflict_id: 'conf-002',
    project_id: 'proj-001',
    project_name: 'RECALL Core',
    status: 'unresolved',
    conflicting_memories: [
      { memory_id: 'mem-008', content: 'Use PostgreSQL for better concurrent access...', status: 'conflicting', confidence: 0.55 },
      { memory_id: 'mem-009', content: 'Keep SQLite for simplicity and portability...', status: 'conflicting', confidence: 0.52 },
    ],
    resolution: undefined,
    detected_at: '2026-02-10T14:30:00Z',
  },
  {
    conflict_id: 'conf-003',
    project_id: 'proj-002',
    project_name: 'Frontend Dashboard',
    status: 'partially_resolved',
    conflicting_memories: [
      { memory_id: 'mem-010', content: 'Use Redux for global state management...', status: 'superseded', confidence: 0.35 },
      { memory_id: 'mem-011', content: 'Use React Context + hooks for simpler state...', status: 'preferred', confidence: 0.72 },
    ],
    resolution: {
      preferred_memories: ['mem-011'],
      superseded_memories: ['mem-010'],
      reason: 'Project scope instruction prefers simpler React patterns. Local model used for final arbitration.',
      deterministic: false,
      local_model_used: true,
      confidence: 0.72,
    },
    detected_at: '2026-02-05T10:00:00Z',
    resolved_at: '2026-02-05T10:15:00Z',
  },
];

const mockProjects: Project[] = [
  {
    project_id: 'proj-001',
    name: 'RECALL Core',
    description: 'Core memory engine implementation',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-02-15T10:00:00Z',
    memory_count: 45,
    session_count: 23,
  },
  {
    project_id: 'proj-002',
    name: 'Frontend Dashboard',
    description: 'React + Tailwind web dashboard for RECALL',
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-15T14:00:00Z',
    memory_count: 18,
    session_count: 12,
  },
  {
    project_id: 'proj-003',
    name: 'OpenCode Integration',
    description: 'MCP adapter and /recall command family',
    created_at: '2026-01-20T00:00:00Z',
    updated_at: '2026-02-10T16:00:00Z',
    memory_count: 22,
    session_count: 15,
  },
];

const mockSessions: Session[] = [
  {
    session_id: 'sess-001',
    project_id: 'proj-001',
    project_name: 'RECALL Core',
    started_at: '2026-02-15T09:00:00Z',
    ended_at: '2026-02-15T11:30:00Z',
    message_count: 45,
    memory_captures: 3,
  },
  {
    session_id: 'sess-002',
    project_id: 'proj-002',
    project_name: 'Frontend Dashboard',
    started_at: '2026-02-15T14:00:00Z',
    ended_at: '2026-02-15T16:45:00Z',
    message_count: 28,
    memory_captures: 2,
  },
  {
    session_id: 'sess-003',
    project_id: 'proj-001',
    project_name: 'RECALL Core',
    started_at: '2026-02-14T10:00:00Z',
    ended_at: '2026-02-14T12:00:00Z',
    message_count: 52,
    memory_captures: 5,
  },
];

const mockStats: Stats = {
  total_memories: 85,
  active_memories: 78,
  total_projects: 3,
  total_sessions: 50,
  total_instructions: 3,
  active_instructions: 2,
  unresolved_conflicts: 1,
  semantic_index_status: 'healthy',
  last_indexed_at: '2026-02-15T16:30:00Z',
  database_connected: true,
  chromadb_connected: true,
  local_llm_available: true,
};

// Simulate network delay
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

let memoryIdCounter = mockMemories.length + 1;
let instructionIdCounter = mockInstructions.length + 1;

function createNewMemory(memory: Omit<Memory, 'memory_id' | 'created_at' | 'updated_at'>): Memory {
  const now = new Date().toISOString();
  return {
    memory_id: `mem-${String(memoryIdCounter++).padStart(3, '0')}`,
    project_id: memory.project_id,
    project_name: memory.project_name,
    memory_type: memory.memory_type,
    content: memory.content,
    status: memory.status,
    importance: memory.importance,
    provenance: memory.provenance,
    lineage: memory.lineage,
    created_at: now,
    updated_at: now,
    tags: memory.tags,
  };
}

function createNewInstruction(request: CreateCustomInstructionRequest): CustomInstruction {
  const now = new Date().toISOString();
  const project = mockProjects.find(p => p.project_id === request.project_id);
  return {
    instruction_id: `inst-${String(instructionIdCounter++).padStart(3, '0')}`,
    scope: request.scope,
    project_id: request.project_id,
    project_name: project?.name,
    content: request.content,
    active: request.active ?? true,
    created_at: now,
    updated_at: now,
    version: 1,
  };
}

function updateMemoryObj(memory: Memory, updates: Partial<Memory>): Memory {
  return {
    ...memory,
    ...updates,
    updated_at: new Date().toISOString(),
  };
}

function updateInstructionObj(instruction: CustomInstruction, updates: UpdateCustomInstructionRequest): CustomInstruction {
  return {
    ...instruction,
    ...updates,
    updated_at: new Date().toISOString(),
    version: instruction.version + 1,
  };
}

function findMemoryById(id: string): Memory | undefined {
  return mockMemories.find(m => m.memory_id === id);
}

function findInstructionById(id: string): CustomInstruction | undefined {
  return mockInstructions.find(i => i.instruction_id === id);
}

function findMemoryIndex(id: string): number {
  return mockMemories.findIndex(m => m.memory_id === id);
}

function findInstructionIndex(id: string): number {
  return mockInstructions.findIndex(i => i.instruction_id === id);
}

export const mockApiClient = {
  // Health
  async getHealth(): Promise<HealthStatus> {
    await sleep(100);
    return {
      status: 'healthy',
      api_version: '1.0.0',
      database_connected: true,
      chromadb_connected: true,
      local_llm_available: true,
      timestamp: new Date().toISOString(),
    };
  },

  // Memories
  async getMemories(query: MemoryQuery = {}): Promise<MemoryListResponse> {
    await sleep(300);
    let filtered = [...mockMemories];

    if (query.project_id) {
      filtered = filtered.filter(m => m.project_id === query.project_id);
    }
    if (query.memory_type) {
      filtered = filtered.filter(m => m.memory_type === query.memory_type);
    }
    if (query.status && query.status !== 'all') {
      filtered = filtered.filter(m => m.status === query.status);
    } else if (!query.status) {
      filtered = filtered.filter(m => m.status === 'active');
    }
    if (query.search) {
      const search = query.search.toLowerCase();
      filtered = filtered.filter(m =>
        m.content.toLowerCase().includes(search) ||
        m.tags?.some(t => t.toLowerCase().includes(search))
      );
    }

    // Sort
    const sortBy = query.sort_by || 'created_at';
    const sortOrder = query.sort_order || 'desc';
    filtered.sort((a, b) => {
      const aVal = a[sortBy];
      const bVal = b[sortBy];
      if (aVal < bVal) return sortOrder === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortOrder === 'asc' ? 1 : -1;
      return 0;
    });

    const page = query.page || 1;
    const pageSize = query.page_size || 20;
    const start = (page - 1) * pageSize;
    const end = start + pageSize;

    return {
      memories: filtered.slice(start, end),
      total: filtered.length,
      page,
      page_size: pageSize,
    };
  },

  async getMemory(id: string): Promise<Memory> {
    await sleep(150);
    const memory = findMemoryById(id);
    if (!memory) throw new Error(`Memory ${id} not found`);
    return memory;
  },

  async createMemory(memory: Omit<Memory, 'memory_id' | 'created_at' | 'updated_at'>): Promise<Memory> {
    await sleep(200);
    const newMemory = createNewMemory(memory);
    mockMemories.unshift(newMemory);
    return newMemory;
  },

  async updateMemory(id: string, updates: Partial<Memory>): Promise<Memory> {
    await sleep(200);
    const index = findMemoryIndex(id);
    if (index < 0) throw new Error(`Memory ${id} not found`);
    const existing = mockMemories[index]!;
    const updated = updateMemoryObj(existing, updates);
    mockMemories[index] = updated;
    return updated;
  },

  async deleteMemory(id: string): Promise<void> {
    await sleep(150);
    const index = findMemoryIndex(id);
    if (index < 0) throw new Error(`Memory ${id} not found`);
    mockMemories.splice(index, 1);
  },

  // Custom Instructions
  async getCustomInstructions(projectId?: string): Promise<CustomInstructionListResponse> {
    await sleep(200);
    let filtered = [...mockInstructions];
    if (projectId) {
      filtered = filtered.filter(i => i.scope === 'global' || i.project_id === projectId);
    }
    return { instructions: filtered, total: filtered.length };
  },

  async createCustomInstruction(request: CreateCustomInstructionRequest): Promise<CustomInstruction> {
    await sleep(250);
    const newInstruction = createNewInstruction(request);
    mockInstructions.unshift(newInstruction);
    return newInstruction;
  },

  async updateCustomInstruction(id: string, updates: UpdateCustomInstructionRequest): Promise<CustomInstruction> {
    await sleep(200);
    const index = findInstructionIndex(id);
    if (index < 0) throw new Error(`Instruction ${id} not found`);
    const existing = mockInstructions[index]!;
    const updated = updateInstructionObj(existing, updates);
    mockInstructions[index] = updated;
    return updated;
  },

  async deleteCustomInstruction(id: string): Promise<void> {
    await sleep(150);
    const index = findInstructionIndex(id);
    if (index < 0) throw new Error(`Instruction ${id} not found`);
    mockInstructions.splice(index, 1);
  },

  // Conflicts
  async getConflicts(projectId?: string): Promise<ConflictListResponse> {
    await sleep(250);
    let filtered = [...mockConflicts];
    if (projectId) {
      filtered = filtered.filter(c => c.project_id === projectId);
    }
    return { conflicts: filtered, total: filtered.length };
  },

  // Projects
  async getProjects(): Promise<ProjectListResponse> {
    await sleep(200);
    return { projects: mockProjects, total: mockProjects.length };
  },

  async createProject(request: CreateProjectRequest): Promise<Project> {
    await sleep(200);
    const now = new Date().toISOString();
    const newProject: Project = {
      project_id: `proj-${String(mockProjects.length + 1).padStart(3, '0')}`,
      name: request.name,
      description: request.description,
      created_at: now,
      updated_at: now,
      memory_count: 0,
      session_count: 0,
    };
    mockProjects.push(newProject);
    return newProject;
  },

  // Sessions
  async getSessions(projectId?: string): Promise<SessionListResponse> {
    await sleep(200);
    let filtered = [...mockSessions];
    if (projectId) {
      filtered = filtered.filter(s => s.project_id === projectId);
    }
    return { sessions: filtered, total: filtered.length };
  },

  async createSession(request: CreateSessionRequest): Promise<Session> {
    await sleep(200);
    const now = new Date().toISOString();
    const proj = mockProjects.find(p => p.project_id === request.project_id);
    const newSession: Session = {
      session_id: request.session_id || `sess-${String(mockSessions.length + 1).padStart(3, '0')}`,
      project_id: request.project_id,
      project_name: proj?.name || 'Mock Project',
      started_at: now,
      message_count: 0,
      memory_captures: 0,
    };
    mockSessions.push(newSession);
    return newSession;
  },

  // Stats
  async getStats(): Promise<Stats> {
    await sleep(200);
    return mockStats;
  },

  // Chat
  async sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
    await sleep(500);
    // Simple mock response
    const relevantMemories = mockMemories
      .filter(m => !request.project_id || m.project_id === request.project_id)
      .slice(0, 3)
      .map(m => ({
        memory_id: m.memory_id,
        content: m.content,
        relevance_score: 0.7 + Math.random() * 0.25,
      }));

    return {
      response: `Based on the current memory context, here's what I found regarding "${request.query}":\n\n${relevantMemories.map((m, i) => `${i + 1}. ${m.content}`).join('\n\n')}\n\nThese memories are from project ${request.project_id || 'all projects'}. Would you like me to search for more specific information?`,
      supporting_memories: relevantMemories,
      session_id: request.session_id || `sess-${Date.now()}`,
    };
  },

  // Context compact
  async compactContext(projectId: string): Promise<{ success: boolean; message: string }> {
    await sleep(1000);
    return {
      success: true,
      message: `Context compacted for project ${projectId}. Reduced active context while preserving canonical history and lineage.`,
    };
  },
};

// Export a factory function to choose between real and mock API.
// Mock mode is intentionally opt-in to avoid silently masking missing backend integration.
import apiClient from './client';

export function createApiClient(useMock = false) {
  const shouldUseMock = useMock || import.meta.env.VITE_USE_MOCK_API === 'true';
  return shouldUseMock ? mockApiClient : apiClient;
}

export function createApiError(message: string, status: number, response?: Response): Error {
  const error = new Error(message);
  (error as Error & { status: number; response?: Response }).status = status;
  (error as Error & { status: number; response?: Response }).response = response;
  return error;
}

export type { Memory, MemoryListResponse, MemoryQuery } from '../types';