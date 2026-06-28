import type { CSSProperties } from "react";

// Allows CSS custom properties (e.g. --star-color) in inline style objects.
type CSSVars = CSSProperties & Record<`--${string}`, string>;

const GLIMMERS: CSSProperties[] = [
	{ top: "12%", left: "8%", animationDuration: "4.2s" },
	{ top: "28%", left: "72%", animationDuration: "3.8s" },
	{ top: "65%", left: "15%", animationDuration: "5.1s" },
	{ top: "45%", left: "88%", animationDuration: "3.5s" },
	{ top: "80%", left: "45%", animationDuration: "4.8s" },
	{ top: "18%", left: "52%", animationDuration: "3.2s" },
	{ top: "72%", left: "78%", animationDuration: "4.5s" },
	{ top: "38%", left: "35%", animationDuration: "5.5s" },
];

const STARS: CSSVars[] = [
	{
		top: "calc(50% - 120px)",
		left: "calc(50% - 80px)",
		"--star-color": "var(--c-cyan)",
		"--star-delay": "0ms",
	},
	{
		top: "calc(50% + 60px)",
		left: "calc(50% - 220px)",
		"--star-color": "var(--c-pink)",
		"--star-delay": "4200ms",
	},
	{
		top: "calc(50% - 200px)",
		left: "calc(50% - 150px)",
		"--star-color": "var(--c-lime)",
		"--star-delay": "8500ms",
	},
	{
		top: "calc(50% + 150px)",
		left: "calc(50% + 50px)",
		"--star-color": "var(--c-red)",
		"--star-delay": "12800ms",
	},
	{
		top: "calc(50% - 50px)",
		left: "calc(50% + 100px)",
		"--star-color": "var(--c-orange)",
		"--star-delay": "17000ms",
	},
	{
		top: "calc(50% + 100px)",
		left: "calc(50% - 300px)",
		"--star-color": "var(--c-cyan)",
		"--star-delay": "21500ms",
	},
];

// Decorative animated backdrop (fairy-dust glimmers + shooting stars), ported
// from the legacy base template.
export function AuroraBackground() {
	return (
		<div className="glimmer-container" aria-hidden="true">
			{GLIMMERS.map((style) => (
				<div
					key={`${style.top}-${style.left}`}
					className="glimmer-dot"
					style={style}
				/>
			))}
			<div className="shooting-star-field">
				{STARS.map((style) => (
					<div
						key={`${style.top}-${style.left}`}
						className="shooting-star"
						style={style}
					/>
				))}
			</div>
		</div>
	);
}
