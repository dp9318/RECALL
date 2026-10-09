"""SQLite implementation of SessionRepository."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional
from uuid import UUID

from contracts.base import PaginatedResult, PaginationParams, Result
from contracts.project import Session, SessionCreateRequest, SessionUpdateRequest
from database.repositories import SessionRepository
from database.repositories.base import (
    session_row_to_dto,
    datetime_to_str,
    dict_to_json,
    uuid_to_str,
)


class SQLiteSessionRepository(SessionRepository):
    """SQLite implementation of SessionRepository."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, request: SessionCreateRequest) -> Result[Session]:
        """Create a new session."""
        session = Session(
            id=request.id if hasattr(request, "id") and request.id else UUID(int=0),
            project_id=request.project_id,
            metadata=request.metadata,
        )
        if session.id == UUID(int=0):
            from uuid import uuid4
            session = Session(
                id=uuid4(),
                project_id=request.project_id,
                metadata=request.metadata,
            )

        try:
            self._conn.execute(
                """
                INSERT INTO sessions (session_id, project_id, started_at, ended_at, status, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid_to_str(session.id),
                    uuid_to_str(session.project_id),
                    datetime_to_str(session.started_at),
                    None,
                    "active",
                    dict_to_json(session.metadata),
                    datetime_to_str(session.created_at),
                    datetime_to_str(session.updated_at),
                ),
            )
            # Note: Transaction commit is managed by the caller (UnitOfWork/transaction context)
            return Result.ok(session)
        except sqlite3.IntegrityError as e:
            return Result.err(f"Session creation failed: {e}")
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def get(self, session_id: UUID) -> Result[Optional[Session]]:
        """Get a session by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (uuid_to_str(session_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return Result.ok(None)
        return Result.ok(session_row_to_dto(dict(row)))

    def get_active_for_project(self, project_id: UUID) -> Result[Optional[Session]]:
        """Get the active session for a project."""
        cursor = self._conn.execute(
            """
            SELECT * FROM sessions
            WHERE project_id = ? AND status = 'active'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (uuid_to_str(project_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return Result.ok(None)
        return Result.ok(session_row_to_dto(dict(row)))

    def update(self, session_id: UUID, request: SessionUpdateRequest) -> Result[Optional[Session]]:
        """Update a session."""
        existing = self.get(session_id)
        if not existing.success or existing.value is None:
            return Result.ok(None)

        session = existing.value
        updated_ended_at = request.ended_at if request.ended_at is not None else session.ended_at
        updated_metadata = request.metadata if request.metadata is not None else session.metadata
        updated_at = datetime.now().isoformat()
        updated_status = "completed" if updated_ended_at is not None else "active"

        try:
            self._conn.execute(
                """
                UPDATE sessions
                SET ended_at = ?, status = ?, metadata = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (
                    datetime_to_str(updated_ended_at),
                    updated_status,
                    dict_to_json(updated_metadata),
                    updated_at,
                    uuid_to_str(session_id),
                ),
            )
            # Note: Transaction commit is managed by the caller (UnitOfWork/transaction context)

            updated_session = Session(
                id=session.id,
                project_id=session.project_id,
                started_at=session.started_at,
                ended_at=updated_ended_at,
                metadata=updated_metadata,
                created_at=session.created_at,
                updated_at=datetime.fromisoformat(updated_at),
            )
            return Result.ok(updated_session)
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")

    def list(self, params: PaginationParams, project_id: Optional[UUID] = None) -> Result[PaginatedResult[Session]]:
        """List sessions with pagination."""
        try:
            if project_id:
                count_cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE project_id = ?",
                    (uuid_to_str(project_id),),
                )
                total = count_cursor.fetchone()[0]

                cursor = self._conn.execute(
                    """
                    SELECT * FROM sessions
                    WHERE project_id = ?
                    ORDER BY started_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (uuid_to_str(project_id), params.limit, params.offset),
                )
            else:
                count_cursor = self._conn.execute("SELECT COUNT(*) FROM sessions")
                total = count_cursor.fetchone()[0]

                cursor = self._conn.execute(
                    """
                    SELECT * FROM sessions
                    ORDER BY started_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (params.limit, params.offset),
                )

            rows = cursor.fetchall()
            sessions = [session_row_to_dto(dict(row)) for row in rows]

            return Result.ok(PaginatedResult(
                items=sessions,
                total=total,
                limit=params.limit,
                offset=params.offset,
            ))
        except sqlite3.Error as e:
            return Result.err(f"Database error: {e}")