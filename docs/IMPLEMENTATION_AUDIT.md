# RECALL Implementation Audit

**Date:** 2026-10-09
**Branch:** fix/core-correctness

## Summary

This document records the concrete implementation status of each architectural component defined in the RECALL architecture. Interfaces alone are not proof of implementation.

## Component Status

| Component | Interface | Concrete Implementation | Status |
|-----------|-----------|------------------------|--------|
| Contracts (DTOs) | N/A | `contracts/*.py` | **COMPLETE** |
| Repository Interfaces | `database/repositories.py` | N/A | Interface only |
| SQLite Repositories | `database/repositories.py` | None | **MISSING** |
| Unit of Work | `database/repositories.py` | None | **MISSING** |
| ChromaDB Semantic Index | `database/repositories.py` | None | **MISSING** |
| Retrieval Service | `intelligence/retrieval.py` | None | **MISSING** |
| Embedding Service | `intelligence/retrieval.py` | None | **MISSING** |
| Conflict Resolution Service | `intelligence/conflict.py` | None | **MISSING** |
| Conflict Detector | `intelligence/conflict.py` | None | **MISSING** |
| Conflict Resolver | `intelligence/conflict.py` | None | **MISSING** |
| MCP Server | N/A | `mcp/` (empty) | **MISSING** |
| OpenCode Integration | N/A | None | **MISSING** |
| REST API | N/A | `api/` (empty) | **MISSING** |
| MemoryManager (Core) | N/A | `core/recall_core/memory_manager.py` | **COMPLETE** |
| ContextAssemblyService | N/A | `core/recall_core/context_assembly.py` | **COMPLETE** |
| CustomInstructionService | N/A | `core/recall_core/instruction_service.py` | **COMPLETE** |
| Exceptions | N/A | `core/recall_core/exceptions.py` | **COMPLETE** |

## What Exists

### Contracts Layer (Complete)
- `contracts/base.py` — Result, PaginationParams, PaginatedResult, TimestampMixin, enums
- `contracts/memory.py` — Memory, MemoryCreateRequest, MemoryUpdateRequest, MemorySearchParams, MemoryLineage
- `contracts/project.py` — Project, Session, and their request types
- `contracts/instruction.py` — CustomInstruction and request types
- `contracts/conflict.py` — ConflictCandidate, ConflictResolutionResult, ResolutionDecision
- `contracts/retrieval.py` — RetrievalRequest, RetrievalResult, ContextAssemblyRequest, AssembledContext, CompactRequest/Result, UpdateContextRequest/Result

### Core Layer (Complete)
- `core/recall_core/memory_manager.py` — MemoryManager orchestration (delegates to repositories and services)
- `core/recall_core/context_assembly.py` — ContextAssemblyService
- `core/recall_core/instruction_service.py` — CustomInstructionService
- `core/recall_core/exceptions.py` — All custom exceptions

### Intelligence Layer (Interfaces Only)
- `intelligence/retrieval.py` — RetrievalService, EmbeddingService (abstract)
- `intelligence/conflict.py` — ConflictDetector, ConflictResolver, ConflictResolutionService (abstract)

### Database Layer (Interfaces Only)
- `database/repositories.py` — ProjectRepository, SessionRepository, MemoryRepository, CustomInstructionRepository, SemanticIndexRepository, UnitOfWork (all abstract)

## What Is Missing

### 1. SQLite Repositories and Unit of Work
**Required by:** Architecture (canonical storage)
**Interface:** `database/repositories.py`
**Needed:** Concrete `SQLiteProjectRepository`, `SQLiteSessionRepository`, `SQLiteMemoryRepository`, `SQLiteCustomInstructionRepository`, `SQLiteUnitOfWork`
**Priority:** CRITICAL — without this, no data persistence exists

### 2. ChromaDB Semantic Index
**Required by:** Architecture (derived semantic index)
**Interface:** `SemanticIndexRepository` in `database/repositories.py`
**Needed:** Concrete `ChromaDBSemanticIndexRepository`
**Priority:** HIGH — required for semantic retrieval

### 3. Retrieval Service
**Required by:** Architecture (retrieval)
**Interface:** `RetrievalService` in `intelligence/retrieval.py`
**Needed:** Concrete `DefaultRetrievalService` implementing structured + semantic search, ranking, conflict detection
**Priority:** HIGH — required for memory retrieval

### 4. Embedding Service
**Required by:** Retrieval Service
**Interface:** `EmbeddingService` in `intelligence/retrieval.py`
**Needed:** Concrete embedding generator (local model or API-based)
**Priority:** HIGH — required for semantic search

### 5. Conflict Resolution Service
**Required by:** Architecture (conflict handling)
**Interface:** `ConflictResolutionService` in `intelligence/conflict.py`
**Needed:** Concrete `DefaultConflictResolutionService` with deterministic rules + optional LLM arbitration
**Priority:** MEDIUM — required for conflict detection/resolution

### 6. MCP Server
**Required by:** OpenCode integration
**Needed:** MCP server exposing RECALL operations via MCP protocol
**Priority:** MEDIUM — required for OpenCode agent integration

### 7. REST API
**Required by:** Web Dashboard
**Needed:** HTTP/JSON API wrapping Core operations
**Priority:** MEDIUM — required for dashboard communication

## Integration Test Coverage

### Verified (through unit tests with mocks)
- MemoryManager delegates to repositories correctly
- ContextAssemblyService assembles context from sources
- CustomInstructionService manages instruction lifecycle
- Authority hierarchy: explicit instructions > explicit updates > current canonical > historical
- Semantic index failures are best-effort (don't block canonical operations)
- Project/session isolation in context assembly

### Not Verified (no concrete implementation exists)
- SQLite persistence (close/reopen)
- ChromaDB index rebuild from canonical records
- End-to-end retrieval with real embeddings
- Conflict resolution with real arbitration
- MCP request/response cycle
- REST API endpoints

## Recommendation

Before any integration testing can occur, the SQLite repositories and Unit of Work must be implemented. This is the foundational layer that all other components depend on. The ChromaDB semantic index and retrieval service are the next priority for enabling semantic search capabilities.
