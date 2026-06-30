import { describe, expect, it } from "vitest";
import { bezierPt, computeCP, taperPath } from "./bezier";

describe("computeCP", () => {
	it("returns null for endpoints closer than 1px", () => {
		expect(computeCP(0, 0, 0.5, 0.5, 0, 0, 1, 1, 50)).toBeNull();
	});

	it("places the control point on the midpoint when oscillation is zero", () => {
		// phase 0, t 0 → sin(0) = 0, so no perpendicular offset.
		const cp = computeCP(0, 0, 100, 0, 0, 0, 1, 0.2, 50);
		expect(cp).toEqual({ cpx: 50, cpy: 0 });
	});

	it("offsets the control point perpendicular to the segment", () => {
		// Horizontal segment, max oscillation (sin = 1): offset is purely vertical.
		const cp = computeCP(0, 0, 100, 0, Math.PI / 2, 0, 1, 1, 30);
		expect(cp).not.toBeNull();
		expect(cp?.cpx).toBeCloseTo(50, 5);
		// amp = min(len * ampFactor, cap) = min(100, 30) = 30, sin(π/2) = 1.
		expect(cp?.cpy).toBeCloseTo(30, 5);
	});

	it("caps oscillation amplitude at capPx", () => {
		const cp = computeCP(0, 0, 1000, 0, Math.PI / 2, 0, 1, 1, 40);
		// len * ampFactor = 1000, but capped to 40.
		expect(cp?.cpy).toBeCloseTo(40, 5);
	});
});

describe("bezierPt", () => {
	it("returns the start point at tv=0", () => {
		expect(bezierPt(0, 0, 100, 100, 50, 50, 0)).toEqual({ x: 0, y: 0 });
	});

	it("returns the end point at tv=1", () => {
		expect(bezierPt(0, 0, 100, 100, 50, 50, 1)).toEqual({ x: 100, y: 100 });
	});

	it("bends toward the control point at the midpoint", () => {
		// At tv=0.5 with a control point pulled up, y should be above the chord.
		const pt = bezierPt(0, 0, 100, 0, 50, -40, 0.5);
		expect(pt.x).toBeCloseTo(50, 5);
		expect(pt.y).toBeCloseTo(-20, 5);
	});
});

describe("taperPath", () => {
	const path = taperPath(0, 0, 100, 0, 50, 0, 20);

	it("produces a closed SVG path", () => {
		expect(path.startsWith("M")).toBe(true);
		expect(path.endsWith("Z")).toBe(true);
	});

	it("is needle-thin at both endpoints (half-width ~0 at tv=0 and tv=1)", () => {
		// The spindle profile is maxW/2 * sin(π·tv): zero at the ends. The first
		// "left" vertex (tv=0) sits on the start point.
		const firstVertex = path.slice(1).split(" L")[0];
		const [x, y] = firstVertex.split(",").map(Number);
		expect(x).toBeCloseTo(0, 1);
		expect(y).toBeCloseTo(0, 1);
	});

	it("widens to roughly maxW at the middle of a straight segment", () => {
		// Mid-segment (tv=0.5) the two sides are ~maxW apart along the normal.
		const verts = path
			.slice(1)
			.replaceAll(" L", " ")
			.trim()
			.split(" ")
			.map((p) => p.replace("Z", "").split(",").map(Number));
		// 13 left vertices (N=12 → 0..12), then 13 right reversed. Left index 6 is tv=0.5.
		const leftMid = verts[6];
		const rightMid = verts[verts.length - 1 - 6];
		const spread = Math.abs(leftMid[1] - rightMid[1]);
		expect(spread).toBeCloseTo(20, 0);
	});
});
