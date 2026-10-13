import React from "react";
import { Img, staticFile } from "remotion";
import { siForgejo, siGit, siMysql, siNginx, siNixos, siRedis } from "simple-icons";
import { C } from "../theme";

// The server's tools: their own logos (simple-icons, or the project's
// artwork in public/logos), and drawn ones for those without a logo.
type SI = { path: string; hex: string };
const simple = (i: SI, size: number) => (
  <svg width={size} height={size} viewBox="0 0 24 24"><path d={i.path} fill={`#${i.hex}`} /></svg>
);

export type LogoName = "kanidm" | "forgejo" | "harmonia" | "fleet" | "tang" | "mysql" | "redis" | "nginx" | "git" | "comin" | "nixos";

export const Logo: React.FC<{ name: LogoName; size?: number }> = ({ name, size = 56 }) => {
  switch (name) {
    case "kanidm": return <Img src={staticFile("logos/kanidm.png")} style={{ width: size * 1.4, height: size, objectFit: "contain" }} />;
    case "fleet": return <Img src={staticFile("logos/fleet.png")} style={{ width: size, height: size, objectFit: "contain" }} />;
    case "forgejo": return simple(siForgejo, size);
    case "mysql": return simple(siMysql, size);
    case "redis": return simple(siRedis, size);
    case "nginx": return simple(siNginx, size);
    case "git": return simple(siGit, size);
    case "nixos": case "harmonia": return simple(siNixos, size); // Harmonia serves Nix's store
    case "tang": return <KeyIcon size={size} color={C.tealHi} />;
    case "comin": return <SyncIcon size={size} color={C.green} />;
  }
};

export const KeyIcon: React.FC<{ size?: number; color?: string }> = ({ size = 48, color = C.amber }) => (
  <svg width={size} height={size} viewBox="0 0 48 48">
    <circle cx={15} cy={24} r={10} fill="none" stroke={color} strokeWidth={5} />
    <path d="M25 24H44M37 24v8M43 24v6" stroke={color} strokeWidth={5} fill="none" strokeLinecap="round" />
  </svg>
);

export const SyncIcon: React.FC<{ size?: number; color?: string }> = ({ size = 48, color = C.green }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none" stroke={color} strokeWidth={5} strokeLinecap="round">
    <path d="M38 18a15 15 0 0 0-27-3M10 30a15 15 0 0 0 27 3" />
    <path d="M10 7v9h9M38 41v-9h-9" />
  </svg>
);

export const ChipIcon: React.FC<{ size?: number; color?: string }> = ({ size = 64, color = C.green }) => (
  <svg width={size} height={size} viewBox="0 0 64 64">
    {[14, 24, 34, 44].map((p) => (
      <g key={p} stroke={color} strokeWidth={3}>
        <line x1={p + 3} y1={4} x2={p + 3} y2={12} /><line x1={p + 3} y1={52} x2={p + 3} y2={60} />
        <line x1={4} y1={p + 3} x2={12} y2={p + 3} /><line x1={52} y1={p + 3} x2={60} y2={p + 3} />
      </g>
    ))}
    <rect x={12} y={12} width={40} height={40} rx={4} fill={C.raised} stroke={color} strokeWidth={3} />
    <text x={32} y={37} textAnchor="middle" fontFamily="monospace" fontWeight={700} fontSize={13} fill={color}>TPM</text>
  </svg>
);

export const FidoIcon: React.FC<{ size?: number; color?: string; glow?: number }> = ({ size = 64, color = C.blue, glow = 0 }) => (
  <svg width={size} height={size} viewBox="0 0 64 64">
    <rect x={22} y={2} width={20} height={14} fill={C.dim} />
    <rect x={14} y={14} width={36} height={46} rx={8} fill={C.raised} stroke={color} strokeWidth={3} />
    <circle cx={32} cy={40} r={9} fill={glow > 0 ? C.amber : C.line} opacity={0.4 + 0.6 * glow} />
  </svg>
);

export const PaperIcon: React.FC<{ size?: number; color?: string }> = ({ size = 64, color = C.sand }) => (
  <svg width={size} height={size} viewBox="0 0 64 64">
    <path d="M12 4h30l10 10v46H12Z" fill={C.text} stroke={color} strokeWidth={2} />
    {[22, 30, 38, 46].map((y) => <line key={y} x1={18} y1={y} x2={46} y2={y} stroke={C.dim} strokeWidth={3} />)}
  </svg>
);

export const KeyboardIcon: React.FC<{ size?: number; color?: string }> = ({ size = 64, color = C.sand }) => (
  <svg width={size} height={size} viewBox="0 0 64 64">
    <rect x={4} y={18} width={56} height={30} rx={4} fill={C.raised} stroke={color} strokeWidth={3} />
    {[0, 1, 2].map((r) => [0, 1, 2, 3, 4, 5].map((c) => (
      <rect key={`${r}${c}`} x={9 + c * 8.5} y={23 + r * 7.5} width={6} height={5} fill={color} opacity={0.7} />
    )))}
  </svg>
);

// Computers, drawn: a laptop, a desktop, the server, the USB stick.
export const Machine: React.FC<{ kind: "laptop" | "desktop" | "server"; size?: number; color?: string }> = ({ kind, size = 80, color = C.text }) => (
  <svg width={size} height={size} viewBox="0 0 80 80" fill="none" stroke={color} strokeWidth={4} strokeLinejoin="round">
    {kind === "laptop" ? (
      <><rect x={14} y={14} width={52} height={36} rx={3} /><path d="M6 60h68l-6-8H12Z" fill={color} opacity={0.9} /></>
    ) : kind === "desktop" ? (
      <><rect x={8} y={10} width={64} height={42} rx={3} /><path d="M32 52l-4 14h24l-4-14M22 68h36" /></>
    ) : (
      <>{[8, 30, 52].map((y) => <g key={y}><rect x={12} y={y} width={56} height={18} rx={3} /><circle cx={58} cy={y + 9} r={3} fill={color} /></g>)}</>
    )}
  </svg>
);

export const StickIcon: React.FC<{ size?: number; color?: string }> = ({ size = 48, color = C.amber }) => (
  <svg width={size} height={size} viewBox="0 0 48 48">
    <rect x={17} y={2} width={14} height={12} fill={C.dim} />
    <rect x={12} y={12} width={24} height={34} rx={4} fill={color} />
    <text x={24} y={34} textAnchor="middle" fontFamily="monospace" fontWeight={900} fontSize={13} fill={C.ink}>M</text>
  </svg>
);
