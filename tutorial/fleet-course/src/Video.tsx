import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { BeatsContext } from "./components/Beats";
import { Frame } from "./components/Frame";
import { Scene, scenes } from "./script";
import { FPS } from "./theme";
import durations from "./durations.json";

const D = durations as Record<string, { parts: number[] }>;
const LEAD = Math.round(0.35 * FPS); // before a scene's first words
const GAP = Math.round(1.1 * FPS); // the pause before each new segment: a new command
const PAD = 18; // a breath at the end of each scene

export const segmentsOf = (s: Scene) => s.text.split("|").map((t) => t.trim());
const spokenParts = (s: Scene) => (s.say ?? s.text).split("|").map((t) => t.trim());

// Each scene's timing: the beats (frame each segment starts), the segments'
// lengths, the total. From the narration's real lengths, or an estimate
// before `npm run voice`.
export const timing = scenes.map((s) => {
  const words = spokenParts(s);
  const secs = D[s.id]?.parts?.length === words.length ? D[s.id].parts : words.map((w) => w.split(/\s+/).length / 2.6);
  const lengths = secs.map((x) => Math.ceil(x * FPS));
  const beats: number[] = [];
  let t = LEAD;
  lengths.forEach((n, i) => {
    if (i > 0) t += GAP;
    beats.push(t);
    t += n;
  });
  return { beats, lengths, frames: Math.max(3 * FPS, t + PAD + (s.tail ?? 0)), voiced: !!D[s.id] };
});
export const totalFrames = timing.reduce((a, t) => a + t.frames, 0);

export const Video: React.FC = () => {
  let from = 0;
  return (
    <AbsoluteFill>
      {scenes.map((s, i) => {
        const at = from;
        const { beats, lengths, frames, voiced } = timing[i];
        from += frames;
        return (
          <Sequence key={s.id} from={at} durationInFrames={frames} name={s.id}>
            <BeatsContext.Provider value={beats}>
              <Frame chapter={s.chapter} segments={segmentsOf(s)} beats={beats} lengths={lengths} progress={(at + frames) / totalFrames}>
                {s.visual()}
              </Frame>
            </BeatsContext.Provider>
            {voiced
              ? beats.map((b, k) => (
                  <Sequence key={k} from={b} durationInFrames={lengths[k] + 2} layout="none">
                    <Audio src={staticFile(`audio/${s.id}.${k}.wav`)} />
                  </Sequence>
                ))
              : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
