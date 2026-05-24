# NeuroField — Codebase Guide

## What this project is

Autonomous agricultural robot agent. A simulated 10×10 farm grid with 100 sectors. A Supervisor agent (Claude) triages the whole farm and builds a priority queue. A Worker agent (Claude) confirms each task and decides whether to execute. A physical robot (simulated) carries out the action. The cycle repeats every ~10 seconds.

## How to run

```bash
# One-time setup
python -m venv .venv
source .venv/bin/activate
pip install -e .                    # installs `neurofield` CLI
cd dashboard && npm install && cd ..

# Launch
export ANTHROPIC_API_KEY=sk-ant-...
neurofield start --demo             # demo mode pre-seeds dramatic anomalies
neurofield start                    # live simulation (anomalies emerge naturally)
neurofield doctor                   # check all deps before starting
```

PyBullet is disabled (incompatible with macOS 15 SDK / Xcode 17). 3D view is the browser canvas in the dashboard instead.

## Architecture

```
main.py                 entry point — wires all subsystems, runs asyncio.gather
cli.py                  Click CLI — start / status / logs / alerts / reset / doctor

agent/
  brain.py              NeuroFieldBrain — main async loop, orchestrates everything
  supervisor.py         Supervisor — farm-wide triage, produces priority_queue JSON
  worker.py             Worker — task confirmation, produces confirmed/action/confidence
  prompts.py            all system prompts + message builders
  memory.py             AgentMemory — persistent JSON at data/memory.json
  outcome_tracker.py    registers treatments, checks delta after 20s, marks success/fail
  alert_dispatcher.py   fires alerts on critical decisions / outcome failures / spreading anomalies

simulation/
  sensors.py            SensorStream — 100-sector state, anomaly injection, natural drift
  farm_env.py           FarmEnvironment — PyBullet wrapper (falls back to no-op if unavailable)
  robot.py              RobotController — A* pathfinding, execute_action()
  renderer.py           terminal or headless renderer
  logger.py             SnapshotLogger — SQLite at data/replay.db, 2000-snapshot rolling window
  demo_seeder.py        seeds 10 dramatic anomalies for demo mode

api/
  main.py               FastAPI app + setup_api() wiring
  routes.py             REST endpoints: /state /health /log /outcomes /alerts /alerts/mark-read
  chat.py               POST /chat — streaming Claude response via SSE
  replay.py             GET /replay/bounds|timeline|snapshot|range|events
  websocket.py          WebSocket /ws — ConnectionManager, broadcasts to all clients

dashboard/src/
  App.jsx               root — WebSocket client, all shared state
  FarmGrid.jsx          2D grid with health/moisture color coding, failed-sector overlay
  FarmScene3D.jsx       isometric canvas 3D view — painter's algorithm, animated robot
  AgentLog.jsx          SupervisorCard / WorkerCard / OutcomeCard
  ReplayPanel.jsx       timeline scrubber, playback at 1×/2×/5×/10×
  ChatPanel.jsx         streaming chat, SSE reader, suggested prompts
  AlertToast.jsx        toast notifications + AlertHistoryPanel

data/
  memory.json           persistent agent memory (treated sectors, outcome log, failed treatments)
  farm_config.json      sector layout config
  alerts_config.json    webhook/email config (disabled by default)
  replay.db             SQLite replay database (created at runtime)
```

## Agent loop (brain.py)

Every cycle (~10s):
1. `sensors.tick()` — advance simulation one step
2. `outcome_tracker.check_due()` — evaluate any treatments that are 20s old
3. `alert_dispatcher.check_spreading_anomaly()` — fire alert if anomaly severity ≥ 0.8 for 3+ cycles
4. `supervisor.plan(snapshot)` — Claude produces priority_queue (up to 4 tasks)
5. For top task: `worker.execute_task(task, snapshot)` — Claude confirms/rejects
6. If confirmed: `robot.execute_action()` → `sensors.treat_sector()`
7. `outcome_tracker.register_treatment()` — schedule delta check at +20s
8. `alert_dispatcher.check_worker_decision()` — alert if critical + confirmed

## Key data contracts

**Supervisor output** (JSON):
```json
{
  "priority_queue": [
    {"sector": "A1", "action": "irrigate", "urgency": "critical", "reason": "..."}
  ],
  "farm_summary": "..."
}
```

**Worker output** (JSON):
```json
{
  "confirmed": true,
  "action": "irrigate",
  "confidence": 0.85,
  "diagnosis": "..."
}
```

**WebSocket message types**: `state_update`, `agent_decision`, `outcome_evaluated`, `alert_dispatched`

## Alert channels

Edit `data/alerts_config.json` or set env vars:
- `NEUROFIELD_WEBHOOK_URL` — POST JSON payload to this URL
- SMTP: set `email.enabled: true`, fill `smtp_*` fields in config

Alerts fire on:
- Worker confirms a critical-level action
- Outcome tracker sees 2+ consecutive failures on a sector
- Anomaly severity ≥ 0.8 with 3+ cycles active (spreading)

Per-sector cooldown: 300s (configurable).

## Memory schema (data/memory.json)

```json
{
  "treated_sectors": {"A1": {"last_treated": 1234567890, "treatment_count": 3}},
  "intervention_stats": {"irrigate": {"attempts": 10, "successes": 7}, ...},
  "chronic_sectors": {"A1": 3},
  "failed_treatments": {"A1": {"action": "irrigate", "fail_count": 2, "deltas": [...]}},
  "outcome_log": [...],
  "event_log": [...]
}
```

`neurofield reset` wipes memory.json and replay.db.

## Replay

SQLite stores up to 2000 snapshots (~5.5h at 10s/cycle). Query via:
- `GET /replay/bounds` — min/max timestamp
- `GET /replay/timeline` — all timestamps + stats
- `GET /replay/snapshot?ts=1234567890` — nearest snapshot
- `GET /replay/range?start=...&end=...` — batch range

Dashboard ReplayPanel uses these to scrub through history. Robot interpolates position during playback.

## Model

`claude-sonnet-4-6` for both Supervisor and Worker. Worker prompt includes outcome history for the target sector so it can escalate if prior treatments failed.

## Common issues

- `neurofield` command not found after `pip install -e .`: check `which neurofield` — may need to activate the venv first, or `pip install -e .` inside the venv.
- If `memory.json` has a schema mismatch after upgrading: run `neurofield reset` to rebuild it.
- Dashboard shows "Connecting...": backend not running, or CORS issue — check `http://localhost:8000/health`.
- Replay scrubber empty: simulation hasn't run long enough to log snapshots (10s per entry).
