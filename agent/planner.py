"""Action plan parser — extracts and validates structured JSON from Claude output."""
import json
import re
from typing import Optional

VALID_ACTIONS = {"irrigate", "spray", "fertilize", "navigate", "report", "wait"}
VALID_ALERT_LEVELS = {"low", "medium", "critical"}


def parse_action_plan(raw: str) -> Optional[dict]:
    raw = raw.strip()

    # strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # extract first JSON object
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None

    try:
        plan = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    return validate_plan(plan)


def validate_plan(plan: dict) -> Optional[dict]:
    required = {"observation", "diagnosis", "confidence", "action", "target_sector", "reasoning", "alert_level"}
    if not required.issubset(plan.keys()):
        missing = required - plan.keys()
        # fill defaults for missing fields
        for field in missing:
            if field == "confidence":
                plan[field] = 0.0
            elif field == "action":
                plan[field] = "wait"
            elif field == "alert_level":
                plan[field] = "low"
            elif field == "target_sector":
                plan[field] = "A1"
            else:
                plan[field] = ""

    # coerce types
    try:
        plan["confidence"] = float(plan["confidence"])
    except (ValueError, TypeError):
        plan["confidence"] = 0.0

    plan["confidence"] = max(0.0, min(1.0, plan["confidence"]))

    if plan["action"] not in VALID_ACTIONS:
        plan["action"] = "report"

    if plan["alert_level"] not in VALID_ALERT_LEVELS:
        plan["alert_level"] = "low"

    # enforce confidence threshold
    if plan["confidence"] < 0.4 and plan["action"] not in ("report", "wait"):
        plan["action"] = "report"
        plan["reasoning"] = (
            f"[Confidence {plan['confidence']:.2f} below threshold 0.4 — "
            f"downgraded to report] " + plan.get("reasoning", "")
        )

    return plan
