"""NeuroField entry point — wires all subsystems together."""
import asyncio
import os
import sys

import uvicorn

from agent.brain import NeuroFieldBrain
from agent.memory import AgentMemory
from api.main import app, setup_api
from simulation.farm_env import FarmEnvironment
from simulation.logger import SnapshotLogger
from simulation.renderer import Renderer
from simulation.robot import RobotController
from simulation.sensors import SensorStream


async def run(headless: bool = False):
    sensors = SensorStream()
    memory = AgentMemory()
    logger = SnapshotLogger()
    farm = FarmEnvironment(headless=headless)
    farm.start()

    robot = RobotController(farm, sensors)
    brain = NeuroFieldBrain(sensors, memory)
    renderer = Renderer(farm, sensors)

    # ---- wire agent callbacks ----
    async def on_decision(decision, snapshot):
        from api.websocket import manager
        # log the agent action against the snapshot it acted on
        await logger.log_event("agent_decision", {
            "action": decision.get("action"),
            "sector": decision.get("target_sector"),
            "agent": decision.get("agent", "worker"),
            "alert_level": decision.get("alert_level"),
            "confirmed": decision.get("confirmed", True),
        })
        await manager.broadcast({
            "type": "agent_decision",
            "decision": decision,
            "snapshot_ts": snapshot["timestamp"],
        })

    async def on_execution_request(action: str, sector: str) -> dict:
        return await robot.execute_action(action, sector)

    brain.on_decision(on_decision)
    brain.on_execution_request(on_execution_request)

    # ---- periodic snapshot logging ----
    async def logging_loop():
        last_logged = 0.0
        while True:
            snap = sensors.snapshot()
            if snap["timestamp"] != last_logged:
                await logger.log_snapshot(snap, brain.last_decision)
                last_logged = snap["timestamp"]
            await asyncio.sleep(10.0)

    setup_api(sensors, memory, brain, robot, logger=logger)

    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)

    tasks = [
        asyncio.create_task(brain.run()),
        asyncio.create_task(renderer.run()),
        asyncio.create_task(logging_loop()),
        asyncio.create_task(server.serve()),
    ]

    print("[NeuroField] All systems online")
    print("[NeuroField] API        → http://localhost:8000")
    print("[NeuroField] Replay API → http://localhost:8000/replay/bounds")
    print("[NeuroField] Dashboard  → http://localhost:3000")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        brain.stop()
        renderer.stop()
        farm.stop()
        print("[NeuroField] Shutdown complete")


if __name__ == "__main__":
    headless = "--headless" in sys.argv
    asyncio.run(run(headless=headless))
