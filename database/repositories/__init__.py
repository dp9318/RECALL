"""Database repositories package for RECALL.

This package provides both the abstract repository interfaces (in interfaces.py)
and their concrete SQLite implementations.
"""

from database.repositories.interfaces import (
    ProjectRepository,
    SessionRepository,
    MemoryRepository,
    CustomInstructionRepository,
    SemanticIndexRepository,
    DatabaseTransaction,
    UnitOfWork,
)

# Import concrete implementations
from database.repositories.project_repo import SQLiteProjectRepository
from database.repositories.session_repo import SQLiteSessionRepository
from database.repositories.memory_repo import SQLiteMemoryRepository
from database.repositories.instruction_repo import SQLiteCustomInstructionRepository
from database.repositories.unit_of_work import SQLiteUnitOfWork

__all__ = [
    # Interfaces
    "ProjectRepository",
    "SessionRepository",
    "MemoryRepository",
    "CustomInstructionRepository",
    "SemanticIndexRepository",
    "DatabaseTransaction",
    "UnitOfWork",
    # Concrete implementations
    "SQLiteProjectRepository",
    "SQLiteSessionRepository",
    "SQLiteMemoryRepository",
    "SQLiteCustomInstructionRepository",
    "SQLiteUnitOfWork",
]