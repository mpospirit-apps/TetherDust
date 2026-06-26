import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  deleteChatSession,
  getAgentStatus,
  listChatSessions,
  type ChatSessionItem,
} from "../api/chat";
import { ChatComposer } from "./ChatComposer";
import { useChatSocket } from "./useChatSocket";

function groupSessions(sessions: ChatSessionItem[]): [string, ChatSessionItem[]][] {
  const map = new Map<string, ChatSessionItem[]>();
  for (const s of sessions) {
    const arr = map.get(s.group) ?? [];
    arr.push(s);
    map.set(s.group, arr);
  }
  return [...map.entries()];
}

export function ChatPage() {
  const queryClient = useQueryClient();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [connKey, setConnKey] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const sessionsQuery = useQuery({ queryKey: ["chat", "sessions"], queryFn: listChatSessions });
  const agentQuery = useQuery({
    queryKey: ["chat", "agent-status"],
    queryFn: getAgentStatus,
    refetchInterval: 20000,
  });

  const onSessionCreated = useCallback(
    (id: string) => {
      setSelectedSessionId(id);
      queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] });
    },
    [queryClient],
  );

  const { messages, statusText, streaming, connected, currentSessionId, send, cancel } =
    useChatSocket({ sessionId: selectedSessionId, connKey, onSessionCreated });

  function newChat() {
    setSelectedSessionId(null);
    setConnKey((k) => k + 1);
  }

  function selectSession(id: string) {
    if (id === currentSessionId) return;
    setSelectedSessionId(id);
    setConnKey((k) => k + 1);
  }

  const delSession = useMutation({
    mutationFn: deleteChatSession,
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] });
      if (id === currentSessionId) newChat();
    },
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, statusText]);

  const grouped = groupSessions(sessionsQuery.data?.sessions ?? []);
  const agentName = agentQuery.data?.name ?? null;
  const agentConnected = agentQuery.data?.connected ?? false;

  return (
    <div className="chat-layout">
      <aside className="chat-sidebar">
        <button className="btn btn-primary" style={{ width: "100%" }} onClick={newChat}>
          + New chat
        </button>
        <div className="chat-agent">
          <span className={agentConnected ? "chat-dot is-on" : "chat-dot is-off"} />
          <span>{agentName ?? "No agent active"}</span>
        </div>
        <div className="chat-sessions">
          {grouped.map(([group, items]) => (
            <div key={group}>
              <div className="chat-sessions-heading">{group}</div>
              {items.map((s) => (
                <div
                  key={s.id}
                  className={s.id === currentSessionId ? "chat-session active" : "chat-session"}
                >
                  <button className="chat-session-name" onClick={() => selectSession(s.id)}>
                    {s.title}
                  </button>
                  <button
                    className="chat-session-del"
                    title="Delete session"
                    onClick={() => delSession.mutate(s.id)}
                  >
                    <i className="fa-solid fa-trash" />
                  </button>
                </div>
              ))}
            </div>
          ))}
        </div>
      </aside>

      <main className="chat-main">
        <div className="chat-messages" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="chat-empty">
              <p className="text-sec">
                {agentName
                  ? "Ask the agent anything about your data."
                  : "Activate an agent in Control → Agents to start."}
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`chat-msg chat-msg--${m.role}`}>
              <div className="chat-bubble">
                {((m.sources && m.sources.length > 0) || (m.prompts && m.prompts.length > 0)) && (
                  <div className="primitives-used">
                    {m.sources?.map((s) => (
                      <span key={`s:${s.uri}`} className="mention-chip">
                        <span className="mention-chip-prefix">@</span>
                        {s.name}
                      </span>
                    ))}
                    {m.prompts?.map((p) => (
                      <span key={`p:${p.name}`} className="mention-chip mention-chip-prompt">
                        <span className="mention-chip-prefix">/</span>
                        {p.display_name}
                      </span>
                    ))}
                  </div>
                )}
                {m.role === "assistant" ? (
                  <Markdown remarkPlugins={[remarkGfm]}>{m.content || "…"}</Markdown>
                ) : (
                  m.content
                )}
                {m.tools && m.tools.length > 0 && (
                  <div className="chat-tools">
                    {m.tools.map((t) => (
                      <span key={t} className="chat-tool">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {statusText && (
            <div className="chat-status">
              <i className="fa-solid fa-spinner fa-spin" /> {statusText}
            </div>
          )}
        </div>
        <ChatComposer
          connected={connected}
          streaming={streaming}
          onSend={send}
          onCancel={cancel}
        />
      </main>
    </div>
  );
}
