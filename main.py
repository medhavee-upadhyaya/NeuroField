"""NeuroField entry point — wires all subsystems together."""
import asyncio
import os
import signal
import sys

import uvicorn

from agent.brain import NeuroFieldBrain
from agent.memory import AgentMemory
from api.main import app, setup_api
from simulation.farm_env import FarmEnvironment
from simulation.renderer import Renderer
from simulation.robot import RobotController
from simulation.sensors import SensorStream


async def run(headless: bool = False):
    # ---- subsystem init ----
    sensors = SensorStream()
    memory = AgentMemory()
    farm = FarmEnvironment(headless=headless)
    farm.start()

    robot = RobotController(farm, sensors)
    brain = NeuroFieldBrain(sensors, memory)
    renderer = Renderer(farm, sensors)

    # ---- wire agent callbacks ----
    async def on_decision(decision, snapshot):
        from api.websocket import manager
        await manager.broadcast({
            "type": "agent_decision",
            "decision": decision,
            "snapshot_ts": snapshot["timestamp"],
        })

    async def on_execution_request(action: str, sector: str) -> dict:
        return await robot.execute_action(action, sector)

    brain.on_decision(on_decision)
    brain.on_execution_request(on_execution_request)

    # ---- configure API ----
    setup_api(sensors, memory, brain, robot)

    # ---- run all tasks concurrently ----
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)

    tasks = [
        asyncio.create_task(brain.run()),
        asyncio.create_task(renderer.run()),
        asyncio.create_task(server.serve()),
    ]

    print("[NeuroField] All systems online")
    print("[NeuroField] API → http://localhost:8000")
    print("[NeuroField] Dashboard → http://localhost:3000")

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
