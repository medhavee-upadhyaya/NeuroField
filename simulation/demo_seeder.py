"""Demo seeder — injects a dramatic, pre-planned scenario at startup.

Gives hiring managers an immediately compelling view: multiple spreading
anomalies, a chronic sector, and a failing crop cluster — all ready for
the AI to reason about from the first cycle.
"""
from simulation.sensors import SensorStream, Anomaly


DEMO_SCENARIO = [
    # Drought crisis spreading from corner
    {"type": "drought",            "sector": "A1", "severity": 0.75, "cycles": 8},
    {"type": "drought",            "sector": "A2", "severity": 0.55, "cycles": 5},
    {"type": "drought",            "sector": "B1", "severity": 0.45, "cycles": 3},

    # Active pest outbreak mid-farm
    {"type": "pest_outbreak",      "sector": "E5", "severity": 0.82, "cycles": 6},
    {"type": "pest_outbreak",      "sector": "E6", "severity": 0.65, "cycles": 4},
    {"type": "pest_outbreak",      "sector": "F5", "severity": 0.40, "cycles": 2},

    # Slow nutrient deficiency spreading across row H
    {"type": "nutrient_deficiency","sector": "H3", "severity": 0.60, "cycles": 12},
    {"type": "nutrient_deficiency","sector": "H4", "severity": 0.50, "cycles": 9},
    {"type": "nutrient_deficiency","sector": "H5", "severity": 0.35, "cycles": 6},

    # Heat stress pocket
    {"type": "heat_stress",        "sector": "J8", "severity": 0.70, "cycles": 5},
    {"type": "heat_stress",        "sector": "J9", "severity": 0.50, "cycles": 3},
]


def seed(stream: SensorStream):
    """Inject the demo scenario into a running SensorStream."""
    # First run several ticks to let natural drift establish baselines
    for _ in range(3):
        stream.tick()

    # Inject anomalies
    for entry in DEMO_SCENARIO:
        sid = entry["sector"]
        atype = entry["type"]
        existing = {a.anomaly_type for a in stream.active_anomalies if a.sector_id == sid}
        if atype not in existing:
            stream.active_anomalies.append(Anomaly(
                anomaly_type=atype,
                sector_id=sid,
                severity=entry["severity"],
                cycles_active=entry["cycles"],
                spread_probability=stream.anomaly_configs[atype].get("spread_prob", 0.1),
            ))

    # Apply them immediately so the first snapshot shows the problem
    for _ in range(entry["cycles"] // 3 + 1):
        stream._apply_anomalies()
        stream._apply_natural_drift()

    print(f"[Demo] Seeded {len(DEMO_SCENARIO)} anomalies across "
          f"{len({e['sector'] for e in DEMO_SCENARIO})} sectors")
    snap = stream.snapshot()
    print(f"[Demo] Farm state: {snap['stats']['anomaly_count']} active anomalies, "
          f"{snap['stats']['critical_sectors']} critical sectors")
