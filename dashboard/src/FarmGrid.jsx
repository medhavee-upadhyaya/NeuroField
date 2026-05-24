const ROWS = ["A","B","C","D","E","F","G","H","I","J"];
const COLS = [1,2,3,4,5,6,7,8,9,10];
const SECTOR_SIZE = 2.0;
const GRID_PX = 300;
const CELL = GRID_PX / 10;

function healthColor(health, moisture) {
  if (health < 0.3) return "#c62828";
  if (health < 0.5) return "#e65100";
  if (health < 0.65) return "#f9a825";
  if (moisture < 0.25) return "#f57f17";
  return "#388e3c";
}

function robotGridPos(robotXY) {
  if (!robotXY) return null;
  const col = Math.round(robotXY.x / SECTOR_SIZE - 0.5);
  const row = Math.round(robotXY.y / SECTOR_SIZE - 0.5);
  return { col: Math.max(0, Math.min(9, col)), row: Math.max(0, Math.min(9, row)) };
}

export default function FarmGrid({ snapshot, robot, selectedSector, onSelectSector }) {
  const sectors = snapshot?.sectors || {};
  const robotPos = robotGridPos(robot);

  return (
    <div style={styles.wrapper}>
      <div style={styles.grid}>
        {/* Column headers */}
        <div style={styles.cornerCell} />
        {COLS.map((c) => (
          <div key={c} style={styles.headerCell}>{c}</div>
        ))}

        {/* Grid rows */}
        {ROWS.map((row, ri) => (
          <>
            <div key={`row-${row}`} style={styles.headerCell}>{row}</div>
            {COLS.map((col, ci) => {
              const sid = `${row}${col}`;
              const s = sectors[sid];
              const health = s?.crop_health ?? 0.85;
              const moisture = s?.soil_moisture ?? 0.6;
              const bg = healthColor(health, moisture);
              const isRobot = robotPos?.row === ri && robotPos?.col === ci;
              const isSelected = selectedSector === sid;
              const hasAnomaly = (s?.anomalies?.length ?? 0) > 0;

              return (
                <div
                  key={sid}
                  onClick={() => onSelectSector(sid)}
                  style={{
                    ...styles.cell,
                    background: bg,
                    outline: isSelected ? "2px solid #fff" : isRobot ? "2px solid #2196f3" : "none",
                    cursor: "pointer",
                    position: "relative",
                  }}
                  title={`${sid}: health=${health.toFixed(2)} moisture=${moisture.toFixed(2)}`}
                >
                  {isRobot && <div style={styles.robotDot} />}
                  {hasAnomaly && !isRobot && <div style={styles.anomalyDot} />}
                </div>
              );
            })}
          </>
        ))}
      </div>
    </div>
  );
}

const HEADER = CELL * 0.6;

const styles = {
  wrapper: { display: "flex", justifyContent: "center", alignItems: "center" },
  grid: {
    display: "grid",
    gridTemplateColumns: `${HEADER}px repeat(10, ${CELL}px)`,
    gridTemplateRows: `${HEADER}px repeat(10, ${CELL}px)`,
    gap: 1,
    background: "#30363d",
    padding: 1,
    borderRadius: 4,
  },
  cornerCell: { background: "#0d1117" },
  headerCell: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#21262d",
    color: "#8b949e",
    fontSize: 9,
    fontWeight: 700,
  },
  cell: {
    width: CELL,
    height: CELL,
    borderRadius: 1,
    transition: "background 0.4s ease",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  robotDot: {
    width: CELL * 0.45,
    height: CELL * 0.45,
    borderRadius: "50%",
    background: "#2196f3",
    border: "1.5px solid #fff",
    boxShadow: "0 0 6px #2196f3",
    animation: "pulse 1.2s infinite",
  },
  anomalyDot: {
    width: CELL * 0.3,
    height: CELL * 0.3,
    borderRadius: "50%",
    background: "#fff",
    opacity: 0.7,
  },
};
