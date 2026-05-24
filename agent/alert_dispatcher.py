"""Alert dispatcher — escalates critical events to humans via webhook and/or email."""
import asyncio
import json
import os
import smtplib
import time
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx

CONFIG_PATH = Path(__file__).parent.parent / "data" / "alerts_config.json"
MAX_ALERT_LOG = 100


@dataclass
class Alert:
    level: str           # "critical" | "warning"
    trigger: str         # what caused the alert
    sector_id: str
    message: str
    details: dict
    timestamp: float = field(default_factory=time.time)
    dispatched_via: List[str] = field(default_factory=list)


class AlertDispatcher:
    def __init__(self):
        self._config = self._load_config()
        self._cooldowns: Dict[str, float] = {}   # sector → last alert timestamp
        self._log: List[Alert] = []
        self._on_alert: Optional[Callable] = None

    def _load_config(self) -> dict:
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            return {"enabled": True, "cooldown_seconds": 300, "triggers": {}, "channels": {}}

    def on_alert(self, callback: Callable):
        self._on_alert = callback

    def _is_cooled_down(self, sector_id: str) -> bool:
        cooldown = self._config.get("cooldown_seconds", 300)
        last = self._cooldowns.get(sector_id, 0)
        return time.time() - last >= cooldown

    def _mark_sent(self, sector_id: str):
        self._cooldowns[sector_id] = time.time()

    # ── Trigger evaluation ────────────────────────────────────────────────

    async def check_worker_decision(self, decision: dict, snapshot: dict):
        """Call after every confirmed Worker action."""
        if not self._config.get("enabled"):
            return

        sector = decision.get("target_sector", "")
        alert_level = decision.get("alert_level", "low")
        action = decision.get("action", "wait")
        confirmed = decision.get("confirmed", False)

        triggers = self._config.get("triggers", {})

        if (
            triggers.get("critical_action_confirmed", True)
            and confirmed
            and alert_level == "critical"
            and action not in ("report", "wait")
            and self._is_cooled_down(sector)
        ):
            sector_data = snapshot.get("sectors", {}).get(sector, {})
            await self._dispatch(Alert(
                level="critical",
                trigger="critical_action_confirmed",
                sector_id=sector,
                message=(
                    f"Critical intervention dispatched on sector {sector}: "
                    f"{action.upper()}. "
                    f"Crop health={sector_data.get('crop_health', 0):.2f}, "
                    f"moisture={sector_data.get('soil_moisture', 0):.2f}."
                ),
                details={
                    "action": action,
                    "confidence": decision.get("confidence", 0),
                    "diagnosis": decision.get("diagnosis", ""),
                    "sensor": {
                        "crop_health": sector_data.get("crop_health"),
                        "soil_moisture": sector_data.get("soil_moisture"),
                        "temperature": sector_data.get("temperature"),
                    },
                    "anomalies": sector_data.get("anomalies", []),
                },
            ))

    async def check_outcome_failure(self, outcome, fail_count: int):
        """Call when a treatment outcome is evaluated as failed."""
        if not self._config.get("enabled"):
            return
        triggers = self._config.get("triggers", {})

        if (
            triggers.get("treatment_failed_twice", True)
            and fail_count >= 2
            and self._is_cooled_down(outcome.sector_id)
        ):
            await self._dispatch(Alert(
                level="critical",
                trigger="treatment_failed_twice",
                sector_id=outcome.sector_id,
                message=(
                    f"Treatment failure on sector {outcome.sector_id}: "
                    f"{outcome.action} has failed {fail_count} times. "
                    f"Crop health Δ={outcome.delta.get('crop_health', 0):+.3f}. "
                    f"Manual inspection may be required."
                ),
                details={
                    "action": outcome.action,
                    "fail_count": fail_count,
                    "delta": outcome.delta,
                    "pre": outcome.pre,
                    "post": outcome.post,
                },
            ))

    async def check_spreading_anomaly(self, anomalies: list, snapshot: dict):
        """Call each cycle to check for high-severity spreading anomalies."""
        if not self._config.get("enabled"):
            return
        threshold = self._config.get("triggers", {}).get("spreading_anomaly_severity", 0.8)

        for anomaly in anomalies:
            if anomaly.get("severity", 0) >= threshold and anomaly.get("cycles", 0) >= 3:
                sector = anomaly["sector"]
                if self._is_cooled_down(f"anomaly_{sector}"):
                    sector_data = snapshot.get("sectors", {}).get(sector, {})
                    await self._dispatch(Alert(
                        level="critical",
                        trigger="spreading_anomaly",
                        sector_id=sector,
                        message=(
                            f"High-severity {anomaly['type']} detected in sector {sector} "
                            f"(severity={anomaly['severity']:.2f}, {anomaly['cycles']} cycles active). "
                            f"Risk of spread to neighbouring sectors."
                        ),
                        details={
                            "anomaly_type": anomaly["type"],
                            "severity": anomaly["severity"],
                            "cycles": anomaly["cycles"],
                            "health": sector_data.get("crop_health"),
                            "moisture": sector_data.get("soil_moisture"),
                        },
                    ))
                    self._mark_sent(f"anomaly_{sector}")

    # ── Dispatch ──────────────────────────────────────────────────────────

    async def _dispatch(self, alert: Alert):
        self._mark_sent(alert.sector_id)
        self._log.append(alert)
        if len(self._log) > MAX_ALERT_LOG:
            self._log = self._log[-MAX_ALERT_LOG:]

        channels = self._config.get("channels", {})
        tasks = []

        if channels.get("webhook", {}).get("enabled"):
            tasks.append(self._send_webhook(alert, channels["webhook"]))

        if channels.get("email", {}).get("enabled"):
            tasks.append(self._send_email(alert, channels["email"]))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    print(f"[Alert] Dispatch error: {r}")

        print(f"[Alert] 🚨 {alert.level.upper()} — {alert.sector_id}: {alert.message[:80]}")

        if self._on_alert:
            await self._on_alert(alert)

    async def _send_webhook(self, alert: Alert, cfg: dict) -> str:
        url = cfg.get("url") or os.environ.get("NEUROFIELD_WEBHOOK_URL", "")
        if not url:
            return "no url"

        fmt = cfg.get("format", "slack")
        if fmt == "slack":
            payload = _slack_payload(alert)
        else:
            payload = _generic_payload(alert)

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            alert.dispatched_via.append("webhook")
            return "ok"

    async def _send_email(self, alert: Alert, cfg: dict) -> str:
        smtp_host = cfg.get("smtp_host") or os.environ.get("SMTP_HOST", "")
        smtp_port = int(cfg.get("smtp_port") or os.environ.get("SMTP_PORT", 587))
        from_addr = cfg.get("from") or os.environ.get("SMTP_FROM", "")
        to_addr = cfg.get("to") or os.environ.get("ALERT_EMAIL_TO", "")
        password = os.environ.get("SMTP_PASSWORD", "")

        if not all([smtp_host, from_addr, to_addr]):
            return "incomplete config"

        subject = f"[NeuroField] {alert.level.upper()} — Sector {alert.sector_id}"
        body = _email_body(alert)

        def _send():
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = to_addr
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if cfg.get("use_tls", True):
                    server.starttls()
                if password:
                    server.login(from_addr, password)
                server.sendmail(from_addr, [to_addr], msg.as_string())

        await asyncio.get_event_loop().run_in_executor(None, _send)
        alert.dispatched_via.append("email")
        return "ok"

    # ── Read helpers ──────────────────────────────────────────────────────

    def get_log(self, limit: int = 20) -> List[dict]:
        return [
            {
                "level": a.level,
                "trigger": a.trigger,
                "sector_id": a.sector_id,
                "message": a.message,
                "details": a.details,
                "timestamp": a.timestamp,
                "dispatched_via": a.dispatched_via,
            }
            for a in reversed(self._log[-limit:])
        ]

    def get_unread_count(self) -> int:
        cutoff = time.time() - 300
        return sum(1 for a in self._log if a.timestamp >= cutoff)


# ── Message formatters ────────────────────────────────────────────────────

def _slack_payload(alert: Alert) -> dict:
    emoji = "🚨" if alert.level == "critical" else "⚠️"
    color = "#ff0000" if alert.level == "critical" else "#ff9800"
    ts = time.strftime("%H:%M:%S", time.localtime(alert.timestamp))
    return {
        "attachments": [
            {
                "color": color,
                "title": f"{emoji} NeuroField {alert.level.upper()} — Sector {alert.sector_id}",
                "text": alert.message,
                "fields": [
                    {"title": "Trigger", "value": alert.trigger.replace("_", " "), "short": True},
                    {"title": "Time", "value": ts, "short": True},
                ],
                "footer": "NeuroField Autonomous Farm Agent",
            }
        ]
    }


def _generic_payload(alert: Alert) -> dict:
    return {
        "level": alert.level,
        "trigger": alert.trigger,
        "sector": alert.sector_id,
        "message": alert.message,
        "details": alert.details,
        "timestamp": alert.timestamp,
        "source": "neurofield",
    }


def _email_body(alert: Alert) -> str:
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(alert.timestamp))
    lines = [
        f"NeuroField Alert — {alert.level.upper()}",
        f"Time: {ts}",
        f"Sector: {alert.sector_id}",
        f"Trigger: {alert.trigger}",
        "",
        alert.message,
        "",
        "Details:",
        json.dumps(alert.details, indent=2),
        "",
        "---",
        "NeuroField Autonomous Agricultural AI",
    ]
    return "\n".join(lines)
