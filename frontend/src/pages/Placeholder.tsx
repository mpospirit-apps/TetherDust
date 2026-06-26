interface PlaceholderProps {
  title: string;
  blurb: string;
}

// Temporary section page used until each feature is built out in Phase 1.
export function Placeholder({ title, blurb }: PlaceholderProps) {
  return (
    <div className="page">
      <h1>{title}</h1>
      <div className="placeholder-card">
        <p className="muted">{blurb}</p>
      </div>
    </div>
  );
}
