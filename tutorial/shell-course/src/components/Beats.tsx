import React, { createContext, useContext } from "react";
import { Sequence, useVideoConfig } from "remotion";

// A scene's beats: the frame each narration segment starts at (after the
// pause before it). Visuals start on a beat to stay in step with the voice.
export const BeatsContext = createContext<number[]>([0]);
export const useBeats = () => useContext(BeatsContext);

// The frame for "beat k, plus `delay` seconds"; or `at` (fraction of the
// scene); or `fallback`.
export const useStart = (o: { beat?: number; delay?: number; at?: number }, fallback = 0) => {
  const beats = useBeats();
  const { durationInFrames: D, fps } = useVideoConfig();
  if (o.beat !== undefined) return (beats[Math.min(o.beat, beats.length - 1)] ?? 0) + Math.round((o.delay ?? 0) * fps);
  if (o.at !== undefined) return Math.round(o.at * D);
  return fallback;
};

// Different visuals one after another, each from its beat: a terminal where
// `yazi` is typed, then yazi itself. Inside each, frames and beats count
// from its own start.
export const Phases: React.FC<{ phases: { beat: number; delay?: number; render: () => React.ReactNode }[] }> = ({ phases }) => {
  const beats = useBeats();
  const { durationInFrames: D, fps } = useVideoConfig();
  const starts = phases.map((p) => (beats[Math.min(p.beat, beats.length - 1)] ?? 0) + Math.round((p.delay ?? 0) * fps));
  starts[0] = 0;
  return (
    <>
      {phases.map((p, i) => {
        const from = starts[i];
        const to = i + 1 < phases.length ? starts[i + 1] : D;
        return (
          <Sequence key={i} from={from} durationInFrames={Math.max(1, to - from)} layout="none">
            <BeatsContext.Provider value={beats.map((b) => b - from)}>{p.render()}</BeatsContext.Provider>
          </Sequence>
        );
      })}
    </>
  );
};
