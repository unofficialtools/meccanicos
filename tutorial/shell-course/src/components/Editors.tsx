import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO } from "../theme";
import { useBeats } from "./Beats";
import { Keys } from "./Keys";
import { Markup, plain } from "./Markup";
import { Window } from "./Window";

// The text appears as if typed between `from` and `to` (fractions of the scene).
const typed = (lines: string[], frac: number) => {
  const total = lines.reduce((a, l) => a + plain(l).length + 1, 0);
  let left = Math.floor(total * frac);
  const out: string[] = [];
  for (const l of lines) {
    const n = plain(l).length + 1;
    if (left >= n) { out.push(l); left -= n; continue; }
    out.push(plain(l).slice(0, left));
    break;
  }
  return out;
};

export type EditorProps = {
  file: string; lines: string[]; typeFrom?: number; typeTo?: number; message?: string; modified?: boolean;
  keys?: { keys: string; at?: number; beat?: number }[]; menu?: boolean; mode?: string; dir?: string;
};

export const Jed: React.FC<EditorProps> = ({ file, lines, typeFrom, typeTo, message = "", modified, keys = [], menu: menuProp, mode = "Text", dir = "~/projects/gearbox/" }) => {
  const f = useCurrentFrame();
  const { durationInFrames: D, fps } = useVideoConfig();
  const beats = useBeats();
  const keyAt = (k: { at?: number; beat?: number }) =>
    k.beat !== undefined ? (beats[Math.min(k.beat, beats.length - 1)] ?? 0) + Math.round(0.4 * fps) : Math.round((k.at ?? 0) * D);
  const frac = typeFrom === undefined ? 1 : Math.min(1, Math.max(0, (f / D - typeFrom) / ((typeTo ?? 0.8) - typeFrom)));
  const shown = typed(lines, frac);
  const saved = keys.some((k) => k.keys.includes("Ctrl+S") && f >= keyAt(k) + 20);
  const dirty = modified ?? (frac > 0 && !saved);
  const msg = saved ? `Wrote ${lines.length} lines to ${dir}${file}` : message;
  const menu = menuProp || keys.some((k) => k.keys === "F10" && f >= keyAt(k) + 12);
  return (
    <>
      <Window title={`Jed: ${file}`}>
        <div style={{ fontFamily: MONO, fontSize: 26, height: "100%", display: "flex", flexDirection: "column", color: "#bcbcbc" }}>
          <div style={{ background: "#262626", padding: "4px 14px", whiteSpace: "pre" }}>
            <span style={{ color: C.dim }}>F10 key ==&gt; </span>
            {["File", "Edit", "Mode", "Search", "Buffers", "Windows", "System", "Help"].map((m, i) => (
              <span key={m} style={{ marginRight: 26, background: menu && i === 0 ? "#444444" : undefined, padding: "0 4px" }}>
                <span style={{ color: "#ffaf00" }}>{m[0]}</span>{m.slice(1)}
              </span>
            ))}
          </div>
          <div style={{ flex: 1, padding: "8px 14px", position: "relative" }}>
            {shown.map((l, i) => <div key={i} style={{ height: 36, whiteSpace: "pre" }}><Markup text={l} />{i === shown.length - 1 ? <span style={{ background: "#e4e4e4" }}> </span> : null}</div>)}
            {menu ? (
              <div style={{ position: "absolute", left: 120, top: 0, background: "#262626", border: `1px solid ${C.line}`, padding: "6px 0", width: 340 }}>
                {["Open", "Save", "Save As", "Save Buffers", "Insert File", "Exit"].map((m, i) => (
                  <div key={m} style={{ padding: "2px 18px", background: i === 1 ? "#444444" : undefined, color: "#e4e4e4" }}><span style={{ color: "#ffaf00" }}>{m[0]}</span>{m.slice(1)}</div>
                ))}
              </div>
            ) : null}
          </div>
          <div style={{ background: "#262626", padding: "4px 14px", whiteSpace: "pre", color: "#bcbcbc" }}>
            {`-${dirty ? "**" : "--"}-----|Jed 0.99.19: ${file}   (${mode})  All  ${shown.length}/${lines.length}  ${"-".repeat(30)}`}
          </div>
          <div style={{ height: 38, padding: "4px 14px", color: "#8a8a8a" }}>{msg}</div>
        </div>
      </Window>
      {keys.map((k, i) => <Keys key={i} keys={k.keys} from={keyAt(k)} dur={50} />)}
    </>
  );
};

export const Codium: React.FC<EditorProps & { tree?: string[] }> = ({ file, lines, tree = [] }) => (
  <Window title={`${file} - projects - VSCodium`} bg="#1e1e1e">
    <div style={{ display: "flex", height: "100%", fontFamily: MONO, fontSize: 24 }}>
      <div style={{ width: 70, background: "#333333" }} />
      <div style={{ width: 330, background: "#252526", color: "#cccccc", padding: "10px 14px", fontSize: 20 }}>
        <div style={{ color: "#bbbbbb", fontSize: 16, letterSpacing: 2, marginBottom: 10 }}>EXPLORER</div>
        {tree.map((t, i) => <div key={i} style={{ padding: "3px 0", background: t.includes(file) ? "#37373d" : undefined }}>{t}</div>)}
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ height: 44, background: "#252526", display: "flex" }}>
          <div style={{ background: "#1e1e1e", color: "#ffffff", padding: "8px 22px", fontSize: 20, borderTop: "2px solid #f8a800" }}>{file}</div>
        </div>
        <div style={{ padding: "12px 0", color: "#d4d4d4" }}>
          {lines.map((l, i) => (
            <div key={i} style={{ height: 36, whiteSpace: "pre", display: "flex" }}>
              <span style={{ width: 70, textAlign: "right", paddingRight: 24, color: "#858585" }}>{i + 1}</span>
              <Markup text={l} />
            </div>
          ))}
        </div>
      </div>
    </div>
  </Window>
);
