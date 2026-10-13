// The narration: every scene's text, spoken by Piper (offline), one WAV per
// segment ("|" in the text) into public/audio/<id>.<k>.wav, and their lengths
// into src/durations.json (the video times every scene by them). Only
// changed scenes are spoken again.
//   npm run voice        (PIPER_VOICE: the .onnx voice; MeccanicOS sets it)
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { build } from "esbuild";

const voice = process.env.PIPER_VOICE;
if (!voice) throw new Error("PIPER_VOICE is not set (the Piper .onnx voice file)");
const scale = process.env.LENGTH_SCALE ?? "0.95";

// The scenes come from src/script.tsx: bundle just enough to read them.
await build({
  entryPoints: ["src/narration.ts"], bundle: true, platform: "node", format: "esm",
  outfile: "out/narration.mjs", jsx: "automatic", logLevel: "error",
  external: ["react", "remotion"],
});
const { scenes, spoken } = await import(`../out/narration.mjs?${Date.now()}`);

for (const s of scenes) {
  const n = s.text.split("|").length;
  if (spoken(s).length !== n) throw new Error(`${s.id}: "say" has ${spoken(s).length} segments, "text" has ${n}`);
}
mkdirSync("public/audio", { recursive: true });
const durFile = "src/durations.json";
const old = existsSync(durFile) ? JSON.parse(readFileSync(durFile, "utf8")) : {};
const out = {};
let made = 0;
for (const s of scenes) {
  const parts = spoken(s);
  const hash = createHash("sha1").update(`${scale}|${voice}|${parts.join("|")}`).digest("hex").slice(0, 12);
  const wavs = parts.map((_, k) => `public/audio/${s.id}.${k}.wav`);
  if (old[s.id]?.hash === hash && wavs.every((w) => existsSync(w))) {
    out[s.id] = old[s.id];
    continue;
  }
  const secs = parts.map((text, k) => {
    execFileSync("piper", ["-m", voice, "--length-scale", scale, "--sentence-silence", "0.35", "-f", wavs[k]],
      { input: text, stdio: ["pipe", "ignore", "ignore"] });
    const b = readFileSync(wavs[k]);
    // A plain PCM WAV: byte rate at 28, the data chunk's size after "data".
    const rate = b.readUInt32LE(28);
    const data = b.indexOf("data");
    return Math.round((b.readUInt32LE(data + 4) / rate) * 100) / 100;
  });
  out[s.id] = { hash, parts: secs };
  made++;
  process.stdout.write(`\r${made} spoken (${s.id})                    `);
}
writeFileSync(durFile, JSON.stringify(out, null, 1) + "\n");
const total = Object.values(out).reduce((a, d) => a + d.parts.reduce((x, y) => x + y, 0), 0);
console.log(`\n${scenes.length} scenes, ${made} new; narration ${Math.floor(total / 60)}:${String(Math.round(total % 60)).padStart(2, "0")}`);
