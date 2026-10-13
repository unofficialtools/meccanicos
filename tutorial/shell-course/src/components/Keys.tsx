import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, MONO } from "../theme";

// Keys being pressed, as keycaps, top right of the stage: "Ctrl+R" -> [Ctrl] + [R].
export const Keys: React.FC<{ keys: string; from: number; dur?: number }> = ({ keys, from, dur = 60 }) => {
  const f = useCurrentFrame();
  if (f < from || f > from + dur) return null;
  const o = interpolate(f, [from, from + 5, from + dur - 6, from + dur], [0, 1, 1, 0]);
  return (
    <div style={{ position: "absolute", right: 70, top: 20, display: "flex", gap: 10, alignItems: "center", opacity: o, zIndex: 5 }}>
      {keys.split(/\s+/).map((combo, j) => (
        <React.Fragment key={j}>
          {j > 0 && <span style={{ color: C.dim, fontSize: 26, margin: "0 6px" }}>then</span>}
          {combo.split("+").map((k, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span style={{ color: C.dim, fontSize: 30 }}>+</span>}
              <span style={{ fontFamily: MONO, fontSize: 30, color: C.ink, background: C.text, borderRadius: 8,
                padding: "6px 16px", boxShadow: `0 5px 0 ${C.dim}` }}>{k}</span>
            </React.Fragment>
          ))}
        </React.Fragment>
      ))}
    </div>
  );
};
