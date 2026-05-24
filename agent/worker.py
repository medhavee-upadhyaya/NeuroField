"""Worker agent — confirms and executes one task assigned by the Supervisor."""
import asyncio
import json
import re
from typing import Optional

import anthropic

from agent.planner import validate_plan
from agent.prompts import WORKER_PROMPT, build_worker_message

MAX_RETRIES = 2
RETRY_DELAY = 1.5


def _parse_worker_response(raw: str) -> Optional[dict]:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    data.setdefault("confirmed", False)
    data.setdefault("action", "report")
    data.setdefault("target_sector", "A1")
    data.setdefault("confidence", 0.0)
    data.setdefault("reasoning", "")
    data.setdefault("alert_level", "low")

    try:
        data["confidence"] = float(data["confidence"])
    except (TypeError, ValueError):
        data["confidence"] = 0.0

    data["confidence"] = max(0.0, min(1.0, data["confidence"]))
    if data["confidence"] < 0.4:
        data["confirmed"] = False
        data["action"] = "report"

    return data


class Worker:
    def __init__(self, client: anthropic.Anthropic):
        self.client = client
        self.last_result: Optional[dict] = None

    async def execute_task(self, task: dict, snapshot: dict) -> Optional[dict]:
        message = build_worker_message(task, snapshot)
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=512,
                        system=WORKER_PROMPT,
                        messages=[{"role": "user", "content": message}],
                    )
                )
                raw = response.content[0].text
                result = _parse_worker_response(raw)
                if result:
                    self.last_result = result
                    return result
                print(f"[Worker] Parse failed (attempt {attempt + 1}): {raw[:200]}")
            except Exception as e:
                print(f"[Worker] API error (attempt {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
        return None
