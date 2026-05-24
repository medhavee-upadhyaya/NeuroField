"""NeuroField CLI — one command to rule them all."""
import asyncio
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import click
import httpx


API_BASE = "http://localhost:8000"
DATA_DIR = Path(__file__).parent / "data"


@click.group()
def cli():
    """NeuroField — Autonomous Agricultural Robot Agent"""
    pass


@cli.command()
@click.option("--headless", is_flag=True, default=False, help="Run without 3D visualization")
@click.option("--no-browser", is_flag=True, default=False, help="Don't open browser automatically")
def start(headless: bool, no_browser: bool):
    """Launch simulation, agent loop, and dashboard."""
    _check_api_key()

    click.echo("\n╔══════════════════════════════════════╗")
    click.echo("║     NeuroField v1.0 — Booting Up     ║")
    click.echo("╚══════════════════════════════════════╝\n")

    # Start the React dashboard in background if node_modules exists
    dashboard_dir = Path(__file__).parent / "dashboard"
    node_modules = dashboard_dir / "node_modules"
    dashboard_proc = None

    if node_modules.exists():
        click.echo("[1/3] Starting React dashboard...")
        dashboard_proc = subprocess.Popen(
            ["npm", "start"],
            cwd=str(dashboard_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        click.echo("      Dashboard → http://localhost:3000")
    else:
        click.echo("[1/3] Dashboard: run 'cd dashboard && npm install && npm start' separately")

    click.echo("[2/3] Starting simulation + agent backend...")
    click.echo(f"      API → {API_BASE}")
    click.echo(f"      Mode: {'headless' if headless else '3D visualization'}\n")

    if not no_browser and node_modules.exists():
        # Open browser after a short delay
        def open_browser():
            time.sleep(5)
            webbrowser.open("http://localhost:3000")
        import threading
        threading.Thread(target=open_browser, daemon=True).start()

    try:
        args = [sys.executable, "main.py"]
        if headless:
            args.append("--headless")
        subprocess.run(args, cwd=str(Path(__file__).parent))
    except KeyboardInterrupt:
        click.echo("\n[NeuroField] Shutting down...")
        if dashboard_proc:
            dashboard_proc.terminate()


@cli.command()
def status():
    """Print current farm state to terminal."""
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(f"{API_BASE}/state")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        click.echo(f"Error: cannot reach API at {API_BASE} — {e}")
        return

    stats = data.get("stats", {})
    robot = data.get("robot", {})
    decision = data.get("last_decision", {})
    agent_status = data.get("agent_status", "unknown")

    click.echo("\n╔══════════════════════════════════════╗")
    click.echo("║        NeuroField — Farm Status       ║")
    click.echo("╚══════════════════════════════════════╝")
    click.echo(f"  Agent:       {agent_status.upper()}")
    click.echo(f"  Sectors:     {stats.get('total_sectors', '?')}")
    click.echo(f"  Anomalies:   {stats.get('anomaly_count', '?')} active")
    click.echo(f"  Critical:    {stats.get('critical_sectors', '?')} sectors")

    if robot:
        click.echo(f"  Robot:       sector={robot.get('sector','?')} pos=({robot.get('x','?')}, {robot.get('y','?')})")

    if decision:
        click.echo(f"\n  Last decision:")
        click.echo(f"    Action:    {decision.get('action','?')} → {decision.get('target_sector','?')}")
        click.echo(f"    Confidence:{decision.get('confidence', 0):.2f}")
        click.echo(f"    Alert:     {decision.get('alert_level','?')}")
        click.echo(f"    Diagnosis: {decision.get('diagnosis','?')[:80]}")

    # top problem sectors
    sectors = data.get("sectors", {})
    problems = []
    for sid, s in sectors.items():
        if s["crop_health"] < 0.5 or s["soil_moisture"] < 0.3:
            problems.append((sid, s["crop_health"], s["soil_moisture"]))
    problems.sort(key=lambda x: x[1])
    if problems:
        click.echo(f"\n  Problem sectors (top 5):")
        for sid, h, m in problems[:5]:
            bar_h = "█" * int(h * 10) + "░" * (10 - int(h * 10))
            bar_m = "█" * int(m * 10) + "░" * (10 - int(m * 10))
            click.echo(f"    {sid:4s}  health={bar_h} {h:.2f}  moisture={bar_m} {m:.2f}")
    click.echo()


@cli.command()
@click.confirmation_option(prompt="This will clear all agent memory and reset the simulation. Continue?")
def reset():
    """Clear memory and reset simulation state."""
    try:
        memory_path = DATA_DIR / "memory.json"
        default = {
            "treated_sectors": {},
            "intervention_stats": {
                action: {"attempts": 0, "successes": 0}
                for action in ("irrigate", "spray", "fertilize", "navigate", "report", "wait")
            },
            "chronic_sectors": {},
            "event_log": [],
            "last_updated": None,
        }
        memory_path.write_text(json.dumps(default, indent=2))
        click.echo("[NeuroField] Memory cleared.")
        click.echo("[NeuroField] Restart the simulation for a full reset.")
    except Exception as e:
        click.echo(f"Error: {e}")


def _check_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo("Error: ANTHROPIC_API_KEY environment variable not set.")
        click.echo("  export ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)


if __name__ == "__main__":
    cli()
