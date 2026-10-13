import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, MONO, SANS } from "../theme";
import { Caption } from "./Caption";

// Every scene: graphite background, the chapter bar on top (amber edge, like
// the desktop's windows), the stage, and the captions.
export const Frame: React.FC<{
  chapter: string; segments: string[]; beats: number[]; lengths: number[]; children: React.ReactNode; progress: number;
}> = ({ chapter, segments, beats, lengths, children, progress }) => {
  const f = useCurrentFrame();
  const fade = interpolate(f, [0, 8], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: C.ink, fontFamily: SANS, color: C.text }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 72, background: C.base, borderTop: `4px solid ${C.amber}`,
        display: "flex", alignItems: "center", padding: "0 48px", gap: 22 }}>
        <svg width="34" height="34" viewBox="0 0 34 34">
          <path d="M0 0H24L34 10V34H10L0 24Z" fill={C.amber} />
          <path d="M8 26V9h4l5 7 5-7h4v17h-4V16l-5 6-5-6v10Z" fill={C.ink} />
        </svg>
        <span style={{ fontFamily: MONO, letterSpacing: "0.35em", fontSize: 20, color: C.dim }}>MECCANICOS · THE SHELL</span>
        <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 22, color: C.text }}>{chapter}</span>
      </div>
      <div style={{ position: "absolute", top: 72, left: 0, height: 3, width: `${progress * 100}%`, background: C.amberDim }} />
      <div style={{ position: "absolute", top: 96, left: 0, right: 0, height: 770, opacity: fade }}>{children}</div>
      <Caption segments={segments} beats={beats} lengths={lengths} />
    </AbsoluteFill>
  );
};
