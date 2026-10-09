import { createApiClient } from './mockClient';
import apiClient from './client';
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
  Session,
  SessionListResponse,
  Stats,
  ChatRequest,
  ChatResponse,
  HealthStatus,
  ChatMessage,
  MemoryReference,
} from '../types';

// Real API is the default. Mock mode remains available only when explicitly enabled.
const USE_MOCK = import.meta.env.VITE_USE_MOCK_API === 'true';

export const api = createApiClient(USE_MOCK);

// Re-export types for convenience
export type {
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
  Session,
  SessionListResponse,
  Stats,
  ChatRequest,
  ChatResponse,
  HealthStatus,
  ChatMessage,
  MemoryReference,
};