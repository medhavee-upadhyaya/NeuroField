import { useState, useEffect, useRef } from "react";

const HISTORY_SIZE = 20;

function useHistory(value) {
  const histRef = useRef([]);
  if (value !== undefined && value !== null) {
    histRef.current = [...histRef.current, value].slice(-HISTORY_SIZE);
  }
  return histRef.current;
}

function Sparkline({ values, color, min = 0, max = 1, height = 32 }) {
  if (!values.length) return null;
  const w = 200;
  const h = height;
  const step = w / Math.max(values.length - 1, 1);

  const pts = values.map((v, i) => {
    const x = i * step;
    const y = h - ((v - min) / (max - min + 0.001)) * h;
    return `${x},${y}`;
  });

  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <polyline
        points={pts.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
      <circle cx={pts[pts.length - 1]?.split(",")[0]} cy={pts[pts.length - 1]?.split(",")[1]} r={2.5} fill={color} />
    </svg>
  );
}

function Gauge({ value, max = 1, color, label, unit = "" }) {
  const pct = Math.round((value / max) * 100);
  return (
    <div style={gaugeStyles.wrap}>
      <div style={gaugeStyles.top}>
        <span style={gaugeStyles.label}>{label}</span>
        <span style={{ ...gaugeStyles.value, color }}>
          {typeof value === "number" ? value.toFixed(2) : "–"}{unit}
        </span>
      </div>
      <div style={gaugeStyles.track}>
        <div style={{ ...gaugeStyles.fill, width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

const gaugeStyles = {
  wrap: { marginBottom: 12 },
  top: { display: "flex", justifyContent: "space-between", marginBottom: 3 },
  label: { color: "#8b949e", fontSize: 10, letterSpacing: 1, fontWeight: 700 },
  value: { fontSize: 13, fontWeight: 700 },
  track: { height: 6, background: "#30363d", borderRadius: 3, overflow: "hidden" },
  fill: { height: "100%", borderRadius: 3, transition: "width 0.3s ease" },
};

export default function SensorPanel({ snapshot, sectorId }) {
  const sector = snapshot?.sectors?.[sectorId];
  const moistureHist = useHistory(sector?.soil_moisture);
  const healthHist = useHistory(sector?.crop_health);
  const tempHist = useHistory(sector?.temperature);

  if (!sector) {
    return <div style={styles.empty}>No data for sector {sectorId}</div>;
  }

  const anomalies = sector.anomalies || [];
  const moistureColor = sector.soil_moisture < 0.25 ? "#f44336" : sector.soil_moisture < 0.45 ? "#ff9800" : "#2196f3";
  const healthColor = sector.crop_health < 0.35 ? "#f44336" : sector.crop_health < 0.6 ? "#ff9800" : "#4caf50";
  const tempColor = sector.temperature > 35 ? "#f44336" : sector.temperature > 30 ? "#ff9800" : "#4caf50";

  return (
    <div style={styles.panel}>
      {anomalies.length > 0 && (
        <div style={styles.anomalyBanner}>
          {anomalies.map((a) => (
            <span key={a} style={styles.anomalyTag}>{a.replace("_", " ")}</span>
          ))}
        </div>
      )}

      <Gauge
        label="SOIL MOISTURE"
        value={sector.soil_moisture}
        color={moistureColor}
      />
      <div style={styles.sparkWrap}>
        <Sparkline values={moistureHist} color={moistureColor} min={0} max={1} />
      </div>

      <Gauge
        label="CROP HEALTH"
        value={sector.crop_health}
        color={healthColor}
      />
      <div style={styles.sparkWrap}>
        <Sparkline values={healthHist} color={healthColor} min={0} max={1} />
      </div>

      <Gauge
        label="TEMPERATURE"
        value={sector.temperature}
        max={50}
        color={tempColor}
        unit="°C"
      />
      <div style={styles.sparkWrap}>
        <Sparkline values={tempHist} color={tempColor} min={10} max={50} />
      </div>

      <div style={styles.meta}>
        <div style={styles.metaRow}>
          <span style={styles.metaLabel}>SECTOR</span>
          <span style={styles.metaValue}>{sectorId}</span>
        </div>
        <div style={styles.metaRow}>
          <span style={styles.metaLabel}>STATUS</span>
          <span style={{ ...styles.metaValue, color: healthColor }}>
            {sector.crop_health >= 0.7 ? "HEALTHY" : sector.crop_health >= 0.5 ? "WARNING" : "CRITICAL"}
          </span>
        </div>
        {sector.last_treated && (
          <div style={styles.metaRow}>
            <span style={styles.metaLabel}>TREATED</span>
            <span style={styles.metaValue}>
              {new Date(sector.last_treated * 1000).toLocaleTimeString()}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  panel: { display: "flex", flexDirection: "column", gap: 2 },
  empty: { color: "#8b949e", fontSize: 11 },
  anomalyBanner: { display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 12 },
  anomalyTag: {
    background: "#f4433622",
    color: "#f44336",
    border: "1px solid #f4433644",
    padding: "2px 8px",
    borderRadius: 3,
    fontSize: 9,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  sparkWrap: { marginBottom: 10, opacity: 0.8 },
  meta: { marginTop: 8, background: "#21262d", borderRadius: 4, padding: 8 },
  metaRow: { display: "flex", justifyContent: "space-between", marginBottom: 4 },
  metaLabel: { color: "#8b949e", fontSize: 10, letterSpacing: 1 },
  metaValue: { color: "#e6edf3", fontSize: 11, fontWeight: 600 },
};
