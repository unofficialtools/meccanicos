import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { COMMANDS } from "../commands";
import { C, MONO, SANS } from "../theme";
import { useBeats } from "./Beats";
import { Keys } from "./Keys";
import { Markup } from "./Markup";
import { Window } from "./Window";

export type Step = {
  cmd?: string; // typed at the prompt
  out?: string | string[]; // what it prints (Markup)
  beat?: number; // start with this narration segment (see Beats)...
  delay?: number; // ...this many seconds into it
  at?: number; // or: start, as a fraction of the scene (default: spread evenly)
  cd?: string; // the prompt's folder from the next prompt on
  keys?: string; // keycaps shown while it is typed (e.g. "Tab", "Ctrl+C")
  typed?: number; // characters per second (default 22)
  noPrompt?: boolean; // output only (a program writing while it runs)
  complete?: string; // added by Tab, `completeIn` seconds after the step starts
  completeIn?: number;
  keysIn?: number; // when the keycaps show, seconds after the step starts (default 0)
  note?: string[] | false; // new commands: a callout says what each does (set by script.tsx's term)
  nix?: boolean; // in a nix-shell (true) or back out (false), from the next prompt on
};

// A new command's callout shows this long before it is typed.
const NOTE_LEAD = 0.8;

const LINE = 36;

const Prompt: React.FC<{ cwd: string; who: string; nix?: boolean }> = ({ cwd, who, nix }) => (
  <div style={{ height: LINE, whiteSpace: "pre" }}>
    {nix
      ? <span style={{ color: C.green, fontWeight: 700 }}>[nix-shell:{cwd}]</span>
      : <><span style={{ background: "#005f5f", color: "#dadada" }}> {who} #1 </span><span style={{ color: "#d7af87" }}> {cwd} </span></>}
  </div>
);

// Which computer this shell is on: big at first, top right, for a few seconds.
export type Host = { name: string; role: string; color?: string };
const OnHost: React.FC<{ host: Host }> = ({ host }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const to = Math.round(4.5 * fps);
  if (f > to) return null;
  const o = interpolate(f, [0, 6, to - 8, to], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const color = host.color ?? C.amber;
  return (
    <div style={{ position: "absolute", right: 140, top: 60, opacity: o, zIndex: 7, background: C.raised, border: `3px solid ${color}`,
      borderRadius: 10, padding: "14px 26px", boxShadow: "0 16px 40px rgba(0,0,0,0.6)", minWidth: 420 }}>
      <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: "0.3em", color }}>A SHELL ON</div>
      <div style={{ fontFamily: MONO, fontSize: 44, fontWeight: 700, color: C.text, marginTop: 4 }}>{host.name}</div>
      <div style={{ fontFamily: SANS, fontSize: 28, color: C.text }}>{host.role}</div>
    </div>
  );
};

// "New command": what it does, top right, from just before it is typed.
const Callout: React.FC<{ names: string[]; from: number; to: number }> = ({ names, from, to }) => {
  const f = useCurrentFrame();
  if (f < from || f > to) return null;
  const o = interpolate(f, [from, from + 6, to - 6, to], [0, 1, 1, 0]);
  const y = interpolate(f, [from, from + 8], [14, 0], { extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", right: 140, bottom: 40, width: 560, opacity: o, transform: `translateY(${y}px)`, zIndex: 6,
      background: C.raised, border: `2px solid ${C.amber}`, borderRadius: 10, padding: "16px 24px", boxShadow: "0 16px 40px rgba(0,0,0,0.6)" }}>
      <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: "0.3em", color: C.amber, marginBottom: 8 }}>NEW COMMAND</div>
      {names.map((n) => (
        <div key={n} style={{ marginTop: 6 }}>
          <div style={{ fontFamily: MONO, fontSize: 40, fontWeight: 700, color: C.text }}>{n}</div>
          <div style={{ fontFamily: SANS, fontSize: 28, color: C.text, lineHeight: 1.25 }}>{COMMANDS[n]}</div>
        </div>
      ))}
    </div>
  );
};

export const Terminal: React.FC<{
  steps: Step[]; cwd?: string; title?: string; x?: number; y?: number; w?: number; h?: number; fontSize?: number; history?: string[];
  busy?: boolean; // the last command is still running (a full-screen program): no new prompt
  nix?: boolean; // already in a nix-shell
  who?: string; // the prompt's user@computer
  on?: Host; // the callout: which computer this shell is on
}> = ({ steps, cwd = "~", title, x, y, w, h = 740, fontSize = 27, history = [], busy, nix = false, who = "mrossi@laptop", on }) => {
  const f = useCurrentFrame();
  const { durationInFrames: D, fps } = useVideoConfig();
  const beats = useBeats();
  // When each step starts: on its beat, at its fraction, or spread over the
  // scene; a new command a moment later, after its callout.
  const lead = (s: Step) => (s.note ? Math.round(NOTE_LEAD * fps) : 0);
  const marks = steps.map((s, i) =>
    s.beat !== undefined
      ? (beats[Math.min(s.beat, beats.length - 1)] ?? 0) + Math.round((s.delay ?? 0) * fps)
      : Math.round((s.at ?? 0.04 + (0.76 * i) / Math.max(1, steps.length)) * D));
  const starts = steps.map((s, i) => marks[i] + lead(s));
  const rows: React.ReactNode[] = history.map((l, i) => (
    <div key={`h${i}`} style={{ height: LINE, whiteSpace: "pre" }}><Markup text={l} /></div>
  ));
  let dir = cwd;
  let inNix = nix;
  let cursorShown = false;
  steps.forEach((s, i) => {
    const t0 = starts[i];
    if (f < t0) return;
    const cps = s.typed ?? 22;
    const completeFrame = t0 + Math.round((s.completeIn ?? 0) * fps);
    const completed = s.complete !== undefined && f >= completeFrame;
    const cmd = (s.cmd ?? "") + (completed ? s.complete : "");
    const base = (s.cmd ?? "").length;
    const typedChars = completed ? cmd.length : Math.min(base, Math.floor(((f - t0) / fps) * cps));
    const typingDone = typedChars >= cmd.length;
    const outAt = s.complete !== undefined
      ? Math.max(t0 + Math.ceil((base / cps) * fps), completeFrame) + 20
      : t0 + Math.ceil((base / cps) * fps) + (s.noPrompt ? 0 : 9);
    if (!s.noPrompt) {
      rows.push(<Prompt key={`p${i}`} cwd={dir} who={who} nix={inNix} />);
      rows.push(
        <div key={`c${i}`} style={{ height: LINE, whiteSpace: "pre" }}>
          <span style={{ color: C.amber }}>{"> "}</span>
          <span>{cmd.slice(0, typedChars)}</span>
          {!typingDone || f < outAt ? <span style={{ background: C.text, color: C.ink }}> </span> : null}
        </div>,
      );
      if (!typingDone || f < outAt) cursorShown = true;
    }
    if (f >= outAt && s.out !== undefined) {
      const lines = Array.isArray(s.out) ? s.out : s.out.split("\n");
      lines.forEach((l, j) => rows.push(<div key={`o${i}_${j}`} style={{ height: LINE, whiteSpace: "pre" }}><Markup text={l} /></div>));
    }
    if (s.cd && f >= outAt) dir = s.cd;
    if (s.nix !== undefined && f >= outAt) inNix = s.nix;
  });
  // The next, empty prompt once everything so far is done.
  if (!cursorShown && !busy && f >= (starts[0] ?? 0)) {
    rows.push(<Prompt key="pz" cwd={dir} who={who} nix={inNix} />);
    rows.push(
      <div key="cz" style={{ height: LINE }}>
        <span style={{ color: C.amber }}>{"> "}</span>
        {Math.floor(f / 15) % 2 === 0 ? <span style={{ background: C.text }}> </span> : null}
      </div>,
    );
  }
  const visible = Math.floor((h - 38 - 30) / LINE);
  const shown = rows.slice(Math.max(0, rows.length - visible));
  // A callout stays until a while after the output, or until the next one.
  const noted = steps.map((s, i) => ({ s, i })).filter(({ s }) => s.note);
  const callouts = noted.map(({ s, i }, k) => {
    const from = marks[i];
    const typedEnd = starts[i] + Math.ceil(((s.cmd ?? "").length / (s.typed ?? 22)) * fps);
    const next = k + 1 < noted.length ? marks[noted[k + 1].i] : Infinity;
    return { names: s.note as string[], from, to: Math.min(Math.max(from + 5 * fps, typedEnd + 2.5 * fps), next - 1, D - 1) };
  });
  const keyStep = steps.map((s, i) => ({ s, t: starts[i] + Math.round((s.keysIn ?? 0) * fps) })).filter(({ s }) => s.keys);
  return (
    <>
      <Window title={title ?? `Terminal: ${who}`} x={x} y={y} w={w} h={h}>
        <div style={{ padding: "14px 22px", fontFamily: MONO, fontSize, color: C.text, lineHeight: `${LINE}px` }}>{shown}</div>
      </Window>
      {on ? <OnHost host={on} /> : null}
      {callouts.map((c, i) => <Callout key={`n${i}`} {...c} />)}
      {keyStep.map(({ s, t }, i) => <Keys key={i} keys={s.keys!} from={t} dur={Math.max(45, Math.ceil(((s.cmd ?? "").length / (s.typed ?? 22)) * fps) + 40)} />)}
    </>
  );
};
