import {
	type ComponentProps,
	isValidElement,
	type ReactNode,
	useRef,
	useState,
} from "react";

export type PreProps = ComponentProps<"pre"> & { node?: unknown };

// Reads the fence's language off the <code> child's `language-xxx` class,
// e.g. ```sql -> "sql". Returns null for fences with no declared language.
export function codeLanguage(children: ReactNode): string | null {
	if (!isValidElement(children)) return null;
	const props = children.props as { className?: string };
	return props.className?.match(/\blanguage-(\S+)\b/)?.[1] ?? null;
}

// Fenced code block with a language label and copy-to-clipboard button in the
// top-right corner. Reads the copy text off the rendered <pre>'s textContent
// rather than the React children, since highlighting wraps the source in
// nested token spans. Shared by the docs viewer and chat message rendering.
export function CodeBlock({ children, ...rest }: PreProps) {
	const ref = useRef<HTMLPreElement>(null);
	const [copied, setCopied] = useState(false);
	const language = codeLanguage(children);

	async function handleCopy() {
		const text = ref.current?.textContent ?? "";
		try {
			await navigator.clipboard.writeText(text);
			setCopied(true);
			setTimeout(() => setCopied(false), 1500);
		} catch {
			// Clipboard API unavailable (e.g. insecure context) — nothing to do.
		}
	}

	return (
		<div className="docs-code-block">
			<div className="docs-code-toolbar">
				{language && <span className="docs-code-lang">{language}</span>}
				<button
					type="button"
					className="docs-code-copy"
					onClick={handleCopy}
					aria-label={copied ? "Copied" : "Copy code"}
					title={copied ? "Copied" : "Copy code"}
				>
					<i className={copied ? "fa-solid fa-check" : "fa-solid fa-copy"} />
				</button>
			</div>
			<pre ref={ref} {...rest}>
				{children}
			</pre>
		</div>
	);
}
