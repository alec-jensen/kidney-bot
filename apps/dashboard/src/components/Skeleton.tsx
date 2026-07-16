interface SkeletonProps {
  /** Number of pulsing bar rows to render. */
  rows?: number;
}

/** Simple pulsing placeholder bars, used instead of "Loading…" text. */
export function Skeleton({ rows = 4 }: SkeletonProps) {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div className="skeleton-bar" key={i} style={{ width: `${85 - (i % 3) * 12}%` }} />
      ))}
    </div>
  );
}

/** Grid of pulsing placeholder cards, used for the guild grid while it loads. */
export function SkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="guild-grid">
      {Array.from({ length: count }).map((_, i) => (
        <div className="guild-card guild-card--skeleton" key={i} aria-busy="true" aria-label="Loading">
          <div className="skeleton-circle" />
          <div className="skeleton-bar" style={{ width: "70%", margin: "0 auto 8px" }} />
          <div className="skeleton-bar" style={{ width: "50%", margin: "0 auto" }} />
        </div>
      ))}
    </div>
  );
}
