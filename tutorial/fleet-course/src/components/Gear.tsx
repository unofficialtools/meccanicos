import React from "react";
import { useCurrentFrame } from "remotion";
import { C } from "../theme";

// A spur gear: `teeth` teeth around radius r, turning `speed` degrees a frame.
export const gearPath = (r: number, teeth: number) => {
  const inner = r * 0.82;
  const pts: string[] = [];
  for (let i = 0; i < teeth; i++) {
    const a = (i / teeth) * Math.PI * 2;
    const step = (Math.PI * 2) / teeth;
    const p = (ang: number, rad: number) => `${(Math.cos(ang) * rad).toFixed(2)},${(Math.sin(ang) * rad).toFixed(2)}`;
    pts.push(p(a - step * 0.25, inner), p(a - step * 0.15, r), p(a + step * 0.15, r), p(a + step * 0.25, inner));
  }
  return `M${pts.join("L")}Z`;
};

export const Gear: React.FC<{
  x: number; y: number; r: number; teeth?: number; speed?: number; color?: string; hole?: string; phase?: number; opacity?: number;
}> = ({ x, y, r, teeth = 12, speed = 0.6, color = C.amber, hole = C.ink, phase = 0, opacity = 1 }) => {
  const f = useCurrentFrame();
  return (
    <g transform={`translate(${x} ${y}) rotate(${phase + f * speed})`} opacity={opacity}>
      <path d={gearPath(r, teeth)} fill={color} />
      <circle r={r * 0.32} fill={hole} />
      <circle r={r * 0.12} fill={color} />
    </g>
  );
};
