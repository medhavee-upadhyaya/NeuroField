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
            lines.append(f"  [{score:2d}] {sid}{treated}{chronic_note}: {', '.join(issues)}")
    else:
        lines.append("  All sectors nominal.")

    if anomalies:
        lines.extend(["", "SPREADING ANOMALIES:"])
        for a in sorted(anomalies, key=lambda x: -x["severity"])[:6]:
            lines.append(f"  {a['sector']}: {a['type']} sev={a['severity']:.2f} cycles={a['cycles']}")

    lines.extend([
        "",
        f"RECENTLY TREATED: {', '.join(treated_recently) or 'none'}",
        f"CHRONIC SECTORS: {len(chronic)}",
        "",
        "Build the priority queue for the Worker agent.",
    ])
    return "\n".join(lines)


def build_worker_message(task: dict, snapshot: dict) -> str:
    sector_id = task.get("sector", "")
    sector = snapshot.get("sectors", {}).get(sector_id, {})

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
            f"  Last treated: {sector.get('last_treated', 'never')}",
        ]
    else:
        lines.append("  No sensor data available for this sector.")

    lines.extend(["", "Confirm or reject this task. Cite the sensor values in your reasoning."])
    return "\n".join(lines)


# kept for any legacy callers
SYSTEM_PROMPT = SUPERVISOR_PROMPT

def build_user_message(snapshot: dict, memory_summary: dict) -> str:
    return build_supervisor_message(snapshot, memory_summary)
