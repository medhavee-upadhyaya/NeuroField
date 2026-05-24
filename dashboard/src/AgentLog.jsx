import { useRef, useEffect } from "react";

const ALERT_COLORS = {
  critical: "#f44336",
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
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("en-US", { hour12: false });
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

export default function AgentLog({ decisions }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [decisions.length]);

  if (!decisions.length) {
    return (
      <div style={styles.empty}>
        Waiting for agent decisions...
      </div>
    );
  }

  return (
    <div style={styles.log}>
      {[...decisions].reverse().map((d, i) => (
        <DecisionCard key={i} decision={d} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function DecisionCard({ decision }) {
  const alertColor = ALERT_COLORS[decision.alert_level] || "#9e9e9e";
  const icon = ACTION_ICONS[decision.action] || "❓";
  const isActionable = !["report", "wait"].includes(decision.action);

  return (
    <div style={{ ...styles.card, borderLeft: `3px solid ${alertColor}` }}>
      <div style={styles.cardHeader}>
        <div style={styles.cardLeft}>
          <span style={styles.ts}>{timestamp(decision.timestamp)}</span>
          <span
            style={{
              ...styles.alertBadge,
              background: alertColor + "22",
              color: alertColor,
              border: `1px solid ${alertColor}44`,
            }}
          >
            {decision.alert_level?.toUpperCase()}
          </span>
        </div>
        <div style={styles.actionTag}>
          <span>{icon}</span>
          <span style={{ color: isActionable ? "#e6edf3" : "#8b949e" }}>
            {decision.action?.toUpperCase()}
          </span>
          {decision.target_sector && (
            <span style={styles.sectorTag}>{decision.target_sector}</span>
          )}
        </div>
      </div>

      <div style={styles.field}>
        <span style={styles.label}>OBS</span>
        <span style={styles.value}>{decision.observation}</span>
      </div>
      <div style={styles.field}>
        <span style={styles.label}>DX</span>
        <span style={styles.value}>{decision.diagnosis}</span>
      </div>
      <div style={styles.field}>
        <span style={styles.label}>CONF</span>
        <ConfidenceBar value={decision.confidence} />
      </div>
      {decision.reasoning && (
        <details style={styles.details}>
          <summary style={styles.detailsSummary}>Full reasoning</summary>
          <div style={styles.reasoning}>{decision.reasoning}</div>
        </details>
      )}
    </div>
  );
}

const styles = {
  log: { display: "flex", flexDirection: "column-reverse", gap: 8, overflowY: "auto", flex: 1 },
  empty: { color: "#8b949e", textAlign: "center", marginTop: 40 },
  card: {
    background: "#21262d",
    borderRadius: 6,
    padding: "8px 10px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  cardHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 },
  cardLeft: { display: "flex", alignItems: "center", gap: 8 },
  ts: { color: "#8b949e", fontSize: 10 },
  alertBadge: { fontSize: 9, padding: "1px 6px", borderRadius: 3, fontWeight: 700 },
  actionTag: { display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 600 },
  sectorTag: { background: "#30363d", padding: "1px 6px", borderRadius: 3, color: "#58a6ff" },
  field: { display: "flex", gap: 8, alignItems: "flex-start" },
  label: { fontSize: 9, color: "#8b949e", fontWeight: 700, minWidth: 28, marginTop: 1, letterSpacing: 1 },
  value: { color: "#c9d1d9", fontSize: 11, lineHeight: 1.4, flex: 1 },
  confBarWrap: { display: "flex", alignItems: "center", gap: 6, flex: 1, height: 12 },
  confBar: { height: "100%", borderRadius: 2, transition: "width 0.3s ease", minWidth: 2 },
  details: { marginTop: 2 },
  detailsSummary: { color: "#58a6ff", fontSize: 10, cursor: "pointer" },
  reasoning: { color: "#8b949e", fontSize: 10, lineHeight: 1.5, marginTop: 4, whiteSpace: "pre-wrap" },
};
