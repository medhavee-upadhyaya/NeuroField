"""Supervisor agent — farm-wide triage, outputs a priority work queue."""
import asyncio
import json
import re
from typing import List, Optional

import anthropic

from agent.prompts import build_supervisor_message

MAX_RETRIES = 3
RETRY_DELAY = 2.0


def _parse_queue(raw: str) -> Optional[dict]:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    queue = data.get("priority_queue", [])
    if not isinstance(queue, list):
        return None

    valid = []
    valid_actions = {"irrigate", "spray", "fertilize", "navigate", "report", "wait"}
    valid_urgency = {"critical", "high", "medium", "low"}
    for item in queue[:4]:
        if not isinstance(item, dict):
            continue
        item.setdefault("action", "report")
        item.setdefault("urgency", "low")
        item.setdefault("reasoning", "")
        item.setdefault("sector", "A1")
        if item["action"] not in valid_actions:
            item["action"] = "report"
        if item["urgency"] not in valid_urgency:
            item["urgency"] = "low"
        valid.append(item)

    return {
        "farm_summary": data.get("farm_summary", ""),
        "priority_queue": valid,
    }


class Supervisor:
    def __init__(self, client: anthropic.Anthropic, prompt_store):
        self.client = client
        self.prompt_store = prompt_store
        self.last_result: Optional[dict] = None

    async def plan(self, snapshot: dict, memory_summary: dict) -> Optional[dict]:
        message = build_supervisor_message(snapshot, memory_summary)
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=1024,
                        system=self.prompt_store.get_supervisor_prompt(),
                        messages=[{"role": "user", "content": message}],
                    )
                )
                raw = response.content[0].text
                result = _parse_queue(raw)
                if result:
                    self.last_result = result
                    return result
                print(f"[Supervisor] Parse failed (attempt {attempt + 1}): {raw[:200]}")
            except Exception as e:
                print(f"[Supervisor] API error (attempt {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
        return None
