// Panel.tsx — the one container every sidebar section uses.
//
// The sidebar reads as a single dark instrument surface rather than a stack of
// cards, so a panel draws no box of its own: it contributes a header bar, a
// hairline rule above itself, and a body. The continuous surface belongs to
// `.sidebar`; panels only divide it.
//
// Before this existed each section rolled its own heading — some `<h2>`, one a
// collapsible button, one a non-collapsible imitation of that button — which
// is what made the sidebar look like several people had designed it.

import { useState, type ReactNode } from "react";

export function Panel({
  title,
  hint,
  badge,
  defaultOpen = false,
  children,
}: {
  title: string;
  /** One line shown in place of the body while collapsed. */
  hint?: string;
  /**
   * A live readout pinned to the header, visible whether or not the panel is
   * open — for a value worth watching without expanding the section.
   */
  badge?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={`panel ${open ? "is-open" : "is-closed"}`}>
      <button
        className="panel-head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="panel-title">{title}</span>
        {badge && <span className="panel-badge">{badge}</span>}
        <span className="panel-chevron" aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      {!open && hint && <div className="panel-collapsed-hint">{hint}</div>}
      {open && <div className="panel-body">{children}</div>}
    </section>
  );
}

/**
 * A labelled group inside a panel body — what the old `<h3>` sub-headings
 * were. Distinct from `Panel`'s own header: it never collapses and sits at a
 * lower level in the type hierarchy.
 */
export function Subsection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="subsection">
      <div className="subhead">{title}</div>
      {children}
    </div>
  );
}
