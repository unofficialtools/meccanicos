import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, MONO, SANS } from "../theme";
import { Gear } from "./Gear";

// A chapter's first scene: its number, its title, and its machine.
export const Title: React.FC<{ n: number | string; title: string; metaphor: string }> = ({ n, title, metaphor }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [4, 20], [0, 1], { extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <svg width={1920} height={770} style={{ position: "absolute" }}>
        <Gear x={1520} y={360} r={210} teeth={18} speed={0.35} color={C.raised} hole={C.ink} />
        <Gear x={1770} y={600} r={120} teeth={11} speed={-0.62} phase={9} color={C.amberDim} hole={C.ink} />
        <Gear x={1290} y={640} r={80} teeth={9} speed={-0.82} color={C.line} hole={C.ink} />
      </svg>
      <div style={{ position: "absolute", left: 150, top: 150, opacity: o }}>
        <div style={{ fontFamily: MONO, fontSize: 34, color: C.amber, letterSpacing: "0.3em" }}>{typeof n === "number" ? `CHAPTER ${n}` : n}</div>
        <div style={{ fontFamily: SANS, fontSize: 96, fontWeight: 800, marginTop: 20, maxWidth: 1050, lineHeight: 1.05 }}>{title}</div>
        <div style={{ fontFamily: SANS, fontSize: 40, color: C.dim, marginTop: 34, maxWidth: 1000 }}>{metaphor}</div>
      </div>
    </div>
  );
};
