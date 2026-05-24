import { useState, useEffect, useRef, useCallback } from "react";
import FarmGrid from "./FarmGrid";
import AgentLog from "./AgentLog";
import SensorPanel from "./SensorPanel";
import ReplayPanel from "./ReplayPanel";
import ChatPanel from "./ChatPanel";
import { useAlertToasts, AlertToastContainer, AlertHistoryPanel } from "./AlertToast";

const WS_URL = "ws://localhost:8000/ws/live";
const API_URL = "http://localhost:8000";

function useWebSocket(url, onMessage, paused) {
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(url);
    ws.onopen = () => console.log("[WS] Connected");
    ws.onmessage = (e) => { if (!paused) onMessage(JSON.parse(e.data)); };
    ws.onerror = () => console.warn("[WS] Error");
    ws.onclose = () => { reconnectTimer.current = setTimeout(connect, 3000); };
    wsRef.current = ws;
  }, [url, onMessage, paused]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);
}

export default function App() {
  const [liveSnapshot, setLiveSnapshot] = useState(null);
  const [replaySnapshot, setReplaySnapshot] = useState(null);
  const [isReplayMode, setIsReplayMode] = useState(false);
  const [robot, setRobot] = useState(null);
  const [agentStatus, setAgentStatus] = useState("offline");
  const [decisions, setDecisions] = useState([]);
  const [selectedSector, setSelectedSector] = useState(null);
  const [alerts, setAlerts] = useState(0);
  const [interventionsToday, setInterventionsToday] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);
  const [showReplay, setShowReplay] = useState(false);
  const [rightTab, setRightTab] = useState("sensor"); // "sensor" | "chat"
  const [failedSectors, setFailedSectors] = useState({});
  const [alertHistory, setAlertHistory] = useState([]);
  const [showAlerts, setShowAlerts] = useState(false);
  const { toasts, addToast } = useAlertToasts();

  const snapshot = isReplayMode ? replaySnapshot : liveSnapshot;

  useEffect(() => {
    fetch(`${API_URL}/log?limit=50`)
      .then((r) => r.json())
      .then((d) => setDecisions(d.log || []))
      .catch(() => {});

    fetch(`${API_URL}/state`)
      .then((r) => r.json())
      .then((d) => {
        setLiveSnapshot(d);
        setRobot(d.robot);
        setAgentStatus(d.agent_status || "offline");
        if (d.last_decision) setDecisions((prev) => [...prev, d.last_decision].slice(-100));
        setAlerts(d.stats?.critical_sectors || 0);
      })
      .catch(() => {});
  }, []);

  const handleWsMessage = useCallback((msg) => {
    setWsConnected(true);
    if (msg.type === "state_update") {
      setLiveSnapshot(msg.snapshot);
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
    } else if (msg.type === "alert_dispatched") {
      const a = msg.alert;
      addToast(a);
      setAlertHistory((prev) => [a, ...prev].slice(0, 50));
      setAlerts((n) => n + 1);
    } else if (msg.type === "outcome_evaluated") {
      const o = msg.outcome;
      setDecisions((prev) => [...prev, { ...o, _type: "outcome" }].slice(-100));
      if (!o.success) {
        setFailedSectors((prev) => ({
          ...prev,
          [o.sector_id]: { action: o.action, fail_count: (prev[o.sector_id]?.fail_count || 0) + 1 },
        }));
      } else {
        setFailedSectors((prev) => {
          const next = { ...prev };
          delete next[o.sector_id];
          return next;
        });
      }
    }
  }, []);

  useWebSocket(WS_URL, handleWsMessage, isReplayMode);

  const handleReplaySnapshot = (snap) => {
    if (snap === null) { setIsReplayMode(false); return; }
    setReplaySnapshot(snap);
    setIsReplayMode(true);
  };

  const handleExitReplay = () => {
    setIsReplayMode(false);
    setReplaySnapshot(null);
  };

  const statusColor = {
    idle: "#4caf50",
    thinking: "#ff9800",
    acting: "#2196f3",
    offline: "#9e9e9e",
  }[agentStatus] || "#9e9e9e";

  return (
    <div style={styles.app}>
      <AlertToastContainer toasts={toasts} />

      {showAlerts && (
        <div style={styles.alertOverlay} onClick={() => setShowAlerts(false)}>
          <div style={styles.alertPanel} onClick={(e) => e.stopPropagation()}>
            <div style={styles.alertPanelHeader}>
              <span>🚨 ALERT HISTORY</span>
              <button onClick={() => setShowAlerts(false)} style={styles.closeBtn}>✕</button>
            </div>
            <AlertHistoryPanel alerts={alertHistory} />
            <div style={{ marginTop: 8, fontSize: 10, color: "#8b949e" }}>
              Configure webhook/email in <code>data/alerts_config.json</code> or set{" "}
              <code>NEUROFIELD_WEBHOOK_URL</code> env var.
            </div>
          </div>
        </div>
      )}

      {/* Top bar */}
      <div style={styles.topBar}>
        <div style={styles.topLeft}>
          <span style={styles.logo}>🌾 NeuroField</span>
          <span style={styles.tagline}>Autonomous Agricultural AI</span>
          {isReplayMode && (
            <span style={styles.replayBadge}>⏪ REPLAY</span>
          )}
        </div>
        <div style={styles.topMetrics}>
          <div
            onClick={() => setShowAlerts((v) => !v)}
            style={{ cursor: "pointer", position: "relative" }}
            title="Click to view alert history"
          >
            <Metric label="ALERTS" value={alerts} color={alerts > 0 ? "#f44336" : "#4caf50"} />
            {alerts > 0 && <div style={styles.alertPing} />}
          </div>
          <Metric label="INTERVENTIONS TODAY" value={interventionsToday} color="#2196f3" />
          <div style={styles.agentStatus}>
            <div style={{ ...styles.statusDot, background: isReplayMode ? "#7c4dff" : statusColor }} />
            <span style={{ color: isReplayMode ? "#b39ddb" : statusColor, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>
              {isReplayMode ? "replay" : agentStatus}
            </span>
            {!wsConnected && !isReplayMode && <span style={styles.offlineBadge}>NO WS</span>}
          </div>
          <button
            onClick={() => setShowReplay((v) => !v)}
            style={{ ...styles.replayToggle, background: showReplay ? "#7c4dff" : "#21262d" }}
          >
            ⏪ Replay
          </button>
        </div>
      </div>

      {/* Replay panel — full-width strip when open */}
      {showReplay && (
        <div style={styles.replayStrip}>
          <ReplayPanel
            onReplaySnapshot={handleReplaySnapshot}
            onExitReplay={handleExitReplay}
            isReplayMode={isReplayMode}
          />
        </div>
      )}

      {/* Main panels */}
      <div style={styles.main}>
        <div style={styles.leftPanel}>
          <div style={styles.panelHeader}>FARM GRID</div>
          <FarmGrid
            snapshot={snapshot}
            robot={isReplayMode ? null : robot}
            selectedSector={selectedSector}
            onSelectSector={setSelectedSector}
            failedSectors={isReplayMode ? {} : failedSectors}
          />
          <div style={styles.gridLegend}>
            <LegendItem color="#388e3c" label="Healthy" />
            <LegendItem color="#f9a825" label="Warning" />
            <LegendItem color="#c62828" label="Critical" />
            <LegendItem color="#1565c0" label="Robot" />
            <LegendItem color="#ff5722" label="Failed TX" />
          </div>
        </div>

        <div style={styles.centerPanel}>
          <div style={styles.panelHeader}>
            AGENT REASONING LOG
            {isReplayMode && replaySnapshot?.agent_action && (
              <span style={styles.replayActionBadge}>
                ↳ {replaySnapshot.agent_action.action} → {replaySnapshot.agent_action.sector}
              </span>
            )}
          </div>
          <AgentLog decisions={decisions} />
        </div>

        <div style={styles.rightPanel}>
          <div style={styles.tabBar}>
            <button
              onClick={() => setRightTab("sensor")}
              style={{ ...styles.tab, ...(rightTab === "sensor" ? styles.tabActive : {}) }}
            >
              {selectedSector ? `📡 ${selectedSector}` : "📡 SENSOR"}
            </button>
            <button
              onClick={() => setRightTab("chat")}
              style={{ ...styles.tab, ...(rightTab === "chat" ? styles.tabActive : {}) }}
            >
              💬 CHAT
            </button>
          </div>
          {rightTab === "sensor" ? (
            <SectorPanel snapshot={snapshot} sectorId={selectedSector} />
          ) : (
            <ChatPanel />
          )}
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
    return <div style={styles.emptySector}>Click a grid cell to view sensor data</div>;
  }
  return <SensorPanel snapshot={snapshot} sectorId={sectorId} />;
}

const styles = {
  app: {
    display: "flex", flexDirection: "column", height: "100vh",
    background: "#0d1117", color: "#e6edf3",
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace", fontSize: 12,
  },
  topBar: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "8px 20px", background: "#161b22",
    borderBottom: "1px solid #30363d", minHeight: 52,
  },
  topLeft: { display: "flex", alignItems: "center", gap: 12 },
  logo: { fontSize: 18, fontWeight: 700, color: "#4caf50" },
  tagline: { color: "#8b949e", fontSize: 11 },
  replayBadge: {
    fontSize: 10, fontWeight: 700, color: "#b39ddb",
    background: "#7c4dff22", border: "1px solid #7c4dff44",
    padding: "2px 8px", borderRadius: 3, letterSpacing: 1,
  },
  topMetrics: { display: "flex", alignItems: "center", gap: 16 },
  metric: { textAlign: "center" },
  metricValue: { fontSize: 22, fontWeight: 700, lineHeight: 1 },
  metricLabel: { fontSize: 9, color: "#8b949e", marginTop: 2, letterSpacing: 1 },
  agentStatus: {
    display: "flex", alignItems: "center", gap: 8,
    padding: "4px 12px", background: "#21262d", borderRadius: 6,
  },
  statusDot: { width: 8, height: 8, borderRadius: "50%" },
  offlineBadge: { fontSize: 9, background: "#f44336", color: "#fff", padding: "1px 5px", borderRadius: 3 },
  replayToggle: {
    padding: "4px 10px", border: "none", borderRadius: 4,
    cursor: "pointer", fontSize: 11, fontWeight: 600, color: "#fff",
  },
  replayStrip: {
    background: "#161b22", borderBottom: "1px solid #30363d",
    padding: "10px 20px",
  },
  replayActionBadge: {
    marginLeft: 8, fontSize: 9, color: "#7c4dff",
    background: "#7c4dff22", padding: "1px 6px", borderRadius: 3,
  },
  main: {
    display: "flex", flex: 1, overflow: "hidden",
    gap: 1, padding: 1, background: "#30363d",
  },
  leftPanel: { display: "flex", flexDirection: "column", width: 340, background: "#161b22", padding: 12 },
  centerPanel: { display: "flex", flexDirection: "column", flex: 1, background: "#161b22", padding: 12, overflow: "hidden" },
  rightPanel: { display: "flex", flexDirection: "column", width: 280, background: "#161b22", padding: 12 },
  panelHeader: {
    fontSize: 10, fontWeight: 700, color: "#8b949e", letterSpacing: 2,
    marginBottom: 8, borderBottom: "1px solid #30363d", paddingBottom: 6,
    display: "flex", alignItems: "center", gap: 8,
  },
  gridLegend: { display: "flex", gap: 12, marginTop: 8, flexWrap: "wrap" },
  legendItem: { display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#8b949e" },
  legendColor: { width: 10, height: 10, borderRadius: 2 },
  emptySector: { color: "#8b949e", textAlign: "center", marginTop: 40, lineHeight: 1.6 },
  tabBar: {
    display: "flex", borderBottom: "1px solid #30363d", marginBottom: 8,
  },
  tab: {
    background: "none", border: "none", borderBottom: "2px solid transparent",
    color: "#8b949e", fontSize: 10, fontWeight: 700, padding: "4px 10px",
    cursor: "pointer", fontFamily: "inherit", letterSpacing: 1,
    marginBottom: -1,
  },
  tabActive: {
    color: "#e6edf3", borderBottomColor: "#4caf50",
  },
  alertPing: {
    position: "absolute", top: 0, right: -4,
    width: 8, height: 8, borderRadius: "50%",
    background: "#f44336", animation: "pulse 1.2s infinite",
  },
  alertOverlay: {
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
    zIndex: 900, display: "flex", alignItems: "flex-start",
    justifyContent: "flex-end", padding: 16, paddingTop: 60,
  },
  alertPanel: {
    background: "#161b22", border: "1px solid #f4433640",
    borderRadius: 8, padding: 16, width: 400, maxHeight: "70vh",
    overflowY: "auto", display: "flex", flexDirection: "column", gap: 8,
  },
  alertPanelHeader: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    fontSize: 11, fontWeight: 700, color: "#f44336", letterSpacing: 1,
    marginBottom: 4,
  },
  closeBtn: {
    background: "none", border: "none", color: "#8b949e",
    cursor: "pointer", fontSize: 14, fontFamily: "inherit",
  },
};
