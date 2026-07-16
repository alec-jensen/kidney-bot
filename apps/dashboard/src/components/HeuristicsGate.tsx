import type { ReactNode } from "react";

/** Persistent (but unobtrusive) notice shown atop weights/thresholds pages when the engine itself is off. */
export function HeuristicsOffNotice({ children }: { children: ReactNode }) {
  return <div className="notice notice--info">{children}</div>;
}
