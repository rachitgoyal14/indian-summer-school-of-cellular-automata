// useSliderFill.ts — paints the "filled" side of every range input in a subtree.
//
// A range input cannot colour the track up to its own value in CSS alone, and
// the sidebar has ten of them across six components. Rather than thread a
// `--pct` style prop through every call site — ten chances to forget one, and
// a slider that silently looks different from its neighbours — this sets the
// variable on the DOM node from one place.
//
// It repaints on every render (so externally-driven values, like a speed the
// server pushed back, stay correct) and on `input` (so a drag is live rather
// than lagging a state round-trip).

import { useEffect, type RefObject } from "react";

function paint(el: HTMLInputElement) {
  const min = Number(el.min || 0);
  const max = Number(el.max || 100);
  const span = max - min;
  const pct = span > 0 ? ((Number(el.value) - min) / span) * 100 : 0;
  el.style.setProperty("--pct", `${Math.max(0, Math.min(100, pct))}%`);
}

export function useSliderFill(root: RefObject<HTMLElement | null>) {
  // No dependency array: values change for reasons this hook cannot observe
  // (a server push, a panel expanding), and repainting ten nodes is far
  // cheaper than tracking why.
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const all = el.querySelectorAll<HTMLInputElement>('input[type="range"]');
    all.forEach(paint);
  });

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const onInput = (e: Event) => {
      const t = e.target as HTMLInputElement;
      if (t instanceof HTMLInputElement && t.type === "range") paint(t);
    };
    el.addEventListener("input", onInput);
    return () => el.removeEventListener("input", onInput);
  }, [root]);
}
