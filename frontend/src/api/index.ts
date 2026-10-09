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

// Use mock client by default since backend doesn't exist yet
const USE_MOCK = import.meta.env.VITE_USE_MOCK_API !== 'false';

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