export interface Memory {
  memory_id: string;
  project_id: string | null;
  project_name?: string | null;
  memory_type: 'fact' | 'decision' | 'pattern' | 'preference' | 'context' | 'constraint';
  content: string;
  status: 'active' | 'superseded' | 'archived' | 'conflicted' | 'deleted';
  importance: number; // 0-100
  provenance: string; // source reference
  lineage: {
    supersedes?: string | null;
    superseded_by?: string | null;
    related_memories?: string[];
  };
  created_at: string;
  updated_at: string;
  tags?: string[];
}

export interface MemoryListResponse {
  memories: Memory[];
  total: number;
  page: number;
  page_size: number;
}

export interface MemoryQuery {
  project_id?: string;
  memory_type?: Memory['memory_type'];
  status?: Memory['status'] | 'all';
  search?: string;
  page?: number;
  page_size?: number;
  sort_by?: 'created_at' | 'updated_at' | 'importance';
  sort_order?: 'asc' | 'desc';
}