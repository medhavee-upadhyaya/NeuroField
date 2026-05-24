import { useEffect, useState } from "react";

export function useAlertToasts() {
  const [toasts, setToasts] = useState([]);

  const addToast = (alert) => {
    const id = Date.now();
    setToasts((prev) => [...prev, { ...alert, id }].slice(-5));
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 7000);
  };

  return { toasts, addToast };
}

export function AlertToastContainer({ toasts }) {
  if (!toasts.length) return null;
  return (
    <div style={styles.container}>
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  );
}

function ToastItem({ toast }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => setVisible(true), 20);
    return () => clearTimeout(id);
  }, []);

  const triggerLabel = toast.trigger?.replace(/_/g, " ") || "alert";
  const channelBadge = toast.dispatched_via?.length
    ? toast.dispatched_via.join(" + ")
    : "dashboard only";

  return (
    <div style={{ ...styles.toast, opacity: visible ? 1 : 0, transform: visible ? "translateX(0)" : "translateX(20px)" }}>
      <div style={styles.toastHeader}>
        <span style={styles.toastIcon}>🚨</span>
        <span style={styles.toastLevel}>CRITICAL ALERT</span>
        <span style={styles.toastSector}>{toast.sector_id}</span>
      </div>
      <div style={styles.toastMessage}>{toast.message}</div>
      <div style={styles.toastFooter}>
        <span style={styles.toastTrigger}>{triggerLabel}</span>
        <span style={styles.toastChannel}>{channelBadge}</span>
      </div>
      <div style={styles.toastBar} />
    </div>
  );
}

export function AlertHistoryPanel({ alerts, onClose }) {
  if (!alerts.length) {
    return (
      <div style={styles.historyEmpty}>
        No alerts fired yet. Alerts trigger on confirmed critical actions,
        repeated treatment failures, and high-severity spreading anomalies.
      </div>
    );
  }

  return (
    <div style={styles.history}>
      {alerts.map((a, i) => {
        const ts = new Date((a.timestamp || 0) * 1000).toLocaleTimeString("en-US", { hour12: false });
        const triggerLabel = a.trigger?.replace(/_/g, " ") || "alert";
        const channelBadge = a.dispatched_via?.length ? a.dispatched_via.join(", ") : "dashboard only";
        return (
          <div key={i} style={styles.historyRow}>
            <div style={styles.historyHeader}>
              <span style={styles.historyTs}>{ts}</span>
              <span style={styles.historyTrigger}>{triggerLabel}</span>
              <span style={styles.historyChannel}>{channelBadge}</span>
              <span style={{ color: "#58a6ff", fontSize: 11 }}>{a.sector_id}</span>
            </div>
            <div style={styles.historyMsg}>{a.message}</div>
          </div>
        );
      })}
    </div>
  );
}

const styles = {
  container: {
    position: "fixed",
    top: 60,
    right: 16,
    zIndex: 1000,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    maxWidth: 340,
  },
  toast: {
    background: "#1a0505",
    border: "1px solid #f44336",
    borderRadius: 6,
    padding: "10px 12px",
    boxShadow: "0 4px 20px rgba(244,67,54,0.3)",
    transition: "all 0.25s ease",
    position: "relative",
    overflow: "hidden",
  },
  toastHeader: { display: "flex", alignItems: "center", gap: 6, marginBottom: 5 },
  toastIcon: { fontSize: 14 },
  toastLevel: { fontSize: 10, fontWeight: 700, color: "#f44336", letterSpacing: 1 },
  toastSector: {
    marginLeft: "auto", fontSize: 11, fontWeight: 700,
    color: "#fff", background: "#f4433620",
    border: "1px solid #f4433640", padding: "1px 6px", borderRadius: 3,
  },
  toastMessage: { fontSize: 11, color: "#e6edf3", lineHeight: 1.5, marginBottom: 6 },
  toastFooter: { display: "flex", justifyContent: "space-between" },
  toastTrigger: { fontSize: 9, color: "#8b949e", textTransform: "uppercase", letterSpacing: 1 },
  toastChannel: { fontSize: 9, color: "#58a6ff" },
  toastBar: {
    position: "absolute",
    bottom: 0,
    left: 0,
    height: 2,
    width: "100%",
    background: "linear-gradient(to right, #f44336, transparent)",
    animation: "shrink 7s linear forwards",
  },
  historyEmpty: { color: "#8b949e", fontSize: 11, lineHeight: 1.6, textAlign: "center", marginTop: 20 },
  history: { display: "flex", flexDirection: "column", gap: 8 },
  historyRow: {
    background: "#1a0505", border: "1px solid #f4433620",
    borderRadius: 4, padding: "6px 8px",
  },
  historyHeader: { display: "flex", alignItems: "center", gap: 8, marginBottom: 3 },
  historyTs: { fontSize: 9, color: "#8b949e" },
  historyTrigger: { fontSize: 9, color: "#ef9a9a", textTransform: "uppercase", letterSpacing: 1 },
  historyChannel: { fontSize: 9, color: "#58a6ff", marginLeft: "auto" },
  historyMsg: { fontSize: 11, color: "#c9d1d9", lineHeight: 1.4 },
};
