from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.graph import AdminAgentGraph
from app.agent.memory import SessionMemoryStore
from app.audit.history import AuditLogger
from app.config import Settings
from app.mcp.client import MCPClient
from app.schemas import AdminChatRequest, AdminChatResponse, StreamEvent


router = APIRouter(prefix="/admin", tags=["admin"])


def _build_graph() -> AdminAgentGraph:
    settings = Settings()
    return AdminAgentGraph(
        settings=settings,
        memory=SessionMemoryStore(settings),
        audit=AuditLogger(settings),
        mcp_client=MCPClient(settings),
    )


@router.post("/chat", response_model=AdminChatResponse)
async def admin_chat(payload: AdminChatRequest) -> AdminChatResponse:
    graph = _build_graph()
    return await graph.invoke(payload)


@router.post("/chat/stream")
async def admin_chat_stream(payload: AdminChatRequest) -> StreamingResponse:
    graph = _build_graph()

    async def event_stream() -> AsyncIterator[str]:
        async for event in graph.stream(payload):
            yield json.dumps(event.model_dump(mode="json"), ensure_ascii=True) + "\n"
            await asyncio.sleep(0)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
