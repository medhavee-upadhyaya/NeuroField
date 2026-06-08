import json
from pathlib import Path

_PROMPTS_PATH = Path(__file__).parent.parent / "data" / "prompts.json"


class PromptStore:
    """Loads prompts from data/prompts.json; falls back to hardcoded defaults."""

    def __init__(self):
        self._supervisor = None
        self._worker = None
        self._load()

    def _load(self):
        if _PROMPTS_PATH.exists():
            try:
                data = json.loads(_PROMPTS_PATH.read_text())
                self._supervisor = data.get("supervisor_prompt")
                self._worker = data.get("worker_prompt")
            except (json.JSONDecodeError, OSError):
                pass

    def get_supervisor_prompt(self) -> str:
        return self._supervisor or SUPERVISOR_PROMPT

    def get_worker_prompt(self) -> str:
        return self._worker or WORKER_PROMPT

    def update(self, supervisor_prompt: str, worker_prompt: str):
        self._supervisor = supervisor_prompt
        self._worker = worker_prompt
        _PROMPTS_PATH.write_text(
            json.dumps({"supervisor_prompt": supervisor_prompt, "worker_prompt": worker_prompt}, indent=2)
        )

    def reset(self):
        self._supervisor = None
        self._worker = None
        if _PROMPTS_PATH.exists():
            _PROMPTS_PATH.unlink()


SUPERVISOR_PROMPT = """You are the NeuroField Supervisor — the strategic planning layer of an autonomous agricultural AI.

You survey the entire farm grid, triage all active problems, and produce a prioritized work queue for the Worker agent to execute one task at a time.

You must:
- Think across the whole farm, not just one sector
- Rank problems by urgency and potential spread
- Assign the single most impactful action per sector
- Consider which sectors were recently treated (deprioritize them)

Output format (respond ONLY with valid JSON, no markdown):
{
  "farm_summary": "one sentence describing overall farm health",
  "priority_queue": [
    {
      "sector": "E6",
      "action": "irrigate|spray|fertilize|navigate|report|wait",
      "urgency": "critical|high|medium|low",
      "reasoning": "why this sector, why this action"
    }
  ]
}

Rules:
- priority_queue must have 1–4 items, ordered most urgent first
- If farm is healthy, output one item with action "wait"
- urgency "critical" = immediate threat to crop survival
- Never queue the same sector twice
- Consider spread risk: a spreading anomaly outranks a static one"""


WORKER_PROMPT = """You are the NeuroField Worker — the tactical execution layer of an autonomous agricultural AI.

The Supervisor has assigned you a specific task. Your job is to:
1. Re-examine the current sensor data for the target sector
2. Confirm whether the Supervisor's recommended action is still correct
3. Execute or reject with clear reasoning

Output format (respond ONLY with valid JSON, no markdown):
{
  "confirmed": true,
  "action": "irrigate|spray|fertilize|navigate|report|wait",
  "target_sector": "E6",
  "confidence": 0.0,
  "reasoning": "detailed justification based on current sensor readings",
  "alert_level": "low|medium|critical"
}

Rules:
- If sensor data no longer supports the action, set confirmed=false and action="report"
- confidence < 0.4 forces confirmed=false
- Be precise: cite actual sensor values in your reasoning
- You are the last safety check before physical robot action"""


def build_supervisor_message(snapshot: dict, memory_summary: dict) -> str:
    stats = snapshot.get("stats", {})
    anomalies = snapshot.get("active_anomalies", [])
    treated_recently = memory_summary.get("treated_recently", [])
    chronic = memory_summary.get("chronic_sectors", {})
    failed_treatments = memory_summary.get("failed_treatments", {})

    problem_sectors = []
    for sid, sector in snapshot["sectors"].items():
        issues = []
        score = 0
        if sector["soil_moisture"] < 0.2:
            issues.append(f"drought (moisture={sector['soil_moisture']:.2f})")
            score += 3
        elif sector["soil_moisture"] < 0.35:
            issues.append(f"low moisture ({sector['soil_moisture']:.2f})")
            score += 1
        if sector["crop_health"] < 0.3:
            issues.append(f"critical health ({sector['crop_health']:.2f})")
            score += 3
        elif sector["crop_health"] < 0.5:
            issues.append(f"poor health ({sector['crop_health']:.2f})")
            score += 1
        if sector["temperature"] > 35:
            issues.append(f"heat stress ({sector['temperature']:.1f}°C)")
            score += 2
        # failed treatment raises priority — something isn't working
        if sid in failed_treatments:
            score += 2 * failed_treatments[sid].get("fail_count", 1)
        if sid in treated_recently:
            score = max(0, score - 2)
        if issues:
            problem_sectors.append((score, sid, issues, sector.get("anomalies", [])))

    problem_sectors.sort(reverse=True)

    lines = [
        f"FARM OVERVIEW: {stats.get('total_sectors', 100)} sectors | "
        f"{stats.get('anomaly_count', 0)} anomalies | "
        f"{stats.get('critical_sectors', 0)} critical",
        "",
        "PROBLEM SECTORS (scored by urgency):",
    ]
    if problem_sectors:
        for score, sid, issues, sector_anomalies in problem_sectors[:8]:
            treated = " [TREATED RECENTLY]" if sid in treated_recently else ""
            chronic_note = f" [CHRONIC x{chronic[sid]['occurrences']}]" if sid in chronic else ""
            failed = ""
            if sid in failed_treatments:
                ft = failed_treatments[sid]
                failed = f" [FAILED TX: {ft['action']} x{ft['fail_count']} — try different action]"
            lines.append(f"  [{score:2d}] {sid}{treated}{chronic_note}{failed}: {', '.join(issues)}")
    else:
        lines.append("  All sectors nominal.")

    if anomalies:
        lines.extend(["", "SPREADING ANOMALIES:"])
        for a in sorted(anomalies, key=lambda x: -x["severity"])[:6]:
            lines.append(f"  {a['sector']}: {a['type']} sev={a['severity']:.2f} cycles={a['cycles']}")

    if failed_treatments:
        lines.extend(["", "FAILED TREATMENTS (require different approach):"])
        for sid, ft in list(failed_treatments.items())[:4]:
            lines.append(
                f"  {sid}: {ft['action']} failed {ft['fail_count']}x "
                f"(Δhealth={ft['delta'].get('crop_health', 0):+.3f} "
                f"Δmoisture={ft['delta'].get('soil_moisture', 0):+.3f})"
            )

    lines.extend([
        "",
        f"RECENTLY TREATED: {', '.join(treated_recently) or 'none'}",
        f"CHRONIC SECTORS: {len(chronic)} | FAILED TREATMENTS: {len(failed_treatments)}",
        "",
        "Build the priority queue. For sectors with FAILED TX, assign a DIFFERENT action than the one that failed.",
    ])
    return "\n".join(lines)


def build_worker_message(task: dict, snapshot: dict, failed_treatments: dict = None) -> str:
    sector_id = task.get("sector", "")
    sector = snapshot.get("sectors", {}).get(sector_id, {})
    failed_treatments = failed_treatments or {}

    lines = [
        f"ASSIGNED TASK from Supervisor:",
        f"  Sector:    {sector_id}",
        f"  Action:    {task.get('action')}",
        f"  Urgency:   {task.get('urgency')}",
        f"  Reasoning: {task.get('reasoning')}",
        "",
        f"CURRENT SENSOR READINGS for {sector_id}:",
    ]
    if sector:
        lines += [
            f"  Soil moisture: {sector.get('soil_moisture', 0):.3f}",
            f"  Crop health:   {sector.get('crop_health', 0):.3f}",
            f"  Temperature:   {sector.get('temperature', 0):.1f}°C",
            f"  Active anomalies: {', '.join(sector.get('anomalies', [])) or 'none'}",
        ]
    else:
        lines.append("  No sensor data available for this sector.")

    if sector_id in failed_treatments:
        ft = failed_treatments[sector_id]
        lines += [
            "",
            f"OUTCOME HISTORY for {sector_id}:",
            f"  Previous action '{ft['action']}' FAILED {ft['fail_count']}x",
            f"  Effect: Δhealth={ft['delta'].get('crop_health', 0):+.3f}  Δmoisture={ft['delta'].get('soil_moisture', 0):+.3f}",
            f"  Consider whether a DIFFERENT action is warranted.",
        ]

    lines.extend(["", "Confirm or reject this task. Cite the sensor values in your reasoning."])
    return "\n".join(lines)


CHAT_SYSTEM_PROMPT = """You are NeuroField's farm intelligence assistant.

You have access to live sensor data, agent memory, and the full decision history of an autonomous agricultural AI managing a 10×10 farm grid. Each sector is labeled A1–J10.

Your job is to answer questions from farm operators about what is happening on the farm, why the AI made certain decisions, and what the current status of any sector or problem is.

Rules:
- Always cite specific sensor values when discussing a sector (soil_moisture, crop_health, temperature)
- Refer to agent decisions by their action type and sector (e.g. "the agent sprayed E6 at 14:32")
- Be concise — 2–4 sentences unless the question requires more
- If you don't have enough context to answer precisely, say so
- Use plain language, not jargon"""


def build_chat_context(snapshot: dict, memory: dict, recent_decisions: list) -> str:
    stats = snapshot.get("stats", {})
    anomalies = snapshot.get("active_anomalies", [])
    chronic = memory.get("chronic_sectors", {})
    stats_by_action = memory.get("intervention_stats", {})

    problem_sectors = []
    for sid, s in snapshot.get("sectors", {}).items():
        issues = []
        if s["soil_moisture"] < 0.35:
            issues.append(f"moisture={s['soil_moisture']:.2f}")
        if s["crop_health"] < 0.55:
            issues.append(f"health={s['crop_health']:.2f}")
        if s["temperature"] > 33:
            issues.append(f"temp={s['temperature']:.1f}°C")
        if issues:
            problem_sectors.append((sid, issues, s.get("anomalies", [])))
    problem_sectors.sort(key=lambda x: len(x[1]), reverse=True)

    lines = [
        "=== CURRENT FARM STATE ===",
        f"Sectors: {stats.get('total_sectors', 100)} | "
        f"Active anomalies: {stats.get('anomaly_count', 0)} | "
        f"Critical sectors: {stats.get('critical_sectors', 0)}",
        "",
    ]

    if problem_sectors:
        lines.append("Problem sectors:")
        for sid, issues, sector_anomalies in problem_sectors[:8]:
            anom = f" [{', '.join(sector_anomalies)}]" if sector_anomalies else ""
            lines.append(f"  {sid}: {', '.join(issues)}{anom}")
        lines.append("")

    if anomalies:
        lines.append("Active anomalies:")
        for a in sorted(anomalies, key=lambda x: -x["severity"])[:6]:
            lines.append(f"  {a['sector']}: {a['type']} severity={a['severity']:.2f} ({a['cycles']} cycles)")
        lines.append("")

    if chronic:
        lines.append("Chronic problem sectors:")
        for sid, info in list(chronic.items())[:5]:
            lines.append(f"  {sid}: {info['occurrences']} incidents")
        lines.append("")

    lines.append("Intervention stats (attempts/successes):")
    for action, s in stats_by_action.items():
        if s["attempts"] > 0:
            lines.append(f"  {action}: {s['attempts']} attempts, {s['successes']} successes")
    lines.append("")

    if recent_decisions:
        lines.append("Recent agent decisions (newest first):")
        for d in recent_decisions[:6]:
            import time as _time
            ts = _time.strftime("%H:%M:%S", _time.localtime(d.get("timestamp", 0)))
            agent = d.get("agent", "agent")
            action = d.get("action", "?")
            sector = d.get("target_sector", "?")
            conf = d.get("confidence", 0)
            lines.append(f"  [{ts}] {agent}: {action} → {sector} (conf={conf:.2f})")
        lines.append("")

    lines.append("=== END CONTEXT ===")
    return "\n".join(lines)


# kept for any legacy callers
SYSTEM_PROMPT = SUPERVISOR_PROMPT

def build_user_message(snapshot: dict, memory_summary: dict) -> str:
    return build_supervisor_message(snapshot, memory_summary)
