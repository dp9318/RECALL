export interface CustomInstruction {
  instruction_id: string;
  scope: 'global' | 'project';
  project_id?: string;
  project_name?: string;
  content: string;
  active: boolean;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface CustomInstructionListResponse {
  instructions: CustomInstruction[];
  total: number;
}

export interface CreateCustomInstructionRequest {
  scope: 'global' | 'project';
  project_id?: string;
  content: string;
  active?: boolean;
}

export interface UpdateCustomInstructionRequest {
  content?: string;
  active?: boolean;
}