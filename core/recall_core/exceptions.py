"""Exceptions for the RECALL Core module."""

from __future__ import annotations


class RecallCoreError(Exception):
    """Base exception for RECALL Core errors."""
    pass


class MemoryNotFoundError(RecallCoreError):
    """Raised when a memory is not found."""
    pass


class ProjectNotFoundError(RecallCoreError):
    """Raised when a project is not found."""
    pass


class SessionNotFoundError(RecallCoreError):
    """Raised when a session is not found."""
    pass


class InstructionNotFoundError(RecallCoreError):
    """Raised when a custom instruction is not found."""
    pass


class ConflictResolutionError(RecallCoreError):
    """Raised when conflict resolution fails."""
    pass


class RetrievalError(RecallCoreError):
    """Raised when retrieval fails."""
    pass


class PersistenceError(RecallCoreError):
    """Raised when persistence operation fails."""
    pass


class ValidationError(RecallCoreError):
    """Raised when input validation fails."""
    pass


class SemanticIndexUnavailableError(RecallCoreError):
    """Raised when semantic index is unavailable."""
    pass


class LocalLLMUnavailableError(RecallCoreError):
    """Raised when local LLM is unavailable."""
    pass