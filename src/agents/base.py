import asyncio
import hashlib
from pathlib import Path
from typing import Literal

from deepseek_harness import DeepSeekHarness, RunResult

from config import Settings

AgentName = Literal["document_analyst", "knowledge_assistant"]


class Agent:
    def __init__(self, name: AgentName, system_prompt: str, settings: Settings) -> None:
        home = Path("/data/dsh", name)
        home.mkdir(parents=True, exist_ok=True)
        self._name = name
        self._lock = asyncio.Lock()
        self._harness = DeepSeekHarness(
            provider=settings.provider,
            model=settings.model,
            max_tokens=settings.max_tokens,
            cwd="/app",
            dsh_bin="/usr/local/bin/dsh",
            profile="docmind",
            dsh_home=str(home),
            env={
                "GEMINI_API_KEY": settings.gemini_api_key.get_secret_value(),
                "MCP_URL": str(settings.mcp_url),
                "DSH_SYSTEM_PROMPT": system_prompt,
            },
            request_timeout_seconds=600,
        )

    async def start(self) -> None:
        await asyncio.to_thread(self._harness.start)

    async def close(self) -> None:
        await asyncio.to_thread(self._harness.close)

    async def run(self, prompt: str, thread_id: str, project_id: str) -> RunResult:
        session_id = self._session_id(thread_id, project_id)
        async with self._lock:
            result = await asyncio.to_thread(self._harness.run, prompt, session_id=session_id)
        if not result.final_response.strip():
            raise RuntimeError(f"{self._name} completed without a final response")
        return result

    def _session_id(self, thread_id: str, project_id: str) -> str:
        digest = hashlib.sha256(f"{project_id}\0{thread_id}".encode()).hexdigest()[:24]
        return f"{self._name}-{digest}"
