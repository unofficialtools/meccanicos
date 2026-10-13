import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO, SANS } from "../theme";
import { useStart } from "./Beats";
import { ChipIcon, FidoIcon, KeyboardIcon, KeyIcon, Machine, PaperIcon } from "./Icons";

// An encrypted (LUKS) disk: a disk with a padlock. The key that opens it
// comes from one place: a password typed, Tang on the office network (with
// the TPM), the TPM chip and a PIN, a FIDO2 security key, or the recovery
// key. On its beat the key arrives and the lock opens; or, `fail`, it
// doesn't (a red cross).
type When = { beat?: number; delay?: number; at?: number };
export type Method = "password" | "tang" | "tpm-pin" | "fido2" | "recovery";

const SOURCE: Record<Method, { label: string; note: string; icon: (glow: number) => React.ReactNode }> = {
  password: { label: "a password", note: "typed at power-on", icon: () => <KeyboardIcon size={86} /> },
  tang: { label: "Tang + TPM", note: "only on the office network", icon: () => (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}><Machine kind="server" size={70} color={C.tealHi} /><KeyIcon size={52} color={C.tealHi} /></div>) },
  "tpm-pin": { label: "TPM + PIN", note: "the chip, and a PIN typed", icon: () => (
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}><ChipIcon size={78} /><span style={{ fontFamily: MONO, fontSize: 30, color: C.green }}>••••••</span></div>) },
  fido2: { label: "FIDO2 key", note: "plugged in and touched", icon: (g) => <FidoIcon size={86} glow={g} /> },
  recovery: { label: "recovery key", note: "from an admin, typed", icon: () => <PaperIcon size={86} /> },
};

const Lock: React.FC<{ open: number; fail: number; x: number; y: number; s?: number }> = ({ open, fail, x, y, s = 1 }) => {
  const color = fail > 0 ? C.red : open > 0.5 ? C.green : C.amber;
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <path d={`M-22 0 V-22 a22 22 0 0 1 44 0 V${0 - 4 * 0}`} transform={`translate(0 ${-18 * open}) rotate(${-25 * open} 22 0)`}
        stroke={color} strokeWidth={10} fill="none" strokeLinecap="round" />
      <rect x={-36} y={-4} width={72} height={58} rx={10} fill={color} />
      <circle cx={0} cy={20} r={8} fill={C.ink} /><rect x={-3} y={22} width={6} height={16} fill={C.ink} />
    </g>
  );
};

// The disk alone: a cylinder, "LUKS", its padlock.
export const Disk: React.FC<{ x: number; y: number; open?: number; fail?: number; label?: string; s?: number }> = ({ x, y, open = 0, fail = 0, label = "LUKS", s = 1 }) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}>
    <path d="M-90 -50 V50 A90 26 0 0 0 90 50 V-50" fill={C.raised} stroke={C.line} strokeWidth={4} />
    <ellipse cx={0} cy={-50} rx={90} ry={26} fill={C.base} stroke={C.line} strokeWidth={4} />
    <ellipse cx={0} cy={-50} rx={22} ry={6} fill={C.line} />
    <text x={-22} y={30} textAnchor="middle" fontFamily={MONO} fontSize={24} fontWeight={700} fill={C.dim}>{label}</text>
    <Lock open={open} fail={fail} x={78} y={-6} s={0.9} />
  </g>
);

// One way of unlocking: the source of the key, a dashed wire, the disk.
export const Vault: React.FC<When & { method: Method; x: number; y: number; fail?: boolean; title?: string; note?: string }> = ({ method, x, y, fail, title, note, ...when }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t0 = useStart(when, 10 ** 9);
  const travel = 1.4 * fps;
  const p = interpolate(f, [t0, t0 + travel], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const done = interpolate(f, [t0 + travel, t0 + travel + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const src = SOURCE[method];
  const glow = method === "fido2" ? interpolate(Math.sin((f - t0) / 4), [-1, 1], [0, 1]) * (f >= t0 ? 1 : 0) : 0;
  // the key travels from the source (left) to the lock (right); a failed one stops halfway
  const kx = 150 + (fail ? Math.min(p, 0.5) : p) * 200;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: 600, height: 330 }}>
      <div style={{ position: "absolute", left: 0, top: 30, width: 220, display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
        <div style={{ height: 96, display: "flex", alignItems: "center" }}>{src.icon(glow)}</div>
        <div style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, color: C.text }}>{title ?? src.label}</div>
        <div style={{ fontFamily: SANS, fontSize: 22, color: C.dim, textAlign: "center" }}>{note ?? src.note}</div>
      </div>
      <svg width={600} height={330} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <line x1={220} y1={95} x2={360} y2={95} stroke={C.line} strokeWidth={4} strokeDasharray="10 8" />
        {f >= t0 && done < 1 ? <g transform={`translate(${kx + 30} 72)`}><KeyGlyph /></g> : null}
        <Disk x={470} y={110} open={fail ? 0 : done} fail={fail ? done : 0} />
        {fail && done > 0 ? <text x={470} y={250} textAnchor="middle" fontFamily={SANS} fontSize={26} fill={C.red} opacity={done}>stays locked</text> : null}
        {!fail && done > 0 ? <text x={470} y={250} textAnchor="middle" fontFamily={SANS} fontSize={26} fill={C.green} opacity={done}>unlocked</text> : null}
      </svg>
    </div>
  );
};

const KeyGlyph = () => (
  <g>
    <circle cx={12} cy={22} r={10} fill="none" stroke={C.amber} strokeWidth={6} />
    <path d="M22 22H58M48 22v10M56 22v8" stroke={C.amber} strokeWidth={6} fill="none" strokeLinecap="round" />
  </g>
);
