from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.agent.memory import SessionMemoryStore
from app.schemas import ConfirmationEnvelope


class ConfirmationManager:
    def __init__(self, memory: SessionMemoryStore) -> None:
        self._memory = memory

    async def pause(self, session_id: str, confirmation: ConfirmationEnvelope) -> None:
        await self._memory.save_pending_confirmation(session_id, confirmation)

    async def create(
        self,
        *,
        session_id: str,
        user_id: str,
        tool_name: str,
        arguments: dict,
        reason: str,
        ttl_seconds: int,
    ) -> ConfirmationEnvelope:
        now = datetime.now(UTC)
        return ConfirmationEnvelope(
            confirmation_id=f"conf_{uuid4().hex}",
            session_id=session_id,
            user_id=user_id,
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
            requested_at_utc=now,
            expires_at_utc=now + timedelta(seconds=ttl_seconds),
        )

    async def resume(
        self,
        *,
        session_id: str,
        user_id: str,
        confirmation_id: str | None,
    ) -> ConfirmationEnvelope | None:
        if not confirmation_id:
            return None
        pending = await self._memory.load_pending_confirmation(session_id)
        if pending is None:
            return None
        if pending.confirmation_id != confirmation_id:
            return None
        if pending.session_id != session_id or pending.user_id != user_id:
            return None
        if pending.expires_at_utc < datetime.now(UTC):
            await self._memory.clear_pending_confirmation(session_id)
            return None
        await self._memory.clear_pending_confirmation(session_id)
        return pending
