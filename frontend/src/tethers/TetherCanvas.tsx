import { useEffect, useRef } from "react";
import { createTetherCanvas } from "./canvasController";
import type { TetherGraph } from "./types";

// Renders the canvas scaffold (matching the legacy tethers viewer DOM) and mounts
// the imperative d3-force controller against the wrap element. The controller
// owns all DOM inside the wrap; React only provides the static scaffold + ref.
export function TetherCanvas({ graph }: { graph: TetherGraph }) {
	const wrapRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!wrapRef.current) return;
		const destroy = createTetherCanvas(wrapRef.current, graph);
		return destroy;
	}, [graph]);

	return (
		<div
			className="tether-canvas-wrap"
			ref={wrapRef}
			style={{ height: "calc(100vh - 180px)", minHeight: 560 }}
		>
			<svg
				id="tether-canvas"
				className="tether-canvas"
				style={{
					position: "absolute",
					inset: 0,
					width: "100%",
					height: "100%",
				}}
			/>
			<div className="tether-cards-layer" />
			<div id="tether-tooltip" className="tether-tooltip" role="tooltip" />
			<div className="tether-controls">
				<div className="tether-info-panel" id="tether-info-panel" hidden />
				<div
					className="tether-filters tether-filters--popup"
					id="tether-filter-panel"
					hidden
				>
					<button
						type="button"
						className="chip chip--reads is-on"
						data-rel="reads"
					>
						reads
					</button>
					<button
						type="button"
						className="chip chip--writes is-on"
						data-rel="writes"
					>
						writes
					</button>
					<button
						type="button"
						className="chip chip--references is-on"
						data-rel="references"
					>
						references
					</button>
					<button
						type="button"
						className="chip chip--maps-to is-on"
						data-rel="maps-to"
					>
						maps-to
					</button>
				</div>
				<input
					className="tether-search tether-search--popup"
					placeholder="Search files, tables, columns, symbols…"
					hidden
				/>
				<div
					className="tether-spread tether-spread--popup"
					id="tether-spread-panel"
					hidden
				>
					<div className="tether-spread__row">
						<label htmlFor="tether-spread-range">Spread</label>
						<input
							type="range"
							id="tether-spread-range"
							min={400}
							max={3000}
							step={50}
							defaultValue={1500}
						/>
					</div>
					<div className="tether-spread__row">
						<label htmlFor="tether-gap-range">Gap</label>
						<input
							type="range"
							id="tether-gap-range"
							min={0.12}
							max={0.45}
							step={0.01}
							defaultValue={0.3}
						/>
					</div>
				</div>
				<div className="tether-controls__row">
					<button
						className="tether-ctrl-btn"
						id="tether-search-toggle"
						title="Search"
						type="button"
					>
						<i className="fa-solid fa-magnifying-glass" />
					</button>
					<button
						className="tether-ctrl-btn"
						id="tether-filter-toggle"
						title="Filter"
						type="button"
					>
						<i className="fa-solid fa-sliders" />
					</button>
					<button
						className="tether-ctrl-btn"
						id="tether-spread-toggle"
						title="Layout"
						type="button"
					>
						<i className="fa-solid fa-up-right-and-down-left-from-center" />
					</button>
					<button
						className="tether-ctrl-btn"
						id="tether-info-toggle"
						title="Graph info"
						type="button"
					>
						<i className="fa-solid fa-circle-info" />
					</button>
					<button
						className="tether-ctrl-btn tether-fitbtn"
						type="button"
						title="Fit view"
					>
						<i className="fa-solid fa-expand" />
					</button>
				</div>
			</div>
			<aside
				id="tether-details-panel"
				className="tether-panel"
				aria-label="Selection details"
			/>
		</div>
	);
}
