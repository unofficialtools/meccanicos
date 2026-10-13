// What the voice reads for each scene, segment by segment: `say` if the scene
// has one, else its text; "|" separates segments, `code` marks are dropped.
import { Scene, scenes } from "./script";

export { scenes };
export const spoken = (s: Scene): string[] => (s.say ?? s.text).split("|").map((t) => t.replace(/`/g, "").trim());
