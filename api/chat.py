"""Chat API — streaming Claude responses grounded in live farm context."""
import json
import os
from typing import AsyncGenerator

import anthropic
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.prompts import CHAT_SYSTEM_PROMPT, build_chat_context

chat_router = APIRouter()

_sensors = None
_memory = None
_brain = None


def inject_chat(sensors, memory, brain):
    global _sensors, _memory, _brain
    _sensors = sensors
    _memory = memory
    _brain = brain


class ChatRequest(BaseModel):
    question: str


async def _stream_claude(question: str, context: str) -> AsyncGenerator[str, None]:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    full_message = f"{context}\n\nQuestion: {question}"

    try:
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=CHAT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": full_message}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


@chat_router.post("/chat")
async def chat(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty")

    # build context from live state
    snapshot = _sensors.snapshot() if _sensors else {"sectors": {}, "active_anomalies": [], "stats": {}}
    memory_data = _memory._data if _memory else {}
    recent_decisions = _memory.get_event_log(limit=10) if _memory else []

    context = build_chat_context(snapshot, memory_data, recent_decisions)

    return StreamingResponse(
        _stream_claude(req.question, context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
