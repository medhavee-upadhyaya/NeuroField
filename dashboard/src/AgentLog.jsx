import { useRef, useEffect } from "react";

const ALERT_COLORS = {
  critical: "#f44336",
  high: "#ff5722",
  medium: "#ff9800",
  low: "#4caf50",
};

const ACTION_ICONS = {
  irrigate: "💧",
  spray: "🌿",
  fertilize: "🌱",
  navigate: "🤖",
  report: "📋",
  wait: "⏳",
};

function timestamp(ts) {
  if (!ts) return "--:--:--";
  return new Date(ts * 1000).toLocaleTimeString("en-US", { hour12: false });
}

function ConfidenceBar({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 70 ? "#4caf50" : pct >= 40 ? "#ff9800" : "#f44336";
  return (
    <div style={styles.confBarWrap}>
      <div style={{ ...styles.confBar, width: `${pct}%`, background: color }} />
      <span style={{ color, minWidth: 30 }}>{pct}%</span>
    </div>
  );
}

function SupervisorCard({ decision }) {
  const queue = decision.priority_queue || [];
  return (
    <div style={{ ...styles.card, borderLeft: "3px solid #7c4dff", background: "#1a1040" }}>
      <div style={styles.cardHeader}>
        <div style={styles.cardLeft}>
          <span style={styles.ts}>{timestamp(decision.timestamp)}</span>
          <span style={{ ...styles.agentBadge, background: "#7c4dff22", color: "#b39ddb", border: "1px solid #7c4dff44" }}>
            SUPERVISOR
          </span>
        </div>
        <span style={{ color: "#8b949e", fontSize: 10 }}>{queue.length} tasks queued</span>
      </div>

      {decision.farm_summary && (
        <div style={styles.field}>
          <span style={styles.label}>FARM</span>
          <span style={styles.value}>{decision.farm_summary}</span>
        </div>
      )}

      {queue.length > 0 && (
        <div style={{ marginTop: 4 }}>
          <div style={{ ...styles.label, marginBottom: 4 }}>QUEUE</div>
          {queue.map((task, i) => {
            const urgencyColor = ALERT_COLORS[task.urgency] || "#9e9e9e";
            const icon = ACTION_ICONS[task.action] || "❓";
            return (
              <div key={i} style={styles.queueItem}>
                <span style={{ color: "#8b949e", minWidth: 14 }}>{i + 1}.</span>
                <span style={{ color: urgencyColor, minWidth: 12 }}>{icon}</span>
                <span style={{ color: "#58a6ff", minWidth: 32 }}>{task.sector}</span>
                <span style={{ color: "#e6edf3", flex: 1 }}>{task.action}</span>
                <span style={{ ...styles.urgencyTag, color: urgencyColor, border: `1px solid ${urgencyColor}44`, background: urgencyColor + "15" }}>
                  {task.urgency}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WorkerCard({ decision }) {
  const alertColor = ALERT_COLORS[decision.alert_level] || "#9e9e9e";
  const icon = ACTION_ICONS[decision.action] || "❓";
  const confirmed = decision.confirmed;

  return (
    <div style={{
      ...styles.card,
      borderLeft: `3px solid ${confirmed ? alertColor : "#616161"}`,
      background: confirmed ? "#0d1117" : "#1a0a0a",
      opacity: confirmed ? 1 : 0.75,
    }}>
      <div style={styles.cardHeader}>
        <div style={styles.cardLeft}>
          <span style={styles.ts}>{timestamp(decision.timestamp)}</span>
          <span style={{ ...styles.agentBadge, background: "#00838f22", color: "#80cbc4", border: "1px solid #00838f44" }}>
            WORKER
          </span>
          <span style={{
            ...styles.confirmBadge,
            background: confirmed ? "#1b5e2022" : "#b71c1c22",
            color: confirmed ? "#81c784" : "#ef9a9a",
            border: `1px solid ${confirmed ? "#1b5e2044" : "#b71c1c44"}`,
          }}>
            {confirmed ? "CONFIRMED" : "REJECTED"}
          </span>
        </div>
        <div style={styles.actionTag}>
          <span>{icon}</span>
          <span style={{ color: confirmed ? "#e6edf3" : "#616161" }}>
            {decision.action?.toUpperCase()}
          </span>
          {decision.target_sector && (
            <span style={{ ...styles.sectorTag, opacity: confirmed ? 1 : 0.5 }}>
              {decision.target_sector}
            </span>
          )}
        </div>
      </div>

      <div style={styles.field}>
        <span style={styles.label}>CONF</span>
        <ConfidenceBar value={decision.confidence} />
      </div>

      {decision.diagnosis && (
        <details style={styles.details}>
          <summary style={styles.detailsSummary}>Reasoning</summary>
          <div style={styles.reasoning}>{decision.diagnosis || decision.reasoning}</div>
        </details>
      )}
    </div>
  );
}

export default function AgentLog({ decisions }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [decisions.length]);

  if (!decisions.length) {
    return <div style={styles.empty}>Waiting for agent decisions…</div>;
  }

  return (
    <div style={styles.log}>
      {[...decisions].map((d, i) =>
        d.agent === "supervisor"
          ? <SupervisorCard key={i} decision={d} />
          : <WorkerCard key={i} decision={d} />
      )}
      <div ref={bottomRef} />
    </div>
  );
}

const styles = {
  log: { display: "flex", flexDirection: "column", gap: 6, overflowY: "auto", flex: 1 },
  empty: { color: "#8b949e", textAlign: "center", marginTop: 40 },
  card: { borderRadius: 6, padding: "8px 10px", display: "flex", flexDirection: "column", gap: 4 },
  cardHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 },
  cardLeft: { display: "flex", alignItems: "center", gap: 6 },
  ts: { color: "#8b949e", fontSize: 10 },
  agentBadge: { fontSize: 9, padding: "1px 6px", borderRadius: 3, fontWeight: 700, letterSpacing: 1 },
  confirmBadge: { fontSize: 9, padding: "1px 6px", borderRadius: 3, fontWeight: 700, letterSpacing: 1 },
  actionTag: { display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 600 },
  sectorTag: { background: "#30363d", padding: "1px 6px", borderRadius: 3, color: "#58a6ff" },
  urgencyTag: { fontSize: 9, padding: "1px 5px", borderRadius: 3, fontWeight: 700 },
  field: { display: "flex", gap: 8, alignItems: "center" },
  label: { fontSize: 9, color: "#8b949e", fontWeight: 700, minWidth: 28, letterSpacing: 1 },
  value: { color: "#c9d1d9", fontSize: 11, lineHeight: 1.4, flex: 1 },
  confBarWrap: { display: "flex", alignItems: "center", gap: 6, flex: 1, height: 12 },
  confBar: { height: "100%", borderRadius: 2, transition: "width 0.3s ease", minWidth: 2 },
  queueItem: { display: "flex", alignItems: "center", gap: 6, padding: "2px 0", fontSize: 11 },
  details: { marginTop: 2 },
  detailsSummary: { color: "#58a6ff", fontSize: 10, cursor: "pointer" },
  reasoning: { color: "#8b949e", fontSize: 10, lineHeight: 1.5, marginTop: 4, whiteSpace: "pre-wrap" },
};
