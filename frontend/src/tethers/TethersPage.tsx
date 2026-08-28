import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, useParams } from "react-router-dom";
import { getTether, getTetherGraph, getTethers } from "../api/tethers";
import { TetherCity } from "./TetherCity";

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
				<TetherCity
					graph={graph.data}
					title={t.name}
					subtitle={`${t.source_name} ↔ ${t.database_name}`}
					codeLabel={t.source_name}
					dataLabel={t.database_name}
				/>
			)}
		</div>
	);
}

export function TethersPage() {
	const { id } = useParams();
	// the list is navigation, not part of the view, so it gets out of the way on
	// request — the city is worth every pixel it can have
	const [navOpen, setNavOpen] = useState(true);
	const { data, isLoading } = useQuery({
		queryKey: ["tethers"],
		queryFn: getTethers,
	});

	const tethers = data?.tethers ?? [];

	return (
		<div className={`docs-layout tether-layout${navOpen ? "" : " nav-shut"}`}>
			<button
				type="button"
				className="tether-nav-toggle"
				onClick={() => setNavOpen((v) => !v)}
				title={navOpen ? "Hide the tether list" : "Show the tether list"}
				aria-expanded={navOpen}
			>
				<i
					className={`fa-solid ${navOpen ? "fa-chevron-left" : "fa-chevron-right"}`}
				/>
			</button>
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
								<i className="fa-solid fa-diagram-project" />
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
					<div className="docs-content">
						<div className="docs-empty-state">
							<p>
								Select a tether from the sidebar to explore its code ↔ database
								graph.
							</p>
						</div>
					</div>
				)}
			</div>
		</div>
	);
}
