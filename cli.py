"""NeuroField CLI — one command to launch the autonomous farm agent."""
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import click
import httpx

API_BASE = "http://localhost:8000"
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"


# ── Helpers ───────────────────────────────────────────────────────────────

def _check_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.secho("\nError: ANTHROPIC_API_KEY is not set.", fg="red", bold=True)
        click.echo("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)


def _api_get(path: str, timeout: int = 5) -> dict:
    with httpx.Client(timeout=timeout) as client:
        r = client.get(f"{API_BASE}{path}")
        r.raise_for_status()
        return r.json()


def _bar(value: float, width: int = 12) -> str:
    filled = int(value * width)
    return "█" * filled + "░" * (width - filled)


# ── Commands ──────────────────────────────────────────────────────────────

@click.group()
@click.version_option("1.0.0", prog_name="neurofield")
def cli():
    """NeuroField — Autonomous Agricultural Robot Agent

    \b
    Quickstart:
      export ANTHROPIC_API_KEY=sk-ant-...
      neurofield start --demo

    \b
    Dashboard → http://localhost:3000
    API docs  → http://localhost:8000/docs
    """
    pass


@cli.command()
@click.option("--headless", is_flag=True, default=True, show_default=True,
              help="Skip PyBullet window (3D is in the dashboard instead)")
@click.option("--demo", is_flag=True, default=False,
              help="Pre-seed dramatic anomalies for immediate visual impact")
@click.option("--no-browser", is_flag=True, default=False,
              help="Don't auto-open browser")
@click.option("--no-dashboard", is_flag=True, default=False,
              help="Skip starting the React dev server")
def start(headless: bool, demo: bool, no_browser: bool, no_dashboard: bool):
    """Launch everything — simulation, agent loop, API, and dashboard."""
    _check_api_key()

    click.echo()
    click.secho("  NeuroField v1.0", bold=True, fg="green")
    click.secho("  Autonomous Agricultural Robot Agent", fg="bright_black")
    click.echo()

    dashboard_proc = None

    # ── Dashboard ─────────────────────────────────────────────────────────
    if not no_dashboard:
        node_modules = DASHBOARD_DIR / "node_modules"
        if node_modules.exists():
            click.echo("  [1/2] Starting React dashboard...")
            dashboard_proc = subprocess.Popen(
                ["npm", "start", "--", "--no-open"],
                cwd=str(DASHBOARD_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "BROWSER": "none"},
            )
            click.echo("        http://localhost:3000")
        else:
            click.secho("  [1/2] Dashboard not installed.", fg="yellow")
            click.echo("        cd dashboard && npm install && npm start")

    # ── Auto-open browser ─────────────────────────────────────────────────
    if not no_browser and not no_dashboard and (DASHBOARD_DIR / "node_modules").exists():
        def _open():
            time.sleep(6)
            webbrowser.open("http://localhost:3000")
        threading.Thread(target=_open, daemon=True).start()

    # ── Backend ───────────────────────────────────────────────────────────
    mode_parts = []
    if demo:
        mode_parts.append("demo scenario")
    if headless:
        mode_parts.append("headless")
    mode_str = " · ".join(mode_parts) if mode_parts else "live"
    click.echo(f"  [2/2] Starting agent backend ({mode_str})...")
    click.echo(f"        http://localhost:8000")
    click.echo()

    args = [sys.executable, str(PROJECT_ROOT / "main.py")]
    if headless:
        args.append("--headless")
    if demo:
        args.append("--demo")

    try:
        subprocess.run(args, cwd=str(PROJECT_ROOT))
    except KeyboardInterrupt:
        pass
    finally:
        if dashboard_proc:
            dashboard_proc.terminate()
        click.echo("\n  Stopped.")


@cli.command()
def status():
    """Print live farm state to the terminal."""
    try:
        data = _api_get("/state")
        alerts_data = _api_get("/alerts")
        outcomes_data = _api_get("/outcomes")
    except Exception as e:
        click.secho(f"Cannot reach {API_BASE} — {e}", fg="red")
        click.echo("  Is the backend running? Try: neurofield start --demo")
        return

    stats = data.get("stats", {})
    robot = data.get("robot") or {}
    decision = data.get("last_decision") or {}
    queue = (data.get("last_queue") or {}).get("priority_queue", [])
    agent_status = data.get("agent_status", "unknown")
    unread_alerts = alerts_data.get("unread_count", 0)
    failed_sectors = outcomes_data.get("failed_sectors", {})

    status_color = {"idle": "green", "thinking": "yellow", "acting": "cyan"}.get(agent_status, "white")

    click.echo()
    click.secho("  NeuroField — Farm Status", bold=True)
    click.echo("  " + "─" * 42)
    click.echo(f"  Agent:     ", nl=False)
    click.secho(agent_status.upper(), fg=status_color, bold=True)
    click.echo(f"  Sectors:   {stats.get('total_sectors', '?')} total")
    click.echo(f"  Anomalies: {stats.get('anomaly_count', '?')} active | "
               f"{stats.get('critical_sectors', '?')} critical")

    if unread_alerts:
        click.secho(f"  Alerts:    {unread_alerts} unread (last 5 min)", fg="red", bold=True)

    if failed_sectors:
        click.secho(f"  Failed TX: {', '.join(failed_sectors.keys())}", fg="yellow")

    if robot:
        click.echo(f"  Robot:     {robot.get('sector', '?')} "
                   f"@ ({robot.get('x', '?')}, {robot.get('y', '?')})")

    # Supervisor queue
    if queue:
        click.echo()
        click.secho("  Supervisor queue:", bold=True)
        for i, task in enumerate(queue[:4]):
            urgency_color = {"critical": "red", "high": "yellow", "medium": "cyan", "low": "white"}.get(
                task.get("urgency", "low"), "white"
            )
            click.echo(f"    [{i+1}] {task['sector']:4s}  ", nl=False)
            click.secho(f"{task['action']:10s}", fg=urgency_color, nl=False)
            click.echo(f"  {task.get('urgency','')}")

    # Problem sectors
    sectors = data.get("sectors", {})
    problems = [
        (sid, s["crop_health"], s["soil_moisture"])
        for sid, s in sectors.items()
        if s["crop_health"] < 0.55 or s["soil_moisture"] < 0.3
    ]
    problems.sort(key=lambda x: x[1])
    if problems:
        click.echo()
        click.secho("  Problem sectors:", bold=True)
        for sid, h, m in problems[:6]:
            failed = " [FAILED TX]" if sid in failed_sectors else ""
            h_color = "red" if h < 0.35 else "yellow" if h < 0.55 else "green"
            m_color = "red" if m < 0.2 else "yellow" if m < 0.35 else "cyan"
            click.echo(f"    {sid:4s}  health=", nl=False)
            click.secho(f"{_bar(h)} {h:.2f}", fg=h_color, nl=False)
            click.echo("  moisture=", nl=False)
            click.secho(f"{_bar(m)} {m:.2f}", fg=m_color, nl=False)
            click.secho(failed, fg="yellow")

    # Last decision
    if decision:
        click.echo()
        click.secho("  Last decision:", bold=True)
        action_color = "red" if decision.get("alert_level") == "critical" else "cyan"
        click.echo(f"    {decision.get('action','?')} → {decision.get('target_sector','?')}  "
                   f"conf={decision.get('confidence',0):.2f}  ", nl=False)
        click.secho(decision.get("alert_level", ""), fg=action_color)
        diag = decision.get("diagnosis", "")[:90]
        if diag:
            click.secho(f"    {diag}", fg="bright_black")

    click.echo()


@cli.command()
@click.option("--limit", default=10, help="Number of recent decisions to show")
@click.option("--follow", "-f", is_flag=True, help="Poll every 5s (like tail -f)")
def logs(limit: int, follow: bool):
    """Stream recent agent decisions to the terminal."""
    def _print_log():
        try:
            data = _api_get(f"/log?limit={limit}")
        except Exception as e:
            click.secho(f"Error: {e}", fg="red")
            return False

        entries = data.get("log", [])
        if not entries:
            click.echo("  No decisions yet.")
            return True

        for entry in reversed(entries):
            ts = time.strftime("%H:%M:%S", time.localtime(entry.get("timestamp", 0)))
            agent = entry.get("agent", "agent")
            action = entry.get("action", "?")
            sector = entry.get("target_sector", "?")
            conf = entry.get("confidence", 0)
            alert = entry.get("alert_level", "low")
            alert_color = {"critical": "red", "medium": "yellow", "low": "green"}.get(alert, "white")
            agent_color = "magenta" if agent == "supervisor" else "cyan"

            click.echo(f"  {ts}  ", nl=False)
            click.secho(f"{agent:10s}", fg=agent_color, nl=False)
            click.echo(f"  {action:10s}  {sector:4s}  conf={conf:.2f}  ", nl=False)
            click.secho(alert, fg=alert_color)

        return True

    click.echo()
    click.secho("  NeuroField — Agent Log", bold=True)
    click.echo("  " + "─" * 42)
    _print_log()

    if follow:
        click.secho("  [following — Ctrl+C to stop]\n", fg="bright_black")
        try:
            while True:
                time.sleep(5)
                click.echo("  " + "─" * 42)
                _print_log()
        except KeyboardInterrupt:
            pass

    click.echo()


@cli.command()
@click.option("--limit", default=10, help="Number of recent alerts to show")
def alerts(limit: int):
    """Show recent critical alerts dispatched by the agent."""
    try:
        data = _api_get("/alerts")
    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        return

    alert_list = data.get("alerts", [])
    unread = data.get("unread_count", 0)
    click.echo()
    click.secho("  NeuroField — Alert Log", bold=True)
    click.echo("  " + "─" * 42)

    if unread:
        click.secho(f"  {unread} unread alerts in the last 5 minutes\n", fg="red", bold=True)

    if not alert_list:
        click.echo("  No alerts fired yet.")
    else:
        for a in alert_list[:limit]:
            ts = time.strftime("%H:%M:%S", time.localtime(a.get("timestamp", 0)))
            trigger = a.get("trigger", "").replace("_", " ")
            channels = ", ".join(a.get("dispatched_via", [])) or "dashboard only"
            click.echo(f"  {ts}  ", nl=False)
            click.secho(f"{a.get('sector_id','?'):4s}", fg="red", bold=True, nl=False)
            click.echo(f"  {trigger:30s}  via: {channels}")
            click.secho(f"       {a.get('message','')[:80]}", fg="bright_black")

    click.echo()
    click.secho("  Configure webhook: data/alerts_config.json", fg="bright_black")
    click.echo()


@cli.command()
@click.confirmation_option(prompt="Clear all agent memory and reset simulation state?")
def reset():
    """Wipe agent memory and outcome history."""
    clean = {
        "treated_sectors": {},
        "intervention_stats": {
            a: {"attempts": 0, "successes": 0}
            for a in ("irrigate", "spray", "fertilize", "navigate", "report", "wait")
        },
        "chronic_sectors": {},
        "event_log": [],
        "outcome_log": [],
        "failed_treatments": {},
        "last_updated": None,
    }
    (DATA_DIR / "memory.json").write_text(json.dumps(clean, indent=2))

    # also wipe replay db
    replay_db = DATA_DIR / "replay.db"
    if replay_db.exists():
        replay_db.unlink()
        click.echo("  Replay database cleared.")

    click.secho("  Memory cleared.", fg="green")
    click.echo("  Restart the simulation for a fresh run.")
    click.echo()


@cli.command()
def doctor():
    """Check that all dependencies and config are in order."""
    click.echo()
    click.secho("  NeuroField — Doctor", bold=True)
    click.echo("  " + "─" * 42)
    ok = True

    # API key
    if os.environ.get("ANTHROPIC_API_KEY"):
        _check_item("ANTHROPIC_API_KEY", True)
    else:
        _check_item("ANTHROPIC_API_KEY", False, "export ANTHROPIC_API_KEY=sk-ant-...")
        ok = False

    # Python deps
    for dep in ["anthropic", "fastapi", "uvicorn", "click", "httpx"]:
        try:
            __import__(dep)
            _check_item(f"pip: {dep}", True)
        except ImportError:
            _check_item(f"pip: {dep}", False, f"pip install {dep}")
            ok = False

    # Dashboard
    nm = DASHBOARD_DIR / "node_modules"
    _check_item("dashboard: node_modules", nm.exists(),
                "cd dashboard && npm install" if not nm.exists() else None)

    # Data files
    for fname in ["memory.json", "farm_config.json", "alerts_config.json"]:
        p = DATA_DIR / fname
        _check_item(f"data: {fname}", p.exists())

    # API reachability
    try:
        _api_get("/health", timeout=2)
        _check_item("API: localhost:8000", True, extra="running")
    except Exception:
        _check_item("API: localhost:8000", None, "not running (start with: neurofield start)")

    click.echo()
    if ok:
        click.secho("  All checks passed. Run: neurofield start --demo", fg="green", bold=True)
    else:
        click.secho("  Fix the issues above, then run: neurofield start --demo", fg="yellow")
    click.echo()


@cli.command()
@click.option("--skip-api", is_flag=True, default=False,
              help="Only run static & contract checks (no Claude API calls, no cost)")
def review(skip_api: bool):
    """Run the Lead Engineer Agent — verify code correctness and AI-review all source files.

    \b
    Tier 1: Static logic checks  (no API key required)
    Tier 2: Data contract checks (no API key required)
    Tier 3: Integration smoke test via real Supervisor + Worker agents
    Tier 4: Claude acts as senior engineer and reviews the source code
    """
    import asyncio
    from agent.lead_engineer import LeadEngineerAgent

    if not skip_api:
        _check_api_key()

    click.echo()
    click.secho("  NeuroField — Lead Engineer Review", bold=True, fg="cyan")
    click.secho("  Automated code verification + AI senior engineer review", fg="bright_black")
    click.echo()

    agent = LeadEngineerAgent()
    findings = asyncio.run(agent.run(skip_api=skip_api))

    failed = sum(1 for f in findings if f.severity == "fail")
    sys.exit(1 if failed else 0)


def _check_item(label: str, status, hint: str = None, extra: str = None):
    if status is True:
        icon = click.style("  ✓", fg="green")
    elif status is False:
        icon = click.style("  ✗", fg="red")
    else:
        icon = click.style("  ~", fg="yellow")

    line = f"{icon}  {label}"
    if extra:
        line += f"  ({extra})"
    click.echo(line)
    if hint and status is not True:
        click.secho(f"       → {hint}", fg="bright_black")


if __name__ == "__main__":
    cli()
