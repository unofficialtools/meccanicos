// Remotion's own headless Chrome can't run on NixOS (missing libraries), so
// render with the system's Chromium-based browser: $REMOTION_BROWSER, else
// the first of brave / chromium / google-chrome on PATH.
import { Config } from "@remotion/cli/config";
import { execSync } from "node:child_process";
import { realpathSync } from "node:fs";

const find = (): string | null => {
  if (process.env.REMOTION_BROWSER) return process.env.REMOTION_BROWSER;
  for (const name of ["brave", "chromium", "google-chrome"]) {
    try {
      return realpathSync(execSync(`command -v ${name}`, { shell: "/bin/sh" }).toString().trim());
    } catch {
      /* next */
    }
  }
  return null;
};
const browser = find();
if (browser) Config.setBrowserExecutable(browser);
Config.setVideoImageFormat("jpeg");
Config.setConcurrency(4);
