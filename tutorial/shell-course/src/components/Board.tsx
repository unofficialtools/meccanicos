import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO, SANS } from "../theme";
import { useStart } from "./Beats";
import { Gear } from "./Gear";
import { Markup } from "./Markup";

// A mechanics drawing on the stage (1920 x 770): boxes, arrows, gears,
// labels, a conveyor belt and parts moving along a path. Each element
// appears at `at` (fraction of the scene), or with narration segment `beat`
// (plus `delay` seconds).
type When = { at?: number; beat?: number; delay?: number };
export type El = When & (
  | { t: "box"; x: number; y: number; w: number; h: number; title?: string; body?: string | string[]; color?: string; at?: number; mono?: boolean; size?: number; fill?: string; align?: "left" | "center"; top?: boolean }
  | { t: "arrow"; from: [number, number]; to: [number, number]; label?: string; at?: number; color?: string; dashed?: boolean }
  | { t: "gear"; x: number; y: number; r: number; teeth?: number; speed?: number; color?: string; at?: number }
  | { t: "text"; x: number; y: number; text: string; size?: number; color?: string; at?: number; mono?: boolean; w?: number; align?: "left" | "center" }
  | { t: "belt"; x: number; y: number; w: number; at?: number }
  | { t: "part"; path: [number, number][]; label: string; at?: number; dur: number; color?: string });

const useAppear = (w: When) => {
  const f = useCurrentFrame();
  const t0 = useStart(w, 0);
  return { on: f >= t0, o: interpolate(f, [t0, t0 + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) };
};

const Box: React.FC<Extract<El, { t: "box" }>> = ({ x, y, w, h, title, body, color = C.amber, at, beat, delay, mono, size = 28, fill = C.base, align = "center", top }) => {
  const { o } = useAppear({ at, beat, delay });
  const lines = body === undefined ? [] : Array.isArray(body) ? body : [body];
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, opacity: o, transform: `scale(${0.94 + 0.06 * o})`,
      background: fill, border: `2px solid ${C.line}`, borderTop: `5px solid ${color}`, borderRadius: 8, padding: "12px 18px",
      display: "flex", flexDirection: "column", justifyContent: top ? "flex-start" : "center", alignItems: align === "center" ? "center" : "flex-start", textAlign: align, gap: 6 }}>
      {title ? <div style={{ fontFamily: MONO, fontSize: size, fontWeight: 700, color }}>{title}</div> : null}
      {lines.map((l, i) => (
        <div key={i} style={{ fontFamily: mono ? MONO : SANS, fontSize: size * 0.78, color: C.text, lineHeight: 1.3, whiteSpace: mono ? "pre" : "normal" }}><Markup text={l} /></div>
      ))}
    </div>
  );
};

const Text: React.FC<Extract<El, { t: "text" }>> = ({ x, y, text, size = 30, color = C.text, at, beat, delay, mono, w, align = "left" }) => {
  const { o } = useAppear({ at, beat, delay });
  return (
    <div style={{ position: "absolute", left: align === "center" ? x - (w ?? 800) / 2 : x, top: y, width: w ?? (align === "center" ? 800 : undefined), opacity: o,
      fontFamily: mono ? MONO : SANS, fontSize: size, color, textAlign: align, whiteSpace: mono ? "pre" : "pre-line", lineHeight: 1.3 }}>
      <Markup text={text} />
    </div>
  );
};

const Arrow: React.FC<Extract<El, { t: "arrow" }>> = ({ from, to, label, at, beat, delay, color = C.dim, dashed }) => {
  const { o, on } = useAppear({ at, beat, delay });
  if (!on) return null;
  const [x1, y1] = from, [x2, y2] = to;
  const len = Math.hypot(x2 - x1, y2 - y1);
  const ex = x1 + (x2 - x1) * o, ey = y1 + (y2 - y1) * o;
  const a = Math.atan2(y2 - y1, x2 - x1);
  const head = (s: number) => `${ex},${ey} ${ex - s * Math.cos(a - 0.45)},${ey - s * Math.sin(a - 0.45)} ${ex - s * Math.cos(a + 0.45)},${ey - s * Math.sin(a + 0.45)}`;
  return (
    <g>
      <line x1={x1} y1={y1} x2={ex} y2={ey} stroke={color} strokeWidth={4} strokeDasharray={dashed ? "12 10" : undefined} />
      {len > 0 ? <polygon points={head(18)} fill={color} /> : null}
      {label ? <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 14} fill={C.dim} fontSize={24} fontFamily={MONO} textAnchor="middle" opacity={o}>{label}</text> : null}
    </g>
  );
};

const Belt: React.FC<Extract<El, { t: "belt" }>> = ({ x, y, w, at, beat, delay }) => {
  const f = useCurrentFrame();
  const { o } = useAppear({ at, beat, delay });
  const off = (f * 3) % 40;
  return (
    <g opacity={o}>
      <rect x={x} y={y} width={w} height={26} rx={13} fill={C.raised} stroke={C.line} strokeWidth={2} />
      {Array.from({ length: Math.floor(w / 40) }, (_, i) => (
        <line key={i} x1={x + 10 + ((i * 40 + off) % (w - 20))} y1={y + 5} x2={x + 10 + ((i * 40 + off) % (w - 20))} y2={y + 21} stroke={C.line} strokeWidth={3} />
      ))}
      <circle cx={x + 13} cy={y + 13} r={11} fill={C.line} />
      <circle cx={x + w - 13} cy={y + 13} r={11} fill={C.line} />
    </g>
  );
};

const Part: React.FC<Extract<El, { t: "part" }>> = ({ path, label, at, beat, delay, dur, color = C.amber }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t0 = useStart({ at, beat, delay }, 0);
  const p = (f - t0) / (dur * fps); // dur: seconds
  if (p < 0 || p > 1) return null;
  const seg = (path.length - 1) * p;
  const i = Math.min(path.length - 2, Math.floor(seg));
  const u = seg - i;
  const x = path[i][0] + (path[i + 1][0] - path[i][0]) * u;
  const y = path[i][1] + (path[i + 1][1] - path[i][1]) * u;
  const w = Math.max(70, label.length * 15 + 24);
  return (
    <g transform={`translate(${x - w / 2} ${y - 22})`}>
      <rect width={w} height={44} rx={6} fill={color} />
      <text x={w / 2} y={30} textAnchor="middle" fontFamily={MONO} fontSize={22} fill={C.ink} fontWeight={700}>{label}</text>
    </g>
  );
};

const GearEl: React.FC<Extract<El, { t: "gear" }>> = ({ at, beat, delay, ...g }) => {
  const { o } = useAppear({ at, beat, delay });
  return <Gear {...g} opacity={o} />;
};

export const Board: React.FC<{ els: El[] }> = ({ els }) => (
  <div style={{ position: "absolute", inset: 0 }}>
    <svg width={1920} height={770} style={{ position: "absolute", inset: 0 }}>
      {els.map((e, i) => (e.t === "gear" ? <GearEl key={i} {...e} /> : e.t === "belt" ? <Belt key={i} {...e} /> : null))}
      {els.map((e, i) => (e.t === "arrow" ? <Arrow key={i} {...e} /> : null))}
    </svg>
    {els.map((e, i) => (e.t === "box" ? <Box key={i} {...e} /> : e.t === "text" ? <Text key={i} {...e} /> : null))}
    <svg width={1920} height={770} style={{ position: "absolute", inset: 0 }}>
      {els.map((e, i) => (e.t === "part" ? <Part key={i} {...e} /> : null))}
    </svg>
  </div>
);
