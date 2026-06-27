import { useEffect, useRef, useState } from "react";
import { useTheme } from "../hooks/useTheme";

let counter = 0;

// Renders a Mermaid diagram from its source. Mermaid is loaded lazily (dynamic
// import) so it only enters the bundle for docs that actually contain a diagram,
// and re-rendered on theme change to match light/dark. On a parse error we fall
// back to showing the raw source (the pre-0.4.7 behaviour), never a broken SVG.
export function Mermaid({ chart }: { chart: string }) {
  const { theme } = useTheme();
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    void (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: theme === "dark" ? "dark" : "default",
        });
        counter += 1;
        const { svg, bindFunctions } = await mermaid.render(`mermaid-${counter}`, chart);
        if (cancelled || !ref.current) return;
        ref.current.innerHTML = svg;
        bindFunctions?.(ref.current);
      } catch {
        if (!cancelled) setError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart, theme]);

  if (error) {
    return (
      <pre className="mermaid-error">
        <code>{chart}</code>
      </pre>
    );
  }
  return <div className="mermaid" ref={ref} role="img" aria-label="diagram" />;
}
