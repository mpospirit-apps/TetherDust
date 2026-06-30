import { useQuery } from "@tanstack/react-query";
import { NavLink, useParams } from "react-router-dom";
import { getTether, getTetherGraph, getTethers } from "../api/tethers";
import { TetherCanvas } from "./TetherCanvas";

function TetherViewer({ id }: { id: string }) {
	const detail = useQuery({
		queryKey: ["tether", id],
		queryFn: () => getTether(id),
	});
	const graph = useQuery({
		queryKey: ["tether-graph", id],
		queryFn: () => getTetherGraph(id),
		enabled: detail.data?.has_graph === true,
	});

	if (detail.isLoading) {
		return (
			<div className="docs-loading">
				<i className="fa-solid fa-spinner fa-spin" />
			</div>
		);
	}
	if (detail.isError || !detail.data) {
		return <p className="text-sec">Failed to load this tether.</p>;
	}

	const t = detail.data;

	return (
		<div className="tether-viewer">
			<header className="tether-viewer__header">
				<div>
					<h1>{t.name}</h1>
					<p className="text-sec">
						{t.source_name} ↔ {t.database_name}
					</p>
				</div>
			</header>

			{!t.has_graph ? (
				<div className="docs-empty-state">
					<p className="text-sec">
						{t.status
							? `The latest generation is ${t.status}. Ask your administrator to regenerate.`
							: "No graph yet — generation may still be running."}
					</p>
				</div>
			) : graph.isLoading ? (
				<div className="docs-loading">
					<i className="fa-solid fa-spinner fa-spin" />
				</div>
			) : graph.isError || !graph.data ? (
				<p className="text-sec">Failed to load the graph.</p>
			) : (
				<TetherCanvas graph={graph.data} />
			)}
		</div>
	);
}

export function TethersPage() {
	const { id } = useParams();
	const { data, isLoading } = useQuery({
		queryKey: ["tethers"],
		queryFn: getTethers,
	});

	const tethers = data?.tethers ?? [];

	return (
		<div className="docs-layout">
			<aside className="docs-sidebar">
				<div className="docs-tree">
					{isLoading ? (
						<p className="text-sec" style={{ padding: "var(--md) var(--lg)" }}>
							Loading…
						</p>
					) : tethers.length === 0 ? (
						<p className="text-sec" style={{ padding: "var(--md) var(--lg)" }}>
							No tethers available.
						</p>
					) : (
						tethers.map((t) => (
							<NavLink
								key={t.id}
								to={`/tethers/${t.id}`}
								className={({ isActive }) =>
									isActive ? "docs-file-btn active" : "docs-file-btn"
								}
							>
								<i className="fa-solid fa-link" />
								<span>{t.name}</span>
							</NavLink>
						))
					)}
				</div>
			</aside>

			<div className="docs-content-area">
				{id ? (
					<TetherViewer id={id} />
				) : (
					<div className="docs-empty-state">
						<div className="empty-brand">
							Tether<span>Dust</span>
						</div>
						<p>
							Select a tether from the sidebar to explore its code ↔ database
							graph.
						</p>
					</div>
				)}
			</div>
		</div>
	);
}
