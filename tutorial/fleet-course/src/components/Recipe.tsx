import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, FPS, MONO, SANS } from "../theme";
import { useStart } from "./Beats";
import { Markup } from "./Markup";

// A slide of commands, in order, to read rather than hear: where each one
// runs (a badge), the command (or a step done by hand), and a note on what
// it does. Rows appear one after another from `beat` (plus `delay`), `every`
// seconds apart, then stay.
export type Where = "server" | "you" | "new" | "any";
export type Row = { where: Where; cmd?: string | string[]; step?: string; note: string };

const WHERE: Record<Where, { label: string; color: string }> = {
  server: { label: "the server", color: C.tealHi },
  you: { label: "your computer", color: C.amber },
  new: { label: "new computer", color: C.blue },
  any: { label: "any computer", color: C.blue },
};

const RowView: React.FC<{ row: Row; t0: number }> = ({ row, t0 }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [t0, t0 + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const w = WHERE[row.where];
  const lines = row.cmd === undefined ? [] : Array.isArray(row.cmd) ? row.cmd : [row.cmd];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20, opacity: o, transform: `translateX(${(1 - o) * -20}px)`,
      background: C.base, borderLeft: `5px solid ${w.color}`, borderRadius: 6, padding: "8px 18px" }}>
      <div style={{ width: 170, flexShrink: 0, fontFamily: MONO, fontSize: 17, letterSpacing: "0.12em", color: w.color, textTransform: "uppercase" }}>{w.label}</div>
      <div style={{ width: 980, flexShrink: 0 }}>
        {row.step ? <div style={{ fontFamily: SANS, fontSize: 25, fontStyle: "italic", color: C.text }}>{row.step}</div> : null}
        {lines.map((l, i) => (
          <div key={i} style={{ fontFamily: MONO, fontSize: 21, lineHeight: "30px", color: C.text, whiteSpace: "pre" }}>
            {i === 0 || !l.startsWith(" ") ? <span style={{ color: C.amber }}>{"> "}</span> : null}{l}
          </div>
        ))}
      </div>
      <div style={{ flex: 1, fontFamily: SANS, fontSize: 23, lineHeight: 1.25, color: C.text, borderLeft: `2px solid ${C.line}`, paddingLeft: 18 }}>
        <Markup text={row.note} />
      </div>
    </div>
  );
};

export const Recipe: React.FC<{ title: string; rows: Row[]; beat?: number; delay?: number; every?: number; footer?: string }> = ({ title, rows, beat = 0, delay = 0.5, every = 0.8, footer }) => {
  const start = useStart({ beat, delay });
  return (
    <div style={{ position: "absolute", left: 50, right: 50, top: 0, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ fontFamily: SANS, fontSize: 38, fontWeight: 800, marginBottom: 4 }}><Markup text={title} /></div>
      {rows.map((r, i) => <RowView key={i} row={r} t0={start + Math.round(i * every * FPS)} />)}
      {footer ? <div style={{ fontFamily: SANS, fontSize: 23, color: C.dim, marginTop: 4 }}><Markup text={footer} /></div> : null}
    </div>
  );
};
