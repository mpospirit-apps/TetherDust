// Remark plugin porting the legacy Python `WikiLinkExtension` (workspace/views/docs.py).
// Rewrites `[[Source/path.md|Display]]` occurrences in Markdown text into links to
// SPA routes (`/docs/<source>/<path>`). Targets in an unknown/unauthorised source —
// or bare source references with no file — render as a non-interactive "no access"
// span, matching the server-rendered behaviour.

const WIKILINK_RE = /\[\[([^\]]+)\]\]/g;

interface MdNode {
	type: string;
	value?: string;
	url?: string;
	title?: string;
	children?: MdNode[];
	data?: { hProperties?: Record<string, unknown> };
}

export interface WikiLinkOptions {
	/** Folder names of sources the user can see (for access resolution). */
	sources: Set<string>;
	/** Folder of the page being rendered (resolves bare `[[Page.md]]` links). */
	currentSource: string;
}

function encodePath(filePath: string): string {
	return filePath
		.split("/")
		.map((segment) => encodeURIComponent(segment))
		.join("/");
}

function makeLink(raw: string, opts: WikiLinkOptions): MdNode {
	let linkPath: string;
	let display: string;
	const pipe = raw.indexOf("|");
	if (pipe !== -1) {
		linkPath = raw.slice(0, pipe);
		display = raw.slice(pipe + 1);
	} else {
		linkPath = raw;
		display = linkPath.split("/").pop() ?? linkPath;
		if (display.endsWith(".md")) display = display.slice(0, -3);
	}
	linkPath = linkPath.trim();
	display = display.trim();

	let folder: string;
	let filePath: string;
	const slash = linkPath.indexOf("/");
	if (slash !== -1) {
		folder = linkPath.slice(0, slash);
		filePath = linkPath.slice(slash + 1);
	} else if (linkPath.endsWith(".md") && opts.currentSource) {
		folder = opts.currentSource;
		filePath = linkPath;
	} else {
		folder = linkPath;
		filePath = "";
	}

	const hasAccess = opts.sources.has(folder) && filePath !== "";
	if (hasAccess) {
		const url = `/docs/${encodeURIComponent(folder)}/${encodePath(filePath)}`;
		return {
			type: "link",
			url,
			data: { hProperties: { className: "wikilink" } },
			children: [{ type: "text", value: display }],
		};
	}
	return {
		type: "link",
		url: "#",
		data: {
			hProperties: {
				className: "wikilink-noaccess",
				title: "This page doesn't exist or you don't have permission",
			},
		},
		children: [{ type: "text", value: display }],
	};
}

function splitText(value: string, opts: WikiLinkOptions): MdNode[] {
	const out: MdNode[] = [];
	let last = 0;
	for (const match of value.matchAll(WIKILINK_RE)) {
		const idx = match.index ?? 0;
		if (idx > last) out.push({ type: "text", value: value.slice(last, idx) });
		out.push(makeLink(match[1], opts));
		last = idx + match[0].length;
	}
	if (last < value.length) out.push({ type: "text", value: value.slice(last) });
	return out;
}

function transform(node: MdNode, opts: WikiLinkOptions): void {
	if (!node.children) return;
	const next: MdNode[] = [];
	for (const child of node.children) {
		if (child.type === "text" && child.value && child.value.includes("[[")) {
			next.push(...splitText(child.value, opts));
		} else {
			transform(child, opts);
			next.push(child);
		}
	}
	node.children = next;
}

export function remarkWikiLink(opts: WikiLinkOptions) {
	return (tree: MdNode): void => transform(tree, opts);
}
