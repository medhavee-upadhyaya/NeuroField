"""Farm grid environment — PyBullet 3D if available, headless otherwise.

3D visualization is handled by the React dashboard (FarmScene3D.jsx) which
renders an isometric canvas view of the farm grid without any native deps.
PyBullet provides optional physics simulation but is not required for the
full visual demo.
"""
import math
import time
import threading
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    import pybullet as p
    import pybullet_data
    PYBULLET_AVAILABLE = True
except ImportError:
    PYBULLET_AVAILABLE = False

CONFIG_PATH = Path(__file__).parent.parent / "data" / "farm_config.json"


class FarmEnvironment:
    def __init__(self, headless: bool = False):
        self.config = json.loads(CONFIG_PATH.read_text())
        self.grid_size = self.config["grid_size"]
        self.sector_size = self.config["sector_size"]
        self.headless = headless
        self.physics_client: Optional[int] = None
        self.sector_bodies: Dict[str, int] = {}
        self.robot_body: Optional[int] = None
        self.robot_pos = [0.0, 0.0, 0.2]
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        if not PYBULLET_AVAILABLE:
            print("[FarmEnv] PyBullet not available — running in headless mode")
            self._running = True
            return

        mode = p.DIRECT if self.headless else p.GUI
        self.physics_client = p.connect(mode)
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        p.resetDebugVisualizerCamera(
            cameraDistance=25,
            cameraYaw=45,
            cameraPitch=-40,
            cameraTargetPosition=[10, 10, 0]
        )

        self._build_ground()
        self._build_grid()
        self._build_robot()
        self._running = True

    def _build_ground(self):
        ground = p.loadURDF("plane.urdf")
        p.changeVisualShape(ground, -1, rgbaColor=[0.4, 0.3, 0.1, 1])

    def _build_grid(self):
        rows = self.config["sectors"]["rows"]
        cols = self.config["sectors"]["cols"]
        for i, row in enumerate(rows):
            for j, col in enumerate(cols):
                sid = f"{row}{col}"
                x = j * self.sector_size + self.sector_size / 2
                y = i * self.sector_size + self.sector_size / 2
                col_shape = p.createCollisionShape(p.GEOM_BOX,
                    halfExtents=[self.sector_size/2 - 0.05,
                                 self.sector_size/2 - 0.05, 0.02])
                vis_shape = p.createVisualShape(p.GEOM_BOX,
                    halfExtents=[self.sector_size/2 - 0.05,
                                 self.sector_size/2 - 0.05, 0.02],
                    rgbaColor=[0.2, 0.7, 0.2, 1])
                body = p.createMultiBody(
                    baseMass=0,
                    baseCollisionShapeIndex=col_shape,
                    baseVisualShapeIndex=vis_shape,
                    basePosition=[x, y, 0.02],
                )
                self.sector_bodies[sid] = body

                # label
                p.addUserDebugText(
                    sid, [x, y, 0.15],
                    textColorRGB=[1, 1, 1],
                    textSize=0.6
                )

    def _build_robot(self):
        chassis_col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.25, 0.35, 0.15])
        chassis_vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[0.25, 0.35, 0.15],
                                          rgbaColor=[0.8, 0.4, 0.0, 1])
        self.robot_body = p.createMultiBody(
            baseMass=5,
            baseCollisionShapeIndex=chassis_col,
            baseVisualShapeIndex=chassis_vis,
            basePosition=self.robot_pos,
        )

    def sector_to_world(self, sector_id: str) -> Tuple[float, float]:
        rows = self.config["sectors"]["rows"]
        row = sector_id[0]
        col = int(sector_id[1:])
        i = rows.index(row)
        j = col - 1
        x = j * self.sector_size + self.sector_size / 2
        y = i * self.sector_size + self.sector_size / 2
        return x, y

    def update_sector_color(self, sector_id: str, health: float, moisture: float):
        if not PYBULLET_AVAILABLE or sector_id not in self.sector_bodies:
            return
        body = self.sector_bodies[sector_id]
        r = max(0.0, min(1.0, 1.0 - health))
        g = max(0.0, min(1.0, health))
        b = max(0.0, min(1.0, moisture * 0.5))
        p.changeVisualShape(body, -1, rgbaColor=[r, g, b, 1])

    def move_robot(self, x: float, y: float):
        if not PYBULLET_AVAILABLE:
            self.robot_pos = [x, y, 0.2]
            return
        with self._lock:
            steps = 60
            start = list(p.getBasePositionAndOrientation(self.robot_body)[0])
            dx = (x - start[0]) / steps
            dy = (y - start[1]) / steps
            for _ in range(steps):
                self.robot_pos[0] += dx
                self.robot_pos[1] += dy
                p.resetBasePositionAndOrientation(
                    self.robot_body,
                    [self.robot_pos[0], self.robot_pos[1], 0.2],
                    [0, 0, 0, 1]
                )
                p.stepSimulation()
                time.sleep(1.0 / 240)

    def get_robot_position(self) -> Tuple[float, float]:
        if not PYBULLET_AVAILABLE:
            return self.robot_pos[0], self.robot_pos[1]
        pos, _ = p.getBasePositionAndOrientation(self.robot_body)
        return pos[0], pos[1]

    def stop(self):
        self._running = False
        if PYBULLET_AVAILABLE and self.physics_client is not None:
            p.disconnect(self.physics_client)
