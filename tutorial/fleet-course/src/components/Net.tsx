import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO, SANS } from "../theme";
import { useBeats } from "./Beats";
import { Logo, LogoName, Machine } from "./Icons";

const LockGlyph = () => (
  <svg width={16} height={18} viewBox="0 0 16 18" style={{ marginRight: 4 }}><path d="M4 8V5a4 4 0 0 1 8 0v3" stroke={C.sand} strokeWidth={2.4} fill="none" /><rect x={1} y={8} width={14} height={10} rx={2} fill={C.sand} /></svg>
);

// The organization's network, on the stage (1920 x 770), in plain words: the
// company, the server hq with what it holds (one SSH account, the repository,
// the builds, two SQLite databases, Tang), the admin's computer, up to three computers on
// the office network, the Internet. Things appear, light up and
// send packets (labelled pills) along the wires, in step with the narration.
type When = { beat?: number; delay?: number; at?: number };
export type NodeId = "admin" | "hq" | "ssh" | "git" | "build" | "state" | "secrets" | "tang" | "ws1" | "ws2" | "ws3" | "net";
export type Flow = When & { from: NodeId; to: NodeId; label: string; dur?: number; color?: string; repeat?: number; every?: number };
export type Tag = When & { id: NodeId; text: string; color?: string; for?: number };
export type NetProps = {
  show?: NodeId[]; // there from the start (hq always is, unless in `add`)
  add?: (When & { id: NodeId })[]; // appear later ("hq": the server and its services)
  hi?: (When & { id: NodeId; for?: number })[]; // light up (for: seconds; default: to the end)
  flows?: Flow[];
  tags?: Tag[];
};

export const WS = {
  ws1: { name: "ws-001", kind: "desktop", unlock: "office only" },
  ws2: { name: "ws-002", kind: "laptop", unlock: "PIN" },
  ws3: { name: "ws-003", kind: "desktop", unlock: "security key" },
} as const;

const BUS = 470;
const HQ = { x: 470, y: 64, w: 680, h: 340 };
const TILE_W = 206, TILE_H = 128;
const SERVICES: { id: NodeId; logo: LogoName; name: string; dns: string; col: number; row: number }[] = [
  { id: "ssh", logo: "ssh", name: "the door", dns: "one locked entrance", col: 0, row: 0 },
  { id: "git", logo: "git", name: "the plan", dns: "the recipes", col: 1, row: 0 },
  { id: "build", logo: "nixos", name: "the workshop", dns: "builds the systems", col: 2, row: 0 },
  { id: "state", logo: "sqlite", name: "the logbook", dns: "what they report", col: 0, row: 1 },
  { id: "secrets", logo: "sqlite", name: "the safe", dns: "passwords, keys", col: 1, row: 1 },
  { id: "tang", logo: "tang", name: "office unlock", dns: "office only", col: 2, row: 1 },
];
const tile = (col: number, row: number) => ({ x: HQ.x + 22 + col * (TILE_W + 10), y: HQ.y + 64 + row * (TILE_H + 10) });
const WS_X = { ws1: 250, ws2: 650, ws3: 1050 };
const WS_Y = 548, WS_W = 320, WS_H = 196;
const ADMIN = { x: 70, y: 110, w: 320, h: 230 };
const NET = { x: 1610, y: 70, w: 280, h: 250 };

// Where a node's centre is, and where its wire meets it.
const centre = (id: NodeId): [number, number] => {
  const s = SERVICES.find((x) => x.id === id);
  if (s) { const t = tile(s.col, s.row); return [t.x + TILE_W / 2, t.y + TILE_H / 2]; }
  if (id === "hq") return [HQ.x + HQ.w / 2, HQ.y + HQ.h / 2];
  if (id === "admin") return [ADMIN.x + ADMIN.w / 2, ADMIN.y + ADMIN.h / 2];
  if (id === "net") return [NET.x + NET.w / 2, NET.y + NET.h / 2];
  return [WS_X[id as keyof typeof WS_X] + WS_W / 2, WS_Y + WS_H / 2];
};
const port = (id: NodeId): [number, number] => {
  if (id === "admin") return [ADMIN.x + ADMIN.w / 2, ADMIN.y + ADMIN.h];
  if (id === "net") return [NET.x, NET.y + NET.h / 2];
  if (id.startsWith("ws")) return [WS_X[id as keyof typeof WS_X] + WS_W / 2, WS_Y];
  return [HQ.x + HQ.w / 2, HQ.y + HQ.h]; // hq and its services
};
const inHq = (id: NodeId) => !id.startsWith("ws") && id !== "admin" && id !== "net";
const route = (a: NodeId, b: NodeId): [number, number][] => {
  const viaNet = (): [number, number][] => [[HQ.x + HQ.w, HQ.y + 200], [NET.x, NET.y + NET.h / 2]];
  if (a === "net") return [centre(a), ...viaNet().reverse(), centre(b)];
  if (b === "net") return [centre(a), ...viaNet(), centre(b)];
  if (inHq(a) && inHq(b)) return [centre(a), centre(b)];
  const pa = port(a), pb = port(b);
  return [centre(a), pa, [pa[0], BUS], [pb[0], BUS], pb, centre(b)];
};

const useT = () => {
  const beats = useBeats();
  const { durationInFrames: D, fps } = useVideoConfig();
  return (w: When | undefined, fallback = 0) =>
    !w ? fallback
      : w.beat !== undefined ? (beats[Math.min(w.beat, beats.length - 1)] ?? 0) + Math.round((w.delay ?? 0) * fps)
      : w.at !== undefined ? Math.round(w.at * D) : fallback;
};

export const Net: React.FC<NetProps> = ({ show = [], add = [], hi = [], flows = [], tags = [] }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = useT();
  const appear = (id: NodeId) => {
    const key = inHq(id) ? "hq" : id;
    const a = add.find((x) => x.id === key);
    if (a) {
      const t0 = t(a);
      return interpolate(f, [t0, t0 + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    }
    return key === "hq" || show.includes(key) ? 1 : 0;
  };
  const lit = (id: NodeId) => hi.some((h) => {
    if (h.id !== id) return false;
    const t0 = t(h);
    return f >= t0 && (h.for === undefined || f < t0 + h.for * fps);
  });
  const glow = (id: NodeId) => (lit(id) ? `0 0 0 4px ${C.amber}, 0 0 34px ${C.amber}88` : "0 12px 30px rgba(0,0,0,0.5)");
  const box = (id: NodeId, x: number, y: number, w: number, h: number, extra: React.CSSProperties = {}): React.CSSProperties => ({
    position: "absolute", left: x, top: y, width: w, height: h, opacity: appear(id), transform: `scale(${0.92 + 0.08 * appear(id)})`,
    background: C.base, border: `2px solid ${C.line}`, borderRadius: 10, boxShadow: glow(id), ...extra,
  });
  const wsIds = (["ws1", "ws2", "ws3"] as const).filter((w) => appear(w) > 0);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      {/* the company, and the wires */}
      <svg width={1920} height={770} style={{ position: "absolute", inset: 0 }}>
        <rect x={24} y={8} width={1550} height={754} rx={18} fill="none" stroke={C.amberDim} strokeWidth={3} strokeDasharray="14 10" />
        <line x1={110} y1={BUS} x2={1500} y2={BUS} stroke={C.line} strokeWidth={8} strokeLinecap="round" />
        <line x1={HQ.x + HQ.w / 2} y1={HQ.y + HQ.h} x2={HQ.x + HQ.w / 2} y2={BUS} stroke={C.line} strokeWidth={6} />
        <line x1={port("admin")[0]} y1={port("admin")[1]} x2={port("admin")[0]} y2={BUS} stroke={C.line} strokeWidth={6} opacity={appear("admin")} />
        {wsIds.map((w) => <line key={w} x1={port(w)[0]} y1={BUS} x2={port(w)[0]} y2={WS_Y} stroke={C.line} strokeWidth={6} opacity={appear(w)} />)}
        <path d={`M${HQ.x + HQ.w} ${HQ.y + 200} L${NET.x} ${NET.y + NET.h / 2}`} stroke={C.line} strokeWidth={5} strokeDasharray="10 8" opacity={appear("net")} fill="none" />
      </svg>
      <div style={{ position: "absolute", left: 50, top: 22, fontFamily: SANS, fontSize: 30, fontWeight: 800, color: C.text }}>
        Example Corp <span style={{ fontFamily: MONO, fontSize: 24, fontWeight: 400, color: C.sand, marginLeft: 12 }}>corp.example.com</span>
      </div>
      <div style={{ position: "absolute", left: 116, top: BUS + 12, fontFamily: MONO, fontSize: 21, color: C.dim }}>office network</div>

      {/* the server */}
      <div style={box("hq", HQ.x, HQ.y, HQ.w, HQ.h, { borderTop: `5px solid ${C.tealHi}` })}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 20px", fontFamily: MONO, fontSize: 26 }}>
          <Machine kind="server" size={40} color={C.tealHi} />
          <b style={{ color: C.tealHi }}>hq</b><span style={{ color: C.dim, fontSize: 21 }}>the server, in the office</span>
        </div>
      </div>
      {SERVICES.map((s) => {
        const p = tile(s.col, s.row);
        return (
          <div key={s.id} style={box(s.id, p.x, p.y, TILE_W, TILE_H, { background: C.raised, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 4 })}>
            <Logo name={s.logo} size={50} />
            <div style={{ fontFamily: SANS, fontSize: 22, fontWeight: 700, color: C.text }}>{s.name}</div>
            <div style={{ fontFamily: MONO, fontSize: 17, color: C.sand }}>{s.dns}</div>
          </div>
        );
      })}
      {/* the admin's computer */}
      <div style={box("admin", ADMIN.x, ADMIN.y, ADMIN.w, ADMIN.h, { borderTop: `5px solid ${C.amber}`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6 })}>
        <Machine kind="laptop" size={84} color={C.amber} />
        <div style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, color: C.amber }}>laptop</div>
        <div style={{ fontFamily: SANS, fontSize: 21, color: C.text }}>your computer, the admin's</div>
      </div>

      {/* the computers */}
      {(["ws1", "ws2", "ws3"] as const).map((w) => (
        <div key={w} style={box(w, WS_X[w], WS_Y, WS_W, WS_H, { borderTop: `5px solid ${C.blue}`, display: "flex", alignItems: "center", gap: 16, padding: "0 20px" })}>
          <Machine kind={WS[w].kind} size={92} color={C.blue} />
          <div>
            <div style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, color: C.blue }}>{WS[w].name}</div>
            <div style={{ fontFamily: SANS, fontSize: 21, color: C.text }}>office computer</div>
            <div style={{ fontFamily: SANS, fontSize: 20, color: C.sand, marginTop: 4 }}><LockGlyph /> {WS[w].unlock}</div>
          </div>
        </div>
      ))}

      {/* the Internet */}
      <div style={box("net", NET.x, NET.y, NET.w, NET.h, { borderTop: `5px solid ${C.dim}`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, textAlign: "center" })}>
        <div style={{ fontFamily: SANS, fontSize: 26, fontWeight: 700, color: C.text }}>The Internet</div>
        <Logo name="nixos" size={46} />
        <div style={{ fontFamily: MONO, fontSize: 18, color: C.dim, lineHeight: 1.35 }}>MeccanicOS<br />updates</div>
      </div>

      {/* tags, then the packets on top */}
      {tags.map((g, i) => {
        const t0 = t(g);
        if (f < t0 || (g.for !== undefined && f > t0 + g.for * fps)) return null;
        const [cx] = centre(g.id);
        const top = g.id.startsWith("ws") ? WS_Y - 30 : g.id === "admin" ? ADMIN.y - 30 : g.id === "net" ? NET.y - 30 : centre(g.id)[1] - TILE_H / 2 - 22;
        const o = interpolate(f, [t0, t0 + 8], [0, 1], { extrapolateRight: "clamp" });
        return (
          <div key={i} style={{ position: "absolute", left: cx, top, transform: `translateX(-50%) scale(${0.8 + 0.2 * o})`, opacity: o, zIndex: 4,
            background: g.color ?? C.green, color: C.ink, fontFamily: MONO, fontWeight: 700, fontSize: 21, padding: "4px 14px", borderRadius: 20, whiteSpace: "nowrap" }}>{g.text}</div>
        );
      })}
      <svg width={1920} height={770} style={{ position: "absolute", inset: 0, zIndex: 5 }}>
        {flows.flatMap((fl, i) => Array.from({ length: fl.repeat ?? 1 }, (_, k) => {
          const t0 = t(fl) + Math.round(k * (fl.every ?? 3) * fps);
          const dur = (fl.dur ?? 2.2) * fps;
          const p = (f - t0) / dur;
          if (p < 0 || p > 1) return null;
          const pts = route(fl.from, fl.to);
          const lens = pts.slice(1).map((q, j) => Math.hypot(q[0] - pts[j][0], q[1] - pts[j][1]));
          let d = lens.reduce((a, b) => a + b, 0) * p, j = 0;
          while (j < lens.length - 1 && d > lens[j]) d -= lens[j++];
          const u = lens[j] ? d / lens[j] : 0;
          const x = pts[j][0] + (pts[j + 1][0] - pts[j][0]) * u, y = pts[j][1] + (pts[j + 1][1] - pts[j][1]) * u;
          const w = Math.max(60, fl.label.length * 13 + 26);
          return (
            <g key={`${i}.${k}`} transform={`translate(${x - w / 2} ${y - 20})`}>
              <rect width={w} height={40} rx={20} fill={fl.color ?? C.amber} stroke={C.ink} strokeWidth={2} />
              <text x={w / 2} y={27} textAnchor="middle" fontFamily={MONO} fontSize={20} fill={C.ink} fontWeight={700}>{fl.label}</text>
            </g>
          );
        }))}
      </svg>
    </div>
  );
};
