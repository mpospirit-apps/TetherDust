import { siGithub, siGitlab } from "simple-icons";

export interface ProviderMeta {
	icon?: { title: string; path: string };
	faIcon?: string;
	blurb: string;
}

export const PROVIDER_META: Record<string, ProviderMeta> = {
	github: {
		icon: { title: siGithub.title, path: siGithub.path },
		blurb: "Public or private GitHub repository.",
	},
	gitlab: {
		icon: { title: siGitlab.title, path: siGitlab.path },
		blurb:
			"Public or private GitLab.com repository (self-managed instances aren't supported).",
	},
	local: {
		faIcon: "fa-folder-open",
		blurb:
			"A folder placed under sources/codebases/ on the server. Read live from disk and searched semantically — no clone, no token.",
	},
};

export const DEFAULT_PROVIDER_META: ProviderMeta = {
	faIcon: "fa-code-branch",
	blurb: "",
};

function ProviderIconGlyph({
	icon,
	className,
}: {
	icon: { title: string; path: string };
	className?: string;
}) {
	return (
		<span
			className={`choice-card__icon choice-card__icon--logo ${className ?? ""}`}
		>
			<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
				<title>{icon.title}</title>
				<path d={icon.path} />
			</svg>
		</span>
	);
}

export function ProviderGlyph({
	meta,
	className,
}: {
	meta: ProviderMeta;
	className?: string;
}) {
	if (meta.faIcon) {
		return (
			<span className={`choice-card__icon ${className ?? ""}`}>
				<i className={`fa-solid ${meta.faIcon}`} />
			</span>
		);
	}
	if (meta.icon)
		return <ProviderIconGlyph icon={meta.icon} className={className} />;
	return null;
}
