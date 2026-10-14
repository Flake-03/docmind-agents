from fastapi import APIRouter, Request, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from orchestration.state import Action, AgentResult

from .schemas import AgentRequest, AgentResponse, ChatRequest, SummaryRequest

router = APIRouter()


@router.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/summaries", response_model=AgentResponse, tags=["agents"])
async def summarize(payload: SummaryRequest, request: Request) -> AgentResponse:
    return await _invoke(request, "summarize", payload, payload.instructions)


@router.post("/v1/chat", response_model=AgentResponse, tags=["agents"])
async def chat(payload: ChatRequest, request: Request) -> AgentResponse:
    return await _invoke(request, "chat", payload, payload.message)


@router.websocket("/v1/live")
async def live(websocket: WebSocket, project_id: str, thread_id: str) -> None:
    try:
        payload = AgentRequest(project_id=project_id, thread_id=thread_id)
    except ValidationError:
        await websocket.close(code=1008, reason="invalid project_id or thread_id")
        return

    async def answer_question(question: str) -> AgentResult:
        chat_payload = ChatRequest(
            project_id=payload.project_id,
            thread_id=payload.thread_id,
            message=question,
        )
        return await websocket.app.state.graph.ainvoke(
            {
                "action": "chat",
                "project_id": chat_payload.project_id,
                "thread_id": chat_payload.thread_id,
                "message": chat_payload.message,
            }
        )

    await websocket.accept()
    try:
        await websocket.app.state.voice.run(websocket, answer_question)
    except Exception:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011, reason="live voice session failed")


async def _invoke(request: Request, action: Action, payload: AgentRequest, message: str) -> AgentResponse:
    result = await request.app.state.graph.ainvoke(
        {
            "action": action,
            "project_id": payload.project_id,
            "thread_id": payload.thread_id,
            "message": message,
        }
    )
    return AgentResponse(
        thread_id=payload.thread_id,
        agent_session_id=result["agent_session_id"],
        answer=result["answer"],
        finish_reason=result.get("finish_reason"),
    )
