// Pan, zoom, rotate.
//
// Pan and zoom are a transform on one group and never touch the geometry: the
// city is already drawn, it just moves. Rotation is different — it turns the
// world before projection, so it has to re-lay out, which is why it is the only
// gesture that calls back into the scene.

export interface CameraOpts {
	host: SVGSVGElement;
	/** the group everything is drawn into */
	cam: SVGGElement;
	viewBox: { x: number; y: number; w: number; h: number };
	/** rotation changed: the scene must re-place and re-route */
	onTheta(theta: number): void;
	/** apparent scale changed: the scene decides what is legible at it */
	onScale(scale: number): void;
	/** a click that was not a drag */
	onPick(target: Element | null): void;
	reduced: boolean;
}

export interface Camera {
	destroy(): void;
	fit(): void;
	/** snap to the next quarter turn from wherever it was left */
	snap(dir: 1 | -1): void;
	nudge(delta: number): void;
	/** ease the view onto a point at a given zoom, or back to the fitted view */
	flyTo(target: { x: number; y: number; k: number } | null, dur?: number): void;
	theta(): number;
	scale(): number;
}

const ROT_PER_PX = (0.28 * Math.PI) / 180;
const QUARTER = Math.PI / 2;
const K_MIN = 0.35;
const K_MAX = 4;

export function createCamera(o: CameraOpts): Camera {
	const { host, cam } = o;
	let view = { tx: 0, ty: 0, k: 1 };
	let theta = 0;
	let drag: { x: number; y: number; tx: number; ty: number } | null = null;
	let spin: { x: number; theta: number } | null = null;
	let spinning = false;
	let suppressPick = false;
	let raf = 0;
	let flyRaf = 0;
	let alive = true;

	const baseScale = () =>
		host.clientWidth ? host.clientWidth / o.viewBox.w : 1;

	function applyCam(): void {
		cam.setAttribute(
			"transform",
			`translate(${view.tx.toFixed(1)} ${view.ty.toFixed(1)}) scale(${view.k.toFixed(4)})`,
		);
		o.onScale(baseScale() * view.k);
	}

	function setTheta(t: number): void {
		theta = t;
		o.onTheta(t);
	}

	/** screen point → the coordinate system the cam group is drawn in */
	function toLocal(ev: { clientX: number; clientY: number }): {
		x: number;
		y: number;
	} {
		const ctm = host.getScreenCTM();
		if (!ctm) return { x: 0, y: 0 };
		const pt = host.createSVGPoint();
		pt.x = ev.clientX;
		pt.y = ev.clientY;
		const p = pt.matrixTransform(ctm.inverse());
		return { x: (p.x - view.tx) / view.k, y: (p.y - view.ty) / view.k };
	}

	const onWheel = (ev: WheelEvent): void => {
		ev.preventDefault();
		if (flyRaf) {
			cancelAnimationFrame(flyRaf);
			flyRaf = 0;
		}
		const p = toLocal(ev);
		const k2 = Math.max(
			K_MIN,
			Math.min(K_MAX, view.k * (ev.deltaY < 0 ? 1.11 : 1 / 1.11)),
		);
		// keep the point under the cursor where it is
		view.tx += p.x * view.k - p.x * k2;
		view.ty += p.y * view.k - p.y * k2;
		view.k = k2;
		applyCam();
	};

	// No setPointerCapture: capturing on the <svg> retargets the derived mouse
	// events too, so `click` would report the <svg> as its target and the hit
	// test would never match. Window listeners keep a drag alive past the edge of
	// the canvas without that side effect.
	const onDown = (ev: PointerEvent): void => {
		if (spinning) return;
		// a hand on the canvas wins over a flight already in progress
		if (flyRaf) {
			cancelAnimationFrame(flyRaf);
			flyRaf = 0;
		}
		suppressPick = false;
		if (ev.shiftKey || ev.button === 2) {
			spin = { x: ev.clientX, theta };
			host.classList.add("rotating", "spinning");
		} else if (ev.button === 0) {
			const p = toLocal(ev);
			drag = { x: p.x, y: p.y, tx: view.tx, ty: view.ty };
			host.classList.add("dragging");
		} else return;
		// the class above stops a NEW selection; this drops one already made,
		// which the browser would otherwise keep extending as the pointer moves
		const sel = getSelection();
		if (sel && !sel.isCollapsed) sel.removeAllRanges();
	};

	const onMove = (ev: PointerEvent): void => {
		if (spin) {
			if (Math.abs(ev.clientX - spin.x) > 2) suppressPick = true;
			setTheta(spin.theta + (ev.clientX - spin.x) * ROT_PER_PX);
			return;
		}
		if (!drag) return;
		const p = toLocal(ev);
		if (Math.abs(p.x - drag.x) + Math.abs(p.y - drag.y) > 3)
			suppressPick = true;
		view.tx = drag.tx + (p.x - drag.x) * view.k;
		view.ty = drag.ty + (p.y - drag.y) * view.k;
		applyCam();
	};

	const onUp = (): void => {
		if (spin) {
			spin = null;
			host.classList.remove("rotating", "spinning");
		}
		drag = null;
		host.classList.remove("dragging");
	};

	const onClick = (ev: MouseEvent): void => {
		if (suppressPick) {
			suppressPick = false;
			return;
		}
		const t = ev.target;
		o.onPick(t instanceof Element ? t : null);
	};

	const onContext = (ev: Event): void => ev.preventDefault();
	const onDragStart = (ev: Event): void => ev.preventDefault();

	host.addEventListener("wheel", onWheel, { passive: false });
	host.addEventListener("pointerdown", onDown);
	host.addEventListener("click", onClick);
	host.addEventListener("contextmenu", onContext);
	host.addEventListener("dragstart", onDragStart);
	addEventListener("pointermove", onMove);
	addEventListener("pointerup", onUp);
	addEventListener("pointercancel", onUp);

	function rotateTo(to: number, dur: number): void {
		if (spinning || spin) return;
		const from = theta;
		if (o.reduced || dur === 0) {
			setTheta(to);
			return;
		}
		spinning = true;
		host.classList.add("rotating");
		const t0 = performance.now();
		const ease = (u: number): number =>
			u < 0.5 ? 4 * u * u * u : 1 - (-2 * u + 2) ** 3 / 2;
		raf = requestAnimationFrame(function step(now) {
			if (!alive) return;
			const u = Math.max(0, Math.min(1, (now - t0) / dur));
			setTheta(from + (to - from) * ease(u));
			if (u < 1) {
				raf = requestAnimationFrame(step);
				return;
			}
			setTheta(to);
			spinning = false;
			host.classList.remove("rotating");
		});
	}

	/**
	 * Under `translate(t) scale(k)` a local point p lands at t + k·p, so putting p
	 * in the middle of the frame is just t = centre − k·p. The frame's middle in
	 * local units is the viewBox's own centre, because that is exactly what an
	 * untransformed view shows.
	 */
	function flyTo(
		target: { x: number; y: number; k: number } | null,
		dur = 520,
	): void {
		const cx = o.viewBox.x + o.viewBox.w / 2;
		const cy = o.viewBox.y + o.viewBox.h / 2;
		const to = target
			? {
					tx: cx - target.k * target.x,
					ty: cy - target.k * target.y,
					k: target.k,
				}
			: { tx: 0, ty: 0, k: 1 };
		if (flyRaf) cancelAnimationFrame(flyRaf);
		if (o.reduced || dur === 0) {
			view = to;
			applyCam();
			return;
		}
		const from = { ...view };
		const t0 = performance.now();
		const ease = (u: number): number => 1 - (1 - u) ** 3;
		flyRaf = requestAnimationFrame(function step(now) {
			if (!alive) return;
			// clamped at both ends: an easing curve fed a negative u runs backwards
			// past its own start, and there is no clock we control here
			const u = Math.max(0, Math.min(1, (now - t0) / dur));
			const e = ease(u);
			view = {
				tx: from.tx + (to.tx - from.tx) * e,
				ty: from.ty + (to.ty - from.ty) * e,
				k: from.k + (to.k - from.k) * e,
			};
			applyCam();
			if (u < 1) flyRaf = requestAnimationFrame(step);
			else flyRaf = 0;
		});
	}

	applyCam();

	return {
		destroy() {
			alive = false;
			if (raf) cancelAnimationFrame(raf);
			if (flyRaf) cancelAnimationFrame(flyRaf);
			host.removeEventListener("wheel", onWheel);
			host.removeEventListener("pointerdown", onDown);
			host.removeEventListener("click", onClick);
			host.removeEventListener("contextmenu", onContext);
			host.removeEventListener("dragstart", onDragStart);
			removeEventListener("pointermove", onMove);
			removeEventListener("pointerup", onUp);
			removeEventListener("pointercancel", onUp);
		},
		fit() {
			flyTo(null);
		},
		flyTo,
		// the buttons re-align to the next quarter turn from wherever you left it
		snap(dir) {
			const q = theta / QUARTER;
			const target =
				(dir > 0 ? Math.floor(q + 1e-6) + 1 : Math.ceil(q - 1e-6) - 1) *
				QUARTER;
			rotateTo(target, 620);
		},
		nudge(delta) {
			if (!spinning && !spin) setTheta(theta + delta);
		},
		theta: () => theta,
		scale: () => baseScale() * view.k,
	};
}
