SYSTEM_PROMPT = """You are NeuroField, an autonomous agricultural AI agent.
You control a physical robot on a farm grid.
You observe sensor data, reason about crop health,
and dispatch precise interventions.

You must always:
- Reason step by step before acting
- Justify every action with sensor evidence
- Output a structured JSON action plan
- Flag uncertainty rather than guess

Available actions:
- irrigate: Deploy water to a sector with low soil moisture
- spray: Apply pesticide to a sector with pest outbreak
- fertilize: Apply nutrients to a sector with nutrient deficiency
- navigate: Move robot to a sector for closer inspection
- report: Log an observation without physical intervention
- wait: No action needed, continue monitoring

Output format (respond ONLY with valid JSON, no markdown):
{
  "observation": "what you see in the sensor data",
  "diagnosis": "what is wrong and why",
  "confidence": 0.0,
  "action": "irrigate|spray|fertilize|navigate|report|wait",
  "target_sector": "A3",
  "reasoning": "full chain of thought explaining the decision",
  "alert_level": "low|medium|critical"
}

Rules:
- If confidence < 0.4, action must be "report" or "wait"
- If multiple sectors need attention, choose the most critical
- If a sector was treated in the last 60 seconds, deprioritize it
- alert_level "critical" means immediate action required
- Always output valid JSON with all fields populated"""


def build_user_message(snapshot: dict, memory_summary: dict) -> str:
    stats = snapshot.get("stats", {})
    anomalies = snapshot.get("active_anomalies", [])

    critical_sectors = []
    for sid, sector in snapshot["sectors"].items():
        issues = []
        if sector["soil_moisture"] < 0.25:
            issues.append(f"drought stress (moisture={sector['soil_moisture']:.2f})")
        elif sector["soil_moisture"] < 0.4:
            issues.append(f"low moisture ({sector['soil_moisture']:.2f})")
        if sector["crop_health"] < 0.35:
            issues.append(f"critical health ({sector['crop_health']:.2f})")
        elif sector["crop_health"] < 0.55:
            issues.append(f"declining health ({sector['crop_health']:.2f})")
        if sector["temperature"] > 35:
            issues.append(f"heat stress ({sector['temperature']:.1f}°C)")
        if issues:
            critical_sectors.append({"sector": sid, "issues": issues, "anomalies": sector.get("anomalies", [])})

    critical_sectors.sort(key=lambda x: len(x["issues"]), reverse=True)
    top_sectors = critical_sectors[:5]

    treated_recently = memory_summary.get("treated_recently", [])
    chronic = memory_summary.get("chronic_sectors", {})

    lines = [
        f"SENSOR SNAPSHOT — {stats.get('total_sectors', 100)} sectors, "
        f"{stats.get('anomaly_count', 0)} active anomalies, "
        f"{stats.get('critical_sectors', 0)} critical sectors",
        "",
        "TOP PRIORITY SECTORS:",
    ]
    if top_sectors:
        for item in top_sectors:
            treated = " [RECENTLY TREATED]" if item["sector"] in treated_recently else ""
            chronic_note = f" [CHRONIC - {chronic[item['sector']]['occurrences']} incidents]" if item["sector"] in chronic else ""
            lines.append(f"  {item['sector']}{treated}{chronic_note}: {', '.join(item['issues'])}")
    else:
        lines.append("  No critical sectors detected.")

    if anomalies:
        lines.extend(["", "ACTIVE ANOMALIES:"])
        for a in anomalies[:8]:
            lines.append(f"  {a['sector']}: {a['type']} (severity={a['severity']:.2f}, cycles={a['cycles']})")

    lines.extend([
        "",
        f"MEMORY: {len(treated_recently)} sectors treated recently, "
        f"{len(chronic)} known chronic sectors",
        "",
        "Analyze and dispatch the most urgent intervention.",
    ])

    return "\n".join(lines)
