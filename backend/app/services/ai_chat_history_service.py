from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_chat_history import AIChatMessage, AIChatState


class AIChatHistoryStorageUnavailableError(RuntimeError):
    """Raised when AI chat history tables are not available in the database."""


class AIChatHistoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_scope_history(
        self,
        *,
        user_id: UUID,
        scope_key: str,
    ) -> dict[str, Any]:
        normalized_scope = self._normalize_scope_key(scope_key)
        try:
            message_rows = (
                await self.db.scalars(
                    select(AIChatMessage)
                    .where(
                        AIChatMessage.user_id == user_id,
                        AIChatMessage.scope_key == normalized_scope,
                    )
                    .order_by(AIChatMessage.message_index.asc(), AIChatMessage.created_at.asc())
                )
            ).all()
            state_row = await self.db.scalar(
                select(AIChatState).where(
                    AIChatState.user_id == user_id,
                    AIChatState.scope_key == normalized_scope,
                )
            )
        except SQLAlchemyError as exc:
            await self.db.rollback()
            self._raise_storage_error(exc)

        messages: list[dict[str, Any]] = []
        for row in message_rows:
            payload = row.message_payload if isinstance(row.message_payload, dict) else {}
            if payload:
                messages.append(payload)
                continue
            messages.append(
                {
                    "id": str(row.id),
                    "role": row.role,
                    "content": row.content,
                    "timestamp": row.created_at.isoformat(),
                }
            )

        conversation_state = (
            state_row.state_payload
            if state_row and isinstance(state_row.state_payload, dict)
            else {}
        )
        return {
            "scope_key": normalized_scope,
            "messages": messages,
            "conversation_state": conversation_state,
        }

    async def save_scope_history(
        self,
        *,
        user_id: UUID,
        scope_key: str,
        messages: list[dict[str, Any]],
        conversation_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        normalized_scope = self._normalize_scope_key(scope_key)
        sanitized_messages = self._sanitize_messages(messages)
        sanitized_state = (
            dict(conversation_state)
            if isinstance(conversation_state, dict)
            else {}
        )
        try:
            await self.db.execute(
                delete(AIChatMessage).where(
                    AIChatMessage.user_id == user_id,
                    AIChatMessage.scope_key == normalized_scope,
                )
            )

            for index, message in enumerate(sanitized_messages):
                self.db.add(
                    AIChatMessage(
                        user_id=user_id,
                        scope_key=normalized_scope,
                        message_index=index,
                        role=str(message.get("role") or "assistant"),
                        content=str(message.get("content") or ""),
                        message_payload=message,
                    )
                )

            existing_state = await self.db.scalar(
                select(AIChatState).where(
                    AIChatState.user_id == user_id,
                    AIChatState.scope_key == normalized_scope,
                )
            )
            if existing_state is None:
                existing_state = AIChatState(
                    user_id=user_id,
                    scope_key=normalized_scope,
                    state_payload=sanitized_state,
                )
                self.db.add(existing_state)
            else:
                existing_state.state_payload = sanitized_state

            await self.db.commit()
        except SQLAlchemyError as exc:
            await self.db.rollback()
            self._raise_storage_error(exc)
        return {
            "scope_key": normalized_scope,
            "messages": sanitized_messages,
            "conversation_state": sanitized_state,
        }

    async def clear_scope_history(
        self,
        *,
        user_id: UUID,
        scope_key: str,
    ) -> dict[str, int]:
        normalized_scope = self._normalize_scope_key(scope_key)
        try:
            deleted_messages = await self.db.execute(
                delete(AIChatMessage).where(
                    AIChatMessage.user_id == user_id,
                    AIChatMessage.scope_key == normalized_scope,
                )
            )
            deleted_states = await self.db.execute(
                delete(AIChatState).where(
                    AIChatState.user_id == user_id,
                    AIChatState.scope_key == normalized_scope,
                )
            )
            await self.db.commit()
        except SQLAlchemyError as exc:
            await self.db.rollback()
            self._raise_storage_error(exc)
        return {
            "deleted_messages": int(deleted_messages.rowcount or 0),
            "deleted_states": int(deleted_states.rowcount or 0),
        }

    async def clear_all_history(self, *, user_id: UUID) -> dict[str, int]:
        try:
            deleted_messages = await self.db.execute(
                delete(AIChatMessage).where(AIChatMessage.user_id == user_id)
            )
            deleted_states = await self.db.execute(
                delete(AIChatState).where(AIChatState.user_id == user_id)
            )
            await self.db.commit()
        except SQLAlchemyError as exc:
            await self.db.rollback()
            self._raise_storage_error(exc)
        return {
            "deleted_messages": int(deleted_messages.rowcount or 0),
            "deleted_states": int(deleted_states.rowcount or 0),
        }

    @staticmethod
    def _normalize_scope_key(scope_key: str) -> str:
        normalized = " ".join(str(scope_key or "").split()).strip()
        if not normalized:
            raise ValueError("scope_key must not be empty.")
        return normalized[:120]

    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sanitized: list[dict[str, Any]] = []
        for raw_message in messages[:400]:
            if not isinstance(raw_message, dict):
                continue
            role = str(raw_message.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = str(raw_message.get("content") or "").strip()
            timestamp = str(raw_message.get("timestamp") or "").strip()
            message_id = str(raw_message.get("id") or "").strip()
            if not content or not timestamp or not message_id:
                continue

            message_copy = dict(raw_message)
            message_copy["role"] = role
            message_copy["content"] = content
            message_copy["timestamp"] = timestamp[:100]
            message_copy["id"] = message_id[:120]
            sanitized.append(message_copy)
        return sanitized

    @staticmethod
    def _raise_storage_error(exc: SQLAlchemyError) -> None:
        if AIChatHistoryService._is_missing_table_error(exc):
            raise AIChatHistoryStorageUnavailableError(
                "AI chat history storage is not initialized. "
                "Run database migrations: `alembic upgrade head`."
            ) from exc
        raise exc

    @staticmethod
    def _is_missing_table_error(exc: SQLAlchemyError) -> bool:
        raw = str(exc).lower()
        return (
            "undefinedtableerror" in raw
            or 'relation "ai_chat_messages" does not exist' in raw
            or 'relation "ai_chat_states" does not exist' in raw
        )
