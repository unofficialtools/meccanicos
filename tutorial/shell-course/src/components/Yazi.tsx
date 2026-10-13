import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO } from "../theme";
import { useBeats } from "./Beats";
import { Keys } from "./Keys";
import { Markup } from "./Markup";
import { Window } from "./Window";

// yazi's three columns: the parent folder, this folder (the selection in
// amber), and a preview of the selected entry. "name/" is a folder.
export type YaziState = {
  at?: number; // fraction of the scene
  beat?: number; // or: with this narration segment
  cwd: string;
  parent: string[];
  parentSel?: number;
  items: string[];
  sel: number;
  preview: string[]; // a folder's entries ("x/" folders) or a file's lines (Markup)
  previewIsFile?: boolean;
  keys?: string;
  info?: string; // the bottom line: size, permissions
};

const Entry: React.FC<{ name: string; selected?: boolean; dimmed?: boolean }> = ({ name, selected, dimmed }) => {
  const dir = name.endsWith("/");
  const label = dir ? name.slice(0, -1) : name;
  return (
    <div style={{ height: 38, display: "flex", alignItems: "center", gap: 12, padding: "0 12px", whiteSpace: "pre",
      background: selected ? C.amber : "transparent", color: selected ? C.ink : dir ? C.blue : dimmed ? C.dim : C.text,
      fontWeight: dir ? 700 : 400 }}>
      <span style={{ width: 22 }}>{dir ? "" : ""}</span>
      <span>{label}</span>
    </div>
  );
};

export const Yazi: React.FC<{ states: YaziState[] }> = ({ states }) => {
  const f = useCurrentFrame();
  const { durationInFrames: D, fps } = useVideoConfig();
  const beats = useBeats();
  const starts = states.map((s, i) =>
    s.beat !== undefined ? (beats[Math.min(s.beat, beats.length - 1)] ?? 0) + Math.round(0.3 * fps)
      : Math.round((s.at ?? (0.85 * i) / Math.max(1, states.length)) * D));
  let k = 0;
  starts.forEach((t, i) => { if (f >= t) k = i; });
  const s = states[k];
  return (
    <>
      <Window title={`Yazi: ${s.cwd}`}>
        <div style={{ fontFamily: MONO, fontSize: 25, color: C.text, height: "100%", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "8px 16px", color: C.amber, fontWeight: 700 }}>{s.cwd}</div>
          <div style={{ display: "flex", flex: 1, borderTop: `1px solid ${C.line}` }}>
            <div style={{ width: "22%", borderRight: `1px solid ${C.line}`, paddingTop: 6 }}>
              {s.parent.map((n, i) => <Entry key={i} name={n} dimmed selected={false} />).map((e, i) =>
                i === s.parentSel ? <div key={i} style={{ background: C.raised }}>{e}</div> : e)}
            </div>
            <div style={{ width: "36%", borderRight: `1px solid ${C.line}`, paddingTop: 6 }}>
              {s.items.map((n, i) => <Entry key={i} name={n} selected={i === s.sel} />)}
            </div>
            <div style={{ flex: 1, paddingTop: 6, paddingLeft: 6, overflow: "hidden" }}>
              {s.previewIsFile
                ? s.preview.map((l, i) => <div key={i} style={{ height: 36, whiteSpace: "pre", padding: "0 12px", fontSize: 23 }}><Markup text={l} /></div>)
                : s.preview.map((n, i) => <Entry key={i} name={n} />)}
            </div>
          </div>
          <div style={{ height: 40, background: C.base, display: "flex", alignItems: "center", padding: "0 16px", gap: 24, color: C.dim, fontSize: 21 }}>
            <span style={{ background: C.amber, color: C.ink, padding: "0 10px", fontWeight: 700 }}>NOR</span>
            <span>{s.info ?? `${s.sel + 1}/${s.items.length}`}</span>
            <span style={{ marginLeft: "auto" }}>h ← parent · l → open · j/k ↓↑ · q quit</span>
          </div>
        </div>
      </Window>
      {states.map((st, i) => (st.keys ? <Keys key={i} keys={st.keys} from={starts[i]} dur={50} /> : null))}
    </>
  );
};
