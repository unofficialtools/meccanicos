import React from "react";
import { useCurrentFrame } from "remotion";
import { C, MONO, SANS } from "../theme";

// The narration, a sentence or two at a time: each segment from its beat,
// its sentences timed by length (the voice speaks at an even pace).
// `code` in backticks shows in the monospace.
const chunks = (text: string): string[] => {
  // A sentence ends at . ! or ? followed by a space (not the dot in hello.cpp).
  const sentences = text.split(/(?<=[.!?]["')\]]?)\s+/).map((s) => s.trim()).filter(Boolean);
  const out: string[] = [];
  for (const s of sentences) {
    const last = out[out.length - 1];
    if (last && last.length + s.length < 150) out[out.length - 1] = `${last} ${s}`;
    else out.push(s);
  }
  return out.length ? out : [text];
};

const Code: React.FC<{ text: string }> = ({ text }) => (
  <>
    {text.split(/(`[^`]+`)/).map((p, i) =>
      p.startsWith("`") ? (
        <span key={i} style={{ fontFamily: MONO, color: C.amber, fontSize: "0.92em" }}>{p.slice(1, -1)}</span>
      ) : (
        <span key={i}>{p}</span>
      ),
    )}
  </>
);

export const Caption: React.FC<{ segments: string[]; beats: number[]; lengths: number[] }> = ({ segments, beats, lengths }) => {
  const f = useCurrentFrame();
  let k = 0;
  beats.forEach((b, i) => { if (f >= b - 6) k = i; });
  const parts = chunks(segments[k]);
  const total = parts.reduce((a, p) => a + p.length, 0);
  let acc = 0;
  let current = parts[0];
  for (const p of parts) {
    if (f - beats[k] >= (acc / total) * lengths[k]) current = p;
    acc += p.length;
  }
  return (
    <div style={{ position: "absolute", left: 120, right: 120, bottom: 34, height: 170, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ fontFamily: SANS, fontSize: 38, lineHeight: 1.35, textAlign: "center", color: C.text,
        background: "rgba(18,20,23,0.82)", padding: "10px 28px", borderRadius: 10 }}>
        <Code text={current} />
      </div>
    </div>
  );
};
