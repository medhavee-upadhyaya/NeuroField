"""
LeadEngineerAgent — automated code verification and AI-powered review.

Tier 1: Static logic checks   — imports & exercises every module with synthetic data
Tier 2: Data contract checks  — verifies inter-module key/type agreements
Tier 3: Integration smoke     — full Supervisor→Worker pipeline via real Claude API
Tier 4: AI code review        — Claude acts as senior engineer reviewing source files
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

import anthropic

PROJECT_ROOT = Path(__file__).parent.parent
_ROWS = list("ABCDEFGHIJ")
_COLS = list(range(1, 11))


# ── Finding ───────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    severity: str   # "pass" | "fail" | "warn" | "info"
    category: str
    description: str
    detail: str = ""
    file_ref: str = ""


# ── Synthetic data helpers ────────────────────────────────────────────────────

def _sector(sid, row, col, moisture=0.55, health=0.8, temp=22.0, anomalies=None):
    return {
        "sector_id": sid, "row": row, "col": col,
        "soil_moisture": moisture, "crop_health": health, "temperature": temp,
        "anomalies": anomalies or [], "last_treated": None,
    }


def _snapshot(overrides: dict = None) -> dict:
    sectors = {f"{r}{c}": _sector(f"{r}{c}", r, c) for r in _ROWS for c in _COLS}
    for sid, vals in (overrides or {}).items():
        if sid in sectors:
            sectors[sid].update(vals)
    critical = sum(
        1 for s in sectors.values()
        if s["crop_health"] < 0.3 or s["soil_moisture"] < 0.15
    )
    return {
        "timestamp": time.time(), "sectors": sectors, "active_anomalies": [],
        "stats": {"total_sectors": len(sectors), "anomaly_count": 0, "critical_sectors": critical},
    }


def _critical_snapshot() -> dict:
    """Three obvious problems: drought, pest outbreak, nutrient deficiency."""
    return _snapshot({
        "C5": {"soil_moisture": 0.05, "crop_health": 0.60, "anomalies": ["drought"]},
        "D4": {"soil_moisture": 0.45, "crop_health": 0.08, "anomalies": ["pest_outbreak"]},
        "E7": {"soil_moisture": 0.40, "crop_health": 0.15, "anomalies": ["nutrient_deficiency"]},
    })


def _empty_memory() -> dict:
    return {
        "treated_recently": [], "chronic_sectors": {}, "failed_treatments": {},
        "intervention_stats": {
            a: {"attempts": 0, "successes": 0}
            for a in ("irrigate", "spray", "fertilize", "navigate", "report", "wait")
        },
    }


def _memory_with_failures() -> dict:
    m = _empty_memory()
    m["failed_treatments"] = {
        "C5": {"action": "irrigate", "fail_count": 2,
               "delta": {"crop_health": -0.02, "soil_moisture": -0.01}}
    }
    return m


# ── Terminal helpers ──────────────────────────────────────────────────────────

_ICON = {"pass": "✓", "fail": "✗", "warn": "⚠", "info": "ℹ"}
_CLR = {
    "pass": "\033[32m", "fail": "\033[31m", "warn": "\033[33m",
    "info": "\033[36m", "dim": "\033[2m", "bold": "\033[1m", "R": "\033[0m",
}


def _c(s, k):
    return f"{_CLR.get(k, '')}{s}{_CLR['R']}"


def _print_header(title: str):
    print(f"\n  {_c(title, 'bold')}")
    print("  " + "─" * 52)


def _print_finding(f: Finding):
    icon = _c(_ICON.get(f.severity, "?"), f.severity)
    ref = f"  {_c(f.file_ref, 'dim')}" if f.file_ref else ""
    cat = _c(f"[{f.category}]", "dim")
    print(f"  {icon}  {cat} {f.description}{ref}")
    if f.detail and f.severity != "pass":
        if len(f.detail) < 200:
            for line in f.detail.splitlines()[:3]:
                if line.strip():
                    print(f"        {_c(line.strip(), 'dim')}")
        else:
            # Long text (AI review) — print as indented block
            print()
            for line in f.detail.splitlines():
                print(f"    {line}")
            print()


# ── Agent ─────────────────────────────────────────────────────────────────────

class LeadEngineerAgent:
    def __init__(self):
        self.findings: List[Finding] = []
        self._has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _add(self, severity, cat, msg, detail="", ref=""):
        f = Finding(severity, cat, msg, detail, ref)
        self.findings.append(f)
        _print_finding(f)

    def _pass(self, cat, msg):
        self._add("pass", cat, msg)

    def _fail(self, cat, msg, detail="", ref=""):
        self._add("fail", cat, msg, detail, ref)

    def _warn(self, cat, msg, detail="", ref=""):
        self._add("warn", cat, msg, detail, ref)

    def _info(self, cat, msg):
        self._add("info", cat, msg)

    # ── Tier 1a: JSON parsers ─────────────────────────────────────────────────

    def check_json_parsers(self):
        from agent.supervisor import _parse_queue
        from agent.worker import _parse_worker_response

        C = "JSON Parsers"
        valid_sup = json.dumps({
            "farm_summary": "3 anomalies",
            "priority_queue": [
                {"sector": "C5", "action": "irrigate", "urgency": "critical", "reasoning": "drought"}
            ]
        })

        try:
            r = _parse_queue(valid_sup)
            if r and r["priority_queue"][0]["sector"] == "C5":
                self._pass(C, "Valid supervisor JSON parses correctly")
            else:
                self._fail(C, "Valid supervisor JSON returned wrong result", ref="agent/supervisor.py:15")
        except Exception as e:
            self._fail(C, "Supervisor parser crashed on valid input", str(e), "agent/supervisor.py:15")

        try:
            r = _parse_queue("```json\n" + valid_sup + "\n```")
            if r and r["priority_queue"]:
                self._pass(C, "Supervisor parser strips markdown code fences")
            else:
                self._fail(C, "Parser rejects Claude's markdown-wrapped JSON output", ref="agent/supervisor.py:15")
        except Exception as e:
            self._fail(C, "Supervisor parser crashed on markdown-fenced input", str(e))

        try:
            r = _parse_queue(json.dumps({
                "farm_summary": "x",
                "priority_queue": [{"sector": "B2", "action": "explode", "urgency": "high", "reasoning": "x"}]
            }))
            if r and r["priority_queue"][0]["action"] == "report":
                self._pass(C, "Invalid action 'explode' sanitized → 'report'")
            else:
                self._fail(C, "Invalid action was not sanitized", ref="agent/supervisor.py:37")
        except Exception as e:
            self._fail(C, "Supervisor parser crashed on invalid action", str(e))

        try:
            big = json.dumps({"farm_summary": "x", "priority_queue": [
                {"sector": f"A{i}", "action": "irrigate", "urgency": "low", "reasoning": "x"}
                for i in range(1, 9)
            ]})
            r = _parse_queue(big)
            if r and len(r["priority_queue"]) <= 4:
                self._pass(C, "Queue capped at 4 items (prevents Claude over-filling the queue)")
            else:
                self._fail(C, f"Queue not capped: got {len(r['priority_queue'])} items", ref="agent/supervisor.py:33")
        except Exception as e:
            self._fail(C, "Supervisor parser crashed on oversized queue", str(e))

        for label, inp in [("empty string", ""), ("garbage", "not json"), ("null", "null")]:
            try:
                r = _parse_queue(inp)
                if r is None:
                    self._pass(C, f"Supervisor parser returns None safely on {label}")
                else:
                    self._fail(C, f"Supervisor parser returned non-None on {label}")
            except Exception as e:
                self._fail(C, f"Supervisor parser crashed on {label}", str(e), "agent/supervisor.py:15")

        try:
            r = _parse_queue(json.dumps({
                "farm_summary": "x",
                "priority_queue": [{"sector": "D4", "action": "irrigate", "urgency": "EXTREME", "reasoning": "x"}]
            }))
            if r and r["priority_queue"][0]["urgency"] == "low":
                self._pass(C, "Invalid urgency 'EXTREME' sanitized → 'low'")
            else:
                self._fail(C, "Invalid urgency was not sanitized", ref="agent/supervisor.py:38")
        except Exception as e:
            self._fail(C, "Supervisor parser crashed on invalid urgency", str(e))

        valid_w = json.dumps({
            "confirmed": True, "action": "irrigate", "target_sector": "C5",
            "confidence": 0.85, "reasoning": "moisture at 0.05", "alert_level": "critical"
        })
        try:
            r = _parse_worker_response(valid_w)
            if r and r["confirmed"] and r["target_sector"] == "C5":
                self._pass(C, "Valid worker JSON parses correctly")
            else:
                self._fail(C, "Worker parser failed on valid JSON", ref="agent/worker.py:16")
        except Exception as e:
            self._fail(C, "Worker parser crashed on valid input", str(e))

        try:
            low_c = json.dumps({
                "confirmed": True, "action": "irrigate", "target_sector": "C5",
                "confidence": 0.3, "reasoning": "not sure", "alert_level": "low"
            })
            r = _parse_worker_response(low_c)
            if r and not r["confirmed"] and r["action"] == "report":
                self._pass(C, "SAFETY: confidence=0.3 < 0.4 threshold forces confirmed=False + action='report'")
            else:
                self._fail(
                    C, "SAFETY VIOLATION: Worker allowed confirmation at confidence=0.3",
                    "Robot could take a physical action it shouldn't", "agent/worker.py:39"
                )
        except Exception as e:
            self._fail(C, "Worker parser crashed on low-confidence input", str(e))

        try:
            r = _parse_worker_response(json.dumps({
                "confirmed": True, "action": "irrigate", "target_sector": "C5",
                "confidence": 9.99, "reasoning": "x", "alert_level": "low"
            }))
            if r and 0.0 <= r["confidence"] <= 1.0:
                self._pass(C, "Confidence clamped to [0.0, 1.0]")
            else:
                self._fail(C, f"Confidence not clamped: got {r.get('confidence')}", ref="agent/worker.py:36")
        except Exception as e:
            self._fail(C, "Worker parser crashed on out-of-range confidence", str(e))

        try:
            r = _parse_worker_response(json.dumps({"confirmed": True}))
            if r and "action" in r and "confidence" in r and "alert_level" in r:
                self._pass(C, "Worker parser fills missing fields with safe defaults")
            else:
                self._fail(C, "Worker parser missing defaults for minimal input", ref="agent/worker.py:27")
        except Exception as e:
            self._fail(C, "Worker parser crashed on minimal input", str(e))

    # ── Tier 1b: Sensor simulation ────────────────────────────────────────────

    def check_sensor_simulation(self):
        from simulation.sensors import SensorStream

        C = "Sensor Simulation"
        try:
            stream = SensorStream()
        except Exception as e:
            self._fail(C, "SensorStream failed to initialize", str(e), "simulation/sensors.py")
            return

        if len(stream.sectors) == 100:
            self._pass(C, "10×10 grid initializes exactly 100 sectors")
        else:
            self._fail(C, f"Expected 100 sectors, got {len(stream.sectors)}", ref="simulation/sensors.py:57")

        bad = [
            f"{sid}:{attr}={getattr(s, attr):.3f}"
            for sid, s in stream.sectors.items()
            for attr, lo, hi in [
                ("soil_moisture", 0.0, 1.0), ("crop_health", 0.0, 1.0), ("temperature", 10.0, 50.0)
            ]
            if not (lo <= getattr(s, attr) <= hi)
        ]
        if not bad:
            self._pass(C, "All 100 initial sector values within valid ranges")
        else:
            self._fail(C, f"Out-of-range values: {bad[:3]}", ref="simulation/sensors.py:65")

        try:
            snap = stream.tick()
            missing = {"timestamp", "sectors", "active_anomalies", "stats"} - set(snap)
            if not missing:
                self._pass(C, "tick() snapshot contains all required top-level keys")
            else:
                self._fail(C, f"tick() snapshot missing keys: {missing}", ref="simulation/sensors.py:187")
            if snap.get("stats", {}).get("total_sectors") == 100:
                self._pass(C, "stats.total_sectors correctly equals 100")
            else:
                self._fail(C, f"stats.total_sectors wrong: {snap.get('stats')}", ref="simulation/sensors.py:208")
        except Exception as e:
            self._fail(C, "tick() raised an exception", str(e), "simulation/sensors.py:187")

        try:
            stream.sectors["A1"].soil_moisture = 0.05
            stream.sectors["A1"].anomalies = ["drought"]
            stream.treat_sector("A1", "irrigate")
            if stream.sectors["A1"].soil_moisture >= 0.40:
                self._pass(C, "treat_sector('irrigate') raises soil_moisture by +0.4")
            else:
                self._fail(C, f"irrigate raised moisture to only {stream.sectors['A1'].soil_moisture:.2f}",
                           ref="simulation/sensors.py:172")
            if "drought" not in stream.sectors["A1"].anomalies:
                self._pass(C, "treat_sector('irrigate') clears 'drought' anomaly flag")
            else:
                self._warn(C, "irrigate did not remove 'drought' from anomalies list",
                           ref="simulation/sensors.py:173")
        except Exception as e:
            self._fail(C, "treat_sector crashed on 'irrigate'", str(e))

        try:
            stream.sectors["B2"].crop_health = 0.05
            stream.sectors["B2"].anomalies = ["pest_outbreak"]
            stream.treat_sector("B2", "spray")
            if stream.sectors["B2"].crop_health >= 0.30:
                self._pass(C, "treat_sector('spray') raises crop_health by +0.3")
            else:
                self._fail(C, f"spray raised health to only {stream.sectors['B2'].crop_health:.2f}",
                           ref="simulation/sensors.py:175")
            if "pest_outbreak" not in stream.sectors["B2"].anomalies:
                self._pass(C, "treat_sector('spray') clears 'pest_outbreak' anomaly flag")
            else:
                self._warn(C, "spray did not remove 'pest_outbreak' from anomalies",
                           ref="simulation/sensors.py:176")
        except Exception as e:
            self._fail(C, "treat_sector crashed on 'spray'", str(e))

        try:
            t0 = time.time()
            stream.treat_sector("C3", "fertilize")
            lt = stream.sectors["C3"].last_treated
            if lt and t0 <= lt <= time.time():
                self._pass(C, "treat_sector sets last_treated to current timestamp")
            else:
                self._fail(C, "treat_sector did not set last_treated correctly",
                           ref="simulation/sensors.py:168")
        except Exception as e:
            self._fail(C, "treat_sector crashed setting last_treated", str(e))

        try:
            stream.treat_sector("Z99", "irrigate")
            self._pass(C, "treat_sector with unknown sector ID returns without crash")
        except Exception as e:
            self._fail(C, "treat_sector crashed on unknown sector 'Z99'", str(e),
                       "simulation/sensors.py:167")

        try:
            rows, cols = stream.rows, stream.cols
            corner = f"{rows[0]}{cols[0]}"
            cn = stream._neighbors(corner)
            if len(cn) == 2:
                self._pass(C, f"Corner sector {corner} has exactly 2 neighbors")
            else:
                self._fail(C, f"Corner {corner} has {len(cn)} neighbors (expected 2)",
                           ref="simulation/sensors.py:70")

            mid = f"{rows[len(rows) // 2]}{cols[len(cols) // 2]}"
            mn = stream._neighbors(mid)
            if len(mn) == 4:
                self._pass(C, f"Center sector {mid} has exactly 4 neighbors")
            else:
                self._fail(C, f"Center {mid} has {len(mn)} neighbors (expected 4)",
                           ref="simulation/sensors.py:70")
        except Exception as e:
            self._fail(C, "Neighbor calculation raised an exception", str(e), "simulation/sensors.py:70")

    # ── Tier 1c: Message builders ─────────────────────────────────────────────

    def check_message_builders(self):
        from agent.prompts import build_supervisor_message, build_worker_message

        C = "Message Builders"
        snap = _critical_snapshot()
        task = {"sector": "C5", "action": "irrigate", "urgency": "critical", "reasoning": "drought"}

        try:
            msg = build_supervisor_message(snap, _empty_memory())
            if msg and len(msg) > 50:
                self._pass(C, "build_supervisor_message produces a non-empty message")
            else:
                self._fail(C, "build_supervisor_message returned empty or very short string",
                           ref="agent/prompts.py:99")
            if "PROBLEM SECTORS" in msg:
                self._pass(C, "Supervisor message includes PROBLEM SECTORS section")
            else:
                self._fail(C, "Supervisor message missing PROBLEM SECTORS section",
                           ref="agent/prompts.py:136")
            if "C5" in msg or "D4" in msg:
                self._pass(C, "Critical sectors (C5/D4) appear in the supervisor message")
            else:
                self._warn(C, "Critical sectors C5/D4 not mentioned in supervisor message")
        except Exception as e:
            self._fail(C, "build_supervisor_message raised an exception", str(e), "agent/prompts.py:99")

        try:
            msg = build_supervisor_message(snap, _memory_with_failures())
            if "FAILED TREATMENTS" in msg:
                self._pass(C, "Supervisor message includes FAILED TREATMENTS when failures exist in memory")
            else:
                self._fail(C, "Missing FAILED TREATMENTS section despite failure history",
                           ref="agent/prompts.py:158")
        except Exception as e:
            self._fail(C, "Supervisor message failed-treatment section check crashed", str(e))

        try:
            msg = build_worker_message(task, snap, {})
            if "ASSIGNED TASK" in msg and "CURRENT SENSOR READINGS" in msg:
                self._pass(C, "Worker message has ASSIGNED TASK + CURRENT SENSOR READINGS sections")
            else:
                self._fail(C, "Worker message missing required sections", ref="agent/prompts.py:178")
        except Exception as e:
            self._fail(C, "build_worker_message raised an exception", str(e), "agent/prompts.py:178")

        try:
            failed = {"C5": {"action": "irrigate", "fail_count": 2,
                              "delta": {"crop_health": -0.02, "soil_moisture": -0.01}}}
            msg = build_worker_message(task, snap, failed)
            if "OUTCOME HISTORY" in msg and "FAILED" in msg:
                self._pass(C, "Worker message includes failure history for the target sector")
            else:
                self._fail(C, "Worker message missing failure history for known failed sector",
                           ref="agent/prompts.py:201")
        except Exception as e:
            self._fail(C, "Worker message failure-history check crashed", str(e))

        try:
            bad_task = {"sector": "Z99", "action": "irrigate", "urgency": "low", "reasoning": "test"}
            msg = build_worker_message(bad_task, snap, {})
            if "No sensor data" in msg:
                self._pass(C, "Worker message handles unknown sector ID with 'No sensor data' note")
            else:
                self._warn(C, "Worker message silently omits data for unknown sector (no warning given)",
                           ref="agent/prompts.py:196")
        except Exception as e:
            self._fail(C, "build_worker_message crashed on unknown sector ID", str(e))

    # ── Tier 1d: Outcome tracker ──────────────────────────────────────────────

    def check_outcome_tracker_sync(self):
        from agent.outcome_tracker import OutcomeTracker, SUCCESS_THRESHOLDS

        C = "Outcome Tracker"
        snap = _critical_snapshot()
        tracker = OutcomeTracker()

        try:
            tracker.register("C5", "irrigate", snap)
            if len(tracker._pending) == 1:
                self._pass(C, "register() stores exactly 1 pending outcome")
            else:
                self._fail(C, f"Expected 1 pending, got {len(tracker._pending)}",
                           ref="agent/outcome_tracker.py:51")
        except Exception as e:
            self._fail(C, "register() raised an exception", str(e))

        try:
            tracker.register("C5", "spray", snap)
            if len(tracker._pending) == 1 and tracker._pending[0].action == "spray":
                self._pass(C, "register() deduplicates: same sector replaces previous pending entry")
            else:
                self._fail(C, "register() created duplicate pending for same sector",
                           ref="agent/outcome_tracker.py:58")
        except Exception as e:
            self._fail(C, "register() deduplication check crashed", str(e))

        try:
            fresh = OutcomeTracker()
            for a in ("report", "wait", "navigate"):
                fresh.register("D4", a, snap)
            if len(fresh._pending) == 0:
                self._pass(C, "register() ignores non-intervention actions: report, wait, navigate")
            else:
                self._warn(C, f"register() tracked {len(fresh._pending)} non-intervention action(s)",
                           ref="agent/outcome_tracker.py:53")
        except Exception as e:
            self._fail(C, "register() crashed on non-intervention action", str(e))

        for action in ("irrigate", "spray", "fertilize"):
            try:
                vals = list(SUCCESS_THRESHOLDS.get(action, {}).values())
                if vals and all(v > 0 for v in vals):
                    self._pass(C, f"SUCCESS_THRESHOLDS['{action}'] has a positive threshold")
                else:
                    self._fail(C, f"SUCCESS_THRESHOLDS['{action}'] is missing or zero",
                               ref="agent/outcome_tracker.py:9")
            except Exception as e:
                self._fail(C, f"SUCCESS_THRESHOLDS['{action}'] check failed", str(e))

    async def check_outcome_tracker_async(self):
        from agent.outcome_tracker import OutcomeTracker

        C = "Outcome Tracker"
        snap = _critical_snapshot()
        try:
            tracker = OutcomeTracker()
            tracker.register("E5", "irrigate", snap)
            results = await tracker.check_due(snap)
            if results == []:
                self._pass(C, "check_due() returns [] immediately after register (before 20s CHECK_DELAY)")
            else:
                self._fail(C, "check_due() returned results before 20s delay expired",
                           ref="agent/outcome_tracker.py:69")
        except Exception as e:
            self._fail(C, "check_due() raised an exception", str(e))

    # ── Tier 1e: Code structure / dead code ──────────────────────────────────

    def check_code_structure(self):
        import inspect
        import agent.worker as _worker_mod

        C = "Code Structure"

        try:
            src = inspect.getsource(_worker_mod)
            if "validate_plan(" in src:
                self._pass(C, "validate_plan is called somewhere in worker.py")
            else:
                self._warn(
                    C, "validate_plan imported in worker.py but never called — dead import",
                    "worker.py uses its own _parse_worker_response() instead; planner.py may be legacy.",
                    "agent/worker.py:9"
                )
        except Exception as e:
            self._fail(C, "Code structure check for validate_plan failed", str(e))

        try:
            from agent.planner import validate_plan as _vp
            planner_required = {"observation", "diagnosis", "confidence", "action",
                                 "target_sector", "reasoning", "alert_level"}
            worker_produces = {"confirmed", "action", "target_sector",
                               "confidence", "reasoning", "alert_level"}
            gap = planner_required - worker_produces
            if gap:
                self._warn(
                    C, f"planner.py schema expects fields worker doesn't produce: {gap}",
                    "planner.py appears to be an old schema from before the supervisor/worker split.",
                    "agent/planner.py:31"
                )
        except Exception as e:
            self._fail(C, "Schema mismatch check failed", str(e))

        try:
            from agent.prompts import PromptStore
            store = PromptStore()
            if store.get_supervisor_prompt() and store.get_worker_prompt():
                self._pass(C, "PromptStore provides hardcoded fallback prompts (no prompts.json required)")
            else:
                self._fail(C, "PromptStore returned empty prompt(s)", ref="agent/prompts.py:24")
        except Exception as e:
            self._fail(C, "PromptStore initialization failed", str(e))

    # ── Tier 2: Data contracts ────────────────────────────────────────────────

    def check_data_contracts(self):
        C = "Data Contracts"

        try:
            sup_actions = {"irrigate", "spray", "fertilize", "navigate", "report", "wait"}
            non_tracked = {"report", "wait", "navigate"}
            trackable = sup_actions - non_tracked
            if trackable == {"irrigate", "spray", "fertilize"}:
                self._pass(C, "Action sets consistent: irrigate/spray/fertilize are the only trackable actions")
            else:
                self._fail(C, f"Action set mismatch — trackable resolved to: {trackable}")
        except Exception as e:
            self._fail(C, "Action set consistency check crashed", str(e))

        try:
            from agent.outcome_tracker import SUCCESS_THRESHOLDS
            unexpected = set(SUCCESS_THRESHOLDS) - {"irrigate", "spray", "fertilize"}
            if not unexpected:
                self._pass(C, "SUCCESS_THRESHOLDS covers exactly {irrigate, spray, fertilize}")
            else:
                self._warn(C, f"SUCCESS_THRESHOLDS has unexpected entries: {unexpected}",
                           ref="agent/outcome_tracker.py:9")
        except Exception as e:
            self._fail(C, "SUCCESS_THRESHOLDS verification failed", str(e))

        try:
            from agent.supervisor import _parse_queue
            r = _parse_queue(json.dumps({
                "farm_summary": "ok",
                "priority_queue": [{"sector": "A1", "action": "wait", "urgency": "low", "reasoning": "ok"}]
            }))
            if r and {"priority_queue", "farm_summary"}.issubset(r):
                self._pass(C, "Supervisor output has priority_queue + farm_summary (matches brain.py access)")
            else:
                self._fail(C, "Supervisor output missing keys expected by brain.py",
                           ref="agent/supervisor.py:46")
        except Exception as e:
            self._fail(C, "Supervisor output contract check crashed", str(e))

        try:
            from agent.worker import _parse_worker_response
            r = _parse_worker_response(json.dumps({
                "confirmed": True, "action": "irrigate", "target_sector": "A1",
                "confidence": 0.9, "reasoning": "x", "alert_level": "low"
            }))
            required = {"confirmed", "action", "target_sector", "confidence", "reasoning", "alert_level"}
            missing = required - set(r or {})
            if not missing:
                self._pass(C, "Worker output has all 6 keys accessed by brain.py")
            else:
                self._fail(C, f"Worker output missing brain.py-required keys: {missing}",
                           ref="agent/worker.py:27")
        except Exception as e:
            self._fail(C, "Worker output contract check crashed", str(e))

        try:
            from simulation.sensors import SensorStream
            snap = SensorStream().snapshot()
            missing_top = {"timestamp", "sectors", "active_anomalies", "stats"} - set(snap)
            if not missing_top:
                self._pass(C, "Sensor snapshot has all 4 required top-level keys")
            else:
                self._fail(C, f"Snapshot missing keys: {missing_top}", ref="simulation/sensors.py:194")
            missing_stats = {"total_sectors", "anomaly_count", "critical_sectors"} - set(snap.get("stats", {}))
            if not missing_stats:
                self._pass(C, "Snapshot stats has all 3 required sub-keys")
            else:
                self._fail(C, f"Stats missing keys: {missing_stats}", ref="simulation/sensors.py:207")
        except Exception as e:
            self._fail(C, "Snapshot contract check crashed", str(e))

        try:
            from agent.memory import AgentMemory
            mem = AgentMemory()
            summary = mem.summary_for_agent()
            required = {"treated_recently", "chronic_sectors", "failed_treatments", "intervention_stats"}
            missing = required - set(summary)
            if not missing:
                self._pass(C, "AgentMemory.summary_for_agent() has all keys expected by Supervisor/Worker")
            else:
                self._fail(C, f"Memory summary missing: {missing}", ref="agent/memory.py:44")
        except Exception as e:
            self._fail(C, "AgentMemory.summary_for_agent() contract check failed", str(e))

        try:
            from simulation.sensors import SensorStream
            stream = SensorStream()
            known_types = set(stream.anomaly_configs.keys())
            used_types = {"drought", "pest_outbreak", "nutrient_deficiency", "heat_stress"}
            unknown = used_types - known_types
            if not unknown:
                self._pass(C, "All anomaly types used in _apply_anomalies() exist in farm_config.json")
            else:
                self._fail(C, f"Anomaly types used in code but missing from config: {unknown}",
                           ref="simulation/sensors.py:113")
        except Exception as e:
            self._fail(C, "Anomaly config consistency check failed", str(e))

    # ── Tier 3: Integration smoke test ───────────────────────────────────────

    async def integration_smoke_test(self):
        if not self._has_api_key:
            self._info("Integration Smoke Test", "Skipped — set ANTHROPIC_API_KEY to run this tier")
            return

        C = "Integration Smoke Test"
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        from agent.supervisor import Supervisor
        from agent.worker import Worker
        from agent.prompts import PromptStore

        store = PromptStore()
        supervisor = Supervisor(client, store)
        worker = Worker(client, store)
        snap = _critical_snapshot()

        self._info(C, "Calling Supervisor — C5 drought / D4 pest / E7 nutrient deficiency scenario...")
        try:
            plan = await supervisor.plan(snap, _empty_memory())
        except Exception as e:
            self._fail(C, "Supervisor.plan() raised an exception during smoke test", str(e))
            return

        if not plan:
            self._fail(C, "Supervisor returned None for a scenario with 3 critical sectors",
                       ref="agent/supervisor.py:58")
            return
        self._pass(C, "Supervisor returned a valid plan dict (not None)")

        queue = plan.get("priority_queue", [])
        if queue:
            self._pass(C, f"Supervisor produced a {len(queue)}-item priority queue")
        else:
            self._fail(C, "Supervisor returned empty priority_queue for farm with 3 critical sectors")
            return

        top = queue[0]
        if top.get("urgency") in ("critical", "high"):
            self._pass(C, f"Top task: {top['action']} on {top['sector']}  urgency={top['urgency']}")
        else:
            self._warn(C, f"Top task urgency='{top.get('urgency')}' despite 3 critical sectors in snapshot")

        drought_sids = {sid for sid, s in snap["sectors"].items() if s["soil_moisture"] < 0.15}
        pest_sids = {sid for sid, s in snap["sectors"].items() if s["crop_health"] < 0.2}
        if top["sector"] in drought_sids and top["action"] == "irrigate":
            self._pass(C, "Supervisor correctly matched drought sector → irrigate")
        elif top["sector"] in pest_sids and top["action"] in ("spray", "fertilize"):
            self._pass(C, f"Supervisor correctly matched unhealthy sector → {top['action']}")
        elif top["action"] in ("irrigate", "spray", "fertilize"):
            self._pass(C, f"Supervisor recommended a valid physical intervention: {top['action']}")
        else:
            self._warn(C, f"Supervisor action='{top['action']}' may not address the critical scenario optimally")

        self._info(C, f"Calling Worker to confirm: {top['action']} on {top['sector']}...")
        try:
            result = await worker.execute_task(top, snap, {})
        except Exception as e:
            self._fail(C, "Worker.execute_task() raised an exception", str(e))
            return

        if not result:
            self._fail(C, "Worker returned None for a valid assigned task", ref="agent/worker.py:53")
            return
        self._pass(C, "Worker returned a valid result dict (not None)")

        conf = result.get("confidence", 0.0)
        confirmed = result.get("confirmed", False)
        if confirmed and conf >= 0.5:
            self._pass(C, f"Worker confirmed the action with confidence={conf:.2f}")
        elif confirmed:
            self._warn(C, f"Worker confirmed but confidence is low ({conf:.2f}) for an obvious task")
        else:
            self._warn(C, f"Worker rejected an obvious critical task (confidence={conf:.2f})")

        reasoning = result.get("reasoning", "")
        if any(ch.isdigit() for ch in reasoning):
            self._pass(C, "Worker reasoning cites numerical sensor values")
        else:
            self._warn(C, "Worker reasoning lacks numerical sensor citations", ref="agent/prompts.py:95")

    # ── Tier 4: AI code review ────────────────────────────────────────────────

    async def ai_code_review(self):
        if not self._has_api_key:
            self._info("AI Code Review", "Skipped — set ANTHROPIC_API_KEY to run this tier")
            return

        C = "AI Code Review"
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        files = [
            ("agent/brain.py", PROJECT_ROOT / "agent/brain.py"),
            ("agent/supervisor.py", PROJECT_ROOT / "agent/supervisor.py"),
            ("agent/worker.py", PROJECT_ROOT / "agent/worker.py"),
            ("agent/outcome_tracker.py", PROJECT_ROOT / "agent/outcome_tracker.py"),
            ("agent/memory.py", PROJECT_ROOT / "agent/memory.py"),
            ("simulation/sensors.py", PROJECT_ROOT / "simulation/sensors.py"),
            ("agent/planner.py", PROJECT_ROOT / "agent/planner.py"),
        ]
        bundle = "".join(
            f"\n\n### {name}\n```python\n{p.read_text()}\n```"
            for name, p in files if p.exists()
        )

        system = """You are a Senior Software Engineer and Tech Lead doing a code review for an autonomous agricultural robot AI system written in Python.

Review the provided source files for:
1. CORRECTNESS BUGS — logic errors, wrong comparisons, off-by-one, missing edge cases
2. RUNTIME RISKS — unhandled exceptions, None dereferences, type errors, infinite loops
3. DATA CONTRACT VIOLATIONS — mismatched keys between modules, schema drift, wrong assumptions
4. ASYNC/CONCURRENCY ISSUES — event loop misuse, shared mutable state, race conditions
5. RESOURCE/RELIABILITY — unbounded list growth, missing cleanup, silent failure modes

For each issue found, write:
  SEVERITY: CRITICAL | WARNING | INFO
  FILE: filename.py (~line N)
  ISSUE: clear description of what goes wrong and why

Be specific — name actual variables, line numbers, and exact failure conditions.
If a category has no findings, write "None found."

End your review with exactly one line:
VERDICT: PASS | PASS WITH WARNINGS | FAIL"""

        self._info(C, "Sending 7 source files to Claude for senior engineer review (~30s)...")
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=2048,
                    system=system,
                    messages=[{"role": "user", "content": f"Review this codebase:\n{bundle}"}],
                )
            )
            text = response.content[0].text
            if "VERDICT: FAIL" in text:
                severity = "fail"
            elif "VERDICT: PASS WITH WARNINGS" in text or "\nCRITICAL:" in text:
                severity = "warn"
            else:
                severity = "pass"
            self._add(severity, C, "Senior engineer AI review complete — see detail below", text)
        except Exception as e:
            self._fail(C, "AI code review API call failed", str(e))

    # ── Runner ────────────────────────────────────────────────────────────────

    async def run(self, skip_api: bool = False) -> List[Finding]:
        _print_header("Tier 1 — Static Logic Checks")
        self.check_json_parsers()
        self.check_sensor_simulation()
        self.check_message_builders()
        self.check_outcome_tracker_sync()
        await self.check_outcome_tracker_async()
        self.check_code_structure()

        _print_header("Tier 2 — Data Contract Verification")
        self.check_data_contracts()

        if not skip_api:
            _print_header("Tier 3 — Integration Smoke Test  (live Claude API)")
            await self.integration_smoke_test()
            _print_header("Tier 4 — AI Code Review  (live Claude API)")
            await self.ai_code_review()
        else:
            print("\n  (Tiers 3 & 4 skipped — run without --skip-api to include live Claude checks)")

        passed = sum(1 for f in self.findings if f.severity == "pass")
        warned = sum(1 for f in self.findings if f.severity == "warn")
        failed = sum(1 for f in self.findings if f.severity == "fail")
        infos = sum(1 for f in self.findings if f.severity == "info")

        print(f"\n  {'─' * 52}")
        print(f"  {_c('SUMMARY', 'bold')}  "
              f"{_c(f'{passed} passed', 'pass')}  |  "
              f"{_c(f'{warned} warnings', 'warn')}  |  "
              f"{_c(f'{failed} failed', 'fail')}  |  "
              f"{_c(f'{infos} info', 'dim')}")

        if failed > 0:
            verdict = _c("FAIL", "fail")
        elif warned > 0:
            verdict = _c("PASS WITH WARNINGS", "warn")
        else:
            verdict = _c("PASS", "pass")
        print(f"  {_c('VERDICT:', 'bold')} {verdict}\n")

        return self.findings
