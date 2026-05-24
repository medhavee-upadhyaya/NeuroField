"""FastAPI application — wires simulation, agent, and websocket together."""
import asyncio
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router, inject
from api.replay import replay_router, inject_logger
from api.websocket import manager

app = FastAPI(title="NeuroField API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(replay_router)

# injected at startup
_sensors = None
_brain = None


@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        manager.disconnect(ws)


async def broadcast_loop():
    """Continuously push sensor + agent state to all WS clients."""
    while True:
        if _sensors and manager.active:
            snapshot = _sensors.snapshot()
            robot_pos = None
            brain_status = "offline"
            last_decision = None

            from api.routes import _robot, _brain as route_brain
            if _robot:
                x, y = _robot.farm.get_robot_position()
                robot_pos = {"x": round(x, 2), "y": round(y, 2), "sector": _robot.current_sector}
            if route_brain:
                brain_status = route_brain.status
                last_decision = route_brain.last_decision

            last_queue = route_brain.last_queue if route_brain else None
            await manager.broadcast({
                "type": "state_update",
                "timestamp": time.time(),
                "snapshot": snapshot,
                "robot": robot_pos,
                "agent_status": brain_status,
                "last_decision": last_decision,
                "last_queue": last_queue,
            })
        await asyncio.sleep(2.0)


def setup_api(sensors, memory, brain, robot, logger=None):
    global _sensors, _brain
    _sensors = sensors
    _brain = brain
    inject(sensors, memory, brain, robot)
    if logger:
        inject_logger(logger)

    @app.on_event("startup")
    async def _start_broadcast():
        asyncio.create_task(broadcast_loop())
