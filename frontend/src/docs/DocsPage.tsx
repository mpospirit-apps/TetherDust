import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getDocContent, getDocSources, type DocTreeNode } from "../api/docs";
import { DocCode, DocMarkdown } from "./DocMarkdown";

function fileHref(source: string, path: string): string {
  const encPath = path
    .split("/")
    .map((s) => encodeURIComponent(s))
    .join("/");
  return `/docs/${encodeURIComponent(source)}/${encPath}`;
}

function TreeNodes({
  nodes,
  source,
  activePath,
  onOpen,
  depth,
}: {
  nodes: DocTreeNode[];
  source: string;
  activePath: string | undefined;
  onOpen: (path: string) => void;
  depth: number;
}) {
  return (
    <>
      {nodes.map((node) =>
        node.type === "dir" ? (
          <DirNode
            key={node.path}
            node={node}
            source={source}
            activePath={activePath}
            onOpen={onOpen}
            depth={depth}
          />
        ) : (
          <button
            key={node.path}
            type="button"
            className={
              node.path === activePath ? "docs-file-btn active" : "docs-file-btn"
            }
            style={{ paddingLeft: `calc(var(--lg) + ${depth} * var(--md))` }}
            onClick={() => onOpen(node.path)}
          >
            <i className="fa-solid fa-file-lines" />
            {node.name}
          </button>
        )
      )}
    </>
  );
}

function DirNode({
  node,
  source,
  activePath,
  onOpen,
  depth,
}: {
  node: DocTreeNode;
  source: string;
  activePath: string | undefined;
  onOpen: (path: string) => void;
  depth: number;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="docs-dir">
      <button type="button" className="docs-dir-toggle" onClick={() => setOpen((o) => !o)}>
        <i className={open ? "fa-solid fa-chevron-down" : "fa-solid fa-chevron-right"} />
        <i className="fa-solid fa-folder" />
        {node.name}
      </button>
      {open && (
        <TreeNodes
          nodes={node.children ?? []}
          source={source}
          activePath={activePath}
          onOpen={onOpen}
          depth={depth + 1}
        />
      )}
    </div>
  );
}

function SourceGroup({
  name,
  tree,
  activeSource,
  activePath,
  onOpen,
}: {
  name: string;
  tree: DocTreeNode[];
  activeSource: string | undefined;
  activePath: string | undefined;
  onOpen: (path: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const isActiveSource = name === activeSource;
  return (
    <div className="docs-source">
      <button type="button" className="docs-source-toggle" onClick={() => setOpen((o) => !o)}>
        <i className={open ? "fa-solid fa-chevron-down" : "fa-solid fa-chevron-right"} />
        <i className="fa-solid fa-book docs-source-icon" />
        {name}
      </button>
      {open && (
        <div className="docs-source-children">
          <TreeNodes
            nodes={tree}
            source={name}
            activePath={isActiveSource ? activePath : undefined}
            onOpen={onOpen}
            depth={0}
          />
        </div>
      )}
    </div>
  );
}

export function DocsPage() {
  const params = useParams();
  const navigate = useNavigate();
  const sourceName = params.source;
  const filePath = params["*"] || undefined;
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const sourcesQuery = useQuery({ queryKey: ["docs", "sources"], queryFn: getDocSources });

  const contentQuery = useQuery({
    queryKey: ["docs", "content", sourceName, filePath],
    queryFn: () => getDocContent(sourceName as string, filePath as string),
    enabled: Boolean(sourceName && filePath),
  });

  const sources = sourcesQuery.data?.sources ?? [];
  const sourceNames = sources.map((s) => s.name);

  // Redirect away from a source/file the user can't see once sources load.
  useEffect(() => {
    if (sourceName && sources.length > 0 && !sourceNames.includes(sourceName)) {
      navigate("/docs", { replace: true });
    }
  }, [sourceName, sources.length]);

  function openFile(source: string, path: string) {
    navigate(fileHref(source, path));
  }

  return (
    <div className="docs-layout">
      <aside className={sidebarOpen ? "docs-sidebar" : "docs-sidebar collapsed"}>
        <div className="docs-sidebar-header">
          <h3>Documentation</h3>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            aria-label="Collapse sidebar"
            onClick={() => setSidebarOpen(false)}
          >
            <i className="fa-solid fa-angles-left" />
          </button>
        </div>
        <div className="docs-tree">
          {sourcesQuery.isLoading ? (
            <p className="text-sec" style={{ padding: "var(--md) var(--lg)" }}>
              Loading…
            </p>
          ) : sources.length === 0 ? (
            <p className="text-sec" style={{ padding: "var(--md) var(--lg)" }}>
              No documentation sources available.
            </p>
          ) : (
            sources.map((src) => (
              <SourceGroup
                key={src.id}
                name={src.name}
                tree={src.tree}
                activeSource={sourceName}
                activePath={filePath}
                onOpen={(path) => openFile(src.name, path)}
              />
            ))
          )}
        </div>
      </aside>

      {!sidebarOpen && (
        <button
          type="button"
          className="docs-toggle-btn"
          aria-label="Open sidebar"
          onClick={() => setSidebarOpen(true)}
        >
          <i className="fa-solid fa-angles-right" />
        </button>
      )}

      <div className="docs-content-area">
        <div className="docs-content">
          {!sourceName || !filePath ? (
            <div className="docs-empty-state">
              <div className="empty-brand">
                Tether<span>Dust</span>
              </div>
              <p>Select a document from the sidebar to start reading.</p>
            </div>
          ) : contentQuery.isLoading ? (
            <div className="docs-loading">
              <i className="fa-solid fa-spinner fa-spin" />
            </div>
          ) : contentQuery.isError || !contentQuery.data ? (
            <p className="text-sec">Failed to load this document.</p>
          ) : (
            <>
              <h1 className="docs-title">{contentQuery.data.title}</h1>
              {contentQuery.data.is_markdown ? (
                <DocMarkdown
                  content={contentQuery.data.content}
                  sources={sourceNames}
                  currentSource={contentQuery.data.source}
                />
              ) : (
                <DocCode
                  content={contentQuery.data.content}
                  language={contentQuery.data.language}
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
