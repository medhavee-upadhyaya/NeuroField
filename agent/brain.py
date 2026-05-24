"""Orchestrator — runs Supervisor → Worker pipeline every cycle."""
import asyncio
import os
import time
from typing import Callable, List, Optional

import anthropic

from agent.memory import AgentMemory
from agent.outcome_tracker import OutcomeTracker
from agent.supervisor import Supervisor
from agent.worker import Worker
from simulation.sensors import SensorStream

CYCLE_INTERVAL = 10


class NeuroFieldBrain:
    def __init__(self, sensors: SensorStream, memory: AgentMemory):
        self.sensors = sensors
        self.memory = memory
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.supervisor = Supervisor(self.client)
        self.worker = Worker(self.client)
        self.outcome_tracker = OutcomeTracker()
        self._running = False
        self._on_worker_decision: Optional[Callable] = None
        self._on_execution_request: Optional[Callable] = None
        self._on_outcome: Optional[Callable] = None
        self.last_decision: Optional[dict] = None
        self.last_queue: Optional[dict] = None
        self.status = "idle"

        # wire outcome tracker → memory + broadcast
        async def _handle_outcome(result):
            self.memory.record_outcome(result)
            if self._on_outcome:
                await self._on_outcome(result)

        self.outcome_tracker.on_outcome(_handle_outcome)

    def on_decision(self, callback: Callable):
        self._on_worker_decision = callback

    def on_execution_request(self, callback: Callable):
        self._on_execution_request = callback

    def on_outcome(self, callback: Callable):
        self._on_outcome = callback

    async def run(self):
        self._running = True
        print("[Orchestrator] Multi-agent loop started (Supervisor → Worker + Outcome Learning)")
        while self._running:
            try:
                await self._cycle()
            except Exception as e:
                print(f"[Orchestrator] Cycle error: {e}")
            await asyncio.sleep(CYCLE_INTERVAL)

    async def _cycle(self):
        snapshot = self.sensors.tick()
        memory_summary = self.memory.summary_for_agent()

        print(f"\n[Orchestrator] === {time.strftime('%H:%M:%S')} | "
              f"anomalies={snapshot['stats']['anomaly_count']} "
              f"critical={snapshot['stats']['critical_sectors']} ===")

        # ── Check outcomes from previous interventions ────────────────────
        new_outcomes = await self.outcome_tracker.check_due(snapshot)
        if new_outcomes:
            failed = [o for o in new_outcomes if not o.success]
            succeeded = [o for o in new_outcomes if o.success]
            if failed:
                print(f"[Outcome] {len(failed)} failed, {len(succeeded)} succeeded — adjusting priorities")

        # ── Step 1: Supervisor plans ──────────────────────────────────────
        self.status = "thinking"
        plan = await self.supervisor.plan(snapshot, memory_summary)
        if not plan:
            self.status = "idle"
            return

        self.last_queue = plan
        queue: List[dict] = plan.get("priority_queue", [])
        summary = plan.get("farm_summary", "")

        print(f"[Supervisor] {summary}")
        for i, task in enumerate(queue):
            print(f"[Supervisor]   [{i+1}] {task['sector']} → {task['action']} ({task['urgency']})")

        if self._on_worker_decision:
            await self._on_worker_decision(
                {
                    "agent": "supervisor",
                    "farm_summary": summary,
                    "priority_queue": queue,
                    "observation": summary,
                    "diagnosis": f"{len(queue)} tasks queued",
                    "confidence": 1.0,
                    "action": queue[0]["action"] if queue else "wait",
                    "target_sector": queue[0]["sector"] if queue else "",
                    "reasoning": "\n".join(f"{t['sector']}: {t['reasoning']}" for t in queue),
                    "alert_level": queue[0]["urgency"] if queue else "low",
                    "timestamp": time.time(),
                },
                snapshot,
            )

        # ── Step 2: Worker confirms and executes top task ─────────────────
        if not queue or queue[0]["action"] == "wait":
            self.status = "idle"
            return

        top_task = queue[0]
        failed_treatments = memory_summary.get("failed_treatments", {})

        self.status = "acting"
        print(f"[Worker] Confirming: {top_task['sector']} → {top_task['action']}"
              + (" [has failure history]" if top_task["sector"] in failed_treatments else ""))

        worker_result = await self.worker.execute_task(top_task, snapshot, failed_treatments)
        if not worker_result:
            self.status = "idle"
            return

        decision = {
            "agent": "worker",
            "observation": f"Assigned: {top_task['action']} on {top_task['sector']}",
            "diagnosis": worker_result.get("reasoning", ""),
            "confidence": worker_result.get("confidence", 0),
            "action": worker_result.get("action", "report"),
            "target_sector": worker_result.get("target_sector", top_task["sector"]),
            "reasoning": worker_result.get("reasoning", ""),
            "alert_level": worker_result.get("alert_level", "low"),
            "confirmed": worker_result.get("confirmed", False),
            "timestamp": time.time(),
        }

        self.last_decision = decision
        self.memory.record_decision(decision, snapshot["timestamp"])

        confirmed = worker_result.get("confirmed", False)
        print(f"[Worker] {'✓ Confirmed' if confirmed else '✗ Rejected'}: "
              f"{decision['action']} → {decision['target_sector']} "
              f"(confidence={decision['confidence']:.2f})")

        if self._on_worker_decision:
            await self._on_worker_decision(decision, snapshot)

        if confirmed and decision["action"] not in ("report", "wait") and self._on_execution_request:
            result = await self._on_execution_request(decision["action"], decision["target_sector"])
            self.memory.record_execution(result, decision)

            if result.get("success"):
                # register for outcome evaluation in 2 cycles
                self.outcome_tracker.register(decision["target_sector"], decision["action"], snapshot)
                print(f"[Worker] Executed in {result.get('duration', 0):.1f}s — outcome check in {20}s")
            else:
                print(f"[Worker] Execution failed: {result.get('error', '?')}")

        self.status = "idle"

    def stop(self):
        self._running = False
        self.status = "idle"
