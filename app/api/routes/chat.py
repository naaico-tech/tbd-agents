"""Chat API endpoints.

Provides a conversational interface over an agent's existing context —
no tool execution, pure LLM conversation streamed via SSE.

Endpoints
---------
POST   /api/agents/{agent_id}/chat                      — send a message
GET    /api/agents/{agent_id}/chat/sessions             — list sessions
GET    /api/agents/{agent_id}/chat/sessions/{session_id} — session detail
DELETE /api/agents/{agent_id}/chat/sessions/{session_id} — delete session

Workflow-backed chat session endpoints
---------------------------------------
POST   /api/chat/start  — get or create a dedicated chat workflow for an agent
"""

import json
import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import extract_optional_token, get_current_user
from app.config import settings
from app.models.agent import Agent
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.workflow import Workflow, WorkflowStatus
from app.observability import sse_connections_active
from app.schemas.chat import (
    ChatMessageResponse,
    ChatRequest,
    ChatSessionDetail,
    ChatSessionResponse,
)
from app.services.chat_handler import handle_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["chat"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _session_response(s: ChatSession) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=str(s.id),
        agent_id=str(s.agent_id),
        title=s.title,
        message_count=s.message_count,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _message_response(m: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=str(m.id),
        role=m.role,
        content=m.content,
        usage=m.usage,
        created_at=m.created_at,
    )


# ── POST /api/agents/{agent_id}/chat ─────────────────────────────────────────


@router.post("/{agent_id}/chat")
async def chat(
    agent_id: str,
    body: ChatRequest,
    request: Request,
    user=Depends(get_current_user),
    authorization: str | None = Header(None),
):
    """Send a message to an agent and receive a streaming SSE response.

    Pass ``session_id`` in the request body to continue an existing
    conversation; omit it to start a new session.

    The response is ``text/event-stream`` with the following event types:

    - ``session``  — first event, contains ``session_id``
    - ``delta``    — one per token chunk, contains ``content``
    - ``done``     — stream complete, contains ``usage`` and ``message_id``
    - ``error``    — on LLM / provider failure, contains ``message``
    """
    agent = await Agent.get(PydanticObjectId(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    github_user = user["login"]
    token = extract_optional_token(authorization)

    # ── Resolve or create chat session ────────────────────────────────────
    if body.session_id:
        try:
            session = await ChatSession.get(PydanticObjectId(body.session_id))
        except Exception:
            session = None
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        if session.github_user != github_user:
            raise HTTPException(status_code=403, detail="Not your session")
        if str(session.agent_id) != agent_id:
            raise HTTPException(
                status_code=400, detail="Session belongs to a different agent"
            )
    else:
        session = ChatSession(
            agent_id=PydanticObjectId(agent_id),
            github_user=github_user,
        )
        await session.insert()

    async def event_generator():
        sse_connections_active.inc()
        event_id = 0
        try:
            async for event in handle_chat(
                agent=agent,
                session=session,
                user_message=body.message,
                github_user=github_user,
                github_token=token,
            ):
                if await request.is_disconnected():
                    break
                event_id += 1
                yield f"id: {event_id}\ndata: {json.dumps(event)}\n\n"
        except Exception:
            logger.exception("chat SSE generator error for agent %s", agent_id)
            event_id += 1
            yield (
                f"id: {event_id}\ndata: "
                + json.dumps({"type": "error", "message": "An internal error occurred."})
                + "\n\n"
            )
        finally:
            sse_connections_active.dec()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── GET /api/agents/{agent_id}/chat/sessions ─────────────────────────────────


@router.get(
    "/{agent_id}/chat/sessions",
    response_model=list[ChatSessionResponse],
)
async def list_chat_sessions(
    agent_id: str,
    skip: int = 0,
    limit: int = 20,
    user=Depends(get_current_user),
):
    """List chat sessions for an agent, newest first (paginated)."""
    agent = await Agent.get(PydanticObjectId(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    github_user = user["login"]
    sessions = (
        await ChatSession.find(
            {
                "agent_id": PydanticObjectId(agent_id),
                "github_user": github_user,
            }
        )
        .sort("-updated_at")
        .skip(skip)
        .limit(limit)
        .to_list()
    )
    return [_session_response(s) for s in sessions]


# ── GET /api/agents/{agent_id}/chat/sessions/{session_id} ────────────────────


@router.get(
    "/{agent_id}/chat/sessions/{session_id}",
    response_model=ChatSessionDetail,
)
async def get_chat_session(
    agent_id: str,
    session_id: str,
    user=Depends(get_current_user),
):
    """Get a chat session including full message history (chronological)."""
    agent = await Agent.get(PydanticObjectId(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        session = await ChatSession.get(PydanticObjectId(session_id))
    except Exception:
        session = None
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your session")
    if str(session.agent_id) != agent_id:
        raise HTTPException(status_code=400, detail="Session belongs to a different agent")

    messages = (
        await ChatMessage.find({"session_id": session.id})
        .sort("created_at")
        .to_list()
    )

    return ChatSessionDetail(
        id=str(session.id),
        agent_id=str(session.agent_id),
        title=session.title,
        message_count=session.message_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[_message_response(m) for m in messages],
    )


# ── DELETE /api/agents/{agent_id}/chat/sessions/{session_id} ─────────────────


@router.delete(
    "/{agent_id}/chat/sessions/{session_id}",
    status_code=204,
)
async def delete_chat_session(
    agent_id: str,
    session_id: str,
    user=Depends(get_current_user),
):
    """Delete a chat session and cascade-delete all its messages."""
    agent = await Agent.get(PydanticObjectId(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        session = await ChatSession.get(PydanticObjectId(session_id))
    except Exception:
        session = None
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session.github_user != user["login"]:
        raise HTTPException(status_code=403, detail="Not your session")
    if str(session.agent_id) != agent_id:
        raise HTTPException(status_code=400, detail="Session belongs to a different agent")

    # Cascade delete messages
    await ChatMessage.find({"session_id": session.id}).delete()
    await session.delete()
    return None


# ── Workflow-backed chat session router ───────────────────────────────────────

workflow_chat_router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatStartRequest(BaseModel):
    agent_id: str


class ChatStartResponse(BaseModel):
    workflow_id: str
    agent_name: str
    agent_id: str


@workflow_chat_router.post("/start", response_model=ChatStartResponse, status_code=200)
async def start_chat_session(
    body: ChatStartRequest,
    current_user: dict = Depends(get_current_user),
):
    """Get or create a dedicated chat workflow for the given agent.

    Looks for an existing active workflow with title matching ``Chat: {agent.name}``
    owned by this user.  If found, returns it.  If not, creates a new one.
    This ensures each user has one persistent chat workflow per agent.
    """
    github_user = current_user.get("login") or "local"

    try:
        agent = await Agent.get(PydanticObjectId(body.agent_id))
    except Exception:
        agent = None
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    chat_title = f"Chat: {agent.name}"

    # Look for existing active chat workflow for this user + agent
    existing = await Workflow.find_one(
        Workflow.github_user == github_user,
        Workflow.agent_id == str(agent.id),
        Workflow.status == WorkflowStatus.ACTIVE,
        Workflow.infinite_session == True,  # noqa: E712 – beanie query, not Python bool
    )

    if existing:
        return ChatStartResponse(
            workflow_id=str(existing.id),
            agent_name=agent.name,
            agent_id=str(agent.id),
        )

    # Create new chat workflow
    model = agent.model or settings.default_model
    new_wf = Workflow(
        title=chat_title,
        agent_id=str(agent.id),
        github_user=github_user,
        model=model,
        infinite_session=True,
        status=WorkflowStatus.ACTIVE,
        max_turns=50,
    )
    await new_wf.insert()

    return ChatStartResponse(
        workflow_id=str(new_wf.id),
        agent_name=agent.name,
        agent_id=str(agent.id),
    )
