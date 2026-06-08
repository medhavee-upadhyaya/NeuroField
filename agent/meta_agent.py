"""MetaAgent — reviews outcome statistics and rewrites Supervisor/Worker prompts."""
import asyncio
import json
import re
import time
from typing import Optional

import anthropic

META_INTERVAL = 20  # run every N cycles (~3.3 min at 10s/cycle)

META_PROMPT = """You are NeuroFieldMeta — the self-improvement layer of an autonomous agricultural AI.

Your job: review how the Supervisor and Worker agents have been performing, identify weaknesses in their current prompts, and rewrite them to improve future decisions.

You will receive:
- The current Supervisor and Worker system prompts
- Outcome statistics per action type (attempts vs successes)
- Failed treatment history (sectors where the same action kept failing)
- Chronic sector data (sectors that keep recurring as problems)
- Recent outcome log (what actually happened after each intervention)

Look for signals like:
- Low success rate on a specific action → prompt may not guide the agent to choose wisely
- Chronic sectors not being resolved → Supervisor may be under-prioritising them
- Worker rejecting too aggressively (many low-confidence rejections) → Worker prompt may be too conservative
- Failed treatments being repeated → agents aren't adapting to failures fast enough
- Spreading anomalies not being contained → prioritisation logic needs adjustment

INVARIANTS — preserve these exactly, do not change the output format instructions:
1. Supervisor JSON output must have: farm_summary (string), priority_queue (array with: sector, action, urgency, reasoning)
2. Worker JSON output must have: confirmed (bool), action, target_sector, confidence (0.0–1.0), reasoning, alert_level
3. Valid actions: irrigate, spray, fertilize, navigate, report, wait
4. Valid urgency: critical, high, medium, low
5. Valid alert_level: low, medium, critical

Output ONLY valid JSON, no markdown:
{
  "supervisor_prompt": "full rewritten supervisor system prompt",
  "worker_prompt": "full rewritten worker system prompt",
  "changes_summary": "2-3 sentences: what patterns you found and what you changed"
}"""


def _parse(raw: str) -> Optional[dict]:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    if not all(k in data for k in ("supervisor_prompt", "worker_prompt", "changes_summary")):
        return None
    if not data["supervisor_prompt"].strip() or not data["worker_prompt"].strip():
        return None
    return data


def _build_message(prompt_store, memory_summary: dict, outcome_log: list) -> str:
    lines = [
        "CURRENT SUPERVISOR PROMPT:",
        prompt_store.get_supervisor_prompt(),
        "",
        "CURRENT WORKER PROMPT:",
        prompt_store.get_worker_prompt(),
        "",
        "OUTCOME STATISTICS:",
    ]

    stats = memory_summary.get("intervention_stats", {})
    any_stats = False
    for action, s in stats.items():
        if s["attempts"] > 0:
            rate = s["successes"] / s["attempts"] * 100
            lines.append(
                f"  {action}: {s['attempts']} attempts, {s['successes']} successes ({rate:.0f}% rate)"
            )
            any_stats = True
    if not any_stats:
        lines.append("  No intervention data yet.")

    failed = memory_summary.get("failed_treatments", {})
    if failed:
        lines.extend(["", "FAILED TREATMENTS (same sector+action failed repeatedly):"])
        for sid, ft in list(failed.items())[:8]:
            lines.append(
                f"  {sid}: {ft['action']} failed {ft['fail_count']}x "
                f"(Δhealth={ft['delta'].get('crop_health', 0):+.3f} "
                f"Δmoisture={ft['delta'].get('soil_moisture', 0):+.3f})"
            )

    chronic = memory_summary.get("chronic_sectors", {})
    if chronic:
        lines.extend(["", "CHRONIC SECTORS (keep recurring):"])
        for sid, info in list(chronic.items())[:6]:
            lines.append(f"  {sid}: {info.get('occurrences', '?')} incidents")

    if outcome_log:
        lines.extend(["", "RECENT OUTCOMES (newest first):"])
        for o in outcome_log[:20]:
            status = "OK" if o.get("success") else "FAIL"
            lines.append(
                f"  [{status}] {o.get('action')} on {o.get('sector_id')}: {o.get('note', '')}"
            )

    lines.extend(["", "Based on the above, rewrite the prompts to address any weaknesses you identify."])
    return "\n".join(lines)


class MetaAgent:
    def __init__(self, client: anthropic.Anthropic, prompt_store):
        self.client = client
        self.prompt_store = prompt_store
        self.last_run: Optional[float] = None
        self.revision_count = 0

    async def run(self, memory_summary: dict, outcome_log: list) -> Optional[dict]:
        message = _build_message(self.prompt_store, memory_summary, outcome_log)
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=2048,
                    system=META_PROMPT,
                    messages=[{"role": "user", "content": message}],
                ),
            )
            raw = response.content[0].text
            result = _parse(raw)
            if result:
                self.prompt_store.update(result["supervisor_prompt"], result["worker_prompt"])
                self.last_run = time.time()
                self.revision_count += 1
                print(f"[MetaAgent] Revision #{self.revision_count}: {result['changes_summary']}")
                return result
            print(f"[MetaAgent] Parse failed: {raw[:200]}")
        except Exception as e:
            print(f"[MetaAgent] Error: {e}")
        return None
