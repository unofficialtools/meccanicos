import React from "react";
import { C, MONO, SANS } from "../theme";

// The last page: every mos-fleet command on one sheet.
const SHEET: [string, [string, string][]][] = [
  ["The server", [["server init --domain D --organization O --lan NET", "set it up (again: safe)"], ["server status", "every service ok?"], ["person add / password / reset", "people"], ["member add PROFILE NAME", "who logs in where"]]],
  ["Your computer", [["connect you@hq", "the kit, ~/fleet"], ["admin-key", "back it up, on paper"], ["profile add NAME", "a kind of computer"], ["doctor", "check everything"]]],
  ["A new computer", [["prepare NAME --profile P --unlock U", "files on the stick"], ["(install from the stick)", "organization install"], ["add NAME", "into the repository"], ["status [NAME]", "build, Fleet, version"]]],
  ["Changes", [["edit ~/fleet, git commit, git push", "every change"], ["upgrade [--testing]", "new MeccanicOS"], ["git revert C && git push", "undo"], ["retire NAME", "out of the fleet"]]],
  ["Trouble", [["recover NAME", "the recovery key"], ["journalctl -u comin", "on the computer"], ["journalctl -b -u NAME", "on the server"], ["boot menu: previous entry", "a bad update"]]],
];

export const Sheet: React.FC = () => (
  <div style={{ position: "absolute", left: 60, right: 60, top: 0, display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 16 }}>
    {SHEET.map(([title, rows]) => (
      <div key={title} style={{ background: C.base, borderTop: `4px solid ${C.amber}`, padding: "12px 16px", height: 740, boxSizing: "border-box" }}>
        <div style={{ fontFamily: MONO, color: C.amber, fontSize: 26, fontWeight: 700, marginBottom: 14 }}>{title}</div>
        {rows.map(([cmd, what]) => (
          <div key={cmd} style={{ marginBottom: 22 }}>
            <div style={{ fontFamily: MONO, fontSize: 22, color: C.text, lineHeight: 1.3 }}>{cmd}</div>
            <div style={{ fontFamily: SANS, fontSize: 21, color: C.dim }}>{what}</div>
          </div>
        ))}
      </div>
    ))}
  </div>
);
