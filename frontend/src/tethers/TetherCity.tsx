import { useCallback, useEffect, useMemo, useRef } from "react";
import { planCity } from "./city/plan";
import { createCityScene, type SceneHandle } from "./city/scene";
import type { TetherGraph } from "./types";

// React provides the host <svg> and nothing else inside it: the scene rewrites
// on the order of a thousand attributes per frame, and reconciling that through
// React would cost far more than the arithmetic it is drawing. Same division the
// old canvas controller used, for the same reason.
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

	useEffect(() => {
		const host = svgRef.current;
		if (!host) return;
		const scene = createCityScene(host, city);
		sceneRef.current = scene;
		const onKey = (ev: KeyboardEvent) => {
			if (ev.target instanceof HTMLInputElement) return;
			if (ev.key === "[") scene.nudge((-5 * Math.PI) / 180);
			else if (ev.key === "]") scene.nudge((5 * Math.PI) / 180);
		};
		addEventListener("keydown", onKey);
		return () => {
			removeEventListener("keydown", onKey);
			sceneRef.current = null;
			scene.destroy();
		};
	}, [city]);

	const snap = useCallback((dir: 1 | -1) => sceneRef.current?.snap(dir), []);
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
			</div>
			<div className="city-legend">
				<span className="ttl">Tethers</span>
				<div className="rels">
					<span className="rel">
						<i className="sw sw-reads" />
						reads
					</span>
					<span className="rel">
						<i className="sw sw-writes" />
						writes
					</span>
					<span className="rel">
						<i className="sw sw-references" />
						references
					</span>
					<span className="rel">
						<i className="sw sw-maps-to" />
						maps-to
					</span>
				</div>
				<span className="note">
					drag to pan · <kbd>shift</kbd>-drag or right-drag to turn · scroll to
					zoom
				</span>
				<span className="note">
					{city.buildings.length} buildings · storeys are symbols and columns ·{" "}
					{city.bundles.length} cords carrying{" "}
					{city.bundles.reduce((s, b) => s + b.strands.length, 0)} tethers
				</span>
			</div>
		</div>
	);
}
