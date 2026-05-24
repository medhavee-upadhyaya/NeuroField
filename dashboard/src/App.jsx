import { useState, useEffect, useRef, useCallback } from "react";
import FarmGrid from "./FarmGrid";
import AgentLog from "./AgentLog";
import SensorPanel from "./SensorPanel";

const WS_URL = "ws://localhost:8000/ws/live";
const API_URL = "http://localhost:8000";

function useWebSocket(url, onMessage) {
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(url);
    ws.onopen = () => console.log("[WS] Connected");
    ws.onmessage = (e) => onMessage(JSON.parse(e.data));
    ws.onerror = () => console.warn("[WS] Error");
    ws.onclose = () => {
      reconnectTimer.current = setTimeout(connect, 3000);
    };
    wsRef.current = ws;
  }, [url, onMessage]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);
}

export default function App() {
  const [snapshot, setSnapshot] = useState(null);
  const [robot, setRobot] = useState(null);
  const [agentStatus, setAgentStatus] = useState("offline");
  const [decisions, setDecisions] = useState([]);
  const [selectedSector, setSelectedSector] = useState(null);
  const [alerts, setAlerts] = useState(0);
  const [interventionsToday, setInterventionsToday] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);

  // Load initial log from REST
  useEffect(() => {
    fetch(`${API_URL}/log?limit=50`)
      .then((r) => r.json())
      .then((d) => setDecisions(d.log || []))
      .catch(() => {});

    fetch(`${API_URL}/state`)
      .then((r) => r.json())
      .then((d) => {
        setSnapshot(d);
        setRobot(d.robot);
        setAgentStatus(d.agent_status || "offline");
        if (d.last_decision) setDecisions((prev) => [d.last_decision, ...prev].slice(0, 100));
        setAlerts(d.stats?.critical_sectors || 0);
      })
      .catch(() => {});
  }, []);

  const handleWsMessage = useCallback((msg) => {
    setWsConnected(true);
    if (msg.type === "state_update") {
      setSnapshot(msg.snapshot);
      setRobot(msg.robot);
      setAgentStatus(msg.agent_status || "idle");
      setAlerts(msg.snapshot?.stats?.critical_sectors || 0);
    } else if (msg.type === "agent_decision") {
      const d = msg.decision;
      setDecisions((prev) => [...prev, d].slice(-100));
      if (d.agent === "worker" && d.confirmed && !["report", "wait"].includes(d.action)) {
        setInterventionsToday((n) => n + 1);
      }
      if (d.agent !== "supervisor") setAgentStatus("idle");
    }
  }, []);

  useWebSocket(WS_URL, handleWsMessage);

  const statusColor = {
    idle: "#4caf50",
    thinking: "#ff9800",
    acting: "#2196f3",
    offline: "#9e9e9e",
  }[agentStatus] || "#9e9e9e";

  return (
    <div style={styles.app}>
      {/* Top bar */}
      <div style={styles.topBar}>
        <div style={styles.topLeft}>
          <span style={styles.logo}>🌾 NeuroField</span>
          <span style={styles.tagline}>Autonomous Agricultural AI</span>
        </div>
        <div style={styles.topMetrics}>
          <Metric
            label="ALERTS"
            value={alerts}
            color={alerts > 0 ? "#f44336" : "#4caf50"}
          />
          <Metric label="INTERVENTIONS TODAY" value={interventionsToday} color="#2196f3" />
          <div style={styles.agentStatus}>
            <div style={{ ...styles.statusDot, background: statusColor }} />
            <span style={{ color: statusColor, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>
              {agentStatus}
            </span>
            {!wsConnected && <span style={styles.offlineBadge}>NO WS</span>}
          </div>
        </div>
      </div>

      {/* Main panels */}
      <div style={styles.main}>
        <div style={styles.leftPanel}>
          <div style={styles.panelHeader}>FARM GRID</div>
          <FarmGrid
            snapshot={snapshot}
            robot={robot}
            selectedSector={selectedSector}
            onSelectSector={setSelectedSector}
          />
          <div style={styles.gridLegend}>
            <LegendItem color="#388e3c" label="Healthy" />
            <LegendItem color="#f9a825" label="Warning" />
            <LegendItem color="#c62828" label="Critical" />
            <LegendItem color="#1565c0" label="Robot" />
          </div>
        </div>

        <div style={styles.centerPanel}>
          <div style={styles.panelHeader}>AGENT REASONING LOG</div>
          <AgentLog decisions={decisions} />
        </div>

        <div style={styles.rightPanel}>
          <div style={styles.panelHeader}>
            {selectedSector ? `SECTOR ${selectedSector}` : "SELECT A SECTOR"}
          </div>
          <SectorPanel snapshot={snapshot} sectorId={selectedSector} />
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, color }) {
  return (
    <div style={styles.metric}>
      <div style={{ ...styles.metricValue, color }}>{value}</div>
      <div style={styles.metricLabel}>{label}</div>
    </div>
  );
}

function LegendItem({ color, label }) {
  return (
    <div style={styles.legendItem}>
      <div style={{ ...styles.legendColor, background: color }} />
      <span>{label}</span>
    </div>
  );
}

function SectorPanel({ snapshot, sectorId }) {
  if (!sectorId || !snapshot) {
    return (
      <div style={styles.emptySector}>
        Click a grid cell to view sensor data
      </div>
    );
  }
  return <SensorPanel snapshot={snapshot} sectorId={sectorId} />;
}

const styles = {
  app: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    background: "#0d1117",
    color: "#e6edf3",
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
    fontSize: 12,
  },
  topBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 20px",
    background: "#161b22",
    borderBottom: "1px solid #30363d",
    minHeight: 52,
  },
  topLeft: { display: "flex", alignItems: "center", gap: 16 },
  logo: { fontSize: 18, fontWeight: 700, color: "#4caf50" },
  tagline: { color: "#8b949e", fontSize: 11 },
  topMetrics: { display: "flex", alignItems: "center", gap: 24 },
  metric: { textAlign: "center" },
  metricValue: { fontSize: 22, fontWeight: 700, lineHeight: 1 },
  metricLabel: { fontSize: 9, color: "#8b949e", marginTop: 2, letterSpacing: 1 },
  agentStatus: { display: "flex", alignItems: "center", gap: 8, padding: "4px 12px", background: "#21262d", borderRadius: 6 },
  statusDot: { width: 8, height: 8, borderRadius: "50%" },
  offlineBadge: { fontSize: 9, background: "#f44336", color: "#fff", padding: "1px 5px", borderRadius: 3 },
  main: { display: "flex", flex: 1, overflow: "hidden", gap: 1, padding: 1, background: "#30363d" },
  leftPanel: { display: "flex", flexDirection: "column", width: 340, background: "#161b22", padding: 12 },
  centerPanel: { display: "flex", flexDirection: "column", flex: 1, background: "#161b22", padding: 12, overflow: "hidden" },
  rightPanel: { display: "flex", flexDirection: "column", width: 280, background: "#161b22", padding: 12 },
  panelHeader: { fontSize: 10, fontWeight: 700, color: "#8b949e", letterSpacing: 2, marginBottom: 8, borderBottom: "1px solid #30363d", paddingBottom: 6 },
  gridLegend: { display: "flex", gap: 12, marginTop: 8, flexWrap: "wrap" },
  legendItem: { display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#8b949e" },
  legendColor: { width: 10, height: 10, borderRadius: 2 },
  emptySector: { color: "#8b949e", textAlign: "center", marginTop: 40, lineHeight: 1.6 },
};
