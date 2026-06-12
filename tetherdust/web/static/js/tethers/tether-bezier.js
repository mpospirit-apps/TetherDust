/* Bezier helpers extracted from chat/templates/chat/home.html (~lines 786-886).
 * Pure functions; safe to import from anywhere. */

export function computeCP(ax, ay, bx, by, t, phase, speed, ampFactor, capPx) {
    var dx = bx - ax, dy = by - ay;
    var len = Math.sqrt(dx * dx + dy * dy);
    if (len < 1) return null;
    var px = -dy / len, py = dx / len;
    var osc = Math.sin(t * speed + phase) * Math.min(len * ampFactor, capPx || 50);
    return { cpx: (ax + bx) / 2 + px * osc, cpy: (ay + by) / 2 + py * osc };
}

export function bezierPt(ax, ay, bx, by, cpx, cpy, tv) {
    var t1 = 1 - tv;
    return {
        x: t1 * t1 * ax + 2 * tv * t1 * cpx + tv * tv * bx,
        y: t1 * t1 * ay + 2 * tv * t1 * cpy + tv * tv * by,
    };
}

export function bezierTan(ax, ay, bx, by, cpx, cpy, tv) {
    var t1 = 1 - tv;
    return {
        tx: 2 * t1 * (cpx - ax) + 2 * tv * (bx - cpx),
        ty: 2 * t1 * (cpy - ay) + 2 * tv * (by - cpy),
    };
}

/* Build a tapered "spindle" path between (ax,ay) and (bx,by) bending through
 * (cpx,cpy). Half-width follows a sin profile so endpoints are needle-thin. */
export function taperPath(ax, ay, bx, by, cpx, cpy, maxW) {
    var N = 12;
    var left = [], right = [];
    for (var i = 0; i <= N; i++) {
        var tv = i / N, t1 = 1 - tv;
        var qx = t1 * t1 * ax + 2 * tv * t1 * cpx + tv * tv * bx;
        var qy = t1 * t1 * ay + 2 * tv * t1 * cpy + tv * tv * by;
        var tx = 2 * (t1 * (cpx - ax) + tv * (bx - cpx));
        var ty = 2 * (t1 * (cpy - ay) + tv * (by - cpy));
        var tl = Math.sqrt(tx * tx + ty * ty) || 0.001;
        var nx = -ty / tl, ny = tx / tl;
        var hw = (maxW / 2) * Math.sin(Math.PI * tv);
        left.push((qx + nx * hw).toFixed(1) + ',' + (qy + ny * hw).toFixed(1));
        right.push((qx - nx * hw).toFixed(1) + ',' + (qy - ny * hw).toFixed(1));
    }
    right.reverse();
    return 'M' + left[0] + ' L' + left.slice(1).join(' L') + ' L' + right.join(' L') + 'Z';
}
