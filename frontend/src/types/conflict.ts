export interface Conflict {
  conflict_id: string;
  project_id: string;
  project_name?: string;
  status: 'detected' | 'resolved' | 'partially_resolved' | 'unresolved' | 'abstained';
  conflicting_memories: ConflictMemory[];
  resolution?: ConflictResolution;
  detected_at: string;
  resolved_at?: string;
}

export interface ConflictMemory {
  memory_id: string;
  content: string;
  status: 'preferred' | 'superseded' | 'conflicting' | 'abstained';
  confidence?: number;
}

export interface ConflictResolution {
  preferred_memories: string[];
  superseded_memories: string[];
  reason: string;
  deterministic: boolean;
  local_model_used: boolean;
  confidence?: number;
}

export interface ConflictListResponse {
  conflicts: Conflict[];
  total: number;
}