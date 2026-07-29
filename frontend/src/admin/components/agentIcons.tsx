import {
	siAnthropic,
	siClaudecode,
	siOllama,
	siOpenrouter,
} from "simple-icons";

export type AgentIcon =
	| {
			kind: "logo";
			title: string;
			path: string;
			color: string;
			// Some brand colors are near-black (Anthropic, Ollama), which is
			// invisible against the dark-theme card background — flip them via
			// the existing `brand-icon-invert-dark` filter in dark mode. Vivid
			// colors (Claude's orange, OpenRouter's slate) don't need this.
			invertDark?: boolean;
	  }
	| { kind: "img"; src: string; alt: string }
	| { kind: "fa"; family: "solid" | "brands"; icon: string };

// Simple Icons dropped OpenAI's mark (trademark request), so Codex/OpenAI
// types fall back to the official PNG under public/images/brand-icons —
// inverted in dark mode via `brand-icon-invert-dark` since it's a black
// mark on a white background.
const OPENAI_ICON: AgentIcon = {
	kind: "img",
	src: "/images/brand-icons/openai.png",
	alt: "OpenAI",
};

const CLAUDE_CODE_ICON: AgentIcon = {
	kind: "logo",
	title: siClaudecode.title,
	path: siClaudecode.path,
	color: siClaudecode.hex,
};

export const AGENT_TYPE_ICONS: Record<string, AgentIcon> = {
	codex: OPENAI_ICON,
	codex_api: OPENAI_ICON,
	openai_platform: OPENAI_ICON,
	// "OpenAI-compatible API (Custom)" — any base URL, but it's still the
	// OpenAI protocol/brand, so it gets the same mark rather than a generic
	// fallback icon.
	openai_api: OPENAI_ICON,
	claude_code: CLAUDE_CODE_ICON,
	claude_code_api: CLAUDE_CODE_ICON,
	claude_console: {
		kind: "logo",
		title: siAnthropic.title,
		path: siAnthropic.path,
		color: siAnthropic.hex,
		invertDark: true,
	},
	ollama: {
		kind: "logo",
		title: siOllama.title,
		path: siOllama.path,
		color: siOllama.hex,
		invertDark: true,
	},
	openrouter: {
		kind: "logo",
		title: siOpenrouter.title,
		path: siOpenrouter.path,
		color: siOpenrouter.hex,
	},
};

export const DEFAULT_AGENT_ICON: AgentIcon = {
	kind: "fa",
	family: "solid",
	icon: "fa-plug",
};

export function AgentIconGlyph({
	icon,
	className,
}: {
	icon: AgentIcon;
	className?: string;
}) {
	if (icon.kind === "logo") {
		return (
			<span
				className={`choice-card__icon choice-card__icon--logo${
					icon.invertDark ? " brand-icon-invert-dark" : ""
				} ${className ?? ""}`}
				style={{ color: `#${icon.color}` }}
			>
				<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
					<title>{icon.title}</title>
					<path d={icon.path} />
				</svg>
			</span>
		);
	}
	if (icon.kind === "img") {
		return (
			<span
				className={`choice-card__icon choice-card__icon--logo ${className ?? ""}`}
			>
				<img src={icon.src} alt={icon.alt} className="brand-icon-invert-dark" />
			</span>
		);
	}
	return (
		<i
			className={`fa-${icon.family} ${icon.icon} choice-card__icon ${className ?? ""}`}
		/>
	);
}
