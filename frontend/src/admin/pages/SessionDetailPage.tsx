import { useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import Markdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { getSession, type SessionMessage } from "../../api/admin";

const ROLE_COLOR: Record<string, string> = {
  user: "var(--c-pink)",
  assistant: "var(--c-cyan)",
  system: "var(--c-orange)",
};

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span
        style={{
          fontSize: "var(--text-xs)",
          textTransform: "uppercase",
          letterSpacing: 1,
          color: "var(--text-muted)",
          fontWeight: 700,
        }}
      >
        {label}
      </span>
      <span style={{ fontSize: "var(--text-sm)" }}>{value}</span>
    </div>
  );
}

function MessageRow({ msg }: { msg: SessionMessage }) {
  const color = ROLE_COLOR[msg.role] ?? "var(--border)";
  const rowStyle: CSSProperties = {
    display: "flex",
    gap: "var(--md)",
    padding: "var(--md) var(--lg)",
    borderLeft: `3px solid ${color}`,
  };
  return (
    <div style={rowStyle}>
      <div style={{ flexShrink: 0, width: 90 }}>
        <span
          className="badge"
          style={{ background: "transparent", border: `1px solid ${color}`, color }}
        >
          {msg.role}
        </span>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--text-sm)", lineHeight: 1.7, overflowWrap: "break-word" }}>
          {msg.role === "assistant" ? (
            <Markdown remarkPlugins={[remarkGfm]}>{msg.content || "…"}</Markdown>
          ) : (
            <div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>
          )}
        </div>
        {msg.sources_used.length > 0 && (
          <div className="flex-gap" style={{ flexWrap: "wrap", marginTop: "var(--xs)" }}>
            {msg.sources_used.map((s, i) => (
              <span key={i} className="badge badge-muted">
                @{s.name ?? s.uri}
              </span>
            ))}
          </div>
        )}
        {msg.prompts_used.length > 0 && (
          <div className="flex-gap" style={{ flexWrap: "wrap", marginTop: "var(--xs)" }}>
            {msg.prompts_used.map((p, i) => (
              <span key={i} className="badge badge-muted">
                /{p.display_name ?? p.name}
              </span>
            ))}
          </div>
        )}
        {msg.tools_used.length > 0 && (
          <div className="flex-gap" style={{ flexWrap: "wrap", marginTop: "var(--xs)" }}>
            {msg.tools_used.map((t, i) => (
              <span key={i} className="badge badge-muted text-mono">
                {t}
              </span>
            ))}
          </div>
        )}
        <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 4 }}>
          {new Date(msg.created_at).toLocaleString()}
        </div>
      </div>
    </div>
  );
}

export function SessionDetailPage() {
  const { id } = useParams();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "sessions", id],
    queryFn: () => getSession(id as string),
    enabled: Boolean(id),
  });

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{data?.title || "Untitled session"}</h1>
          <p className="text-mono">{data ? `${data.id} — ${data.user ?? "—"}` : "Transcript"}</p>
        </div>
        <Link to="/admin/sessions" className="btn btn-ghost">
          Back
        </Link>
      </div>

      {isLoading ? (
        <div className="card">
          <p className="text-sec">Loading…</p>
        </div>
      ) : isError || !data ? (
        <div className="card">
          <p className="text-sec">Failed to load session.</p>
        </div>
      ) : (
        <>
          <div className="card" style={{ marginBottom: "var(--md)" }}>
            <div className="flex-gap" style={{ gap: "var(--xl)", flexWrap: "wrap" }}>
              <MetaItem label="User" value={data.user ?? "—"} />
              <MetaItem label="Messages" value={String(data.message_count)} />
              <MetaItem label="Created" value={new Date(data.created_at).toLocaleString()} />
              <MetaItem label="Last activity" value={new Date(data.updated_at).toLocaleString()} />
            </div>
          </div>

          <div className="card" style={{ padding: 0 }}>
            {data.messages.length === 0 ? (
              <p className="text-sec" style={{ padding: "var(--md) var(--lg)" }}>
                No messages in this session.
              </p>
            ) : (
              data.messages.map((m) => <MessageRow key={m.id} msg={m} />)
            )}
          </div>
        </>
      )}
    </div>
  );
}
