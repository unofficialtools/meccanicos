import React from "react";
import { C, MONO } from "../theme";

// A desktop window: graphite title bar with the amber edge on top.
export const Window: React.FC<{ title: string; x?: number; y?: number; w?: number; h?: number; children: React.ReactNode; bg?: string }> = ({
  title, x = 110, y = 10, w = 1700, h = 740, children, bg = "#16181b",
}) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: h, background: bg, border: `1px solid ${C.line}`,
    borderTop: `4px solid ${C.amber}`, boxShadow: "0 18px 50px rgba(0,0,0,0.55)", overflow: "hidden", display: "flex", flexDirection: "column" }}>
    <div style={{ height: 38, background: "#2c2c2c", display: "flex", alignItems: "center", padding: "0 18px", fontFamily: MONO, fontSize: 18, color: C.dim, flexShrink: 0 }}>
      <span style={{ fontWeight: 700, color: C.text }}>{title}</span>
      <span style={{ marginLeft: "auto", letterSpacing: 18 }}>– □ ×</span>
    </div>
    <div style={{ position: "relative", flex: 1, overflow: "hidden" }}>{children}</div>
  </div>
);
