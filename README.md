# NeuroField

Autonomous agricultural robot agent that manages a simulated 10×10 farm grid. A multi-agent AI system (Supervisor + Worker, both powered by Claude) triages the farm, dispatches a simulated robot via A* pathfinding, and learns from treatment outcomes over time.

## Features

- **Dual-agent AI loop** — Supervisor ranks all 100 sectors every ~10s; Worker confirms each action with confidence scoring
- **Outcome learning** — treatments are evaluated 20s after application; failures are logged and influence future decisions
- **Real-time dashboard** — React app with 2D grid, isometric 3D view, live agent log, replay timeline, and streaming chat
- **Alert dispatch** — escalates critical events (failed treatments, spreading anomalies) via webhook or SMTP
- **Replay** — SQLite stores up to 2000 snapshots (~5.5h); scrub through full farm history in the dashboard

## Stack

| Layer | Tech |
|---|---|
| Agent / AI | Claude (claude-sonnet-4-6), Anthropic Python SDK |
| Backend | FastAPI, asyncio, WebSocket |
| Simulation | NumPy, A* pathfinding, SQLite |
| Dashboard | React, Vite, Canvas 2D/3D |
| CLI | Click (`neurofield` command) |

## Quick Start

```bash
# One-time setup
python -m venv .venv
source .venv/bin/activate
pip install -e .
cd dashboard && npm install && cd ..

# Run
export ANTHROPIC_API_KEY=sk-ant-...
neurofield start --demo     # pre-seeds dramatic anomalies for a quick demo
neurofield start            # live simulation — anomalies emerge naturally
```

The dashboard opens automatically at `http://localhost:5173`. The backend API runs at `http://localhost:8000`.

## CLI Commands

| Command | Description |
|---|---|
| `neurofield start [--demo]` | Launch simulation + API + dashboard |
| `neurofield status` | Print current farm snapshot |
| `neurofield logs` | Tail the agent decision log |
| `neurofield alerts` | Show recent alerts |
| `neurofield reset` | Wipe memory and replay database |
| `neurofield doctor` | Check all dependencies before starting |

## Project Structure

```
agent/          Supervisor, Worker, memory, outcome tracker, alert dispatcher
api/            FastAPI routes, WebSocket, replay, streaming chat
simulation/     Sensor stream, robot controller, A* pathfinding, snapshot logger
dashboard/      React frontend (2D grid, 3D canvas, chat, replay)
data/           Persistent state (memory.json, replay.db, config files)
```

## Configuration

### Alerts

Edit `data/alerts_config.json` or set environment variables:

```bash
NEUROFIELD_WEBHOOK_URL=https://your-webhook.example.com  # POST JSON on critical events
```

SMTP alerts: set `email.enabled: true` and fill in `smtp_*` fields in `data/alerts_config.json`.

Alert triggers:
- Worker confirms a `critical`-level action
- 2+ consecutive treatment failures on a sector
- Anomaly severity ≥ 0.8 sustained for 3+ cycles

## Requirements

- Python 3.10+
- Node.js 18+
- An Anthropic API key

> PyBullet is disabled on macOS 15 / Xcode 17 due to SDK incompatibility. The 3D view is rendered in the browser canvas instead.
