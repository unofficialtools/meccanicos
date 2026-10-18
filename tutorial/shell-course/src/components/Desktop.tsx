import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO, SANS } from "../theme";
import { useStart } from "./Beats";
import { Keys } from "./Keys";
import { Terminal } from "./Terminal";

// The MeccanicOS desktop (its wallpaper and top bar); then Super+Space
// opens the command bar, "terminal" is typed, Enter opens the terminal.
// Each step on a narration beat.
const TopBar: React.FC = () => (
  <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 34, background: "#16181b", display: "flex", alignItems: "center",
    padding: "0 12px", gap: 14, fontFamily: MONO, fontSize: 17, color: C.dim, borderBottom: `1px solid ${C.line}` }}>
    <svg width="22" height="22" viewBox="0 0 34 34"><path d="M0 0H24L34 10V34H10L0 24Z" fill={C.amber} /><path d="M8 26V9h4l5 7 5-7h4v17h-4V16l-5 6-5-6v10Z" fill={C.ink} /></svg>
    <span style={{ color: C.text, letterSpacing: "0.3em" }}>MECCANICOS</span>
    <span style={{ marginLeft: "auto" }}>Mon 12 Oct  09:00   CPU 4%   ▲ Wi-Fi   ◖ 87%</span>
  </div>
);

const Bar: React.FC<{ typed: string; result: boolean }> = ({ typed, result }) => (
  <div style={{ position: "absolute", left: 330, top: 150, width: 1140, background: C.base, border: `1px solid ${C.line}`, boxShadow: "0 30px 80px rgba(0,0,0,0.6)" }}>
    <div style={{ display: "flex", alignItems: "center", gap: 22, padding: "22px 28px", borderBottom: `1px solid ${C.line}` }}>
      <svg width="54" height="54" viewBox="0 0 34 34"><path d="M0 0H24L34 10V34H10L0 24Z" fill={C.amber} /><path d="M8 26V9h4l5 7 5-7h4v17h-4V16l-5 6-5-6v10Z" fill={C.ink} /></svg>
      <span style={{ fontFamily: MONO, fontSize: 30, letterSpacing: "0.5em", color: C.text }}>MECCANICOS</span>
      <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 20, color: C.dim, letterSpacing: "0.1em" }}>WI-FI  ·  POWER</span>
    </div>
    <div style={{ padding: "18px 28px", fontFamily: MONO, fontSize: 40, color: C.text }}>
      <span style={{ color: C.amber }}>❯ </span>{typed}<span style={{ borderLeft: `3px solid ${C.text}`, marginLeft: 2 }} />
    </div>
    {result ? (
      <div style={{ margin: "0 18px 14px", padding: "14px 18px", background: C.raised, borderLeft: `4px solid ${C.amber}`, display: "flex", alignItems: "center", gap: 22 }}>
        <span style={{ fontFamily: MONO, fontSize: 26, border: `1px solid ${C.line}`, padding: "4px 10px", color: C.text }}>&gt;_</span>
        <span style={{ fontFamily: SANS, fontSize: 34 }}><span style={{ color: C.amber }}>Terminal</span> (bash)</span>
      </div>
    ) : null}
    <div style={{ padding: "12px 28px", fontFamily: MONO, fontSize: 19, color: C.dim, borderTop: `1px solid ${C.line}` }}>
      Enter: open  ·  / or ~ a folder  ·  !… run a command  ·  shortcuts: every key
    </div>
  </div>
);

export const Desktop: React.FC<{ barBeat: number; typeBeat: number; enterBeat: number; promptBeat?: number }> = ({ barBeat, typeBeat, enterBeat, promptBeat }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const tBar = useStart({ beat: barBeat, delay: 0.3 });
  const tType = useStart({ beat: typeBeat, delay: 0.2 });
  const tEnter = useStart({ beat: enterBeat, delay: 0.4 });
  const word = "terminal";
  const typed = word.slice(0, Math.max(0, Math.min(word.length, Math.floor(((f - tType) / fps) * 9))));
  const termOn = f >= tEnter + 10;
  const o = interpolate(f, [tEnter + 10, tEnter + 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      <div style={{ position: "absolute", left: 60, top: 0, width: 1800, height: 770, overflow: "hidden", border: `1px solid ${C.line}` }}>
        <Img src={staticFile("wallpaper.jpg")} style={{ width: 1800, height: 1013, objectFit: "cover" }} />
        <TopBar />
        {f >= tBar && !termOn ? <Bar typed={f >= tType ? typed : ""} result={f >= tType && typed.length >= 4} /> : null}
        {termOn ? (
          <div style={{ position: "absolute", inset: 0, opacity: o }}>
            <Terminal steps={promptBeat !== undefined ? [{ cmd: "", beat: promptBeat }] : []} x={140} y={70} w={1520} h={640} title="Terminal" />
          </div>
        ) : null}
      </div>
      <Keys keys="Super+Space" from={tBar - 8} dur={55} />
      <Keys keys="Enter" from={tEnter} dur={40} />
    </div>
  );
};
