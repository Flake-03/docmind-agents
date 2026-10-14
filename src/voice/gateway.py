import asyncio
from collections.abc import Awaitable, Callable

from fastapi import WebSocket
from google import genai
from google.genai import types

from config import Settings
from orchestration.state import AgentResult

INPUT_AUDIO = "audio/pcm;rate=16000"
OUTPUT_AUDIO = "audio/pcm;rate=24000"
TOOL_NAME = "ask_project_knowledge"

SYSTEM_PROMPT = """You are the voice interface for a project knowledge assistant.
Reply in the same language as the user and keep spoken answers concise and natural.
For every question about the project, you MUST call `ask_project_knowledge` and treat
its result as the only source of project facts. Do not mention tools or internal details."""

AnswerQuestion = Callable[[str], Awaitable[AgentResult]]


class VoiceGateway:
    def __init__(self, settings: Settings) -> None:
        self._model = settings.live_model
        self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

    async def close(self) -> None:
        await self._client.aio.aclose()
        self._client.close()

    async def run(self, websocket: WebSocket, answer_question: AnswerQuestion) -> None:
        async with self._client.aio.live.connect(model=self._model, config=self._config()) as session:
            await websocket.send_json(
                {"type": "session_ready", "input_audio": INPUT_AUDIO, "output_audio": OUTPUT_AUDIO}
            )
            await self._bridge(websocket, session, answer_question)

    async def _bridge(self, websocket: WebSocket, session, answer_question: AnswerQuestion) -> None:
        tasks = [
            asyncio.create_task(self._send_audio(websocket, session)),
            asyncio.create_task(self._receive(websocket, session, answer_question)),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            await task

    async def _send_audio(self, websocket: WebSocket, session) -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if audio := message.get("bytes"):
                await session.send_realtime_input(audio=types.Blob(data=audio, mime_type=INPUT_AUDIO))

    async def _receive(self, websocket: WebSocket, session, answer_question: AnswerQuestion) -> None:
        while True:
            async for response in session.receive():
                if response.data is not None:
                    await websocket.send_bytes(response.data)
                if response.tool_call is not None:
                    await self._answer_tool_call(websocket, session, response.tool_call, answer_question)

                content = response.server_content
                if content is None:
                    continue
                if content.input_transcription is not None:
                    await websocket.send_json({"type": "input_transcript", "text": content.input_transcription.text})
                if content.output_transcription is not None:
                    await websocket.send_json({"type": "output_transcript", "text": content.output_transcription.text})
                if content.interrupted:
                    await websocket.send_json({"type": "interrupted"})
                if content.turn_complete:
                    await websocket.send_json({"type": "turn_complete"})

    async def _answer_tool_call(self, websocket, session, tool_call, answer_question: AnswerQuestion) -> None:
        call = tool_call.function_calls[0]
        result = await answer_question(call.args["question"])
        await websocket.send_json(
            {
                "type": "knowledge_result",
                "answer": result["answer"],
                "agent_session_id": result["agent_session_id"],
            }
        )
        await session.send_tool_response(
            function_responses=types.FunctionResponse(
                id=call.id,
                name=call.name,
                response={"answer": result["answer"]},
            )
        )

    def _config(self) -> dict:
        return {
            "response_modalities": ["AUDIO"],
            "input_audio_transcription": {},
            "output_audio_transcription": {},
            "context_window_compression": {"sliding_window": {}},
            "system_instruction": SYSTEM_PROMPT,
            "tools": [
                {
                    "function_declarations": [
                        {
                            "name": TOOL_NAME,
                            "description": "Answer a question using the current project's merged documentation.",
                            "parameters": {
                                "type": "object",
                                "properties": {"question": {"type": "string"}},
                                "required": ["question"],
                            },
                        }
                    ]
                }
            ],
        }
