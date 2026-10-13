import React from "react";
import { C } from "../theme";

// Coloured text in a line: {a}amber{/} {d}dim{/} {g}green{/} {b}blue{/}
// {r}red{/} {t}teal{/} {s}sand{/} {w}bright{/} {B}bold{/}.
const COLORS: Record<string, React.CSSProperties> = {
  a: { color: C.amber }, d: { color: C.dim }, g: { color: C.green }, b: { color: C.blue, fontWeight: 700 },
  r: { color: C.red }, t: { color: C.tealHi }, s: { color: C.sand }, w: { color: "#ffffff" }, B: { fontWeight: 700 },
};
export const Markup: React.FC<{ text: string }> = ({ text }) => {
  const parts = text.split(/(\{[adgbrtswB]\}.*?\{\/\})/);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\{([adgbrtswB])\}(.*)\{\/\}$/);
        return m ? <span key={i} style={COLORS[m[1]]}>{m[2]}</span> : <span key={i}>{p}</span>;
      })}
    </>
  );
};
export const plain = (text: string) => text.replace(/\{[adgbrtswB]\}|\{\/\}/g, "");
