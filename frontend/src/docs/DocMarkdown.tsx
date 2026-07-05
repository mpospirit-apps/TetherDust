import {
	type ComponentProps,
	isValidElement,
	type ReactNode,
	useMemo,
} from "react";
import Markdown from "react-markdown";
import { useNavigate } from "react-router-dom";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import { CodeBlock, type PreProps } from "./CodeBlock";
import { Mermaid } from "./Mermaid";
import { remarkWikiLink } from "./wikilink";

type MarkdownProps = ComponentProps<typeof Markdown>;
type AnchorProps = ComponentProps<"a"> & { node?: unknown };

// `mermaid` fences are kept as raw text (rehype-highlight `plainText`) so this
// can read the source straight off the <code> child instead of un-highlighted
// spans.
function mermaidSource(children: ReactNode): string | null {
	if (!isValidElement(children)) return null;
	const props = children.props as { className?: string; children?: ReactNode };
	if (!props.className || !/\blanguage-mermaid\b/.test(props.className))
		return null;
	return String(props.children ?? "").replace(/\n$/, "");
}

// Render a ```mermaid fence as an SVG diagram; every other fenced block stays a
// normal highlighted <pre> with a copy button.
function DocPre({ node: _node, children, ...rest }: PreProps) {
	const chart = mermaidSource(children);
	if (chart) return <Mermaid chart={chart} />;
	return <CodeBlock {...rest}>{children}</CodeBlock>;
}

// Anchor renderer: WikiLinks and other in-app `/docs/...` hrefs navigate via the
// router (no reload); "no access" wikilinks render inert; everything else opens
// in a new tab.
function DocLink({ href, className, title, children }: AnchorProps) {
	const navigate = useNavigate();
	if (className?.includes("wikilink-noaccess")) {
		return (
			<span className="wikilink-noaccess" title={title}>
				{children}
			</span>
		);
	}
	if (href?.startsWith("/docs/")) {
		return (
			<a
				href={href}
				className={className ?? "wikilink"}
				onClick={(event) => {
					event.preventDefault();
					navigate(href);
				}}
			>
				{children}
			</a>
		);
	}
	return (
		<a href={href} className={className} target="_blank" rel="noreferrer">
			{children}
		</a>
	);
}

export function DocMarkdown({
	content,
	sources,
	currentSource,
}: {
	content: string;
	sources: string[];
	currentSource: string;
}) {
	const remarkPlugins = useMemo(() => {
		const sourceSet = new Set(sources);
		return [
			remarkGfm,
			[remarkWikiLink, { sources: sourceSet, currentSource }],
		] as MarkdownProps["remarkPlugins"];
	}, [sources, currentSource]);

	return (
		<div className="docs-rendered">
			<Markdown
				remarkPlugins={remarkPlugins}
				rehypePlugins={[
					[rehypeHighlight, { ignoreMissing: true, plainText: ["mermaid"] }],
				]}
				components={{ a: DocLink, pre: DocPre }}
			>
				{content}
			</Markdown>
		</div>
	);
}

// Highlights a raw code-file by wrapping it in a fenced block (reusing the same
// rehype-highlight pipeline). The fence is chosen longer than any backtick run in
// the source so embedded fences can't break out.
export function DocCode({
	content,
	language,
}: {
	content: string;
	language: string;
}) {
	const fenced = useMemo(() => {
		let longestRun = 0;
		for (const match of content.matchAll(/`+/g)) {
			longestRun = Math.max(longestRun, match[0].length);
		}
		const fence = "`".repeat(Math.max(3, longestRun + 1));
		return `${fence}${language}\n${content}\n${fence}`;
	}, [content, language]);

	return (
		<div className="docs-rendered">
			<Markdown
				rehypePlugins={[[rehypeHighlight, { ignoreMissing: true }]]}
				components={{ pre: DocPre }}
			>
				{fenced}
			</Markdown>
		</div>
	);
}
