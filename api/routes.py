"""FastAPI route handlers."""
import time
from typing import Optional

from fastapi import APIRouter, HTTPException

router = APIRouter()

# These are injected by main.py at startup
_sensors = None
_memory = None
_brain = None
_robot = None


def inject(sensors, memory, brain, robot):
    global _sensors, _memory, _brain, _robot
    _sensors = sensors
    _memory = memory
    _brain = brain
    _robot = robot


@router.get("/state")
async def get_state():
    if not _sensors:
        raise HTTPException(503, "Simulation not running")
    snapshot = _sensors.snapshot()
    robot_pos = None
    if _robot:
        x, y = _robot.farm.get_robot_position()
        robot_pos = {"x": round(x, 2), "y": round(y, 2), "sector": _robot.current_sector}
    return {
        **snapshot,
        "robot": robot_pos,
        "agent_status": _brain.status if _brain else "offline",
        "last_decision": _brain.last_decision if _brain else None,
        "last_queue": _brain.last_queue if _brain else None,
    }


@router.get("/memory")
async def get_memory():
    if not _memory:
        raise HTTPException(503, "Memory not available")
    return {
        "summary": _memory.summary_for_agent(),
        "data": _memory._data,
    }


@router.get("/log")
async def get_log(limit: int = 50):
    if not _memory:
        raise HTTPException(503, "Memory not available")
    return {"log": _memory.get_event_log(limit=limit)}


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}
