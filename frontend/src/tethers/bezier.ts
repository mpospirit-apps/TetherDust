// Tapered-bezier helpers ported verbatim from the legacy tethers/tether-bezier.js.
// Pure geometry — no DOM.

export interface ControlPoint {
	cpx: number;
	cpy: number;
}

export function computeCP(
	ax: number,
	ay: number,
	bx: number,
	by: number,
	t: number,
	phase: number,
	speed: number,
	ampFactor: number,
	capPx: number,
): ControlPoint | null {
	const dx = bx - ax;
	const dy = by - ay;
	const len = Math.sqrt(dx * dx + dy * dy);
	if (len < 1) return null;
	const px = -dy / len;
	const py = dx / len;
	const osc =
		Math.sin(t * speed + phase) * Math.min(len * ampFactor, capPx || 50);
	return { cpx: (ax + bx) / 2 + px * osc, cpy: (ay + by) / 2 + py * osc };
}

export function bezierPt(
	ax: number,
	ay: number,
	bx: number,
	by: number,
	cpx: number,
	cpy: number,
	tv: number,
): { x: number; y: number } {
	const t1 = 1 - tv;
	return {
		x: t1 * t1 * ax + 2 * tv * t1 * cpx + tv * tv * bx,
		y: t1 * t1 * ay + 2 * tv * t1 * cpy + tv * tv * by,
	};
}

// Build a tapered "spindle" path between (ax,ay) and (bx,by) bending through
// (cpx,cpy). Half-width follows a sin profile so endpoints are needle-thin.
export function taperPath(
	ax: number,
	ay: number,
	bx: number,
	by: number,
	cpx: number,
	cpy: number,
	maxW: number,
): string {
	const N = 12;
	const left: string[] = [];
	const right: string[] = [];
	for (let i = 0; i <= N; i++) {
		const tv = i / N;
		const t1 = 1 - tv;
		const qx = t1 * t1 * ax + 2 * tv * t1 * cpx + tv * tv * bx;
		const qy = t1 * t1 * ay + 2 * tv * t1 * cpy + tv * tv * by;
		const tx = 2 * (t1 * (cpx - ax) + tv * (bx - cpx));
		const ty = 2 * (t1 * (cpy - ay) + tv * (by - cpy));
		const tl = Math.sqrt(tx * tx + ty * ty) || 0.001;
		const nx = -ty / tl;
		const ny = tx / tl;
		const hw = (maxW / 2) * Math.sin(Math.PI * tv);
		left.push(`${(qx + nx * hw).toFixed(1)},${(qy + ny * hw).toFixed(1)}`);
		right.push(`${(qx - nx * hw).toFixed(1)},${(qy - ny * hw).toFixed(1)}`);
	}
	right.reverse();
	return (
		"M" +
		left[0] +
		" L" +
		left.slice(1).join(" L") +
		" L" +
		right.join(" L") +
		"Z"
	);
}
