import { describe, expect, it } from "vitest";
import { remarkWikiLink, type WikiLinkOptions } from "./wikilink";

// Minimal MDAST shape used to drive and inspect the transform.
interface TestNode {
	type: string;
	value?: string;
	url?: string;
	children?: TestNode[];
	data?: { hProperties?: Record<string, unknown> };
}

function runOnParagraph(text: string, opts: WikiLinkOptions): TestNode[] {
	const paragraph: TestNode = {
		type: "paragraph",
		children: [{ type: "text", value: text }],
	};
	const tree: TestNode = { type: "root", children: [paragraph] };
	remarkWikiLink(opts)(tree);
	return paragraph.children ?? [];
}

const opts: WikiLinkOptions = {
	sources: new Set(["Docs"]),
	currentSource: "Docs",
};

describe("remarkWikiLink", () => {
	it("rewrites [[Source/path|Display]] into a wikilink with an encoded URL", () => {
		const [node] = runOnParagraph("[[Docs/file.md|Display]]", opts);
		expect(node.type).toBe("link");
		expect(node.url).toBe("/docs/Docs/file.md");
		expect(node.data?.hProperties?.className).toBe("wikilink");
		expect(node.children?.[0].value).toBe("Display");
	});

	it("derives the display name and resolves bare [[Page.md]] against currentSource", () => {
		const [node] = runOnParagraph("[[Page.md]]", opts);
		expect(node.url).toBe("/docs/Docs/Page.md");
		expect(node.data?.hProperties?.className).toBe("wikilink");
		// Trailing ".md" stripped, folder dropped from the visible label.
		expect(node.children?.[0].value).toBe("Page");
	});

	it("percent-encodes path segments", () => {
		const [node] = runOnParagraph("[[Docs/my file.md|X]]", opts);
		expect(node.url).toBe("/docs/Docs/my%20file.md");
	});

	it("renders an unknown source as a non-interactive no-access span", () => {
		const [node] = runOnParagraph("[[Secret/x.md|Hidden]]", opts);
		expect(node.url).toBe("#");
		expect(node.data?.hProperties?.className).toBe("wikilink-noaccess");
		expect(node.children?.[0].value).toBe("Hidden");
	});

	it("renders a bare source reference with no file as no-access", () => {
		const [node] = runOnParagraph("[[Docs]]", opts);
		expect(node.data?.hProperties?.className).toBe("wikilink-noaccess");
	});

	it("preserves the text on either side of a match", () => {
		const nodes = runOnParagraph("before [[Docs/a.md|A]] after", opts);
		expect(nodes).toHaveLength(3);
		expect(nodes[0]).toMatchObject({ type: "text", value: "before " });
		expect(nodes[1].type).toBe("link");
		expect(nodes[2]).toMatchObject({ type: "text", value: " after" });
	});

	it("leaves text with no wikilinks unchanged", () => {
		const nodes = runOnParagraph("just some prose", opts);
		expect(nodes).toEqual([{ type: "text", value: "just some prose" }]);
	});
});
