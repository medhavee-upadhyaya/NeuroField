import { useState, useEffect, useRef, useCallback } from "react";

const API_URL = "http://localhost:8000";
const PLAYBACK_SPEEDS = [1, 2, 5, 10];

function formatTime(ts) {
  if (!ts) return "--:--:--";
  return new Date(ts * 1000).toLocaleTimeString("en-US", { hour12: false });
}

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s}s`;
}

export default function ReplayPanel({ onReplaySnapshot, onExitReplay, isReplayMode }) {
  const [bounds, setBounds] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [currentTs, setCurrentTs] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [loading, setLoading] = useState(false);
  const playRef = useRef(null);
  const timelineIdxRef = useRef(0);

  const fetchBoundsAndTimeline = useCallback(async () => {
    try {
      const [boundsRes, tlRes] = await Promise.all([
        fetch(`${API_URL}/replay/bounds`),
        fetch(`${API_URL}/replay/timeline`),
      ]);
      const b = await boundsRes.json();
      const tl = await tlRes.json();
      setBounds(b);
      setTimeline(tl.timeline || []);
      if (!currentTs && b.min_ts) setCurrentTs(b.min_ts);
    } catch {}
  }, [currentTs]);

  useEffect(() => {
    fetchBoundsAndTimeline();
    const id = setInterval(fetchBoundsAndTimeline, 15000);
    return () => clearInterval(id);
  }, [fetchBoundsAndTimeline]);

  // Load snapshot at currentTs
  const loadSnapshot = useCallback(async (ts) => {
    if (!ts) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_URL}/replay/snapshot?ts=${ts}`);
      if (!r.ok) return;
      const snap = await r.json();
      onReplaySnapshot(snap);
    } catch {}
    setLoading(false);
  }, [onReplaySnapshot]);

  useEffect(() => {
    if (isReplayMode && currentTs) loadSnapshot(currentTs);
  }, [currentTs, isReplayMode, loadSnapshot]);

  // Playback loop
  useEffect(() => {
    if (!playing || !timeline.length) return;
    const idx = timeline.findIndex((t) => t.timestamp >= currentTs);
    timelineIdxRef.current = idx < 0 ? 0 : idx;

    playRef.current = setInterval(() => {
      timelineIdxRef.current += 1;
      if (timelineIdxRef.current >= timeline.length) {
        setPlaying(false);
        return;
      }
      setCurrentTs(timeline[timelineIdxRef.current].timestamp);
    }, 2000 / speed);

    return () => clearInterval(playRef.current);
  }, [playing, speed, timeline]);

  const handleSlider = (e) => {
    setPlaying(false);
    const pct = parseFloat(e.target.value) / 1000;
    if (!bounds) return;
    const ts = bounds.min_ts + pct * (bounds.max_ts - bounds.min_ts);
    setCurrentTs(ts);
  };

  const sliderValue = bounds
    ? Math.round(((currentTs - bounds.min_ts) / Math.max(bounds.max_ts - bounds.min_ts, 1)) * 1000)
    : 0;

  const duration = bounds ? bounds.max_ts - bounds.min_ts : 0;

  if (!bounds || bounds.total === 0) {
    return (
      <div style={styles.empty}>
        No replay data yet.<br />
        Snapshots are logged every 10s once the simulation starts.
      </div>
    );
  }

  return (
    <div style={styles.panel}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.title}>TIME-LAPSE REPLAY</span>
        <span style={styles.meta}>{bounds.total} snapshots · {formatDuration(duration)}</span>
      </div>

      {/* Timeline bar */}
      <TimelineBar timeline={timeline} bounds={bounds} currentTs={currentTs} />

      {/* Scrubber */}
      <div style={styles.scrubberWrap}>
        <span style={styles.timeLabel}>{formatTime(bounds.min_ts)}</span>
        <input
          type="range"
          min={0}
          max={1000}
          value={sliderValue}
          onChange={handleSlider}
          style={styles.slider}
        />
        <span style={styles.timeLabel}>{formatTime(bounds.max_ts)}</span>
      </div>

      {/* Current time */}
      <div style={styles.currentTime}>
        {loading ? "Loading…" : `▶ ${formatTime(currentTs)}`}
      </div>

      {/* Controls */}
      <div style={styles.controls}>
        <button
          onClick={() => setPlaying((p) => !p)}
          style={{ ...styles.btn, background: playing ? "#f44336" : "#4caf50" }}
        >
          {playing ? "⏸ Pause" : "▶ Play"}
        </button>

        <div style={styles.speedGroup}>
          {PLAYBACK_SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              style={{ ...styles.speedBtn, background: speed === s ? "#30363d" : "transparent", color: speed === s ? "#fff" : "#8b949e" }}
            >
              {s}×
            </button>
          ))}
        </div>

        {isReplayMode ? (
          <button onClick={onExitReplay} style={{ ...styles.btn, background: "#1565c0" }}>
            ⚡ Live
          </button>
        ) : (
          <button
            onClick={() => { onReplaySnapshot(null); loadSnapshot(currentTs); }}
            style={{ ...styles.btn, background: "#7c4dff" }}
          >
            Enter Replay
          </button>
        )}
      </div>
    </div>
  );
}

function TimelineBar({ timeline, bounds, currentTs }) {
  if (!timeline.length || !bounds) return null;
  const range = Math.max(bounds.max_ts - bounds.min_ts, 1);

  return (
    <div style={styles.timelineBar}>
      {timeline.map((t, i) => {
        const pct = ((t.timestamp - bounds.min_ts) / range) * 100;
        const isCurrent = Math.abs(t.timestamp - currentTs) < 5;
        let color = "#2d3748";
        if (t.critical_count > 0) color = "#c62828";
        else if (t.anomaly_count > 0) color = "#f9a825";
        else if (t.has_action) color = "#1565c0";
        return (
          <div
            key={i}
            style={{
              ...styles.timelineTick,
              left: `${pct}%`,
              background: color,
              height: isCurrent ? 16 : t.critical_count > 0 ? 12 : 8,
              width: isCurrent ? 3 : 2,
              opacity: isCurrent ? 1 : 0.7,
            }}
          />
        );
      })}
      {/* cursor */}
      {currentTs && (
        <div style={{
          ...styles.cursor,
          left: `${((currentTs - bounds.min_ts) / range) * 100}%`,
        }} />
      )}
    </div>
  );
}

const styles = {
  panel: { display: "flex", flexDirection: "column", gap: 8 },
  empty: { color: "#8b949e", fontSize: 11, lineHeight: 1.6, textAlign: "center", marginTop: 20 },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  title: { fontSize: 10, fontWeight: 700, color: "#8b949e", letterSpacing: 2 },
  meta: { fontSize: 10, color: "#58a6ff" },
  timelineBar: {
    position: "relative",
    height: 20,
    background: "#21262d",
    borderRadius: 3,
    overflow: "hidden",
  },
  timelineTick: {
    position: "absolute",
    bottom: 0,
    borderRadius: "1px 1px 0 0",
    transition: "height 0.1s",
  },
  cursor: {
    position: "absolute",
    top: 0,
    bottom: 0,
    width: 2,
    background: "#fff",
    opacity: 0.9,
    pointerEvents: "none",
  },
  scrubberWrap: { display: "flex", alignItems: "center", gap: 6 },
  timeLabel: { fontSize: 9, color: "#8b949e", whiteSpace: "nowrap" },
  slider: { flex: 1, accentColor: "#58a6ff", cursor: "pointer" },
  currentTime: { fontSize: 11, color: "#58a6ff", textAlign: "center", letterSpacing: 1 },
  controls: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  btn: {
    padding: "4px 10px",
    borderRadius: 4,
    border: "none",
    cursor: "pointer",
    fontSize: 11,
    fontWeight: 600,
    color: "#fff",
  },
  speedGroup: { display: "flex", border: "1px solid #30363d", borderRadius: 4, overflow: "hidden" },
  speedBtn: {
    padding: "4px 8px",
    border: "none",
    cursor: "pointer",
    fontSize: 10,
    fontFamily: "inherit",
  },
};
