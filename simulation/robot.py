"""Robot execution layer — A* navigation + arm actions."""
import asyncio
import heapq
import time
from typing import Dict, List, Optional, Tuple

from simulation.farm_env import FarmEnvironment
from simulation.sensors import SensorStream


class RobotController:
    def __init__(self, farm: FarmEnvironment, sensors: SensorStream):
        self.farm = farm
        self.sensors = sensors
        self.current_sector: Optional[str] = None
        self.busy = False

    def _sector_grid_pos(self, sector_id: str) -> Tuple[int, int]:
        rows = self.farm.config["sectors"]["rows"]
        row = sector_id[0]
        col = int(sector_id[1:])
        return rows.index(row), col - 1

    def _astar(self, start: str, goal: str) -> List[str]:
        rows = self.farm.config["sectors"]["rows"]
        cols = self.farm.config["sectors"]["cols"]

        def neighbors(sid: str) -> List[str]:
            r = sid[0]
            c = int(sid[1:])
            ri = rows.index(r)
            ci = cols.index(c)
            result = []
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = ri + dr, ci + dc
                if 0 <= nr < len(rows) and 0 <= nc < len(cols):
                    result.append(f"{rows[nr]}{cols[nc]}")
            return result

        def heuristic(a: str, b: str) -> float:
            ar, ac = self._sector_grid_pos(a)
            br, bc = self._sector_grid_pos(b)
            return abs(ar - br) + abs(ac - bc)

        open_set = [(0.0, start)]
        came_from: Dict[str, Optional[str]] = {start: None}
        g_score: Dict[str, float] = {start: 0.0}

        while open_set:
            _, current = heapq.heappop(open_set)
            if current == goal:
                path = []
                while current:
                    path.append(current)
                    current = came_from[current]
                return list(reversed(path))
            for nb in neighbors(current):
                tentative = g_score[current] + 1.0
                if tentative < g_score.get(nb, float("inf")):
                    came_from[nb] = current
                    g_score[nb] = tentative
                    f = tentative + heuristic(nb, goal)
                    heapq.heappush(open_set, (f, nb))
        return [start, goal]

    async def navigate_to(self, sector_id: str) -> bool:
        if self.current_sector == sector_id:
            return True
        start = self.current_sector or "A1"
        path = self._astar(start, sector_id)
        x, y = self.farm.sector_to_world(sector_id)
        await asyncio.get_event_loop().run_in_executor(None, self.farm.move_robot, x, y)
        self.current_sector = sector_id
        return True

    async def execute_action(self, action: str, sector_id: str) -> dict:
        self.busy = True
        start_time = time.time()
        try:
            nav_ok = await self.navigate_to(sector_id)
            if not nav_ok:
                return {"success": False, "error": "navigation_failed", "duration": 0}

            await self._perform_action(action, sector_id)
            self.sensors.treat_sector(sector_id, action)

            duration = time.time() - start_time
            return {"success": True, "action": action, "sector": sector_id, "duration": round(duration, 2)}
        except Exception as e:
            return {"success": False, "error": str(e), "duration": time.time() - start_time}
        finally:
            self.busy = False

    async def _perform_action(self, action: str, sector_id: str):
        """Simulate arm movements for each action type."""
        if action == "irrigate":
            # arm extends down for 3s
            await asyncio.sleep(3.0)
        elif action == "spray":
            # arm rotates 360° — simulate as 2s pause
            await asyncio.sleep(2.0)
        elif action == "fertilize":
            # arm pulses 3 times
            for _ in range(3):
                await asyncio.sleep(0.5)
        elif action == "navigate":
            pass  # already navigated
        elif action in ("report", "wait"):
            await asyncio.sleep(0.5)
