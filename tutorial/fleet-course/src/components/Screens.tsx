import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, MONO, SANS } from "../theme";
import { useBeats } from "./Beats";
import { Markup } from "./Markup";

// Screenshots, one per narration segment: the picture on the left (scaled to
// the stage's height), what it shows on the right. The pictures are
// docs/fleet/tui/*.png (public/tui links there).
export type Shot = { src: string; title: string; note: string };

export const Screens: React.FC<{ shots: Shot[] }> = ({ shots }) => {
  const f = useCurrentFrame();
  const beats = useBeats();
  let k = 0;
  beats.forEach((b, i) => { if (i < shots.length && f >= b - 6) k = i; });
  const t0 = k === 0 ? 0 : beats[k] - 6;
  const o = interpolate(f, [t0, t0 + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const s = shots[k];
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <Img src={staticFile(`tui/${s.src}`)} style={{ position: "absolute", left: 80, top: 0, height: 770, borderRadius: 8,
        border: `2px solid ${C.line}`, boxShadow: "0 16px 40px rgba(0,0,0,0.6)", opacity: o }} />
      <div style={{ position: "absolute", left: 1060, top: 60, width: 780, opacity: o }}>
        <div style={{ fontFamily: MONO, fontSize: 20, letterSpacing: "0.3em", color: C.amber }}>MOS-FLEET, FULL SCREEN · {k + 1}/{shots.length}</div>
        <div style={{ fontFamily: SANS, fontSize: 52, fontWeight: 800, marginTop: 14 }}>{s.title}</div>
        <div style={{ fontFamily: SANS, fontSize: 32, lineHeight: 1.35, marginTop: 20, color: C.text }}><Markup text={s.note} /></div>
      </div>
    </div>
  );
};
