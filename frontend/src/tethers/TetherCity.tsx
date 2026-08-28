import { useEffect, useMemo, useRef } from "react";
import { planCity } from "./city/plan";
import { createCityScene } from "./city/scene";
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

	useEffect(() => {
		const host = svgRef.current;
		if (!host) return;
		const scene = createCityScene(host, city);
		return () => scene.destroy();
	}, [city]);

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
					{city.buildings.length} buildings · storeys are symbols and columns ·{" "}
					{city.bundles.length} cords carrying{" "}
					{city.bundles.reduce((s, b) => s + b.strands.length, 0)} tethers
				</span>
			</div>
		</div>
	);
}
