"""Outcome tracker — evaluates treatment results 2 cycles after each intervention."""
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

CHECK_DELAY = 20.0  # seconds after treatment to evaluate outcome

# minimum improvement required to call treatment a success
SUCCESS_THRESHOLDS = {
    "irrigate":   {"soil_moisture": 0.08},
    "spray":      {"crop_health": 0.04},
    "fertilize":  {"crop_health": 0.03},
}


@dataclass
class PendingOutcome:
    sector_id: str
    action: str
    pre_moisture: float
    pre_health: float
    pre_temp: float
    treated_at: float
    check_at: float = field(init=False)

    def __post_init__(self):
        self.check_at = self.treated_at + CHECK_DELAY


@dataclass
class OutcomeResult:
    sector_id: str
    action: str
    success: bool
    pre: dict
    post: dict
    delta: dict
    evaluated_at: float
    note: str


class OutcomeTracker:
    def __init__(self):
        self._pending: List[PendingOutcome] = []
        self._results: List[OutcomeResult] = []
        self._on_outcome: Optional[Callable] = None

    def on_outcome(self, callback: Callable):
        self._on_outcome = callback

    def register(self, sector_id: str, action: str, snapshot: dict):
        """Call immediately after a physical intervention is confirmed."""
        if action in ("report", "wait", "navigate"):
            return
        sector = snapshot.get("sectors", {}).get(sector_id, {})
        if not sector:
            return
        # deduplicate — if same sector+action already pending, replace it
        self._pending = [p for p in self._pending if p.sector_id != sector_id]
        self._pending.append(PendingOutcome(
            sector_id=sector_id,
            action=action,
            pre_moisture=sector.get("soil_moisture", 0.5),
            pre_health=sector.get("crop_health", 0.8),
            pre_temp=sector.get("temperature", 22.0),
            treated_at=time.time(),
        ))

    async def check_due(self, snapshot: dict) -> List[OutcomeResult]:
        """Call every cycle. Returns list of newly evaluated outcomes."""
        now = time.time()
        due = [p for p in self._pending if now >= p.check_at]
        if not due:
            return []

        new_results = []
        for pending in due:
            self._pending.remove(pending)
            sector = snapshot.get("sectors", {}).get(pending.sector_id, {})
            if not sector:
                continue

            post_moisture = sector.get("soil_moisture", pending.pre_moisture)
            post_health = sector.get("crop_health", pending.pre_health)
            post_temp = sector.get("temperature", pending.pre_temp)

            delta = {
                "soil_moisture": round(post_moisture - pending.pre_moisture, 3),
                "crop_health": round(post_health - pending.pre_health, 3),
                "temperature": round(post_temp - pending.pre_temp, 3),
            }

            thresholds = SUCCESS_THRESHOLDS.get(pending.action, {})
            success = False
            if pending.action == "irrigate":
                success = delta["soil_moisture"] >= thresholds.get("soil_moisture", 0.05)
            elif pending.action in ("spray", "fertilize"):
                success = delta["crop_health"] >= thresholds.get("crop_health", 0.03)

            if success:
                note = f"{pending.action} succeeded — metrics improved as expected"
            else:
                note = (
                    f"{pending.action} failed or insufficient — "
                    f"Δmoisture={delta['soil_moisture']:+.3f} "
                    f"Δhealth={delta['crop_health']:+.3f}"
                )

            result = OutcomeResult(
                sector_id=pending.sector_id,
                action=pending.action,
                success=success,
                pre={"soil_moisture": pending.pre_moisture, "crop_health": pending.pre_health, "temperature": pending.pre_temp},
                post={"soil_moisture": post_moisture, "crop_health": post_health, "temperature": post_temp},
                delta=delta,
                evaluated_at=now,
                note=note,
            )
            self._results.append(result)
            new_results.append(result)

            status = "✓ SUCCESS" if success else "✗ FAILED"
            print(f"[Outcome] {status}: {pending.action} on {pending.sector_id} | {note}")

            if self._on_outcome:
                await self._on_outcome(result)

        # keep last 50 results in memory
        self._results = self._results[-50:]
        return new_results

    def get_recent(self, limit: int = 20) -> List[dict]:
        return [
            {
                "sector_id": r.sector_id,
                "action": r.action,
                "success": r.success,
                "pre": r.pre,
                "post": r.post,
                "delta": r.delta,
                "evaluated_at": r.evaluated_at,
                "note": r.note,
            }
            for r in reversed(self._results[-limit:])
        ]

    def get_failed_sectors(self) -> Dict[str, dict]:
        """Sectors where the most recent outcome was a failure."""
        by_sector: Dict[str, OutcomeResult] = {}
        for r in self._results:
            by_sector[r.sector_id] = r
        return {
            sid: {"action": r.action, "delta": r.delta, "evaluated_at": r.evaluated_at}
            for sid, r in by_sector.items()
            if not r.success
        }
