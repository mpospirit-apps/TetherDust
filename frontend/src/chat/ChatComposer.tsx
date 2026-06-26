import { useQuery } from "@tanstack/react-query";
import { Fragment, useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  listChatPrompts,
  searchDocSources,
  type ChatPrompt,
  type DocResource,
} from "../api/chat";

type Chip = { kind: "doc"; res: DocResource } | { kind: "prompt"; prompt: ChatPrompt };

interface Props {
  connected: boolean;
  streaming: boolean;
  onSend: (text: string, resources: DocResource[], prompts: ChatPrompt[]) => void;
  onCancel: () => void;
}

// Matches `@partial` / `/partial` at the caret (legacy slash-commands.js regex).
function contextAt(value: string, pos: number, trigger: "@" | "/") {
  const text = value.substring(0, pos);
  const re = trigger === "@" ? /(?:^|\s)@([^\s]*)$/ : /(?:^|\s)\/([^\s]*)$/;
  const match = text.match(re);
  if (!match) return null;
  const partial = match[1];
  return { partial, startIndex: pos - partial.length };
}

const Arrow = () => (
  <span className="source-arrow">
    <i className="fa-solid fa-chevron-right" />
  </span>
);

// Chat input box with `@`-mention (doc-source) and `/`-prompt autocomplete +
// selected-item chips. Ports the legacy mention-chips / slash-commands UX; the
// chosen resources/prompts ride along the WS message as
// resource_uris/sources_info/prompt_context/prompts_info.
export function ChatComposer({ connected, streaming, onSend, onCancel }: Props) {
  const [text, setText] = useState("");
  const [chips, setChips] = useState<Chip[]>([]);
  const [mode, setMode] = useState<"doc" | "prompt" | null>(null);
  const [docItems, setDocItems] = useState<DocResource[]>([]);
  const [promptItems, setPromptItems] = useState<ChatPrompt[]>([]);
  const [loading, setLoading] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const promptsQuery = useQuery({
    queryKey: ["chat", "prompts"],
    queryFn: listChatPrompts,
    staleTime: 60_000,
  });
  const allPrompts = promptsQuery.data?.prompts ?? [];

  useEffect(() => () => clearTimeout(debounceRef.current ?? undefined), []);

  const activeItems: (DocResource | ChatPrompt)[] = mode === "doc" ? docItems : promptItems;

  function close() {
    clearTimeout(debounceRef.current ?? undefined);
    setMode(null);
    setDocItems([]);
    setPromptItems([]);
    setHint(null);
    setLoading(false);
    setSelected(0);
  }

  function searchDocs(query: string) {
    clearTimeout(debounceRef.current ?? undefined);
    setMode("doc");
    setLoading(true);
    setHint(null);
    setDocItems([]);
    debounceRef.current = setTimeout(async () => {
      let results: DocResource[] = [];
      try {
        results = (await searchDocSources(query)).resources;
      } catch {
        results = [];
      }
      const ta = textareaRef.current;
      const ctx = ta ? contextAt(ta.value, ta.selectionStart ?? 0, "@") : null;
      if (!ctx || !results.length) {
        close();
        return;
      }
      setDocItems(results.slice(0, 20));
      setSelected(0);
      setLoading(false);
      setMode("doc");
    }, 250);
  }

  // Recompute the dropdown from the value + caret (runs on every input edit).
  function refreshAutocomplete(value: string, cursor: number) {
    const promptCtx = contextAt(value, cursor, "/");
    if (promptCtx) {
      if (promptsQuery.isLoading) {
        setMode("prompt");
        setLoading(true);
        setHint(null);
        return;
      }
      const partial = promptCtx.partial.toLowerCase();
      const filtered = allPrompts.filter(
        (p) =>
          p.display_name.toLowerCase().includes(partial) ||
          p.name.toLowerCase().includes(partial),
      );
      if (filtered.length) {
        setMode("prompt");
        setPromptItems(filtered.slice(0, 20));
        setSelected(0);
        setLoading(false);
        setHint(null);
        return;
      }
    }

    const docCtx = contextAt(value, cursor, "@");
    if (!docCtx) {
      close();
      return;
    }
    if (!docCtx.partial) {
      setMode("doc");
      setDocItems([]);
      setLoading(false);
      setHint("Type to search docs…");
      return;
    }
    searchDocs(docCtx.partial);
  }

  function addResource(res: DocResource) {
    setChips((cs) =>
      cs.some((c) => c.kind === "doc" && c.res.uri === res.uri) ? cs : [...cs, { kind: "doc", res }],
    );
  }
  function addPrompt(prompt: ChatPrompt) {
    setChips((cs) =>
      cs.some((c) => c.kind === "prompt" && c.prompt.name === prompt.name)
        ? cs
        : [...cs, { kind: "prompt", prompt }],
    );
  }
  function removeChip(target: Chip) {
    setChips((cs) =>
      cs.filter((c) =>
        c.kind === "doc"
          ? !(target.kind === "doc" && c.res.uri === target.res.uri)
          : !(target.kind === "prompt" && c.prompt.name === target.prompt.name),
      ),
    );
  }

  // Strip the `@partial` / `/partial` trigger from the textarea, then add a chip.
  function applySelection(trigger: "@" | "/", makeChip: () => void) {
    const ta = textareaRef.current;
    if (!ta) {
      close();
      return;
    }
    const value = ta.value;
    const cursor = ta.selectionStart ?? value.length;
    const ctx = contextAt(value, cursor, trigger);
    if (!ctx) {
      close();
      return;
    }
    let triggerStart = ctx.startIndex - 1;
    if (triggerStart > 0 && value[triggerStart - 1] === " ") triggerStart--;
    const before = value.substring(0, Math.max(triggerStart, 0));
    const after = value.substring(cursor);
    setText((before + after).trim());
    makeChip();
    close();
    requestAnimationFrame(() => {
      const t = textareaRef.current;
      if (t) {
        t.focus();
        t.setSelectionRange(t.value.length, t.value.length);
      }
    });
  }

  function choose(index: number) {
    if (mode === "doc") {
      const res = docItems[index];
      if (res) applySelection("@", () => addResource(res));
    } else if (mode === "prompt") {
      const p = promptItems[index];
      if (p) applySelection("/", () => addPrompt(p));
    }
  }

  function submit() {
    const value = text.trim();
    if (!value || streaming || !connected) return;
    onSend(
      value,
      chips.flatMap((c) => (c.kind === "doc" ? [c.res] : [])),
      chips.flatMap((c) => (c.kind === "prompt" ? [c.prompt] : [])),
    );
    setText("");
    setChips([]);
    close();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (mode) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSelected((i) => Math.min(i + 1, activeItems.length - 1));
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelected((i) => Math.max(i - 1, 0));
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        if (activeItems.length) choose(selected);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
    }
    if (event.key === "Backspace" && !text && chips.length) {
      event.preventDefault();
      setChips((cs) => cs.slice(0, -1));
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      className="chat-input"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="chat-composer">
        {mode && (
          <div className="slash-autocomplete">
            {loading ? (
              <div className="slash-autocomplete-loading">
                <i className="fa-solid fa-spinner fa-spin" />
              </div>
            ) : hint ? (
              <div className="slash-autocomplete-hint">{hint}</div>
            ) : mode === "doc" ? (
              docItems.map((res, i) => (
                <div
                  key={res.uri}
                  className={`slash-autocomplete-item${i === selected ? " selected" : ""}`}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(i);
                  }}
                  onMouseEnter={() => setSelected(i)}
                >
                  <span className="source-name">{res.name}</span>
                  <span className="source-desc">
                    {res.source_name}
                    <Arrow />
                    {res.path.split("/").map((seg, idx) => (
                      <Fragment key={idx}>
                        {idx > 0 && <Arrow />}
                        {seg}
                      </Fragment>
                    ))}
                  </span>
                </div>
              ))
            ) : (
              promptItems.map((p, i) => (
                <div
                  key={p.name}
                  className={`slash-autocomplete-item prompt-item${i === selected ? " selected" : ""}`}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(i);
                  }}
                  onMouseEnter={() => setSelected(i)}
                >
                  <span className="source-name">{p.display_name}</span>
                  <span className="source-desc">{p.name}</span>
                </div>
              ))
            )}
          </div>
        )}

        <div className="mention-chips">
          {chips.map((c) =>
            c.kind === "doc" ? (
              <span key={`d:${c.res.uri}`} className="mention-chip">
                <span className="mention-chip-prefix">@</span>
                <span className="mention-chip-label">{c.res.name}</span>
                <button
                  type="button"
                  className="mention-chip-remove"
                  tabIndex={-1}
                  onClick={() => removeChip(c)}
                >
                  ×
                </button>
              </span>
            ) : (
              <span key={`p:${c.prompt.name}`} className="mention-chip mention-chip-prompt">
                <span className="mention-chip-prefix">/</span>
                <span className="mention-chip-label">{c.prompt.display_name}</span>
                <button
                  type="button"
                  className="mention-chip-remove"
                  tabIndex={-1}
                  onClick={() => removeChip(c)}
                >
                  ×
                </button>
              </span>
            ),
          )}
        </div>

        <textarea
          ref={textareaRef}
          className="form-control"
          rows={2}
          placeholder={connected ? "Message the agent…  (@ for docs, / for prompts)" : "Connecting…"}
          value={text}
          disabled={!connected}
          onChange={(e) => {
            setText(e.target.value);
            refreshAutocomplete(e.target.value, e.target.selectionStart ?? e.target.value.length);
          }}
          onKeyDown={onKeyDown}
        />
      </div>
      {streaming ? (
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Stop
        </button>
      ) : (
        <button type="submit" className="btn btn-primary" disabled={!connected || !text.trim()}>
          Send
        </button>
      )}
    </form>
  );
}
