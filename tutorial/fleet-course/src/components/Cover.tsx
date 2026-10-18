import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, MONO, SANS } from "../theme";

// The first slide: the MeccanicOS logo (branding/logo, public/logo links
// there), the tagline, and the video's title.
export const Cover: React.FC<{ tagline: string; title: string }> = ({ tagline, title }) => {
  const f = useCurrentFrame();
  const o = (from: number) => interpolate(f, [from, from + 15], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center" }}>
      <Img src={staticFile("logo/meccanicos-logo-white.svg")} style={{ width: 960, opacity: o(4) }} />
      <div style={{ fontFamily: MONO, fontSize: 32, color: C.amber, letterSpacing: "0.08em", marginTop: 40, opacity: o(14) }}>{tagline}</div>
      <div style={{ width: 160, height: 4, background: C.line, margin: "56px 0", opacity: o(24) }} />
      <div style={{ fontFamily: SANS, fontSize: 76, fontWeight: 800, color: C.text, maxWidth: 1500, lineHeight: 1.1, opacity: o(30) }}>{title}</div>
    </div>
  );
};
