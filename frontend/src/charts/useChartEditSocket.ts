import { useCallback, useEffect, useRef, useState } from "react";

export interface ChartChatMessage {
  role: "user" | "assistant" | "error";
  content: string;
  pending?: boolean;
}

function patchLastAssistant(
  messages: ChartChatMessage[],
  patch: Partial<ChartChatMessage>
): ChartChatMessage[] {
  const copy = [...messages];
  for (let i = copy.length - 1; i >= 0; i--) {
    if (copy[i].role === "assistant" && copy[i].pending) {
      copy[i] = { ...copy[i], ...patch };
      return copy;
    }
  }
  return copy;
}

// Drives the chart-edit WebSocket (`ws/chart-edit/<chart_id>/`, staff-only). The
// agent edits the chart in place via the update_chart MCP tool; `onDone` fires
// when a turn completes so the editor can re-read the chart's saved state.
export function useChartEditSocket({
  chartId,
  onDone,
}: {
  chartId: string;
  onDone: () => void;
}) {
  const [messages, setMessages] = useState<ChartChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef("");
  const streamingRef = useRef(false);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/chart-edit/${chartId}/`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      if (streamingRef.current) {
        streamingRef.current = false;
        setStreaming(false);
        setMessages((ms) => [
          ...ms.filter((m) => !m.pending),
          { role: "error", content: "Connection lost during agent response." },
        ]);
      }
    };
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case "ready":
          break;
        case "stream_start":
          streamRef.current = "";
          streamingRef.current = true;
          setStreaming(true);
          setStatusText(null);
          setMessages((ms) => [...ms, { role: "assistant", content: "", pending: true }]);
          break;
        case "stream_status":
          setStatusText(data.content);
          break;
        case "stream_chunk":
          streamRef.current += data.content;
          setMessages((ms) => patchLastAssistant(ms, { content: streamRef.current }));
          break;
        case "stream_end":
          streamingRef.current = false;
          setStreaming(false);
          setStatusText(null);
          setMessages((ms) =>
            patchLastAssistant(ms, {
              content: data.content || streamRef.current || "(done)",
              pending: false,
            })
          );
          onDoneRef.current();
          break;
        case "error":
          streamingRef.current = false;
          setStreaming(false);
          setStatusText(null);
          setMessages((ms) => [
            ...ms.filter((m) => !m.pending),
            { role: "error", content: data.message || "Unknown error" },
          ]);
          break;
      }
    };

    return () => ws.close();
  }, [chartId]);

  const send = useCallback((text: string) => {
    const ws = wsRef.current;
    const trimmed = text.trim();
    if (!ws || ws.readyState !== WebSocket.OPEN || !trimmed || streamingRef.current) return;
    setMessages((ms) => [...ms, { role: "user", content: trimmed }]);
    ws.send(JSON.stringify({ message: trimmed }));
  }, []);

  return { messages, streaming, statusText, connected, send };
}
