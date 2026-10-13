import React from "react";
import { C, MONO, SANS } from "../theme";

// The last page: every mos-fleet command on one sheet.
const SHEET: [string, [string, string][]][] = [
  ["The server", [["server init --lan NET --admin-key KEY", "set it up (again: safe)"], ["server status", "every part running?"], ["server admin-key KEY", "a key in, for a day"], ["server backup DIR", "repository, databases, keys"]]],
  ["The repository", [["init / clone", "on your computer"], ["profile add NAME", "a kind of computer"], ["person add NAME \"N\" --group G", "people"], ["validate · diff · push", "check, see, send"]]],
  ["A new computer", [["host prepare NAME --profile P --unlock U", "the stick"], ["(install from the stick)", "organization install"], ["host pending · host add NAME", "compare its key"], ["status [NAME]", "online? up to date?"]]],
  ["Every day", [["edit, git commit, mos-fleet push", "every change"], ["password set NAME · mos-passwd", "passwords"], ["run · logs · shell", "on the computers"], ["upgrade [--testing]", "new MeccanicOS"]]],
  ["Trouble", [["recover NAME", "the recovery key"], ["builds NAME --log", "why it didn't build"], ["git revert C; mos-fleet push", "undo"], ["boot menu: previous entry", "a bad update"]]],
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
