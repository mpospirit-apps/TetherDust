import { useEffect, useRef, useState } from "react";
import { type Theme, useTheme } from "../hooks/useTheme";

let counter = 0;

// mermaid.render() manipulates a shared, hidden DOM sandbox internally and is
// not safe to call concurrently — a doc with multiple ```mermaid fences (each
// its own <Mermaid> instance mounting at once) can otherwise race and corrupt
// each other's output. Chain every render through this queue so only one is
// ever in flight across the whole app.
let renderQueue: Promise<void> = Promise.resolve();

function queueRender<T>(fn: () => Promise<T>): Promise<T> {
	const result = renderQueue.then(fn, fn);
	renderQueue = result.then(
		() => undefined,
		() => undefined,
	);
	return result;
}

function cssVar(name: string): string {
	return getComputedStyle(document.documentElement)
		.getPropertyValue(name)
		.trim();
}

function withAlpha(hex: string, alpha: number): string {
	const clean = hex.replace("#", "");
	const r = Number.parseInt(clean.slice(0, 2), 16);
	const g = Number.parseInt(clean.slice(2, 4), 16);
	const b = Number.parseInt(clean.slice(4, 6), 16);
	return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Maps the TetherDust accent palette (tokens.css) onto mermaid's "base" theme
// hooks, read live off :root so diagrams stay in sync with the design tokens
// instead of duplicating hex values here.
function brandThemeVariables(theme: Theme) {
	const text = theme === "dark" ? "#f0ede8" : "#1a1a1a";
	const cyan = cssVar("--c-cyan");
	const pink = cssVar("--c-pink");
	const lime = cssVar("--c-lime");
	const orange = cssVar("--c-orange");
	const arrowColor = text;

	return {
		fontFamily: cssVar("--font"),
		textColor: text,
		lineColor: arrowColor,
		primaryColor: withAlpha(cyan, 0.14),
		primaryBorderColor: cyan,
		primaryTextColor: text,
		secondaryColor: withAlpha(pink, 0.14),
		secondaryBorderColor: pink,
		tertiaryColor: withAlpha(lime, 0.16),
		tertiaryBorderColor: lime,
		noteBkgColor: withAlpha(orange, 0.16),
		noteBorderColor: orange,
		noteTextColor: text,
		actorBkg: withAlpha(cyan, 0.14),
		actorBorder: cyan,
		actorTextColor: text,
		actorLineColor: arrowColor,
		signalColor: arrowColor,
		signalTextColor: text,
		labelBoxBkgColor: withAlpha(pink, 0.14),
		labelBoxBorderColor: pink,
		labelTextColor: text,
		loopTextColor: text,
		activationBkgColor: withAlpha(cyan, 0.2),
		activationBorderColor: cyan,
		sequenceNumberColor: text,
	};
}

// Renders a Mermaid diagram from its source. Mermaid is loaded lazily (dynamic
// import) so it only enters the bundle for docs that actually contain a diagram,
// and re-rendered on theme change so text colors stay legible in dark mode. On
// a parse error we fall back to showing the raw source (the pre-0.4.7
// behaviour), never a broken SVG.
export function Mermaid({ chart }: { chart: string }) {
	const { theme } = useTheme();
	const ref = useRef<HTMLDivElement>(null);
	const [error, setError] = useState(false);

	useEffect(() => {
		let cancelled = false;
		setError(false);
		void (async () => {
			try {
				const { svg, bindFunctions } = await queueRender(async () => {
					const mermaid = (await import("mermaid")).default;
					mermaid.initialize({
						startOnLoad: false,
						securityLevel: "strict",
						theme: "base",
						themeVariables: brandThemeVariables(theme),
					});
					counter += 1;
					return mermaid.render(`mermaid-${counter}`, chart);
				});
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
