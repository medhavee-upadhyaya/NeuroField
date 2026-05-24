import { useRef, useEffect, useCallback } from "react";

// ── Isometric constants ────────────────────────────────────────────────────
const ROWS = 10;
const COLS = 10;
const TW = 32;          // tile diamond full width
const TH = 16;          // tile diamond height (TW/2)
const MAX_BOX_H = 22;   // max pillar height for healthy crop
const CANVAS_W = 520;
const CANVAS_H = 380;
const ORIGIN_X = CANVAS_W / 2;
const ORIGIN_Y = 80;

// ── Coordinate transform ───────────────────────────────────────────────────
function toScreen(col, row) {
  return {
    x: ORIGIN_X + (col - row) * (TW / 2),
    y: ORIGIN_Y + (col + row) * (TH / 2),
  };
}

// ── Color helpers ──────────────────────────────────────────────────────────
function lerpColor(a, b, t) {
  const ah = parseInt(a.slice(1), 16);
  const bh = parseInt(b.slice(1), 16);
  const ar = (ah >> 16) & 0xff, ag = (ah >> 8) & 0xff, ab = ah & 0xff;
  const br = (bh >> 16) & 0xff, bg = (bh >> 8) & 0xff, bb = bh & 0xff;
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bv = Math.round(ab + (bb - ab) * t);
  return `#${((r << 16) | (g << 8) | bv).toString(16).padStart(6, "0")}`;
}

function healthToColor(health, moisture) {
  if (health < 0.3) return "#c62828";
  if (health < 0.5) return "#e65100";
  if (health < 0.65) return "#f9a825";
  if (moisture < 0.25) return "#f57f17";
  return "#388e3c";
}

function shade(hex, factor) {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.round(((n >> 16) & 0xff) * factor);
  const g = Math.round(((n >> 8) & 0xff) * factor);
  const b = Math.round((n & 0xff) * factor);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

// ── Draw a single isometric box ────────────────────────────────────────────
function drawBox(ctx, col, row, boxH, topColor, selected, hasAnomaly, failed) {
  const { x, y } = toScreen(col, row);
  const hw = TW / 2;
  const hh = TH / 2;

  const leftColor = shade(topColor, 0.58);
  const rightColor = shade(topColor, 0.42);

  // right face
  ctx.beginPath();
  ctx.moveTo(x + hw, y - boxH);
  ctx.lineTo(x + TW, y + hh - boxH);
  ctx.lineTo(x + TW, y + hh);
  ctx.lineTo(x + hw, y);
  ctx.closePath();
  ctx.fillStyle = rightColor;
  ctx.fill();

  // left face
  ctx.beginPath();
  ctx.moveTo(x - hw, y - boxH);
  ctx.lineTo(x, y - TH - boxH);
  ctx.lineTo(x + hw, y - boxH);
  ctx.lineTo(x + hw, y);
  ctx.lineTo(x, y + hh);
  ctx.lineTo(x - hw, y);
  ctx.closePath();
  // left face = top diamond + left rect — draw separately
  ctx.beginPath();
  ctx.moveTo(x - hw, y - boxH);
  ctx.lineTo(x, y - TH - boxH);
  ctx.lineTo(x, y - TH);
  ctx.lineTo(x - hw, y);
  ctx.closePath();
  ctx.fillStyle = leftColor;
  ctx.fill();

  // top face (diamond)
  ctx.beginPath();
  ctx.moveTo(x, y - TH - boxH);
  ctx.lineTo(x + hw, y - boxH);
  ctx.lineTo(x, y - boxH);  // center
  ctx.lineTo(x - hw, y - boxH);
  ctx.closePath();
  // actual diamond top
  ctx.beginPath();
  ctx.moveTo(x, y - TH - boxH);
  ctx.lineTo(x + hw, y - boxH);
  ctx.lineTo(x, y + hh - boxH);
  ctx.lineTo(x - hw, y - boxH);
  ctx.closePath();
  ctx.fillStyle = topColor;
  ctx.fill();

  // selection / failure outline on top
  if (selected || hasAnomaly || failed) {
    ctx.beginPath();
    ctx.moveTo(x, y - TH - boxH);
    ctx.lineTo(x + hw, y - boxH);
    ctx.lineTo(x, y + hh - boxH);
    ctx.lineTo(x - hw, y - boxH);
    ctx.closePath();
    ctx.strokeStyle = selected ? "#ffffff" : failed ? "#ff5722" : "#ff9800";
    ctx.lineWidth = selected ? 2 : 1.5;
    ctx.stroke();
  }
}

// ── Draw the robot ─────────────────────────────────────────────────────────
function drawRobot(ctx, col, row, t) {
  const { x, y } = toScreen(col, row);
  const hw = TW / 2 * 0.65;
  const hh = TH / 2 * 0.65;
  const robotH = 20 + Math.sin(t * 0.003) * 3;  // gentle bob

  // shadow on ground
  ctx.beginPath();
  ctx.ellipse(x, y + hh * 0.3, hw * 0.8, hh * 0.5, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.3)";
  ctx.fill();

  // body — glowing blue box
  const grd = ctx.createLinearGradient(x - hw, 0, x + hw, 0);
  grd.addColorStop(0, "#1565c0");
  grd.addColorStop(0.5, "#42a5f5");
  grd.addColorStop(1, "#1565c0");

  // right face
  ctx.beginPath();
  ctx.moveTo(x + hw, y - robotH);
  ctx.lineTo(x + TW * 0.65, y + hh - robotH);
  ctx.lineTo(x + TW * 0.65, y + hh);
  ctx.lineTo(x + hw, y);
  ctx.closePath();
  ctx.fillStyle = "#0d47a1";
  ctx.fill();

  // left face
  ctx.beginPath();
  ctx.moveTo(x - hw, y - robotH);
  ctx.lineTo(x, y - TH * 0.65 - robotH);
  ctx.lineTo(x, y - TH * 0.65);
  ctx.lineTo(x - hw, y);
  ctx.closePath();
  ctx.fillStyle = "#1565c0";
  ctx.fill();

  // top
  ctx.beginPath();
  ctx.moveTo(x, y - TH * 0.65 - robotH);
  ctx.lineTo(x + hw, y - robotH);
  ctx.lineTo(x, y + hh * 0.65 - robotH);
  ctx.lineTo(x - hw, y - robotH);
  ctx.closePath();
  ctx.fillStyle = grd;
  ctx.fill();

  // glow ring
  const glow = ctx.createRadialGradient(x, y - robotH, 0, x, y - robotH, 18);
  glow.addColorStop(0, "rgba(66,165,245,0.4)");
  glow.addColorStop(1, "rgba(66,165,245,0)");
  ctx.beginPath();
  ctx.arc(x, y - robotH, 18, 0, Math.PI * 2);
  ctx.fillStyle = glow;
  ctx.fill();
}

// ── Main component ────────────────────────────────────────────────────────
export default function FarmScene3D({ snapshot, robot, selectedSector, failedSectors = {} }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const tRef = useRef(0);
  const robotPosRef = useRef({ col: 0, row: 0 });
  const robotTargetRef = useRef({ col: 0, row: 0 });

  // parse robot sector to grid col/row
  useEffect(() => {
    if (!robot?.sector) return;
    const sector = robot.sector;
    const rowIdx = "ABCDEFGHIJ".indexOf(sector[0]);
    const colIdx = parseInt(sector.slice(1)) - 1;
    if (rowIdx >= 0 && colIdx >= 0) {
      robotTargetRef.current = { col: colIdx, row: rowIdx };
    }
  }, [robot?.sector]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    tRef.current += 16;
    const t = tRef.current;

    // smooth robot movement
    const rp = robotPosRef.current;
    const rt = robotTargetRef.current;
    rp.col += (rt.col - rp.col) * 0.08;
    rp.row += (rt.row - rp.row) * 0.08;

    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

    // background gradient
    const bg = ctx.createLinearGradient(0, 0, 0, CANVAS_H);
    bg.addColorStop(0, "#0d1117");
    bg.addColorStop(1, "#161b22");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

    const sectors = snapshot?.sectors || {};

    // draw grid back-to-front (painter's algorithm: col+row ascending)
    for (let sum = 0; sum <= (ROWS - 1) + (COLS - 1); sum++) {
      for (let row = Math.max(0, sum - (COLS - 1)); row <= Math.min(ROWS - 1, sum); row++) {
        const col = sum - row;
        if (col < 0 || col >= COLS) continue;

        const rowLetter = "ABCDEFGHIJ"[row];
        const sid = `${rowLetter}${col + 1}`;
        const s = sectors[sid];
        const health = s?.crop_health ?? 0.85;
        const moisture = s?.soil_moisture ?? 0.6;
        const topColor = healthToColor(health, moisture);
        const boxH = Math.max(4, health * MAX_BOX_H);
        const isSelected = selectedSector === sid;
        const hasAnomaly = (s?.anomalies?.length ?? 0) > 0;
        const hasFailed = sid in failedSectors;

        drawBox(ctx, col, row, boxH, topColor, isSelected, hasAnomaly, hasFailed);
      }
    }

    // draw robot on top
    drawRobot(ctx, rp.col, rp.row, t);

    // sector label for selected
    if (selectedSector && sectors[selectedSector]) {
      const rowIdx = "ABCDEFGHIJ".indexOf(selectedSector[0]);
      const colIdx = parseInt(selectedSector.slice(1)) - 1;
      const { x, y } = toScreen(colIdx, rowIdx);
      const s = sectors[selectedSector];
      ctx.font = "bold 10px 'Courier New', monospace";
      ctx.textAlign = "center";
      ctx.fillStyle = "#fff";
      ctx.fillText(selectedSector, x, y - MAX_BOX_H - 8);
      ctx.font = "9px 'Courier New', monospace";
      ctx.fillStyle = "#8b949e";
      ctx.fillText(`h=${s.crop_health?.toFixed(2)} m=${s.soil_moisture?.toFixed(2)}`, x, y - MAX_BOX_H + 3);
    }

    // legend
    const legend = [
      { color: "#388e3c", label: "Healthy" },
      { color: "#f9a825", label: "Warning" },
      { color: "#c62828", label: "Critical" },
    ];
    legend.forEach(({ color, label }, i) => {
      ctx.fillStyle = color;
      ctx.fillRect(10, CANVAS_H - 60 + i * 16, 10, 10);
      ctx.fillStyle = "#8b949e";
      ctx.font = "9px 'Courier New', monospace";
      ctx.textAlign = "left";
      ctx.fillText(label, 24, CANVAS_H - 51 + i * 16);
    });

    // robot label
    ctx.fillStyle = "#42a5f5";
    ctx.fillRect(10, CANVAS_H - 12, 10, 10);
    ctx.fillStyle = "#8b949e";
    ctx.fillText("Robot", 24, CANVAS_H - 3);

    animRef.current = requestAnimationFrame(draw);
  }, [snapshot, selectedSector, failedSectors]);

  useEffect(() => {
    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [draw]);

  return (
    <canvas
      ref={canvasRef}
      width={CANVAS_W}
      height={CANVAS_H}
      style={{ width: "100%", borderRadius: 4, display: "block" }}
    />
  );
}
