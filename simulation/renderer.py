"""PyBullet render loop — syncs sensor data to visual grid colors."""
import asyncio
import time
from simulation.farm_env import FarmEnvironment
from simulation.sensors import SensorStream


class Renderer:
    def __init__(self, farm: FarmEnvironment, sensors: SensorStream):
        self.farm = farm
        self.sensors = sensors
        self._running = False

    async def run(self):
        self._running = True
        while self._running:
            snapshot = self.sensors.snapshot()
            for sid, sector in snapshot["sectors"].items():
                self.farm.update_sector_color(
                    sid,
                    sector["crop_health"],
                    sector["soil_moisture"]
                )
            await asyncio.sleep(1.0)

    def stop(self):
        self._running = False
