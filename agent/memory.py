"""Persistent agent memory — tracks interventions, success rates, chronic sectors."""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

MEMORY_PATH = Path(__file__).parent.parent / "data" / "memory.json"
MAX_LOG_ENTRIES = 200


class AgentMemory:
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self):
        try:
            if MEMORY_PATH.exists():
                self._data = json.loads(MEMORY_PATH.read_text())
            else:
                self._reset()
        except (json.JSONDecodeError, KeyError):
            self._reset()

    def _reset(self):
        self._data = {
            "treated_sectors": {},
            "intervention_stats": {
                action: {"attempts": 0, "successes": 0}
                for action in ("irrigate", "spray", "fertilize", "navigate", "report", "wait")
            },
            "chronic_sectors": {},
            "event_log": [],
            "outcome_log": [],
            "failed_treatments": {},
            "last_updated": None,
        }

    def save(self):
        MEMORY_PATH.write_text(json.dumps(self._data, indent=2))

    # ---- read helpers ----

    def summary_for_agent(self) -> dict:
        now = time.time()
        treated_recently = [
            sid for sid, info in self._data["treated_sectors"].items()
            if now - info.get("timestamp", 0) < 120
        ]
        return {
            "treated_recently": treated_recently,
            "chronic_sectors": self._data["chronic_sectors"],
            "intervention_stats": self._data["intervention_stats"],
            "failed_treatments": self._data.get("failed_treatments", {}),
        }

    def get_outcome_log(self, limit: int = 20) -> List[dict]:
        return list(reversed(self._data.get("outcome_log", [])))[:limit]

    def get_failed_treatments(self) -> dict:
        return self._data.get("failed_treatments", {})

    def get_event_log(self, limit: int = 50) -> List[dict]:
        return list(reversed(self._data["event_log"]))[:limit]

    # ---- write helpers ----

    def record_decision(self, decision: dict, snapshot_timestamp: float):
        entry = {
            "timestamp": time.time(),
            "snapshot_ts": snapshot_timestamp,
            "observation": decision.get("observation", ""),
            "diagnosis": decision.get("diagnosis", ""),
            "confidence": decision.get("confidence", 0),
            "action": decision.get("action", "wait"),
            "target_sector": decision.get("target_sector", ""),
            "reasoning": decision.get("reasoning", ""),
            "alert_level": decision.get("alert_level", "low"),
        }
        self._data["event_log"].append(entry)
        if len(self._data["event_log"]) > MAX_LOG_ENTRIES:
            self._data["event_log"] = self._data["event_log"][-MAX_LOG_ENTRIES:]

        action = decision.get("action", "wait")
        if action in self._data["intervention_stats"]:
            self._data["intervention_stats"][action]["attempts"] += 1

        self._data["last_updated"] = time.time()
        self.save()

    def record_execution(self, result: dict, decision: dict):
        action = decision.get("action", "wait")
        sector = decision.get("target_sector", "")
        success = result.get("success", False)

        if action in self._data["intervention_stats"] and success:
            self._data["intervention_stats"][action]["successes"] += 1

        if sector and action not in ("report", "wait", "navigate"):
            self._data["treated_sectors"][sector] = {
                "timestamp": time.time(),
                "action": action,
                "success": success,
            }
            # track chronic
            if sector not in self._data["chronic_sectors"]:
                self._data["chronic_sectors"][sector] = {"occurrences": 0, "actions": []}
            self._data["chronic_sectors"][sector]["occurrences"] += 1
            self._data["chronic_sectors"][sector]["actions"].append({
                "action": action,
                "time": time.time(),
                "success": success,
            })

        self._data["last_updated"] = time.time()
        self.save()

    def record_outcome(self, outcome) -> None:
        """Called by OutcomeTracker with an OutcomeResult dataclass."""
        entry = {
            "sector_id": outcome.sector_id,
            "action": outcome.action,
            "success": outcome.success,
            "pre": outcome.pre,
            "post": outcome.post,
            "delta": outcome.delta,
            "evaluated_at": outcome.evaluated_at,
            "note": outcome.note,
        }
        if "outcome_log" not in self._data:
            self._data["outcome_log"] = []
        self._data["outcome_log"].append(entry)
        if len(self._data["outcome_log"]) > 100:
            self._data["outcome_log"] = self._data["outcome_log"][-100:]

        if not outcome.success:
            if "failed_treatments" not in self._data:
                self._data["failed_treatments"] = {}
            prev = self._data["failed_treatments"].get(outcome.sector_id, {})
            self._data["failed_treatments"][outcome.sector_id] = {
                "action": outcome.action,
                "fail_count": prev.get("fail_count", 0) + 1,
                "delta": outcome.delta,
                "last_failed_at": outcome.evaluated_at,
            }
        else:
            # clear failure record on success
            self._data.get("failed_treatments", {}).pop(outcome.sector_id, None)

        # update action-level success rate
        action = outcome.action
        if action in self._data["intervention_stats"] and outcome.success:
            self._data["intervention_stats"][action]["outcome_successes"] = (
                self._data["intervention_stats"][action].get("outcome_successes", 0) + 1
            )

        self._data["last_updated"] = time.time()
        self.save()

    def reset(self):
        self._reset()
        self.save()
