import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CityInspector } from "./CityInspector";
import type { Rel } from "./city/plan";
import { planCity } from "./city/plan";
import { createCityScene, type SceneHandle } from "./city/scene";
import type { TetherGraph } from "./types";

// React provides the host <svg> and nothing else inside it: the scene rewrites
// on the order of a thousand attributes per frame, and reconciling that through
// React would cost far more than the arithmetic it is drawing. Same division the
// old canvas controller used, for the same reason.
const ALL_RELS: Rel[] = ["reads", "writes", "references", "maps-to"];

export function TetherCity({
	graph,
	codeLabel,
	dataLabel,
}: {
	graph: TetherGraph;
	codeLabel?: string;
	dataLabel?: string;
}) {
	const svgRef = useRef<SVGSVGElement>(null);
	const city = useMemo(
		() => planCity(graph, { codeLabel, dataLabel }),
		[graph, codeLabel, dataLabel],
	);

	const sceneRef = useRef<SceneHandle | null>(null);
	const [selected, setSelected] = useState<string | null>(null);
	const [rels, setRels] = useState<ReadonlySet<Rel>>(() => new Set(ALL_RELS));
	const [query, setQuery] = useState("");
	const [hits, setHits] = useState(0);
	const [info, setInfo] = useState(false);

	useEffect(() => {
		const host = svgRef.current;
		if (!host) return;
		const scene = createCityScene(host, city, setSelected);
		sceneRef.current = scene;
		const onKey = (ev: KeyboardEvent) => {
			if (ev.target instanceof HTMLInputElement) return;
			if (ev.key === "[") scene.nudge((-5 * Math.PI) / 180);
			else if (ev.key === "]") scene.nudge((5 * Math.PI) / 180);
			else if (ev.key === "Escape") scene.select(null);
		};
		addEventListener("keydown", onKey);
		return () => {
			removeEventListener("keydown", onKey);
			sceneRef.current = null;
			scene.destroy();
		};
	}, [city]);

	// a graph change rebuilds the scene, which starts with nothing open
	// biome-ignore lint/correctness/useExhaustiveDependencies: reset on new city
	useEffect(() => setSelected(null), [city]);

	// the scene is rebuilt on a new graph, so the chrome has to re-apply itself
	useEffect(() => {
		sceneRef.current?.setFilter(rels);
	}, [rels]);
	useEffect(() => {
		setHits(sceneRef.current?.setSearch(query) ?? 0);
	}, [query]);

	const toggleRel = useCallback((rel: Rel) => {
		setRels((prev) => {
			const next = new Set(prev);
			if (next.has(rel)) next.delete(rel);
			else next.add(rel);
			// turning the last one off would empty the canvas; treat it as a reset
			return next.size ? next : new Set(ALL_RELS);
		});
	}, []);

	const snap = useCallback((dir: 1 | -1) => sceneRef.current?.snap(dir), []);
	const close = useCallback(() => sceneRef.current?.select(null), []);
	const fit = useCallback(() => sceneRef.current?.fit(), []);

	if (city.buildings.length === 0) {
		return (
			<div className="docs-empty-state">
				<p className="text-sec">
					This graph has no code files or database tables to place.
				</p>
			</div>
		);
	}

	return (
		<div className="city-wrap">
			<svg ref={svgRef} className="city" />
			<div className="city-overlay">
				<div className="city-rail">
					<button
						type="button"
						className="city-btn"
						title="Turn anticlockwise"
						onClick={() => snap(-1)}
					>
						<i className="fa-solid fa-rotate-left" />
					</button>
					<button
						type="button"
						className="city-btn"
						title="Turn clockwise"
						onClick={() => snap(1)}
					>
						<i className="fa-solid fa-rotate-right" />
					</button>
					<button
						type="button"
						className="city-btn"
						title="Fit view"
						onClick={fit}
					>
						<i className="fa-solid fa-expand" />
					</button>
					<button
						type="button"
						className={info ? "city-btn is-on" : "city-btn"}
						title="About this graph"
						onClick={() => setInfo((v) => !v)}
					>
						<i className="fa-solid fa-circle-info" />
					</button>
				</div>
				<div className="city-tools">
					<input
						className="city-search"
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						placeholder="Find a file, table, symbol or column…"
						aria-label="Search the city"
					/>
					{query ? (
						<span className="city-search__count">
							{hits} {hits === 1 ? "building" : "buildings"}
						</span>
					) : null}
					<div className="city-chips">
						{ALL_RELS.map((rel) => (
							<button
								key={rel}
								type="button"
								className={`chip chip--${rel}${rels.has(rel) ? " is-on" : ""}`}
								onClick={() => toggleRel(rel)}
							>
								{rel}
							</button>
						))}
					</div>
				</div>

				{info ? (
					<div className="city-info">
						<h3>Codebase</h3>
						<p>{city.codebaseSummary || "No summary was generated."}</p>
						<h3>Database</h3>
						<p>{city.databaseSummary || "No summary was generated."}</p>
						<h3>Graph</h3>
						<p>
							{city.buildings.length} buildings ·{" "}
							{city.buildings.reduce((s, b) => s + b.h, 0)} storeys ·{" "}
							{city.bundles.reduce((s, b) => s + b.strands.length, 0)} tethers
							in {city.bundles.length} cords
							{city.dropped
								? ` · ${city.dropped} edge${city.dropped === 1 ? "" : "s"} joined a building to itself and could not be drawn`
								: ""}
						</p>
						<p className="city-info__note">
							A cord carries every tether between one pair of buildings and
							takes the colour most of them share. Open a building to separate
							them onto the storeys they land on.
						</p>
					</div>
				) : null}

				{selected ? (
					<CityInspector city={city} id={selected} onClose={close} />
				) : null}
				<div className="city-legend">
					<span className="note">
						drag to pan · <kbd>shift</kbd>-drag or right-drag to turn · scroll
						to zoom
					</span>
					<span className="note">
						{city.buildings.length} buildings · storeys are symbols and columns
						· {city.bundles.length} cords carrying{" "}
						{city.bundles.reduce((s, b) => s + b.strands.length, 0)} tethers
					</span>
				</div>
			</div>
		</div>
	);
}
