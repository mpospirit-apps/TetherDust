import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatPrompt, DocResource } from "../api/chat";

// Compact metadata echoed back on a user message (and stored in history) so the
// chips the user picked stay visible above their message.
export interface UsedSource {
  uri: string;
  name: string;
}
export interface UsedPrompt {
  name: string;
  display_name: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  tools?: string[];
  sources?: UsedSource[];
  prompts?: UsedPrompt[];
  pending?: boolean;
}

function setLastAssistant(
  messages: ChatMessage[],
  patch: Partial<ChatMessage>,
  fallbackAppend = false,
): ChatMessage[] {
  const copy = [...messages];
  for (let i = copy.length - 1; i >= 0; i--) {
    if (copy[i].role === "assistant" && copy[i].pending) {
      copy[i] = { ...copy[i], ...patch };
      return copy;
    }
  }
  if (fallbackAppend) {
    copy.push({ role: "assistant", content: patch.content ?? "", tools: patch.tools });
  }
  return copy;
}

interface Options {
  sessionId: string | null;
  connKey: number;
  onSessionCreated: (id: string) => void;
}

// Drives a single chat WebSocket. A reconnect happens only when `connKey`
// changes (the user opens another session or starts a new chat) — the
// server-assigned session id for a fresh chat updates state without reconnecting.
export function useChatSocket({ sessionId, connKey, onSessionCreated }: Options) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(sessionId);

  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef("");
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  const onCreatedRef = useRef(onSessionCreated);
  onCreatedRef.current = onSessionCreated;

  useEffect(() => {
    const sid = sessionIdRef.current;
    setMessages([]);
    setStreaming(false);
    setStatusText(null);
    setCurrentSessionId(sid);
    streamRef.current = "";

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const path = sid ? `/ws/chat/${sid}/` : "/ws/chat/";
    const ws = new WebSocket(`${proto}//${window.location.host}${path}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case "session_info":
          setCurrentSessionId(data.session_id);
          if (!sid && data.session_id) onCreatedRef.current(data.session_id);
          break;
        case "history":
          setMessages(
            (data.messages ?? []).map((m: ChatMessage) => ({
              role: m.role,
              content: m.content,
              tools: m.tools,
              sources: m.sources,
              prompts: m.prompts,
            })),
          );
          break;
        case "stream_start":
          streamRef.current = "";
          setStreaming(true);
          setStatusText(null);
          setMessages((ms) => [...ms, { role: "assistant", content: "", pending: true }]);
          break;
        case "stream_status":
          setStatusText(data.content);
          break;
        case "stream_chunk":
          streamRef.current += data.content;
          setMessages((ms) => setLastAssistant(ms, { content: streamRef.current }));
          break;
        case "stream_end":
          setStreaming(false);
          setStatusText(null);
          setMessages((ms) =>
            setLastAssistant(
              ms,
              { content: data.content || streamRef.current, tools: data.tools, pending: false },
              true,
            ),
          );
          break;
        case "stream_cancelled":
          setStreaming(false);
          setStatusText(null);
          setMessages((ms) =>
            setLastAssistant(ms, { content: data.content || streamRef.current, pending: false }),
          );
          break;
        case "error":
          setStreaming(false);
          setStatusText(null);
          setMessages((ms) => [
            ...ms.filter((m) => !m.pending),
            { role: "assistant", content: `⚠️ ${data.message}` },
          ]);
          break;
      }
    };

    return () => ws.close();
  }, [connKey]);

  const send = useCallback(
    (text: string, resources: DocResource[] = [], prompts: ChatPrompt[] = []) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || !text.trim()) return;
      const sources = resources.map((r) => ({ uri: r.uri, name: r.name }));
      const promptsInfo = prompts.map((p) => ({ name: p.name, display_name: p.display_name }));
      setMessages((ms) => [
        ...ms,
        {
          role: "user",
          content: text,
          sources: sources.length ? sources : undefined,
          prompts: promptsInfo.length ? promptsInfo : undefined,
        },
      ]);
      const payload: Record<string, unknown> = { message: text };
      if (resources.length) {
        payload.resource_uris = resources.map((r) => r.uri);
        payload.sources_info = sources;
      }
      if (prompts.length) {
        payload.prompt_context = prompts.map((p) => p.content);
        payload.prompts_info = promptsInfo;
      }
      ws.send(JSON.stringify(payload));
    },
    [],
  );

  const cancel = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: "cancel" }));
  }, []);

  return { messages, statusText, streaming, connected, currentSessionId, send, cancel };
}
