"""Anthropic API agent loop — the reasoning brain of NeuroField."""
import asyncio
import os
import time
from typing import Callable, Optional

import anthropic

from agent.memory import AgentMemory
from agent.planner import parse_action_plan
from agent.prompts import SYSTEM_PROMPT, build_user_message
from simulation.sensors import SensorStream

CYCLE_INTERVAL = 10  # seconds between agent cycles
MAX_RETRIES = 3
RETRY_DELAY = 2.0


class NeuroFieldBrain:
    def __init__(self, sensors: SensorStream, memory: AgentMemory):
        self.sensors = sensors
        self.memory = memory
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self._running = False
        self._on_decision: Optional[Callable] = None
        self._on_execution_request: Optional[Callable] = None
        self.last_decision: Optional[dict] = None
        self.status = "idle"  # idle | thinking | acting

    def on_decision(self, callback: Callable):
        self._on_decision = callback

    def on_execution_request(self, callback: Callable):
        self._on_execution_request = callback

    async def run(self):
        self._running = True
        print("[Brain] Agent loop started")
        while self._running:
            try:
                await self._cycle()
            except Exception as e:
                print(f"[Brain] Cycle error: {e}")
            await asyncio.sleep(CYCLE_INTERVAL)

    async def _cycle(self):
        self.status = "thinking"
        snapshot = self.sensors.tick()
        memory_summary = self.memory.summary_for_agent()
        user_msg = build_user_message(snapshot, memory_summary)

        print(f"\n[Brain] === Cycle at {time.strftime('%H:%M:%S')} ===")
        print(f"[Brain] Anomalies: {snapshot['stats']['anomaly_count']} | Critical: {snapshot['stats']['critical_sectors']}")

        decision = await self._call_claude(user_msg)
        if not decision:
            self.status = "idle"
            return

        self.last_decision = decision
        self.memory.record_decision(decision, snapshot["timestamp"])

        print(f"[Brain] Action: {decision['action']} → {decision['target_sector']} "
              f"(confidence={decision['confidence']:.2f}, alert={decision['alert_level']})")
        print(f"[Brain] Diagnosis: {decision['diagnosis']}")

        if self._on_decision:
            await self._on_decision(decision, snapshot)

        if decision["action"] not in ("report", "wait") and self._on_execution_request:
            self.status = "acting"
            result = await self._on_execution_request(decision["action"], decision["target_sector"])
            self.memory.record_execution(result, decision)
            print(f"[Brain] Execution: {'✓' if result.get('success') else '✗'} "
                  f"({result.get('duration', 0):.1f}s)")

        self.status = "idle"

    async def _call_claude(self, user_message: str) -> Optional[dict]:
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=1024,
                        system=SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": user_message}],
                    )
                )
                raw = response.content[0].text
                plan = parse_action_plan(raw)
                if plan:
                    return plan
                print(f"[Brain] Parse failed (attempt {attempt + 1}): {raw[:200]}")
            except Exception as e:
                print(f"[Brain] API error (attempt {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
        return None

    def stop(self):
        self._running = False
        self.status = "idle"
