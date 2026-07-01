import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
	type CSSProperties,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
	type ChatSessionItem,
	getAgentStatus,
	listChatSessions,
} from "../api/chat";
import { ChatComposer } from "./ChatComposer";
import { useChatSocket } from "./useChatSocket";

const GROUP_COLORS = [
	"var(--c-cyan)",
	"var(--c-lime)",
	"var(--c-pink)",
	"var(--c-orange)",
	"var(--c-red)",
];

function groupSessions(
	sessions: ChatSessionItem[],
): [string, ChatSessionItem[]][] {
	const map = new Map<string, ChatSessionItem[]>();
	for (const s of sessions) {
		const arr = map.get(s.group) ?? [];
		arr.push(s);
		map.set(s.group, arr);
	}
	return [...map.entries()];
}

function toolDisplayName(name: string): string {
	return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function ChatPage() {
	const queryClient = useQueryClient();
	const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
		null,
	);
	const [connKey, setConnKey] = useState(0);
	const scrollRef = useRef<HTMLDivElement>(null);

	const sessionsQuery = useQuery({
		queryKey: ["chat", "sessions"],
		queryFn: listChatSessions,
	});
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

	const {
		messages,
		statusText,
		streaming,
		connected,
		currentSessionId,
		send,
		cancel,
	} = useChatSocket({
		sessionId: selectedSessionId,
		connKey,
		onSessionCreated,
	});

	function newChat() {
		setSelectedSessionId(null);
		setConnKey((k) => k + 1);
	}

	function selectSession(id: string) {
		if (id === currentSessionId) return;
		setSelectedSessionId(id);
		setConnKey((k) => k + 1);
	}

	useEffect(() => {
		if (messages.length === 0 && !statusText) return;
		scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
	}, [messages, statusText]);

	const grouped = groupSessions(sessionsQuery.data?.sessions ?? []);
	const agentName = agentQuery.data?.name ?? null;

	return (
		<div className="chat-layout">
			<aside className="docs-sidebar">
				<div className="docs-sidebar-header">
					<button type="button" className="history-new-btn" onClick={newChat}>
						<i className="fa-solid fa-pen-to-square" />
						<span>New Chat</span>
					</button>
				</div>
				<div className="docs-tree">
					{grouped.length === 0 ? (
						<p className="text-sec" style={{ padding: "var(--md) var(--lg)" }}>
							No chats yet.
						</p>
					) : (
						grouped.map(([group, items], idx) => (
							<div key={group}>
								<div
									className="history-section-label"
									style={{ color: GROUP_COLORS[idx % GROUP_COLORS.length] }}
								>
									{group}
								</div>
								{items.map((s) => (
									<div key={s.id} className="chat-session">
										<button
											type="button"
											className={
												s.id === currentSessionId
													? "docs-file-btn chat-session-name active"
													: "docs-file-btn chat-session-name"
											}
											onClick={() => selectSession(s.id)}
										>
											<i className="fa-solid fa-comments" />
											<span>{s.title}</span>
										</button>
									</div>
								))}
							</div>
						))
					)}
				</div>
			</aside>

			<div className="chat-container">
				<div className="chat-messages" ref={scrollRef}>
					{messages.length === 0 && (
						<div className="chat-empty-state">
							<div className="empty-brand">
								Tether<span>Dust</span>
							</div>
							<p>
								{agentName
									? "Ask the agent anything about your data."
									: "Activate an agent in Control → Agents to start."}
							</p>
						</div>
					)}
					{messages.map((m) => {
						const isUser = m.role === "user";
						const showTyping =
							m.role === "assistant" && m.pending && !m.content;
						return (
							<div
								key={m.id}
								className={isUser ? "message user" : "message agent"}
							>
								<div className="message-avatar">
									<i
										className={
											isUser ? "fa-solid fa-user" : "fa-solid fa-robot"
										}
									/>
								</div>
								<div className="message-body">
									{((m.sources && m.sources.length > 0) ||
										(m.prompts && m.prompts.length > 0)) && (
										<div className="primitives-used">
											{m.sources?.map((s, si) => (
												<span
													key={`s:${s.uri}`}
													className="mention-chip mention-chip-doc"
													style={{ "--pill-i": si } as CSSProperties}
												>
													<span className="mention-chip-prefix">@</span>
													<span className="mention-chip-label">{s.name}</span>
												</span>
											))}
											{m.prompts?.map((p, pi) => (
												<span
													key={`p:${p.name}`}
													className="mention-chip mention-chip-prompt"
													style={
														{
															"--pill-i": (m.sources?.length ?? 0) + pi,
														} as CSSProperties
													}
												>
													<span className="mention-chip-prefix">/</span>
													<span className="mention-chip-label">
														{p.display_name}
													</span>
												</span>
											))}
										</div>
									)}
									{m.tools && m.tools.length > 0 && (
										<div className="tools-used">
											{m.tools.map((t, ti) => (
												<span
													key={t}
													className="tool-pill"
													style={{ "--pill-i": ti } as CSSProperties}
												>
													<i className="fa-solid fa-wrench" />
													<span>{toolDisplayName(t)}</span>
												</span>
											))}
										</div>
									)}
									{showTyping ? (
										<div className="message-content typing-indicator">
											<div className="typing-dots">
												{[0, 1, 2, 3, 4].map((n) => (
													<div key={n} className="typing-dot" />
												))}
											</div>
										</div>
									) : (
										<div className="message-content">
											{m.role === "assistant" ? (
												<Markdown remarkPlugins={[remarkGfm]}>
													{m.content || "…"}
												</Markdown>
											) : (
												m.content
											)}
										</div>
									)}
									{m.pending && statusText && (
										<div className="typing-inline-status">{statusText}</div>
									)}
								</div>
							</div>
						);
					})}
				</div>
				<ChatComposer
					connected={connected}
					streaming={streaming}
					onSend={send}
					onCancel={cancel}
				/>
			</div>
		</div>
	);
}
