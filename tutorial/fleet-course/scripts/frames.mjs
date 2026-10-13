// Prints "id startFrame length beat0,beat1,..." for every scene (for stills and checks).
import { build } from "esbuild";
await build({
  entryPoints: ["src/Video.tsx"], bundle: true, platform: "node", format: "esm", outfile: "out/timing.mjs",
  jsx: "automatic", logLevel: "error", external: ["react", "remotion"], loader: { ".json": "json" },
});
const { scenes } = await import(`../out/narration.mjs?${Date.now()}`);
const { timing } = await import(`../out/timing.mjs?${Date.now()}`);
let at = 0;
scenes.forEach((s, i) => {
  console.log(s.id, at, timing[i].frames, timing[i].beats.join(","));
  at += timing[i].frames;
});
