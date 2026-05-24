"""Sensor stream generator with procedural anomaly injection."""
import json
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "data" / "farm_config.json"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


@dataclass
class SectorState:
    sector_id: str
    row: str
    col: int
    soil_moisture: float
    crop_health: float
    temperature: float
    anomalies: List[str] = field(default_factory=list)
    last_treated: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Anomaly:
    anomaly_type: str
    sector_id: str
    severity: float       # 0.0–1.0
    cycles_active: int
    spread_probability: float


class SensorStream:
    def __init__(self):
        self.config = load_config()
        self.rows = self.config["sectors"]["rows"]
        self.cols = self.config["sectors"]["cols"]
        self.baselines = self.config["sensor_baselines"]
        self.anomaly_configs = self.config["anomaly_types"]
        self.anomaly_injection_rate = self.config["anomaly_injection_rate"]

        self.sectors: Dict[str, SectorState] = {}
        self.active_anomalies: List[Anomaly] = []
        self._init_sectors()

    def _sector_id(self, row: str, col: int) -> str:
        return f"{row}{col}"

    def _init_sectors(self):
        for row in self.rows:
            for col in self.cols:
                sid = self._sector_id(row, col)
                self.sectors[sid] = SectorState(
                    sector_id=sid,
                    row=row,
                    col=col,
                    soil_moisture=self.baselines["soil_moisture"] + random.uniform(-0.05, 0.05),
                    crop_health=self.baselines["crop_health"] + random.uniform(-0.05, 0.05),
                    temperature=self.baselines["temperature"] + random.uniform(-1.0, 1.0),
                )

    def _neighbors(self, sector_id: str) -> List[str]:
        s = self.sectors.get(sector_id)
        if not s:
            return []
        row_idx = self.rows.index(s.row)
        col_idx = self.cols.index(s.col)
        neighbors = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row_idx + dr, col_idx + dc
            if 0 <= nr < len(self.rows) and 0 <= nc < len(self.cols):
                neighbors.append(self._sector_id(self.rows[nr], self.cols[nc]))
        return neighbors

    def _inject_anomaly(self):
        if random.random() > self.anomaly_injection_rate:
            return
        anomaly_type = random.choice(list(self.anomaly_configs.keys()))
        sector_id = random.choice(list(self.sectors.keys()))
        existing_types = {a.anomaly_type for a in self.active_anomalies if a.sector_id == sector_id}
        if anomaly_type in existing_types:
            return
        cfg = self.anomaly_configs[anomaly_type]
        self.active_anomalies.append(Anomaly(
            anomaly_type=anomaly_type,
            sector_id=sector_id,
            severity=random.uniform(0.3, 0.7),
            cycles_active=0,
            spread_probability=cfg.get("spread_prob", 0.1),
        ))

    def _apply_anomalies(self):
        to_remove = []
        to_add = []

        for anomaly in self.active_anomalies:
            s = self.sectors.get(anomaly.sector_id)
            if not s:
                to_remove.append(anomaly)
                continue

            cfg = self.anomaly_configs[anomaly.anomaly_type]
            anomaly.cycles_active += 1

            if anomaly.anomaly_type == "drought":
                s.soil_moisture = max(0.0, s.soil_moisture - cfg["drop_rate"] * anomaly.severity)
                if anomaly.anomaly_type not in s.anomalies:
                    s.anomalies.append(anomaly.anomaly_type)

            elif anomaly.anomaly_type == "pest_outbreak":
                s.crop_health = max(0.0, s.crop_health - cfg["drop_rate"] * anomaly.severity)
                if anomaly.anomaly_type not in s.anomalies:
                    s.anomalies.append(anomaly.anomaly_type)

            elif anomaly.anomaly_type == "nutrient_deficiency":
                s.crop_health = max(0.0, s.crop_health - cfg["drop_rate"] * anomaly.severity)
                if anomaly.anomaly_type not in s.anomalies:
                    s.anomalies.append(anomaly.anomaly_type)

            elif anomaly.anomaly_type == "heat_stress":
                s.temperature = min(50.0, s.temperature + cfg["rise_rate"] * anomaly.severity)
                if anomaly.anomaly_type not in s.anomalies:
                    s.anomalies.append(anomaly.anomaly_type)

            # natural recovery if sector was treated recently
            if s.last_treated and (time.time() - s.last_treated) < 60:
                to_remove.append(anomaly)
                continue

            # spread to neighbors
            if random.random() < anomaly.spread_probability * 0.1:
                neighbors = self._neighbors(anomaly.sector_id)
                if neighbors:
                    target = random.choice(neighbors)
                    existing = {a.anomaly_type for a in self.active_anomalies if a.sector_id == target}
                    if anomaly.anomaly_type not in existing:
                        to_add.append(Anomaly(
                            anomaly_type=anomaly.anomaly_type,
                            sector_id=target,
                            severity=anomaly.severity * 0.6,
                            cycles_active=0,
                            spread_probability=anomaly.spread_probability,
                        ))

        for a in to_remove:
            if a in self.active_anomalies:
                self.active_anomalies.remove(a)
        self.active_anomalies.extend(to_add)

    def _apply_natural_drift(self):
        for s in self.sectors.values():
            s.soil_moisture = max(0.0, min(1.0,
                s.soil_moisture + random.uniform(-0.005, 0.003)))
            s.crop_health = max(0.0, min(1.0,
                s.crop_health + random.uniform(-0.002, 0.004)))
            s.temperature = max(10.0, min(50.0,
                s.temperature + random.uniform(-0.2, 0.2)))

    def treat_sector(self, sector_id: str, action: str):
        s = self.sectors.get(sector_id)
        if not s:
            return
        s.last_treated = time.time()
        if action == "irrigate":
            s.soil_moisture = min(1.0, s.soil_moisture + 0.4)
            s.anomalies = [a for a in s.anomalies if a != "drought"]
        elif action in ("spray", "fertilize"):
            s.crop_health = min(1.0, s.crop_health + 0.3)
            s.anomalies = [a for a in s.anomalies
                           if a not in ("pest_outbreak", "nutrient_deficiency")]
        self.active_anomalies = [
            a for a in self.active_anomalies
            if not (a.sector_id == sector_id and (
                (action == "irrigate" and a.anomaly_type == "drought") or
                (action in ("spray", "fertilize") and a.anomaly_type in ("pest_outbreak", "nutrient_deficiency"))
            ))
        ]

    def tick(self) -> dict:
        self._inject_anomaly()
        self._apply_anomalies()
        self._apply_natural_drift()
        return self.snapshot()

    def snapshot(self) -> dict:
        return {
            "timestamp": time.time(),
            "sectors": {sid: s.to_dict() for sid, s in self.sectors.items()},
            "active_anomalies": [
                {
                    "type": a.anomaly_type,
                    "sector": a.sector_id,
                    "severity": round(a.severity, 3),
                    "cycles": a.cycles_active,
                }
                for a in self.active_anomalies
            ],
            "stats": {
                "total_sectors": len(self.sectors),
                "anomaly_count": len(self.active_anomalies),
                "critical_sectors": sum(
                    1 for s in self.sectors.values()
                    if s.crop_health < 0.3 or s.soil_moisture < 0.15
                ),
            },
        }
