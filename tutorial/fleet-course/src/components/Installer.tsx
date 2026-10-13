import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO } from "../theme";
import { useBeats } from "./Beats";
import { Markup } from "./Markup";
import { Window } from "./Window";

// mos-install, as on screen (a full-screen terminal program), in its
// organization mode: the form, then the checks (the fleet server's key,
// Tang), the unlocking, the installation (from the stick), and the new
// computer's SSH fingerprint. Each stage starts on a beat.
const UNLOCK = {
  tang: "automatic on the office network (Tang server + this PC's TPM)",
  "tpm-pin": "a PIN at power-on (this PC's TPM chip)",
  fido2: "a FIDO2 security key at power-on",
} as const;

export const Installer: React.FC<{
  host: string; unlock: keyof typeof UNLOCK; fp?: string;
  at: { form?: number; install?: number; checks?: number; unlock?: number; download?: number; done?: number };
}> = ({ host, unlock, at, fp = "SHA256:Qm4x…7Ka0" }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const beats = useBeats();
  const b = (k?: number) => (k === undefined ? 10 ** 9 : beats[Math.min(k, beats.length - 1)] ?? 0);
  const fields: [string, string, boolean?][] = [
    ["Organization", "Example Corp", true],
    ["Computer", `${host}, profile office`, true],
    ["Country", "Italy"],
    ["Language", "English (United States)"],
    ["Time zone", "Europe/Rome"],
    ["Keyboard", "Italian"],
    ["Screen", "Landscape"],
    ["Wi-Fi network", unlock === "tang" ? "(none: a network cable)" : "Corp-Office"],
    ...(unlock === "tpm-pin" ? [["Disk PIN", "••••••"] as [string, string]] : []),
    ["Target disk", "nvme0n1  477G Samsung SSD 980 PRO"],
    ["Filesystem", `encrypted; unlock: ${UNLOCK[unlock]}`, true],
  ];
  const sel = Math.min(fields.length - 1, 2 + Math.floor(Math.max(0, f - b(at.form)) / (0.5 * fps)));
  const installing = f >= b(at.install);
  const log: string[] = [];
  if (installing) log.push("Type YES to erase nvme0n1 and install: {a}YES{/}");
  if (f >= b(at.checks)) {
    const names = ["fleet server hq.corp.example.com (its key matches)", ...(unlock === "tang" ? ["Tang  http://hq.corp.example.com:7654"] : [])];
    const n = Math.floor((f - b(at.checks)) / 10);
    names.slice(0, n).forEach((x) => log.push(`  {g}ok{/}  ${x}`));
  }
  if (f >= b(at.unlock)) {
    log.push(unlock === "tang" ? "Disk: bound to Tang (hq.corp.example.com) and this PC's TPM"
      : unlock === "tpm-pin" ? "Disk: sealed to this PC's TPM, with your PIN"
      : "Disk: touch the security key now… {g}done{/}");
    log.push("Recovery key: encrypted for the admins (on the stick, and for the server)");
  }
  if (f >= b(at.download)) {
    const p = interpolate(f, [b(at.download), b(at.download) + 4 * fps], [0, 1], { extrapolateRight: "clamp" });
    const bar = "█".repeat(Math.round(p * 30)).padEnd(30, "░");
    log.push(`Installing MeccanicOS (from the stick)`);
    log.push(`  ${bar} ${Math.round(p * 100)}%`);
  }
  if (f >= b(at.done)) {
    log.push(`{g}Done.{/} This computer's SSH key: {a}${fp}{/}`);
    log.push(`(the admin compares it in: mos-fleet host add ${host})`);
    log.push("Remove the stick and restart.");
  }
  return (
    <Window title="Install MeccanicOS" x={260} y={0} w={1400} h={760}>
      <div style={{ fontFamily: MONO, fontSize: 25, color: C.text, lineHeight: "36px" }}>
        <div style={{ background: "#202326", padding: "4px 18px" }}><span style={{ color: C.amber }}>MOS //</span> MeccanicOS installer</div>
        {!installing ? (
          <div style={{ paddingTop: 14 }}>
            {fields.map(([k, v, dim], i) => (
              <div key={k} style={{ display: "flex", padding: "0 18px", background: i === sel ? C.amber : undefined, color: i === sel ? C.ink : dim ? C.dim : C.text }}>
                <span style={{ width: 250 }}>{k}</span><span>{v}</span>
              </div>
            ))}
            <div style={{ margin: "22px auto 0", width: 220, textAlign: "center", background: "#3a3d40" }}>Install now</div>
          </div>
        ) : (
          <div style={{ padding: "16px 22px" }}>
            <div style={{ color: C.amber }}>Organization install: {host} (office) for Example Corp</div>
            {log.map((l, i) => <div key={i} style={{ whiteSpace: "pre" }}><Markup text={l} /></div>)}
          </div>
        )}
      </div>
    </Window>
  );
};
